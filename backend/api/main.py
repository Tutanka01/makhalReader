import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import feedparser
import xml.etree.ElementTree as ET
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth import (
    COOKIE_NAME,
    _check_rate_limit,
    _clear_failure,
    _client_ip,
    _record_failure,
    clear_session_cookie,
    create_session,
    delete_session,
    purge_expired_sessions,
    require_session,
    set_session_cookie,
    verify_password,
)
from database import Article, Feed, SessionLocal, get_db, init_db
from models import (
    ArticleListItem,
    ArticleOut,
    FeedCreate,
    FeedOut,
    FeedWithCount,
    InternalArticleCreate,
    InternalScoreUpdate,
)

API_SECRET = os.getenv("API_SECRET", "changeme")
MAX_ARTICLES_PER_FEED = int(os.getenv("MAX_ARTICLES_PER_FEED", "200"))
ARTICLE_RETENTION_DAYS = int(os.getenv("ARTICLE_RETENTION_DAYS", "90"))

# CORS: in production, lock to your actual domain.
# Set CORS_ORIGIN=https://reader.yourdomain.com in .env
_cors_origin = os.getenv("CORS_ORIGIN", "")
_cors_origins = [_cors_origin] if _cors_origin else []

app = FastAPI(title="MakhalReader API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Internal-Secret"],
)

# SSE queue registry: maps client_id -> asyncio.Queue
_sse_queues: Dict[str, asyncio.Queue] = {}

