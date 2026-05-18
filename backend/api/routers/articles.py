import hashlib
import json
import re
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import structlog
from auth import require_session
from database import Article, Feed, ResearchProfile, get_db
from models import ArticleListItem, ArticleOut, RelatedArticleOut

_logger = structlog.get_logger().bind(service="articles")

router = APIRouter()
_auth = Depends(require_session)

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "utm_name", "utm_cid",
    "fbclid", "gclid", "msclkid", "yclid", "twclid", "igshid",
    "_ga", "_gl", "mc_cid", "mc_eid", "ref", "source",
})


class FeedbackRequest(BaseModel):
    value: int  # 1=like, -1=dislike, 0=remove feedback


def _title_fingerprint(title: str) -> str:
    t = re.sub(r"[^\w\s]", " ", title.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()[:16]


def _normalize_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        scheme = p.scheme.lower()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path.rstrip("/") or "/"
        params = parse_qs(p.query, keep_blank_values=False)
        clean = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
        query = urlencode(sorted(clean.items()), doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url


def _row_to_list_item(row) -> ArticleListItem:
    article, feed_name = row
    return ArticleListItem(
        id=article.id,
        feed_id=article.feed_id,
        title=article.title,
        url=article.url,
        published_at=article.published_at,
        score=article.score,
        tags_json=article.tags_json or "[]",
        summary_bullets_json=article.summary_bullets_json or "[]",
        reason=article.reason,
        read_at=article.read_at,
        bookmarked=article.bookmarked,
        extraction_failed=article.extraction_failed,
        created_at=article.created_at,
        feed_name=feed_name or "",
        user_feedback=article.user_feedback,
        contribution_type=article.contribution_type,
        re_document_type=article.re_document_type,
    )


ARISE_RE_DOCUMENT_TYPES = ("elicitation", "extraction", "method")


@router.get("/api/articles", response_model=List[ArticleListItem])
async def list_articles(
    status: str = Query("unread", enum=["unread", "read", "all"]),
    sort: str = Query("score", enum=["score", "date"]),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category: Optional[str] = Query(None),
    bookmarked: Optional[bool] = Query(None),
    url: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=10),
    search: Optional[str] = Query(None, max_length=200),
    contribution_type: Optional[str] = Query(None, max_length=32),
    re_document_type: Optional[str] = Query(None, max_length=32),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    query = db.query(Article, Feed.name.label("feed_name")).join(
        Feed, Article.feed_id == Feed.id
    )

    if url is not None:
        query = query.filter(Article.url == url)
        results = query.all()
        if results:
            row = results[0]
            item = _row_to_list_item(row)
            return [item]
        return []

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Article.title.ilike(like),
                Article.content_text.ilike(like),
                Article.tags_json.ilike(like),
            )
        )
    else:
        if status == "unread":
            query = query.filter(Article.read_at.is_(None))
        elif status == "read":
            query = query.filter(Article.read_at.isnot(None))

    if category and category not in ("All", "all"):
        query = query.filter(Feed.category == category)

    if bookmarked is not None:
        query = query.filter(Article.bookmarked == bookmarked)

    if min_score is not None:
        query = query.filter(Article.score >= min_score)

    if contribution_type is not None:
        query = query.filter(Article.contribution_type == contribution_type)

    if re_document_type is not None:
        if re_document_type == "arise":
            query = query.filter(Article.re_document_type.in_(ARISE_RE_DOCUMENT_TYPES))
        else:
            query = query.filter(Article.re_document_type == re_document_type)

    unread_first = Article.read_at.is_(None).desc()
    if sort == "score":
        query = query.order_by(unread_first, Article.score.desc().nullslast(), Article.created_at.desc())
    else:
        query = query.order_by(unread_first, Article.published_at.desc().nullslast(), Article.created_at.desc())

    query = query.offset(offset).limit(limit)
    results = query.all()
    return [_row_to_list_item(row) for row in results]


