import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from collections import defaultdict

from database import (
    Article,
    ArticleScore,
    Feed,
    ResearchProfile,
    SessionLocal,
    UserConfig,
    UserFeedSubscription,
    get_db,
    get_facet_schema,
)
from models import InternalArticleCreate, InternalScoreUpdate, PromptCacheUpdate
from routers.articles import _title_fingerprint, _pick
from embedder import embed_article_async
from sse import broadcast_new_article

router = APIRouter(prefix="/api/internal", tags=["internal"])

API_SECRET = os.getenv("API_SECRET", "changeme")
MAX_ARTICLES_PER_FEED = int(os.getenv("MAX_ARTICLES_PER_FEED", "200"))
ARTICLE_RETENTION_DAYS = int(os.getenv("ARTICLE_RETENTION_DAYS", "90"))


def _run_cleanup() -> int:
    """Synchronous cleanup logic — returns number of deleted articles."""
    db = SessionLocal()
    try:
        total_deleted = 0

        if ARTICLE_RETENTION_DAYS > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=ARTICLE_RETENTION_DAYS)
            deleted = (
                db.query(Article)
                .filter(Article.created_at < cutoff, Article.bookmarked == False)
                .delete(synchronize_session=False)
            )
            total_deleted += deleted

        feeds = db.query(Feed).filter(Feed.active == True).all()
        for feed in feeds:
            count = db.query(Article).filter(Article.feed_id == feed.id).count()
            if count > MAX_ARTICLES_PER_FEED:
                keep_ids = (
                    db.query(Article.id)
                    .filter(Article.feed_id == feed.id)
                    .order_by(Article.created_at.desc())
                    .limit(MAX_ARTICLES_PER_FEED)
                    .subquery()
                )
                deleted = (
                    db.query(Article)
                    .filter(
                        Article.feed_id == feed.id,
                        Article.id.notin_(keep_ids),
                        Article.bookmarked == False,
                    )
                    .delete(synchronize_session=False)
                )
                total_deleted += deleted

        db.commit()
        return total_deleted
    except Exception as e:
        print(f"[cleanup] Error: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


async def cleanup_old_articles():
    """Run cleanup once at startup, then every 24 h."""
    deleted = await asyncio.to_thread(_run_cleanup)
    if deleted:
        print(f"[cleanup] Startup pass: deleted {deleted} old articles")

    while True:
        await asyncio.sleep(86400)
        deleted = await asyncio.to_thread(_run_cleanup)
        if deleted:
            print(f"[cleanup] Nightly pass: deleted {deleted} old articles")


@router.get("/feeds")
async def internal_list_feeds(
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    results = (
        db.query(Feed, func.count(Article.id).label("article_count"))
        .outerjoin(Article, Feed.id == Article.feed_id)
        .filter(Feed.active == True)
        .group_by(Feed.id)
        .all()
    )
    subs = db.query(UserFeedSubscription).all()
    sub_map: dict[int, list[int]] = defaultdict(list)
    for s in subs:
        sub_map[s.feed_id].append(s.user_id)
    return [
        {
            "id": feed.id,
            "url": feed.url,
            "name": feed.name,
            "category": feed.category,
            "subscriber_user_ids": sub_map.get(feed.id, []),
        }
        for feed, _ in results
    ]


@router.get("/feedback-examples")
async def internal_feedback_examples(
    x_internal_secret: Optional[str] = Header(None),
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Return an aggregated preference profile (tag frequencies + examples) for scorer personalisation.

    When user_id is provided (FR-MT-31), scope queries to that user's article_scores and
    research_profile.  When absent, fall back to corpus-level data (backward compat, NFR-T4).
    """
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    if user_id is not None:
        liked_rows = (
            db.query(Article.title, Article.tags_json)
            .join(ArticleScore, ArticleScore.article_id == Article.id)
            .filter(ArticleScore.user_id == user_id, ArticleScore.user_feedback == 1)
            .order_by(Article.created_at.desc())
            .all()
        )
        disliked_rows = (
            db.query(Article.title, Article.tags_json)
            .join(ArticleScore, ArticleScore.article_id == Article.id)
            .filter(ArticleScore.user_id == user_id, ArticleScore.user_feedback == -1)
            .order_by(Article.created_at.desc())
            .all()
        )
    else:
        liked_rows = (
            db.query(Article.title, Article.tags_json)
            .filter(Article.user_feedback == 1)
            .order_by(Article.created_at.desc())
            .all()
        )
        disliked_rows = (
            db.query(Article.title, Article.tags_json)
            .filter(Article.user_feedback == -1)
            .order_by(Article.created_at.desc())
            .all()
        )

    def aggregate_tags(rows: list, top_n: int) -> list[dict]:
        counts: dict[str, int] = {}
        for row in rows:
            for tag in json.loads(row.tags_json or "[]"):
                counts[tag] = counts.get(tag, 0) + 1
        return [
            {"tag": t, "count": c}
            for t, c in sorted(counts.items(), key=lambda x: -x[1])[:top_n]
        ]

    def format_examples(rows: list, max_n: int) -> list[dict]:
        out = []
        for row in rows[:max_n]:
            tags = json.loads(row.tags_json or "[]")
            out.append({"title": row.title, "tags": tags[:5]})
        return out

    # Build structured preference block from the researcher profile table
    profile_query = db.query(ResearchProfile)
    if user_id is not None:
        profile_query = profile_query.filter(ResearchProfile.user_id == user_id)
    profile_rows = profile_query.order_by(ResearchProfile.kind, ResearchProfile.weight.desc()).all()

    def _group_profile(rows, kind: str) -> list[dict]:
        return [
            {"label": r.label, "weight": r.weight, "source": r.source}
            for r in rows if r.kind == kind
        ]

    profile_preference_block = {
        "topics":  _group_profile(profile_rows, "topic"),
        "methods": _group_profile(profile_rows, "method"),
        "domains": _group_profile(profile_rows, "domain"),
        "avoid":   _group_profile(profile_rows, "avoid"),
    }

    return {
        "liked_tags": aggregate_tags(liked_rows, top_n=10),
        "disliked_tags": aggregate_tags(disliked_rows, top_n=8),
        "liked_examples": format_examples(liked_rows, max_n=4),
        "disliked_examples": format_examples(disliked_rows, max_n=3),
        "total_liked": len(liked_rows),
        "total_disliked": len(disliked_rows),
        "profile_preference_block": profile_preference_block,
    }


@router.get("/articles/exists")
async def internal_article_exists(
    url: str = Query(...),
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    exists = db.query(Article.id).filter(Article.url == url).first() is not None
    return {"exists": exists}


@router.post("/articles")
async def internal_create_article(
    article_data: InternalArticleCreate,
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    existing = db.query(Article).filter(Article.url == article_data.url).first()
    if existing:
        return {"id": existing.id, "created": False}

    fp = _title_fingerprint(article_data.title)
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    title_dup = (
        db.query(Article)
        .filter(
            Article.title_fingerprint == fp,
            Article.created_at >= cutoff,
        )
        .first()
    )
    if title_dup:
        return {"id": title_dup.id, "created": False}

    article = Article(
        feed_id=article_data.feed_id,
        title=article_data.title,
        url=article_data.url,
        published_at=article_data.published_at,
        author=article_data.author,
        content_html=article_data.content_html,
        content_text=article_data.content_text,
        images_json=json.dumps(article_data.images),
        extraction_failed=article_data.extraction_failed,
        created_at=datetime.now(timezone.utc),
        title_fingerprint=fp,
        paper_meta_json=article_data.paper_meta_json,
        contribution_type=article_data.contribution_type,
        re_document_type=article_data.re_document_type,
        tracked_author_alert=article_data.tracked_author_alert,
        ss_paper_id=article_data.ss_paper_id,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return {"id": article.id, "created": True}


@router.post("/articles/{article_id}/score")
async def internal_score_article(
    article_id: int,
    score_data: InternalScoreUpdate,
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    user_id = score_data.user_id

    # Write to article_scores (FR-MT-9)
    score = _get_or_create_article_score(db, user_id, article_id)
    score.score = score_data.score
    score.tags_json = json.dumps(score_data.tags)
    score.summary_bullets_json = json.dumps(score_data.summary_bullets)
    score.reason = score_data.reason
    score.contribution_type = score_data.contribution_type
    score.re_document_type = score_data.re_document_type
    score_meta = {
        "contribution_type": score_data.contribution_type,
        "re_document_type": score_data.re_document_type,
        "novelty": score_data.novelty,
        "rigor": score_data.rigor,
        "relevance_to_topics": score_data.relevance_to_topics,
    }
    score.score_meta_json = json.dumps(
        {k: v for k, v in score_meta.items() if v is not None}
    )

    # Backward compat: also write corpus-level defaults for user_id=1 (NFR-T4)
    if user_id == 1:
        article.score = score_data.score
        article.tags_json = json.dumps(score_data.tags)
        article.summary_bullets_json = json.dumps(score_data.summary_bullets)
        article.reason = score_data.reason
        article.contribution_type = score_data.contribution_type
        article.re_document_type = score_data.re_document_type
        article.score_meta_json = json.dumps(
            {k: v for k, v in score_meta.items() if v is not None}
        )

    db.commit()
    db.refresh(article)

    feed = db.query(Feed).filter(Feed.id == article.feed_id).first()
    article_dict = {
        "id": article.id,
        "feed_id": article.feed_id,
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "score": _pick(score, article, "score"),
        "tags": json.loads(_pick(score, article, "tags_json") or "[]"),
        "summary_bullets": json.loads(_pick(score, article, "summary_bullets_json") or "[]"),
        "reason": _pick(score, article, "reason"),
        "read_at": _pick(score, article, "read_at"),
        "bookmarked": _pick(score, article, "bookmarked") or False,
        "extraction_failed": article.extraction_failed,
        "created_at": article.created_at.isoformat(),
        "feed_name": feed.name if feed else "",
        "user_feedback": _pick(score, article, "user_feedback"),
        "contribution_type": _pick(score, article, "contribution_type"),
        "re_document_type": _pick(score, article, "re_document_type"),
    }
    await broadcast_new_article(article_dict, user_id=user_id)

    # Fire-and-forget embedding — must not block or raise
    asyncio.create_task(embed_article_async(article.id, user_id=user_id))

    return {"status": "ok"}


@router.get("/users/{user_id}/prompt-cache")
async def internal_get_prompt_cache(
    user_id: int,
    db: Session = Depends(get_db),
    x_internal_secret: str = Header(...),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        return {"hash": None, "text": None}
    return {"hash": config.prompt_cache_hash, "text": config.prompt_cache_text}


@router.put("/users/{user_id}/prompt-cache")
async def internal_put_prompt_cache(
    user_id: int,
    body: PromptCacheUpdate,
    db: Session = Depends(get_db),
    x_internal_secret: str = Header(...),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        return {"status": "skipped", "reason": "no config"}
    config.prompt_cache_hash = body.hash
    config.prompt_cache_text = body.text
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


def _safe_json_loads(val: Optional[str]) -> list:
    """Parse a JSON string to list, returning [] on any failure."""
    try:
        parsed = json.loads(val) if val else []
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


@router.get("/users/{user_id}/scoring-context")
async def internal_get_scoring_context(
    user_id: int,
    db: Session = Depends(get_db),
    x_internal_secret: str = Header(...),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        return {}
    thesis_title = config.thesis_title or ""
    thesis_question = config.thesis_question or ""
    thesis_contribution = config.thesis_contribution
    tracked_venues = _safe_json_loads(str(config.tracked_venues_json))
    scoring_clusters = _safe_json_loads(str(config.scoring_clusters_json))
    avoid_topics = _safe_json_loads(str(config.avoid_topics_json))
    prompt_profile = config.prompt_profile or "unified"
    facet_schema = get_facet_schema(db, user_id)
    return {
        "thesis_title": thesis_title,
        "thesis_question": thesis_question,
        "thesis_contribution": thesis_contribution,
        "tracked_venues": tracked_venues,
        "scoring_clusters": scoring_clusters,
        "avoid_topics": avoid_topics,
        "prompt_profile": prompt_profile,
        "facet_schema": facet_schema,
    }


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
