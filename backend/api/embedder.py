"""Embedding module for Baṣīra — Story 3.1.

Responsibilities:
- Lazy-initialize ChromaDB PersistentClient and 'articles' collection.
- embed_article_async: fire-and-forget background task called after scoring.
- All operations are fault-tolerant: any failure logs a warning and returns.
"""
import asyncio
import json
import math
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from sqlalchemy import text

from database import Article, SessionLocal, TrackedAuthor

logger = structlog.get_logger().bind(service="embedder")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CHROMA_PATH = os.getenv("CHROMA_PATH", "/data/chroma")
logger.info("embedder_init", model=OLLAMA_EMBED_MODEL, chroma_path=CHROMA_PATH)

_chroma_collections: dict[str, object] = {}
_reembed_in_progress: dict[int, bool] = {}


def _resolve_collection_name(user_id: int, db) -> str:
    """Return the collection name for the given user based on DB state.

    Reads user_config.embed_model — if set, returns the versioned name
    (articles_u{user_id}_v2). Otherwise returns the default name.
    """
    from database import UserConfig
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if config and config.embed_model:
        return f"articles_u{user_id}_v2"
    return f"articles_u{user_id}"


def _get_chroma(user_id: int = 1, collection_name: Optional[str] = None):
    """Lazy-init per-user singleton — returns a Chroma collection.

    Each tenant's embeddings are isolated in their own collection
    (FR-MT-40). Import of chromadb is deferred so the API service starts even
    if the package is not installed or the Chroma directory is not available.

    When collection_name is provided, uses it directly (for re-embed writers).
    Otherwise resolves the name via DB state (for readers).
    """
    if collection_name is not None:
        return _get_or_create_collection(collection_name)

    # Reader call: determine which collection to serve
    resolved = f"articles_u{user_id}"
    if not _reembed_in_progress.get(user_id):
        db = SessionLocal()
        try:
            resolved = _resolve_collection_name(user_id, db)
        finally:
            db.close()

    if resolved in _chroma_collections:
        return _chroma_collections[resolved]
    return _get_or_create_collection(resolved)


def _get_or_create_collection(name: str):
    """Get or create a Chroma collection by name. Caches result."""
    import chromadb  # deferred import
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
    _chroma_collections[name] = collection
    return collection


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