DEFAULT_FEEDS = [
    # ── Infra / Cloud / Platform ──────────────────────────────────────────
    {"url": "https://kubernetes.io/feed.xml",                            "name": "Kubernetes Blog",            "category": "Infra"},
    {"url": "https://www.cncf.io/feed/",                                 "name": "CNCF",                       "category": "Infra"},
    {"url": "https://thenewstack.io/feed/",                              "name": "The New Stack",              "category": "Infra"},
    {"url": "https://blog.cloudflare.com/rss/",                          "name": "Cloudflare Blog",            "category": "Infra"},
    {"url": "https://netflixtechblog.com/feed",                          "name": "Netflix Tech Blog",          "category": "Infra"},
    {"url": "https://engineering.fb.com/feed/",                          "name": "Meta Engineering",           "category": "Infra"},
    {"url": "https://fly.io/blog/feed.xml",                              "name": "Fly.io Blog",                "category": "Infra"},
    {"url": "https://www.brendangregg.com/blog/rss.xml",                 "name": "Brendan Gregg",              "category": "Infra"},
    {"url": "https://charity.wtf/feed/",                                 "name": "Charity Majors",             "category": "Infra"},
    {"url": "https://martinfowler.com/feed.atom",                        "name": "Martin Fowler",              "category": "Infra"},
    {"url": "https://grafana.com/blog/index.xml",                        "name": "Grafana Blog",               "category": "Infra"},
    {"url": "https://www.datadoghq.com/blog/feed/",                      "name": "Datadog Engineering",        "category": "Infra"},
    {"url": "https://blog.bytebytego.com/feed",                          "name": "ByteByteGo",                 "category": "Infra"},
    # ── Linux / Systems / Containers internals ────────────────────────────
    {"url": "https://iximiuz.com/en/posts.rss",                          "name": "iximiuz",                    "category": "Infra"},
    {"url": "https://lwn.net/headlines/rss",                             "name": "LWN.net",                    "category": "Infra"},
    {"url": "https://fasterthanli.me/index.xml",                         "name": "fasterthanli.me",            "category": "Infra"},
    {"url": "https://danluu.com/atom.xml",                               "name": "Dan Luu",                    "category": "Infra"},
    {"url": "https://xeiaso.net/blog.rss",                               "name": "Xe Iaso",                    "category": "Infra"},
    {"url": "https://drewdevault.com/blog/index.xml",                    "name": "Drew DeVault",               "category": "Infra"},
    {"url": "https://notes.eatonphil.com/rss.xml",                       "name": "Phil Eaton",                 "category": "Infra"},
    {"url": "https://www.phoronix.com/rss.php",                          "name": "Phoronix",                   "category": "Infra"},
    {"url": "https://blog.jessfraz.com/index.xml",                       "name": "Jessie Frazelle",            "category": "Infra"},
    # ── Networking / eBPF ─────────────────────────────────────────────────
    {"url": "https://tailscale.com/blog/index.xml",                      "name": "Tailscale Blog",             "category": "Infra"},
    {"url": "https://isovalent.com/blog/index.xml",                      "name": "Isovalent (Cilium/eBPF)",    "category": "Infra"},
    {"url": "https://www.polarsignals.com/blog/feed",                     "name": "Polar Signals (eBPF)",       "category": "Infra"},
    # ── Self-hosting / Homelab ────────────────────────────────────────────
    {"url": "https://blog.alexellis.io/rss/",                            "name": "Alex Ellis",                 "category": "Infra"},
    {"url": "https://selfh.st/feed/",                                    "name": "selfh.st",                   "category": "Infra"},
    # ── AI / LLM / Agents ────────────────────────────────────────────────
    {"url": "https://huyenchip.com/feed",                                "name": "Huyen Chip",                 "category": "AI"},
    {"url": "https://lilianweng.github.io/feed.xml",                     "name": "Lilian Weng",                "category": "AI"},
    {"url": "https://www.anthropic.com/news/rss.xml",                    "name": "Anthropic",                  "category": "AI"},
    {"url": "https://huggingface.co/blog/feed.xml",                      "name": "HuggingFace Blog",           "category": "AI"},
    {"url": "https://bair.berkeley.edu/blog/feed.xml",                   "name": "BAIR Blog",                  "category": "AI"},
    {"url": "https://eugeneyan.com/rss.xml",                             "name": "Eugene Yan",                 "category": "AI"},
    {"url": "https://magazine.sebastianraschka.com/feed",                "name": "Sebastian Raschka",          "category": "AI"},
    {"url": "https://www.interconnects.ai/feed",                         "name": "interconnects.ai",           "category": "AI"},
    {"url": "https://www.latent.space/feed",                             "name": "Latent Space",               "category": "AI"},
    {"url": "https://mlabonne.github.io/blog/feed.xml",                  "name": "Maxime Labonne",             "category": "AI"},
    {"url": "https://vickiboykis.com/index.xml",                         "name": "Vicky Boykis",               "category": "AI"},
    {"url": "https://www.deeplearning.ai/the-batch/feed/rss/",           "name": "The Batch (Andrew Ng)",      "category": "AI"},
    {"url": "https://hamel.dev/feed.xml",                                "name": "Hamel Husain",               "category": "AI"},
    {"url": "https://timdettmers.com/feed/",                             "name": "Tim Dettmers",               "category": "AI"},
    # ── Cybersécurité ─────────────────────────────────────────────────────
    {"url": "https://portswigger.net/research/rss",                      "name": "PortSwigger Research",       "category": "Sec"},
    {"url": "https://googleprojectzero.blogspot.com/feeds/posts/default","name": "Google Project Zero",        "category": "Sec"},
    {"url": "https://blog.trailofbits.com/feed/",                        "name": "Trail of Bits",              "category": "Sec"},
    {"url": "https://lcamtuf.substack.com/feed",                         "name": "lcamtuf",                    "category": "Sec"},
    {"url": "https://secret.club/feed.xml",                              "name": "secret.club",                "category": "Sec"},
    {"url": "https://krebsonsecurity.com/feed/",                         "name": "Krebs on Security",          "category": "Sec"},
    {"url": "https://www.schneier.com/feed/atom/",                       "name": "Bruce Schneier",             "category": "Sec"},
    {"url": "https://posts.specterops.io/feed",                          "name": "SpecterOps",                 "category": "Sec"},
    {"url": "https://research.nccgroup.com/feed/",                       "name": "NCC Group Research",         "category": "Sec"},
    {"url": "https://blog.xpnsec.com/rss.xml",                          "name": "Adam Chester (XPN)",         "category": "Sec"},
    {"url": "https://objective-see.org/rss.xml",                         "name": "Objective-See",              "category": "Sec"},
    # ── ArXiv — Research Papers ───────────────────────────────────────────
    {"url": "https://export.arxiv.org/rss/cs.AI",                       "name": "arXiv cs.AI",                "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.LG",                       "name": "arXiv cs.LG",                "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.DC",                       "name": "arXiv cs.DC",                "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.NI",                       "name": "arXiv cs.NI",                "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.CR",                       "name": "arXiv cs.CR",                "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.OS",                       "name": "arXiv cs.OS",                "category": "Papers"},
    # ── High-signal généraliste ───────────────────────────────────────────
    {"url": "https://simonwillison.net/atom/everything/",                "name": "Simon Willison",             "category": "High-signal"},
    {"url": "https://jvns.ca/atom.xml",                                  "name": "Julia Evans",                "category": "High-signal"},
    {"url": "https://rachelbythebay.com/w/atom.xml",                     "name": "rachelbythebay",             "category": "High-signal"},
    {"url": "https://news.ycombinator.com/rss",                          "name": "Hacker News",                "category": "High-signal"},
    {"url": "https://lobste.rs/rss",                                     "name": "Lobsters",                   "category": "High-signal"},
    {"url": "https://newsletter.pragmaticengineer.com/feed",             "name": "Pragmatic Engineer",         "category": "High-signal"},
    {"url": "https://queue.acm.org/rss/feeds/queuecontent.xml",          "name": "ACM Queue",                  "category": "High-signal"},
    {"url": "http://www.paulgraham.com/rss.html",                        "name": "Paul Graham",                "category": "High-signal"},
    {"url": "https://the.scapegoat.dev/rss.xml",                         "name": "The Scapegoat Dev",          "category": "High-signal"},
    {"url": "https://matklad.github.io/feed.xml",                        "name": "matklad",                    "category": "High-signal"},
]


