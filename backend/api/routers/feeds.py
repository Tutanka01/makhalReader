import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List

import feedparser
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import require_session
from database import Article, Feed, get_db
from models import ArticleListItem, FeedCreate, FeedOut, FeedWithCount
from routers.articles import _row_to_list_item

router = APIRouter()
_auth = Depends(require_session)


@router.get("/api/feeds", response_model=List[FeedWithCount])
async def list_feeds(db: Session = Depends(get_db), _: None = _auth):
    results = (
        db.query(Feed, func.count(Article.id).label("article_count"))
        .outerjoin(Article, Feed.id == Article.feed_id)
        .filter(Feed.active == True)
        .group_by(Feed.id)
        .all()
    )
    return [
        FeedWithCount(
            id=feed.id, url=feed.url, name=feed.name,
            category=feed.category, active=feed.active,
            last_fetched=feed.last_fetched, article_count=count,
        )
        for feed, count in results
    ]


@router.post("/api/feeds/opml")
async def import_opml(file: UploadFile = File(...), db: Session = Depends(get_db), _: None = _auth):
    content = await file.read()
    try:
        root = ET.fromstring(content.decode("utf-8", errors="replace"))
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Invalid OPML file: {e}")

    feeds_to_add: list[dict] = []
    body = root.find("body")
    if body is None:
        raise HTTPException(status_code=400, detail="No <body> found in OPML")

    for top in body:
        top_url = top.get("xmlUrl") or top.get("xmlurl")
        if top_url:
            feeds_to_add.append({
                "url": top_url,
                "name": top.get("title") or top.get("text") or top_url,
                "category": "General",
            })
        else:
            category = top.get("title") or top.get("text") or "General"
            for child in top:
                child_url = child.get("xmlUrl") or child.get("xmlurl")
                if child_url:
                    feeds_to_add.append({
                        "url": child_url,
                        "name": child.get("title") or child.get("text") or child_url,
                        "category": category,
                    })

    added, skipped = 0, 0
    for f in feeds_to_add:
        existing = db.query(Feed).filter(Feed.url == f["url"]).first()
        if existing:
            if not existing.active:
                existing.active = True
                added += 1
            else:
                skipped += 1
            continue
        db.add(Feed(url=f["url"], name=f["name"], category=f["category"]))
        added += 1

    db.commit()
    return {"added": added, "skipped": skipped, "total": len(feeds_to_add)}


@router.get("/api/digest", response_model=List[ArticleListItem])
async def get_digest(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(20, ge=1, le=50),
    min_score: float = Query(5.0, ge=0.0, le=10.0),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    results = (
        db.query(Article, Feed.name.label("feed_name"))
        .join(Feed, Article.feed_id == Feed.id)
        .filter(
            Article.created_at >= cutoff,
            Article.score.isnot(None),
            Article.score >= min_score,
        )
        .order_by(Article.score.desc())
        .limit(limit)
        .all()
    )
    return [_row_to_list_item(row) for row in results]


@router.post("/api/feeds", response_model=FeedOut)
async def add_feed(feed_data: FeedCreate, db: Session = Depends(get_db), _: None = _auth):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Basira/1.0",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            resp = await client.get(feed_data.url, headers=headers)
            resp.raise_for_status()
            content = resp.content
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid or unreachable feed URL")

    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise HTTPException(status_code=400, detail="Invalid or unreachable feed URL")

    existing = db.query(Feed).filter(Feed.url == feed_data.url).first()
    if existing:
        if not existing.active:
            existing.active = True
            db.commit()
            db.refresh(existing)
            return FeedOut.model_validate(existing)
        raise HTTPException(status_code=409, detail="Feed already exists")

    feed = Feed(url=feed_data.url, name=feed_data.name, category=feed_data.category)
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return FeedOut.model_validate(feed)


@router.delete("/api/feeds/{feed_id}")
async def delete_feed(feed_id: int, db: Session = Depends(get_db), _: None = _auth):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    feed.active = False
    db.commit()
    return {"status": "ok"}