async def embed_article_async(article_id: int, user_id: int = 1) -> None:
    """Fire-and-forget: embed article into user's Chroma collection.

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

        collection = _get_chroma(user_id)
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

        # ── Author radar tracking (Story 5.2) ──────────────────────────────
        if article.score is not None and article.score >= 7.0 and article.paper_meta_json:
            try:
                paper_meta = json.loads(article.paper_meta_json)
                authors = paper_meta.get("authors") or []
                for author_entry in authors:
                    ss_id = author_entry.get("authorId")
                    name = author_entry.get("name", "")
                    if not ss_id or not name:
                        continue
                    db.execute(
                        text("""
                            INSERT OR IGNORE INTO tracked_authors
                            (ss_author_id, name, paper_count, avg_score, alert_count, last_checked, created_at, user_id)
                            VALUES (:ss_id, :name, 0, 0.0, 0, NULL, :now, :uid)
                        """),
                        {"ss_id": ss_id, "name": name, "now": datetime.now(timezone.utc), "uid": user_id},
                    )
                    author = db.query(TrackedAuthor).filter_by(ss_author_id=ss_id, user_id=user_id).first()
                    if author:
                        new_count = author.paper_count + 1
                        new_avg = (author.avg_score * author.paper_count + article.score) / new_count
                        author.paper_count = new_count
                        author.avg_score = round(new_avg, 3)
            except Exception as au_e:
                logger.warning("author_upsert_failed", article_id=article_id, error=str(au_e))

        db.commit()
        logger.info("article_embedded", article_id=article_id, model=OLLAMA_EMBED_MODEL, user_id=user_id)

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


async def reembed_user_collection(user_id: int, force_model: str) -> dict:
    """Re-embed all articles for a user using a new model.

    Creates a versioned collection (articles_u{user_id}_v2), re-embeds every
    article using force_model, then updates user_config.embed_model.
    During migration, readers continue to use the old collection (AC2).
    Returns {"status": "complete", "reembedded": count, "model": model}.
    """
    db = SessionLocal()
    try:
        from database import UserConfig

        _reembed_in_progress[user_id] = True
        config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
        if config:
            config.pending_embed_model = force_model
            db.commit()

        new_name = f"articles_u{user_id}_v2"
        new_collection = _get_chroma(user_id, collection_name=new_name)

        # Use articles from the user's current collection as the source
        old_collection = _get_chroma(user_id)
        old_data = old_collection.get(include=[])
        article_ids = [int(aid) for aid in old_data["ids"]]

        reembedded = 0
        offset = 0
        batch_size = 50
        while offset < len(article_ids):
            batch_ids = article_ids[offset:offset + batch_size]
            articles = db.query(Article).filter(Article.id.in_(batch_ids)).all()
            articles_by_id = {a.id: a for a in articles}

            for aid in batch_ids:
                article = articles_by_id.get(aid)
                if not article:
                    continue
                try:
                    embed_text = _build_embed_text(article)
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f"{OLLAMA_URL}/api/embeddings",
                            json={"model": force_model, "prompt": embed_text},
                        )
                        resp.raise_for_status()
                        vector = resp.json()["embedding"]

                    meta = {
                        "article_id": article.id,
                        "feed_id": article.feed_id or 0,
                        "score": float(article.score or 0.0),
                        "created_at": article.created_at.isoformat() if article.created_at else "",
                    }
                    new_collection.upsert(
                        ids=[str(article.id)],
                        embeddings=[vector],
                        metadatas=[meta],
                    )
                    reembedded += 1
                except Exception as ae:
                    logger.warning("reembed_article_failed", article_id=aid, error=str(ae))
                    continue

            offset += batch_size

        if config:
            config.embed_model = force_model
            config.pending_embed_model = None
            db.commit()

        logger.info("reembed_complete", user_id=user_id, model=force_model, reembedded=reembedded)
        return {"status": "complete", "reembedded": reembedded, "model": force_model}

    except Exception as e:
        logger.error("reembed_failed", user_id=user_id, error=str(e))
        return {"status": "failed", "error": str(e)}
    finally:
        _reembed_in_progress[user_id] = False
        db.close()


def _migrate_chroma_articles_to_per_user() -> int:
    """One-time migration: copy old global 'articles' collection to 'articles_u1'.

    Idempotent — safe to run multiple times. Returns the count of vectors
    migrated, or 0 if nothing was done (no old collection found, or already
    migrated). Never raises; logs warnings on failure.

    Called from main.py startup and exposed as POST /api/admin/reindex.
    """
    try:
        import chromadb  # deferred import
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        try:
            old_collection = client.get_collection(name="articles")
        except ValueError:
            logger.info("chroma_migration_skipped_no_old_collection")
            return 0

        old_data = old_collection.get(include=["embeddings", "metadatas"])
        if not old_data["ids"]:
            client.delete_collection("articles")
            logger.info("chroma_migration_skipped_empty_collection")
            return 0

        u1_collection = client.get_or_create_collection(
            name="articles_u1",
            metadata={"hnsw:space": "cosine"},
        )

        existing = u1_collection.get(ids=old_data["ids"])
        existing_ids = set(existing["ids"])

        new_ids: list[str] = []
        new_embeddings: list[list[float]] = []
        new_metadatas: list[dict] = []
        for i, aid in enumerate(old_data["ids"]):
            if aid not in existing_ids:
                new_ids.append(aid)
                if old_data["embeddings"] is not None:
                    new_embeddings.append(old_data["embeddings"][i])
                if old_data["metadatas"] is not None:
                    new_metadatas.append(old_data["metadatas"][i])

        if new_ids:
            u1_collection.upsert(
                ids=new_ids,
                embeddings=new_embeddings,
                metadatas=new_metadatas,
            )

        client.delete_collection("articles")
        logger.info("chroma_migration_complete", migrated=len(new_ids))
        return len(new_ids)

    except Exception as e:
        logger.warning("chroma_migration_failed", error=str(e))
        return 0