def _run_cleanup() -> int:
    """Synchronous cleanup logic — returns number of deleted articles."""
    db = SessionLocal()
    try:
        total_deleted = 0

        # 1. Delete non-bookmarked articles older than ARTICLE_RETENTION_DAYS.
        if ARTICLE_RETENTION_DAYS > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=ARTICLE_RETENTION_DAYS)
            deleted = (
                db.query(Article)
                .filter(Article.created_at < cutoff, Article.bookmarked == False)
                .delete(synchronize_session=False)
            )
            total_deleted += deleted

        # 2. Per-feed cap: keep only the MAX_ARTICLES_PER_FEED most recent articles.
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
    # First pass immediately so stale articles are gone before the first poll.
    deleted = await asyncio.to_thread(_run_cleanup)
    if deleted:
        print(f"[cleanup] Startup pass: deleted {deleted} old articles")

    while True:
        await asyncio.sleep(86400)
        deleted = await asyncio.to_thread(_run_cleanup)
        if deleted:
            print(f"[cleanup] Nightly pass: deleted {deleted} old articles")


@app.on_event("startup")
async def startup():
    init_db()
    purge_expired_sessions()
    asyncio.create_task(cleanup_old_articles())
    db = SessionLocal()
    try:
        existing_urls = {url for (url,) in db.query(Feed.url).all()}
        added = 0
        for feed_data in DEFAULT_FEEDS:
            if feed_data["url"] not in existing_urls:
                db.add(Feed(**feed_data))
                added += 1
        if added:
            db.commit()
            print(f"[startup] Added {added} new default feed(s)")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auth routes — public (no session required)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str
    remember: bool = False


@app.post("/auth/login")
async def login(body: LoginRequest, request: Request, response: Response):
    ip = _client_ip(request)
    _check_rate_limit(ip)

    if not verify_password(body.password):
        _record_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid password")

    _clear_failure(ip)
    token = create_session(
        remember=body.remember,
        user_agent=request.headers.get("User-Agent"),
    )
    set_session_cookie(response, token, body.remember)
    return {"ok": True}


@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(token)
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/auth/status")
async def auth_status(request: Request):
    from auth import validate_session
    token = request.cookies.get(COOKIE_NAME)
    if not token or not validate_session(token):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Public — health check (no auth, used by Docker and Caddy)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Protected API routes
# ---------------------------------------------------------------------------

_auth = Depends(require_session)


@app.get("/api/articles", response_model=List[ArticleListItem])
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

    # Full-text search: searches across all articles regardless of read status
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

    if sort == "score":
        query = query.order_by(Article.score.desc().nullslast(), Article.created_at.desc())
    else:
        query = query.order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())

    query = query.offset(offset).limit(limit)
    results = query.all()
    return [_row_to_list_item(row) for row in results]


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
    )


