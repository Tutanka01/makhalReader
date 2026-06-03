import hashlib
import json
import re
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select as sa_select, text
from sqlalchemy.orm import Session

import structlog
from auth import require_session
from database import Article, ArticleScore, Feed, NoveltyAlert, ResearchProfile, get_db
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


def _pick(article_score: Optional[ArticleScore], article: Article, attr: str):
    """Prefer article_score value, fall back to article (FR-MT-7)."""
    aval = getattr(article_score, attr, None) if article_score is not None else None
    if aval is not None:
        return aval
    return getattr(article, attr)


def _get_or_create_article_score(db: Session, user_id: int, article_id: int) -> ArticleScore:
    score = db.query(ArticleScore).filter(
        ArticleScore.user_id == user_id,
        ArticleScore.article_id == article_id,
    ).first()
    if score is None:
        score = ArticleScore(user_id=user_id, article_id=article_id)
        db.add(score)
        db.flush()
    return score


def _row_to_list_item(article: Article, feed_name: str, article_score: Optional[ArticleScore] = None, threat_overlap: Optional[float] = None, threat_positioning_note: Optional[str] = None) -> ArticleListItem:
    return ArticleListItem(
        id=article.id,
        feed_id=article.feed_id,
        title=article.title,
        url=article.url,
        published_at=article.published_at,
        score=_pick(article_score, article, "score"),
        tags_json=_pick(article_score, article, "tags_json") or "[]",
        summary_bullets_json=_pick(article_score, article, "summary_bullets_json") or "[]",
        reason=_pick(article_score, article, "reason"),
        read_at=_pick(article_score, article, "read_at"),
        bookmarked=_pick(article_score, article, "bookmarked") or False,
        extraction_failed=article.extraction_failed,
        created_at=article.created_at,
        feed_name=feed_name or "",
        user_feedback=_pick(article_score, article, "user_feedback"),
        contribution_type=_pick(article_score, article, "contribution_type"),
        re_document_type=_pick(article_score, article, "re_document_type"),
        threat_overlap=threat_overlap,
        threat_positioning_note=threat_positioning_note,
        tracked_author_alert=article.tracked_author_alert or None,
    )


ARISE_RE_DOCUMENT_TYPES = ("elicitation", "extraction", "method")


@router.get("/api/articles", response_model=List[ArticleListItem])
async def list_articles(
    status: str = Query("unread", enum=["unread", "read", "all"]),
    sort: str = Query("score", enum=["score", "date", "cited_by_corpus"]),
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
    current_user: dict = _auth,
):
    user_id = current_user["id"]
    threat_overlap_subq = (
        sa_select(NoveltyAlert.overlap_score)
        .where(NoveltyAlert.article_id == Article.id, NoveltyAlert.user_id == user_id)
        .order_by(NoveltyAlert.checked_at.desc())
        .limit(1)
        .correlate(Article)
        .scalar_subquery()
    )
    threat_note_subq = (
        sa_select(NoveltyAlert.positioning_note)
        .where(NoveltyAlert.article_id == Article.id, NoveltyAlert.user_id == user_id)
        .order_by(NoveltyAlert.checked_at.desc())
        .limit(1)
        .correlate(Article)
        .scalar_subquery()
    )
    query = db.query(
        Article, Feed.name.label("feed_name"), ArticleScore,
        threat_overlap_subq.label("threat_overlap"), threat_note_subq.label("threat_note"),
    ).join(
        Feed, Article.feed_id == Feed.id
    ).outerjoin(
        ArticleScore,
        and_(ArticleScore.article_id == Article.id, ArticleScore.user_id == user_id),
    )

    # SQL-level COALESCE helpers for filtering / sorting (FR-MT-7, FR-MT-12)
    _read_at = func.coalesce(ArticleScore.read_at, Article.read_at)
    _bookmarked = func.coalesce(ArticleScore.bookmarked, Article.bookmarked, False)
    _score = func.coalesce(ArticleScore.score, Article.score)
    _ct = func.coalesce(ArticleScore.contribution_type, Article.contribution_type)
    _rdt = func.coalesce(ArticleScore.re_document_type, Article.re_document_type)
    _tags = func.coalesce(ArticleScore.tags_json, Article.tags_json)

    if url is not None:
        query = query.filter(Article.url == url)
        results = query.all()
        if results:
            article, feed_name, article_score, threat_overlap, threat_note = results[0]
            item = _row_to_list_item(article, feed_name, article_score=article_score, threat_overlap=threat_overlap, threat_positioning_note=threat_note)
            return [item]
        return []

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Article.title.ilike(like),
                Article.content_text.ilike(like),
                _tags.ilike(like),
            )
        )
    else:
        if status == "unread":
            query = query.filter(_read_at.is_(None))
        elif status == "read":
            query = query.filter(_read_at.isnot(None))

    if category and category not in ("All", "all"):
        query = query.filter(Feed.category == category)

    if bookmarked is not None:
        query = query.filter(_bookmarked == bookmarked)

    if min_score is not None:
        query = query.filter(_score >= min_score)

    if contribution_type is not None:
        query = query.filter(_ct == contribution_type)

    if re_document_type is not None:
        if re_document_type == "arise":
            query = query.filter(_rdt.in_(ARISE_RE_DOCUMENT_TYPES))
        else:
            query = query.filter(_rdt == re_document_type)

    unread_first = _read_at.is_(None).desc()
    if sort == "score":
        query = query.order_by(unread_first, _score.desc().nullslast(), Article.created_at.desc())
    elif sort == "cited_by_corpus":
        query = query.order_by(unread_first, Article.cited_by_corpus_count.desc(), Article.created_at.desc())
    else:
        query = query.order_by(unread_first, Article.published_at.desc().nullslast(), Article.created_at.desc())

    query = query.offset(offset).limit(limit)
    results = query.all()
    items: List[ArticleListItem] = []
    for row in results:
        article, feed_name, article_score, threat_overlap, threat_note = row
        items.append(_row_to_list_item(article, feed_name, article_score=article_score, threat_overlap=threat_overlap, threat_positioning_note=threat_note))
    return items


