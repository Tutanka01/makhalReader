import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_session
from database import Article, Feed, Highlight, get_db
from models import DailyReadCount, StatsOut, TagFrequency

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