@app.get("/api/articles/{article_id}", response_model=ArticleOut)
async def get_article(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleOut.model_validate(article)


@app.post("/api/articles/{article_id}/read")
async def mark_read(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


@app.post("/api/articles/{article_id}/unread")
async def mark_unread(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.read_at = None
    db.commit()
    return {"status": "ok"}


@app.post("/api/articles/read-all")
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


@app.post("/api/articles/{article_id}/bookmark")
async def toggle_bookmark(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.bookmarked = not article.bookmarked
    db.commit()
    return {"bookmarked": article.bookmarked}


class FeedbackRequest(BaseModel):
    value: int  # 1=like, -1=dislike, 0=remove feedback


@app.post("/api/articles/{article_id}/feedback")
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
    return {"user_feedback": article.user_feedback}


@app.get("/api/feeds", response_model=List[FeedWithCount])
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


@app.post("/api/feeds/opml")
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
            # Flat OPML: outline has a feed URL directly
            feeds_to_add.append({
                "url": top_url,
                "name": top.get("title") or top.get("text") or top_url,
                "category": "General",
            })
        else:
            # Nested: this outline is a category folder
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


@app.get("/api/digest", response_model=List[ArticleListItem])
async def get_digest(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    results = (
        db.query(Article, Feed.name.label("feed_name"))
        .join(Feed, Article.feed_id == Feed.id)
        .filter(Article.created_at >= cutoff, Article.score.isnot(None))
        .order_by(Article.score.desc())
        .limit(limit)
        .all()
    )
    return [_row_to_list_item(row) for row in results]


@app.post("/api/feeds", response_model=FeedOut)
async def add_feed(feed_data: FeedCreate, db: Session = Depends(get_db), _: None = _auth):
    # Validate the URL by trying to parse it
    parsed = feedparser.parse(feed_data.url)
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


@app.delete("/api/feeds/{feed_id}")
async def delete_feed(feed_id: int, db: Session = Depends(get_db), _: None = _auth):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    feed.active = False
    db.commit()
    return {"status": "ok"}


async def _sse_event_generator(request: Request, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        yield "data: {\"type\": \"connected\"}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(message)}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass


@app.get("/api/stream")
async def sse_stream(request: Request, _: None = _auth):
    client_id = str(id(request))
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_queues[client_id] = queue

    async def cleanup_generator():
        try:
            async for chunk in _sse_event_generator(request, queue):
                yield chunk
        finally:
            _sse_queues.pop(client_id, None)

    return StreamingResponse(
        cleanup_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _broadcast_new_article(article_data: dict):
    message = {"type": "new_article", "data": article_data}
    dead_clients = []
    for client_id, queue in _sse_queues.items():
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead_clients.append(client_id)
    for client_id in dead_clients:
        _sse_queues.pop(client_id, None)



@app.get("/api/internal/feeds")
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
    return [
        {"id": feed.id, "url": feed.url, "name": feed.name, "category": feed.category}
        for feed, _ in results
    ]


@app.get("/api/internal/feedback-examples")
async def internal_feedback_examples(
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Return an aggregated preference profile (tag frequencies + examples) for scorer personalisation.

    Aggregates tags across the *entire* feedback history rather than just recent titles —
    this yields a stable, token-efficient signal that generalises to unseen articles.
    """
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

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

    return {
        # Tag frequencies over full history — primary personalisation signal
        "liked_tags": aggregate_tags(liked_rows, top_n=10),
        "disliked_tags": aggregate_tags(disliked_rows, top_n=8),
        # Recent examples for contrastive illustration
        "liked_examples": format_examples(liked_rows, max_n=4),
        "disliked_examples": format_examples(disliked_rows, max_n=3),
        # Totals so the scorer can skip if cold-start
        "total_liked": len(liked_rows),
        "total_disliked": len(disliked_rows),
    }


@app.get("/api/internal/articles/exists")
async def internal_article_exists(
    url: str = Query(...),
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    exists = db.query(Article.id).filter(Article.url == url).first() is not None
    return {"exists": exists}


@app.post("/api/internal/articles")
async def internal_create_article(
    article_data: InternalArticleCreate,
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    # ── Layer 1: exact URL match ─────────────────────────────────────────────
    existing = db.query(Article).filter(Article.url == article_data.url).first()
    if existing:
        return {"id": existing.id, "created": False}

    # ── Layer 2: title fingerprint (catches syndicated articles) ─────────────
    # Same normalised title within a 3-day window → treat as duplicate.
    # The short window avoids false positives on recurring titles like
    # "Weekly Digest" that would match across different issues.
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
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return {"id": article.id, "created": True}


@app.delete("/api/admin/articles/broken")
async def delete_broken_articles(db: Session = Depends(get_db), _: None = _auth):
    """
    Delete articles that have garbled content or no meaningful title.
    Call once after upgrading the extractor to clean up old bad data.
    """
    import re as _re

    def _is_garbled(text: Optional[str]) -> bool:
        if not text or len(text) < 20:
            return False
        sample = text[:1000]
        bad = sum(1 for c in sample if c == "\ufffd" or (ord(c) < 32 and c not in "\t\n\r"))
        return (bad / len(sample)) > 0.04

    def _is_no_title(title: str) -> bool:
        t = (title or "").strip()
        return not t or t in ("[no-title]", "no-title", "Untitled", "") or len(t) < 3

    articles = db.query(Article).all()
    to_delete = []
    for a in articles:
        if _is_garbled(a.content_text) or _is_garbled(a.content_html):
            to_delete.append(a.id)
        elif _is_no_title(a.title) and not a.bookmarked:
            to_delete.append(a.id)

    if to_delete:
        db.query(Article).filter(Article.id.in_(to_delete)).delete(synchronize_session=False)
        db.commit()

    return {"deleted": len(to_delete)}


_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "utm_name", "utm_cid",
    "fbclid", "gclid", "msclkid", "yclid", "twclid", "igshid",
    "_ga", "_gl", "mc_cid", "mc_eid", "ref", "source",
})

# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _title_fingerprint(title: str) -> str:
    """
    16-char hex fingerprint of a normalised title.
    Removes punctuation, collapses whitespace, lowercases — so minor formatting
    differences between syndicated copies don't create separate fingerprints.
    """
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


@app.post("/api/admin/normalize-urls")
async def normalize_article_urls(db: Session = Depends(get_db), _: None = _auth):
    """
    One-time migration: normalize all article URLs already in the DB so they
    match the canonical form now used by the poller.  Safe to call multiple
    times — idempotent.  Merges duplicate normalized URLs by keeping the
    article with richer content and deleting the other.
    """
    articles = db.query(Article).all()
    updated = 0
    merged = 0
    skipped = 0

    for article in articles:
        canonical = _normalize_url(article.url)
        if canonical == article.url:
            continue  # already canonical

        # Check if another article already holds this canonical URL
        conflict = db.query(Article).filter(
            Article.url == canonical,
            Article.id != article.id,
        ).first()

        if conflict:
            # Keep whichever has more content; delete the other
            keep = conflict if len(conflict.content_text or "") >= len(article.content_text or "") else article
            drop = article if keep is conflict else conflict
            # Preserve bookmark status
            if drop.bookmarked:
                keep.bookmarked = True
            db.delete(drop)
            if keep.url != canonical:
                keep.url = canonical
            merged += 1
        else:
            article.url = canonical
            updated += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Migration failed: {e}")

    return {"updated": updated, "merged": merged, "skipped": skipped}


@app.post("/api/internal/articles/{article_id}/score")
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

    article.score = score_data.score
    article.tags_json = json.dumps(score_data.tags)
    article.summary_bullets_json = json.dumps(score_data.summary_bullets)
    article.reason = score_data.reason
    db.commit()
    db.refresh(article)

    # Broadcast to SSE clients
    feed = db.query(Feed).filter(Feed.id == article.feed_id).first()
    article_dict = {
        "id": article.id,
        "feed_id": article.feed_id,
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "score": article.score,
        "tags": json.loads(article.tags_json or "[]"),
        "summary_bullets": json.loads(article.summary_bullets_json or "[]"),
        "reason": article.reason,
        "read_at": article.read_at.isoformat() if article.read_at else None,
        "bookmarked": article.bookmarked,
        "extraction_failed": article.extraction_failed,
        "created_at": article.created_at.isoformat(),
        "feed_name": feed.name if feed else "",
        "user_feedback": article.user_feedback,
    }
    await _broadcast_new_article(article_dict)

    return {"status": "ok"}
