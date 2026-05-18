"""Embedding module for Baṣīra — Story 3.1.

Responsibilities:
- Lazy-initialize ChromaDB PersistentClient and 'articles' collection.
- embed_article_async: fire-and-forget background task called after scoring.
- All operations are fault-tolerant: any failure logs a warning and returns.
"""
import json
import os
from typing import Optional

import httpx
import structlog

from database import Article, SessionLocal

logger = structlog.get_logger().bind(service="embedder")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CHROMA_PATH = os.getenv("CHROMA_PATH", "/data/chroma")

_chroma_collection = None


def _get_chroma():
    """Lazy-init singleton — returns the 'articles' Chroma collection.

    Import of chromadb is deferred so the API service starts even if the
    package is not installed or the Chroma directory is not available.
    """
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    import chromadb  # deferred import
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    _chroma_collection = client.get_or_create_collection(
        name="articles",
        metadata={"hnsw:space": "cosine"},
    )
    return _chroma_collection


def _build_embed_text(article: Article) -> str:
    """Build text to embed: title + abstract (from paper_meta) or summary bullets."""
    parts = [article.title]
    abstract = ""
    if article.paper_meta_json:
        try:
            paper_meta = json.loads(article.paper_meta_json)
            abstract = paper_meta.get("abstract", "")
        except Exception:
            pass
    if abstract:
        parts.append(abstract)
    elif article.summary_bullets_json:
        try:
            bullets = json.loads(article.summary_bullets_json)
            parts.extend(bullets[:3])
        except Exception:
            pass
    return "\n".join(parts)[:4000]


async def embed_article_async(article_id: int) -> None:
    """Fire-and-forget: embed article and upsert into ChromaDB.

    Called via asyncio.create_task() after scoring — must NEVER raise.
    Sets embedding_indexed=1 on success, 0 on failure.
    """
    db = SessionLocal()
    article: Optional[Article] = None
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            logger.warning("embed_article_not_found", article_id=article_id)
            return

        embed_text = _build_embed_text(article)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": OLLAMA_EMBED_MODEL, "prompt": embed_text},
            )
            resp.raise_for_status()
            vector = resp.json()["embedding"]

        collection = _get_chroma()
        collection.upsert(
            ids=[str(article_id)],
            embeddings=[vector],
            metadatas=[{
                "article_id": article_id,
                "feed_id": article.feed_id,
                "contribution_type": article.contribution_type or "",
                "re_document_type": article.re_document_type or "",
                "score": float(article.score or 0.0),
                "created_at": article.created_at.isoformat() if article.created_at else "",
            }],
        )

        article.embedding_indexed = 1
        db.commit()
        logger.info("article_embedded", article_id=article_id, model=OLLAMA_EMBED_MODEL)

    except Exception as e:
        logger.warning("embedding_failed", article_id=article_id, error=str(e))
        try:
            if article is not None:
                article.embedding_indexed = 0
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