@router.get("/api/articles/{article_id}", response_model=ArticleOut)
async def get_article(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleOut.model_validate(article)


@router.post("/api/articles/{article_id}/read")
async def mark_read(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


@router.post("/api/articles/{article_id}/unread")
async def mark_unread(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.read_at = None
    db.commit()
    return {"status": "ok"}


@router.post("/api/articles/read-all")
async def mark_all_read(
    category: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=10),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    query = db.query(Article).filter(Article.read_at.is_(None))
    if category and category not in ("All", "all"):
        query = query.join(Feed, Article.feed_id == Feed.id).filter(Feed.category == category)
    if min_score is not None:
        query = query.filter(Article.score >= min_score)
    count = query.update({"read_at": datetime.now(timezone.utc)}, synchronize_session=False)
    db.commit()
    return {"marked_read": count}


@router.post("/api/articles/{article_id}/bookmark")
async def toggle_bookmark(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.bookmarked = not article.bookmarked
    db.commit()
    return {"bookmarked": article.bookmarked}


@router.get("/api/articles/{article_id}/related", response_model=List[RelatedArticleOut])
async def get_related_articles(
    article_id: int,
    n: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return up to `n` semantically similar articles via ChromaDB cosine similarity."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    try:
        from embedder import _get_chroma  # deferred import

        collection = _get_chroma()
        if collection.count() == 0:
            return []

        # Retrieve the source article's embedding vector
        source_result = collection.get(ids=[str(article_id)], include=["embeddings"])
        if not source_result["embeddings"]:
            return []
        source_vector = source_result["embeddings"][0]

        # Query for similar articles, excluding the source itself
        results = collection.query(
            query_embeddings=[source_vector],
            n_results=min(n + 1, collection.count()),
            include=["metadatas", "distances"],
        )

        related: List[RelatedArticleOut] = []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        for meta, dist in zip(metadatas, distances):
            cid = int(meta["article_id"])
            if cid == article_id:
                continue
            candidate = db.query(Article).filter(Article.id == cid).first()
            if not candidate:
                continue
            similarity = max(0.0, 1.0 - dist)  # cosine distance [0,2] → similarity [0,1]
            related.append(RelatedArticleOut(
                id=candidate.id,
                title=candidate.title,
                url=candidate.url,
                score=candidate.score,
                contribution_type=candidate.contribution_type,
                re_document_type=candidate.re_document_type,
                similarity=round(similarity, 4),
            ))
            if len(related) >= n:
                break

        return related

    except Exception as e:
        import structlog as _slog
        _slog.get_logger().warning("related_articles_failed", article_id=article_id, error=str(e))
        return []


@router.post("/api/articles/{article_id}/feedback")
async def submit_feedback(
    article_id: int,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if body.value not in (-1, 0, 1):
        raise HTTPException(status_code=422, detail="value must be -1, 0, or 1")
    article.user_feedback = None if body.value == 0 else body.value
    db.commit()

    # On 👍 feedback: upsert article tags into research_profile as topic entries
    if body.value == 1:
        _upsert_tags_from_feedback(db, article)

    return {"user_feedback": article.user_feedback}


def _upsert_tags_from_feedback(db: Session, article: Article) -> None:
    """Upsert article tags into research_profile (kind='topic', source='feedback').

    Each tag increments weight by 0.1 (capped at 2.0) if already present,
    or is inserted with weight=1.1 if new.  Tags are normalised to lowercase.
    """
    try:
        tags: list = json.loads(article.tags_json or "[]")
        for raw_tag in tags:
            label = raw_tag.strip().lower()
            if not label:
                continue
            existing = (
                db.query(ResearchProfile)
                .filter(ResearchProfile.kind == "topic", ResearchProfile.label == label)
                .first()
            )
            if existing:
                existing.weight = min(2.0, existing.weight + 0.1)
                existing.source = "feedback"
            else:
                db.add(ResearchProfile(
                    kind="topic",
                    label=label,
                    weight=1.1,
                    source="feedback",
                ))
        db.commit()
        _logger.info("feedback_tags_upserted", article_id=article.id, n_tags=len(tags))
    except Exception as exc:
        _logger.warning("feedback_tags_upsert_failed", error=str(exc))
        db.rollback()