@router.get("/api/articles/{article_id}", response_model=ArticleOut)
async def get_article(article_id: int, db: Session = Depends(get_db), current_user: dict = _auth):
    user_id = current_user["id"]
    row = db.query(Article, ArticleScore).outerjoin(
        ArticleScore,
        and_(ArticleScore.article_id == Article.id, ArticleScore.user_id == user_id),
    ).filter(Article.id == article_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    article, article_score = row
    out = ArticleOut.model_validate(article)
    s = article_score
    if s is not None:
        out.score = s.score if s.score is not None else out.score
        out.tags_json = s.tags_json or out.tags_json
        out.summary_bullets_json = s.summary_bullets_json or out.summary_bullets_json
        out.reason = s.reason if s.reason is not None else out.reason
        out.read_at = s.read_at if s.read_at is not None else out.read_at
        out.bookmarked = s.bookmarked if s.bookmarked is not None else out.bookmarked
        out.user_feedback = s.user_feedback if s.user_feedback is not None else out.user_feedback
        out.contribution_type = s.contribution_type if s.contribution_type is not None else out.contribution_type
        out.re_document_type = s.re_document_type if s.re_document_type is not None else out.re_document_type
    return out


@router.post("/api/articles/{article_id}/read")
async def mark_read(article_id: int, db: Session = Depends(get_db), current_user: dict = _auth):
    user_id = current_user["id"]
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    score = _get_or_create_article_score(db, user_id, article_id)
    score.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


@router.post("/api/articles/{article_id}/unread")
async def mark_unread(article_id: int, db: Session = Depends(get_db), current_user: dict = _auth):
    user_id = current_user["id"]
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    score = _get_or_create_article_score(db, user_id, article_id)
    score.read_at = None
    db.commit()
    return {"status": "ok"}


@router.post("/api/articles/read-all")
async def mark_all_read(
    category: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=10),
    db: Session = Depends(get_db),
    current_user: dict = _auth,
):
    user_id = current_user["id"]
    _read_at = func.coalesce(ArticleScore.read_at, Article.read_at)
    query = db.query(Article).outerjoin(
        ArticleScore,
        and_(ArticleScore.article_id == Article.id, ArticleScore.user_id == user_id),
    ).filter(_read_at.is_(None))
    if category and category not in ("All", "all"):
        query = query.join(Feed, Article.feed_id == Feed.id).filter(Feed.category == category)
    if min_score is not None:
        _score = func.coalesce(ArticleScore.score, Article.score)
        query = query.filter(_score >= min_score)
    articles = query.all()
    for article in articles:
        score = _get_or_create_article_score(db, user_id, article.id)
        score.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"marked_read": len(articles)}


@router.post("/api/articles/{article_id}/bookmark")
async def toggle_bookmark(article_id: int, db: Session = Depends(get_db), current_user: dict = _auth):
    user_id = current_user["id"]
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    score = _get_or_create_article_score(db, user_id, article_id)
    score.bookmarked = not score.bookmarked
    db.commit()
    return {"bookmarked": score.bookmarked}


@router.get("/api/articles/{article_id}/related", response_model=List[RelatedArticleOut])
async def get_related_articles(
    article_id: int,
    n: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Return up to `n` semantically similar articles via ChromaDB cosine similarity."""
    user_id = current_user["id"]
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    try:
        from embedder import _get_chroma  # deferred import

        collection = _get_chroma(user_id)
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
    current_user: dict = _auth,
):
    user_id = current_user["id"]
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if body.value not in (-1, 0, 1):
        raise HTTPException(status_code=422, detail="value must be -1, 0, or 1")
    score = _get_or_create_article_score(db, user_id, article_id)
    score.user_feedback = None if body.value == 0 else body.value
    db.commit()

    # On 👍 feedback: upsert article tags into research_profile as topic entries
    if body.value == 1:
        _upsert_tags_from_feedback(db, article, user_id)

    return {"user_feedback": score.user_feedback}


def _upsert_tags_from_feedback(db: Session, article: Article, user_id: int) -> None:
    """Upsert article tags into research_profile (kind='topic', source='feedback') for a user.

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
                .filter(
                    ResearchProfile.user_id == user_id,
                    ResearchProfile.kind == "topic",
                    ResearchProfile.label == label,
                )
                .first()
            )
            if existing:
                existing.weight = min(2.0, existing.weight + 0.1)
                existing.source = "feedback"
            else:
                db.add(ResearchProfile(
                    user_id=user_id,
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
