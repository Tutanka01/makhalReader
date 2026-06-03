from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from fastapi import HTTPException

from auth import require_session
from database import Article, Feed, Highlight, get_db, get_setting, set_setting
from models import (
    DailyReadCount,
    OldestUnreadItem,
    ReadingDebtOut,
    ReadingGoalUpdate,
    ScoreBucket,
    StatsOut,
    TagFrequency,
)

router = APIRouter()
_auth = Depends(require_session)


def _compute_streak(dates: List[str]) -> int:
    if not dates:
        return 0
    today = datetime.now(timezone.utc).date()
    unique = sorted(
        {datetime.strptime(d, "%Y-%m-%d").date() for d in dates if d},
        reverse=True,
    )
    if not unique:
        return 0
    start = unique[0]
    yesterday = today - timedelta(days=1)
    if start != today and start != yesterday:
        return 0
    streak = 0
    expected = start
    for d in unique:
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
    return streak


@router.get("/api/stats", response_model=StatsOut)
async def get_stats(db: Session = Depends(get_db), _: None = _auth):
    total_read = db.query(Article).filter(Article.read_at.isnot(None)).count()
    total_unread = db.query(Article).filter(Article.read_at.is_(None)).count()
    total_bookmarked = db.query(Article).filter(Article.bookmarked == True).count()

    date_rows = (
        db.query(func.strftime("%Y-%m-%d", Article.read_at).label("d"))
        .filter(Article.read_at.isnot(None))
        .distinct()
        .all()
    )
    all_dates = [row.d for row in date_rows if row.d]
    streak_days = _compute_streak(all_dates)

    cutoff_30 = datetime.now(timezone.utc) - timedelta(days=30)
    daily_rows = (
        db.query(
            func.strftime("%Y-%m-%d", Article.read_at).label("d"),
            func.count(Article.id).label("cnt"),
        )
        .filter(Article.read_at >= cutoff_30)
        .group_by(func.strftime("%Y-%m-%d", Article.read_at))
        .order_by(func.strftime("%Y-%m-%d", Article.read_at))
        .all()
    )
    daily_counts = [DailyReadCount(date=row.d, count=row.cnt) for row in daily_rows if row.d]

    avg_row = (
        db.query(func.avg(Article.score))
        .filter(Article.read_at.isnot(None), Article.score.isnot(None))
        .scalar()
    )
    avg_score_read = round(float(avg_row), 2) if avg_row is not None else None

    tag_rows = (
        db.query(Article.tags_json)
        .filter(Article.read_at.isnot(None), Article.tags_json.isnot(None))
        .order_by(Article.read_at.desc())
        .limit(2000)
        .all()
    )
    tag_counts: Dict[str, int] = {}
    for (tags_json,) in tag_rows:
        try:
            for tag in json.loads(tags_json or "[]"):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except Exception:
            pass
    top_tags = [
        TagFrequency(tag=t, count=c)
        for t, c in sorted(tag_counts.items(), key=lambda x: -x[1])[:20]
    ]

    try:
        total_highlights = db.query(Highlight).count()
    except Exception:
        total_highlights = 0

    cat_rows = (
        db.query(Feed.category, func.count(Article.id).label("cnt"))
        .join(Article, Article.feed_id == Feed.id)
        .filter(Article.read_at.isnot(None))
        .group_by(Feed.category)
        .all()
    )
    articles_per_category = {row.category: row.cnt for row in cat_rows}

    return StatsOut(
        total_read=total_read,
        total_unread=total_unread,
        total_bookmarked=total_bookmarked,
        streak_days=streak_days,
        daily_counts=daily_counts,
        avg_score_read=avg_score_read,
        top_tags=top_tags,
        total_highlights=total_highlights,
        articles_per_category=articles_per_category,
    )


# ── Reading Debt Dashboard (Story 5.4) ────────────────────────────────────────

_WPM = 200
_DEFAULT_MINUTES = 8


def _est_minutes(content_text: str | None) -> int:
    if not content_text:
        return _DEFAULT_MINUTES
    word_count = len(content_text.split())
    return max(3, round(word_count / _WPM))


@router.get("/api/stats/reading-debt", response_model=ReadingDebtOut)
async def reading_debt(db: Session = Depends(get_db), _: None = _auth):
    """Return reading debt statistics."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # All unread articles with score
    unread = (
        db.query(
            Article.id,
            Article.title,
            Article.score,
            Article.content_text,
            Article.created_at,
        )
        .filter(Article.read_at.is_(None), Article.score.isnot(None))
        .all()
    )

    unread_high = [a for a in unread if a.score >= 7]
    unread_critical = [a for a in unread if a.score >= 9]

    # Reading time
    unread_high_minutes = sum(_est_minutes(a.content_text) for a in unread_high)

    # Weekly progress
    weekly_progress = (
        db.query(func.count(Article.id))
        .filter(Article.read_at >= week_ago)
        .scalar()
    ) or 0

    # Backlog clear days
    backlog_clear_days: float | None = None
    if weekly_progress > 0:
        articles_per_day = weekly_progress / 7.0
        backlog_clear_days = round(len(unread_high) / articles_per_day, 1)

    # Weekly goal from settings
    try:
        weekly_goal = int(get_setting(db, "weekly_goal", "10"))
    except (ValueError, TypeError):
        weekly_goal = 10

    # Oldest unread high-value articles (top 5)
    oldest_sorted = sorted(unread_high, key=lambda a: a.created_at)[:5]
    oldest_out = [
        OldestUnreadItem(
            id=a.id,
            title=a.title,
            score=a.score,
            age_days=(now - a.created_at.replace(tzinfo=timezone.utc)).days,
        )
        for a in oldest_sorted
    ]

    # Score distribution buckets
    buckets = [
        ScoreBucket(bucket="9-10", unread_count=len([a for a in unread if a.score >= 9])),
        ScoreBucket(bucket="8-9",  unread_count=len([a for a in unread if 8 <= a.score < 9])),
        ScoreBucket(bucket="7-8",  unread_count=len([a for a in unread if 7 <= a.score < 8])),
        ScoreBucket(bucket="<7",   unread_count=len([a for a in unread if a.score < 7])),
    ]

    return ReadingDebtOut(
        unread_high=len(unread_high),
        unread_critical=len(unread_critical),
        unread_high_minutes=unread_high_minutes,
        weekly_goal=weekly_goal,
        weekly_progress=weekly_progress,
        backlog_clear_days=backlog_clear_days,
        oldest_unread_high=oldest_out,
        score_distribution=buckets,
    )


@router.put("/api/stats/reading-goal")
async def update_reading_goal(
    body: ReadingGoalUpdate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Persist weekly reading goal."""
    set_setting(db, "weekly_goal", str(body.weekly_goal))
    return {"status": "ok", "weekly_goal": body.weekly_goal}
