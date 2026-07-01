import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

import feedparser
import xml.etree.ElementTree as ET
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
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
from database import Article, Briefing, Feed, Highlight, SessionLocal, backfill_reading_time, get_db, init_db
from briefing import generate_briefing
from llm import resolve_provider
from models import (
    ArticleListItem,
    ArticleOut,
    AskRequest,
    BriefingOut,
    BriefingSummaryOut,
    DailyReadCount,
    FeedCreate,
    FeedOut,
    FeedWithCount,
    HighlightCreate,
    HighlightOut,
    HighlightUpdate,
    InternalArticleCreate,
    InternalFeedFetched,
    InternalScoreFailure,
    InternalScoringClaimRequest,
    InternalScoreUpdate,
    StatsOut,
    TagFrequency,
)

API_SECRET = os.getenv("API_SECRET", "changeme")
MAX_ARTICLES_PER_FEED = int(os.getenv("MAX_ARTICLES_PER_FEED", "200"))
ARTICLE_RETENTION_DAYS = int(os.getenv("ARTICLE_RETENTION_DAYS", "90"))
SCORING_MAX_ATTEMPTS = int(os.getenv("SCORING_MAX_ATTEMPTS", "5"))
SCORING_LOCK_TIMEOUT_MINUTES = int(os.getenv("SCORING_LOCK_TIMEOUT_MINUTES", "20"))
SCORING_RETRY_BASE_MINUTES = int(os.getenv("SCORING_RETRY_BASE_MINUTES", "5"))
SCORING_RETRY_MAX_MINUTES = int(os.getenv("SCORING_RETRY_MAX_MINUTES", "360"))

# LLM config (shared with scorer service)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
QA_MODEL = os.getenv("QA_MODEL", os.getenv("SCORER_MODEL", "google/gemini-flash-1.5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host-gateway:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# Semaphore to prevent concurrent LLM ask calls (cost protection)
_ask_semaphore = asyncio.Semaphore(2)

# Briefing regeneration cadence + concurrency guard
BRIEFING_INTERVAL_HOURS = float(os.getenv("BRIEFING_INTERVAL_HOURS", "12"))
_briefing_lock = asyncio.Lock()  # never generate two briefings at once

# CORS: in production, lock to your actual domain.
# Set CORS_ORIGIN=https://reader.yourdomain.com in .env
_cors_origin = os.getenv("CORS_ORIGIN", "")
_cors_origins = [_cors_origin] if _cors_origin else []

app = FastAPI(title="MakhalReader API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
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
    # ── K8s weekly / SRE / Distributed Systems ───────────────────────────
    {"url": "https://lwkd.info/feed.xml",                                "name": "LWKD",                       "category": "Infra"},
    {"url": "https://blog.palark.com/feed",                              "name": "Palark",                     "category": "Infra"},
    {"url": "https://aphyr.com/feed",                                    "name": "Aphyr (Jepsen)",             "category": "Infra"},
    {"url": "https://sreweekly.com/feed",                                "name": "SRE Weekly",                 "category": "Infra"},
    {"url": "https://feed.infoq.com/sre/",                                "name": "InfoQ SRE",                  "category": "Infra"},
    {"url": "https://incident.io/blog.xml",                               "name": "incident.io Blog",           "category": "Infra"},
    {"url": "https://lwcn.dev/newsletter/feed.xml",                       "name": "Last Week in Cloud Native",  "category": "Infra"},
    {"url": "http://feeds.feedburner.com/HighScalability",                "name": "High Scalability",           "category": "Infra"},
    {"url": "https://aws.amazon.com/blogs/architecture/feed/",            "name": "AWS Architecture Blog",      "category": "Infra"},
    {"url": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",    "name": "AWS What's New",             "category": "Infra"},
    {"url": "https://www.linkedin.com/blog/engineering/feed",             "name": "LinkedIn Engineering",       "category": "Infra"},
    {"url": "https://eng.uber.com/feed/",                                 "name": "Uber Engineering",           "category": "Infra"},
    {"url": "https://thereliabilityengineering.substack.com/feed",        "name": "Reliability Engineering",    "category": "Infra"},
    {"url": "https://newsletter.systemdesign.one/feed",                   "name": "System Design Newsletter",   "category": "Infra"},
    {"url": "https://dataengweekly.substack.com/feed",                    "name": "Data Eng Weekly",            "category": "Infra"},
    {"url": "https://cirinc.substack.com/feed",                           "name": "CIR DeepTech",               "category": "Infra"},
    {"url": "https://read.srepath.com/feed",                              "name": "Reliability Enablers",       "category": "Infra"},
    {"url": "https://slack.engineering/feed",                            "name": "Slack Engineering",          "category": "Infra"},
    # ── eBPF deep dives ───────────────────────────────────────────────────
    {"url": "https://howtech.substack.com/feed",                         "name": "How Tech (eBPF/XDP)",        "category": "Infra"},
    # ── Rust / Go ─────────────────────────────────────────────────────────
    {"url": "https://blog.rust-lang.org/feed.xml",                       "name": "Rust Blog",                  "category": "Infra"},
    {"url": "https://blog.rust-lang.org/inside-rust/feed.xml",           "name": "Inside Rust",                "category": "Infra"},
    {"url": "https://go.dev/blog/feed.atom",                             "name": "Go Blog",                    "category": "Infra"},
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
    {"url": "https://decodingml.substack.com/feed",                      "name": "Decoding ML",                "category": "AI"},
    {"url": "https://developer.nvidia.com/blog/feed",                    "name": "NVIDIA Dev Blog",            "category": "AI"},
    {"url": "https://neptune.ai/blog/feed",                              "name": "neptune.ai",                 "category": "AI"},
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
    {"url": "https://www.zerodayinitiative.com/rss/published/",          "name": "Zero Day Initiative",        "category": "Sec"},
    {"url": "https://research.checkpoint.com/feed/",                     "name": "Check Point Research",       "category": "Sec"},
    {"url": "https://infosecwriteups.com/feed",                          "name": "InfoSec Write-ups",          "category": "Sec"},
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
    # ── Reddit communities — scored carefully via Reddit-aware extraction ─
    {"url": "https://www.reddit.com/r/sre/.rss",                          "name": "r/sre",                      "category": "Communities"},
    {"url": "https://www.reddit.com/r/devops/.rss",                       "name": "r/devops",                   "category": "Communities"},
    {"url": "https://www.reddit.com/r/kubernetes/.rss",                   "name": "r/kubernetes",               "category": "Communities"},
    {"url": "https://www.reddit.com/r/sysadmin/.rss",                     "name": "r/sysadmin",                 "category": "Communities"},
    {"url": "https://www.reddit.com/r/homelab/.rss",                      "name": "r/homelab",                  "category": "Communities"},
    {"url": "https://www.reddit.com/r/selfhosted/.rss",                   "name": "r/selfhosted",               "category": "Communities"},
    {"url": "https://www.reddit.com/r/networking/.rss",                   "name": "r/networking",               "category": "Communities"},
    {"url": "https://www.reddit.com/r/Observability/.rss",                "name": "r/Observability",            "category": "Communities"},
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


async def briefing_scheduler():
    """Generate a briefing at startup (if none today) then every BRIEFING_INTERVAL_HOURS."""
    await asyncio.sleep(20)  # let the first poll/scoring settle
    while True:
        db = SessionLocal()
        try:
            today = datetime.now(timezone.utc).date()
            latest = db.query(Briefing).order_by(Briefing.generated_at.desc()).first()
            if latest is None or latest.generated_at.date() < today:
                async with _briefing_lock:
                    briefing = await generate_briefing(db, hours=24)
                if briefing is not None:
                    await _broadcast_briefing(briefing)
                    print(f"[briefing] Generated briefing #{briefing.id} ({briefing.article_count} articles)")
        except Exception as e:  # noqa: BLE001
            print(f"[briefing] scheduler error: {e}")
        finally:
            db.close()
        await asyncio.sleep(BRIEFING_INTERVAL_HOURS * 3600)


@app.on_event("startup")
async def startup():
    init_db()
    purge_expired_sessions()
    asyncio.create_task(cleanup_old_articles())
    asyncio.create_task(briefing_scheduler())

    # Backfill reading_time for legacy articles (non-blocking)
    backfilled = await asyncio.to_thread(backfill_reading_time)
    if backfilled:
        print(f"[startup] Backfilled reading_time for {backfilled} article(s)")

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
def login(body: LoginRequest, request: Request, response: Response):
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
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(token)
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/auth/status")
def auth_status(request: Request):
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
    exclude_category: Optional[str] = Query(None),
    bookmarked: Optional[bool] = Query(None),
    url: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=10),
    search: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    query = db.query(
        Article,
        Feed.name.label("feed_name"),
        Feed.category.label("feed_category"),
    ).join(Feed, Article.feed_id == Feed.id)

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
    elif exclude_category:
        query = query.filter(Feed.category != exclude_category)

    if bookmarked is not None:
        query = query.filter(Article.bookmarked == bookmarked)

    if min_score is not None:
        query = query.filter(Article.score >= min_score)

    # Unread articles always float above read ones (read_at IS NULL = True → 1 > 0)
    unread_first = Article.read_at.is_(None).desc()
    if sort == "score":
        query = query.order_by(unread_first, Article.score.desc().nullslast(), Article.created_at.desc())
    else:
        query = query.order_by(unread_first, Article.published_at.desc().nullslast(), Article.created_at.desc())

    query = query.offset(offset).limit(limit)
    results = query.all()
    return [_row_to_list_item(row) for row in results]


def _row_to_list_item(row) -> ArticleListItem:
    article, feed_name, feed_category = row
    return ArticleListItem(
        id=article.id,
        feed_id=article.feed_id,
        title=article.title,
        url=article.url,
        published_at=article.published_at,
        score=article.score,
        score_details_json=article.score_details_json or "{}",
        tags_json=article.tags_json or "[]",
        summary_bullets_json=article.summary_bullets_json or "[]",
        reason=article.reason,
        read_at=article.read_at,
        bookmarked=article.bookmarked,
        extraction_failed=article.extraction_failed,
        created_at=article.created_at,
        feed_name=feed_name or "",
        feed_category=feed_category or "",
        user_feedback=article.user_feedback,
        reading_time=article.reading_time,
        scoring_status=article.scoring_status or ("done" if article.score is not None else "queued"),
        score_attempts=article.score_attempts or 0,
        next_score_attempt_at=article.next_score_attempt_at,
        scored_at=article.scored_at,
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
    exclude_category: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=10),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    query = db.query(Article).filter(Article.read_at.is_(None))
    if category and category not in ("All", "all"):
        feed_ids = db.query(Feed.id).filter(Feed.category == category)
        query = query.filter(Article.feed_id.in_(feed_ids))
    elif exclude_category:
        feed_ids = db.query(Feed.id).filter(Feed.category != exclude_category)
        query = query.filter(Article.feed_id.in_(feed_ids))
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


def _briefing_summary(b: Briefing) -> BriefingSummaryOut:
    try:
        content = json.loads(b.content_json or "{}")
    except Exception:
        content = {}
    articles = content.get("articles") or {}
    tag_counts: Dict[str, int] = {}
    for a in articles.values():
        for t in a.get("tags") or []:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_tags = [t for t, _ in sorted(tag_counts.items(), key=lambda kv: -kv[1])[:3]]
    return BriefingSummaryOut(
        id=b.id,
        generated_at=b.generated_at,
        window_start=b.window_start,
        window_end=b.window_end,
        model_used=b.model_used,
        article_count=b.article_count,
        intro=content.get("intro", ""),
        sections_count=len(content.get("sections") or []),
        top_picks_count=len(content.get("top_picks") or []),
        top_tags=top_tags,
    )


@app.get("/api/briefings", response_model=List[BriefingSummaryOut])
async def list_briefings(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    rows = (
        db.query(Briefing)
        .order_by(Briefing.generated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_briefing_summary(b) for b in rows]


@app.get("/api/briefings/latest", response_model=BriefingOut)
async def get_latest_briefing(response: Response, db: Session = Depends(get_db), _: None = _auth):
    briefing = db.query(Briefing).order_by(Briefing.generated_at.desc()).first()
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing yet")
    return BriefingOut.model_validate(briefing)


@app.get("/api/briefings/{briefing_id}", response_model=BriefingOut)
async def get_briefing(briefing_id: int, db: Session = Depends(get_db), _: None = _auth):
    briefing = db.query(Briefing).filter(Briefing.id == briefing_id).first()
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return BriefingOut.model_validate(briefing)


@app.post("/api/briefings/generate", response_model=BriefingOut)
async def generate_briefing_now(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    async with _briefing_lock:
        briefing = await generate_briefing(db, hours=hours)
    if briefing is None:
        raise HTTPException(status_code=404, detail="Nothing to synthesize for this window")
    await _broadcast_briefing(briefing)
    return BriefingOut.model_validate(briefing)


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


async def _broadcast_briefing(briefing: "Briefing"):
    message = {"type": "briefing_ready",
               "data": {"id": briefing.id, "generated_at": briefing.generated_at.isoformat()}}
    for client_id, queue in list(_sse_queues.items()):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            _sse_queues.pop(client_id, None)



@app.get("/api/internal/feeds")
def internal_list_feeds(
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
def internal_feedback_examples(
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
        db.query(Article.title, Article.tags_json, Article.score)
        .filter(Article.user_feedback == 1)
        .order_by(Article.created_at.desc())
        .all()
    )
    disliked_rows = (
        db.query(Article.title, Article.tags_json, Article.score)
        .filter(Article.user_feedback == -1)
        .order_by(Article.created_at.desc())
        .all()
    )
    bookmarked_rows = (
        db.query(Article.title, Article.tags_json, Article.score)
        .filter(Article.bookmarked == True)
        .order_by(Article.created_at.desc())
        .limit(50)
        .all()
    )
    read_rows = (
        db.query(Article.title, Article.tags_json, Article.score)
        .filter(Article.read_at.isnot(None), Article.score.isnot(None))
        .order_by(Article.read_at.desc())
        .limit(100)
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
            out.append({"title": row.title, "tags": tags[:5], "score": row.score})
        return out

    return {
        # Tag frequencies over full history — primary personalisation signal
        "liked_tags": aggregate_tags(liked_rows, top_n=10),
        "disliked_tags": aggregate_tags(disliked_rows, top_n=8),
        "bookmarked_tags": aggregate_tags(bookmarked_rows, top_n=8),
        "read_tags": aggregate_tags(read_rows, top_n=8),
        # Recent examples for contrastive illustration
        "liked_examples": format_examples(liked_rows, max_n=4),
        "disliked_examples": format_examples(disliked_rows, max_n=3),
        "bookmarked_examples": format_examples(bookmarked_rows, max_n=3),
        # Totals so the scorer can skip if cold-start
        "total_liked": len(liked_rows),
        "total_disliked": len(disliked_rows),
        "total_bookmarked": len(bookmarked_rows),
        "total_read": len(read_rows),
    }


@app.get("/api/internal/articles/exists")
def internal_article_exists(
    url: str = Query(...),
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    exists = db.query(Article.id).filter(Article.url == url).first() is not None
    return {"exists": exists}


@app.post("/api/internal/feeds/{feed_id}/fetched")
def internal_mark_feed_fetched(
    feed_id: int,
    fetched: InternalFeedFetched,
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    feed.last_fetched = fetched.fetched_at or datetime.now(timezone.utc)
    db.commit()
    return {
        "status": "ok",
        "feed_id": feed.id,
        "last_fetched": feed.last_fetched.isoformat() if feed.last_fetched else None,
        "entry_count": fetched.entry_count,
    }


@app.post("/api/internal/articles")
def internal_create_article(
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
        reading_time=article_data.reading_time,
        scoring_status="queued",
        score_attempts=0,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return {
        "id": article.id,
        "created": True,
        "scoring_status": article.scoring_status,
        "scoring_attempts": article.score_attempts,
        "scoring_next_retry_at": article.next_score_attempt_at.isoformat() if article.next_score_attempt_at else None,
    }


def _score_retry_delay(attempts: int) -> timedelta:
    attempts = max(1, attempts)
    minutes = min(
        SCORING_RETRY_BASE_MINUTES * (2 ** (attempts - 1)),
        SCORING_RETRY_MAX_MINUTES,
    )
    return timedelta(minutes=minutes)


def _score_claim_payload(article: Article) -> dict:
    return {
        "article_id": article.id,
        "id": article.id,
        "title": article.title,
        "content_text": article.content_text or "",
        "rss_summary": "",
        "status": article.scoring_status,
        "attempts": article.score_attempts or 0,
        "next_retry_at": article.next_score_attempt_at.isoformat() if article.next_score_attempt_at else None,
        "created_at": article.created_at.isoformat() if article.created_at else None,
    }


@app.post("/api/internal/scoring/claim")
def internal_claim_scoring_batch(
    claim: InternalScoringClaimRequest,
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    now = datetime.now(timezone.utc)
    stale_lock_cutoff = now - timedelta(minutes=SCORING_LOCK_TIMEOUT_MINUTES)
    eligible = or_(
        Article.scoring_status.is_(None),
        Article.scoring_status.in_(("queued", "retry")),
        and_(
            Article.scoring_status == "processing",
            Article.score_locked_at.isnot(None),
            Article.score_locked_at < stale_lock_cutoff,
        ),
    )
    due = or_(Article.next_score_attempt_at.is_(None), Article.next_score_attempt_at <= now)

    articles = (
        db.query(Article)
        .filter(Article.score.is_(None), eligible, due)
        .order_by(Article.score_attempts.asc(), Article.created_at.asc())
        .limit(claim.limit)
        .all()
    )

    for article in articles:
        article.scoring_status = "processing"
        article.score_attempts = (article.score_attempts or 0) + 1
        article.score_locked_at = now
        article.next_score_attempt_at = None
        article.score_last_error = None

    db.commit()
    for article in articles:
        db.refresh(article)

    return {"items": [_score_claim_payload(article) for article in articles]}


@app.post("/api/internal/articles/{article_id}/score-failed")
def internal_score_article_failed(
    article_id: int,
    failure: InternalScoreFailure,
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    now = datetime.now(timezone.utc)
    attempts = max(article.score_attempts or 1, 1)
    article.score_last_error = failure.error or "Scoring failed"
    article.score_locked_at = None

    if attempts >= SCORING_MAX_ATTEMPTS:
        article.scoring_status = "failed"
        article.next_score_attempt_at = None
    else:
        article.scoring_status = "retry"
        article.next_score_attempt_at = now + _score_retry_delay(attempts)

    db.commit()
    return {
        "status": article.scoring_status,
        "attempts": attempts,
        "next_retry_at": article.next_score_attempt_at.isoformat() if article.next_score_attempt_at else None,
        "max_attempts": SCORING_MAX_ATTEMPTS,
    }


@app.get("/api/internal/scoring/stats")
def internal_scoring_stats(
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    status_rows = (
        db.query(Article.scoring_status, func.count(Article.id))
        .group_by(Article.scoring_status)
        .all()
    )
    by_status = {(status or "queued"): count for status, count in status_rows}
    unscored = db.query(Article).filter(Article.score.is_(None)).count()
    ready = (
        db.query(Article)
        .filter(
            Article.score.is_(None),
            Article.scoring_status.in_(("queued", "retry")),
            or_(Article.next_score_attempt_at.is_(None), Article.next_score_attempt_at <= datetime.now(timezone.utc)),
        )
        .count()
    )
    return {
        "total": db.query(Article).count(),
        "unscored": unscored,
        "ready": ready,
        "by_status": by_status,
        "max_attempts": SCORING_MAX_ATTEMPTS,
    }


@app.post("/api/internal/scoring/requeue-failed")
def internal_requeue_failed_scoring(
    limit: int = Query(100, ge=1, le=1000),
    x_internal_secret: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if x_internal_secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    articles = (
        db.query(Article)
        .filter(Article.score.is_(None), Article.scoring_status == "failed")
        .order_by(Article.created_at.asc())
        .limit(limit)
        .all()
    )
    for article in articles:
        article.scoring_status = "queued"
        article.score_attempts = 0
        article.next_score_attempt_at = None
        article.score_last_error = None
        article.score_locked_at = None

    db.commit()
    return {"status": "ok", "requeued": len(articles)}


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


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

@app.get("/api/articles/{article_id}/highlights", response_model=List[HighlightOut])
async def list_highlights(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    highlights = (
        db.query(Highlight)
        .filter(Highlight.article_id == article_id)
        .order_by(Highlight.created_at)
        .all()
    )
    return [HighlightOut.model_validate(h) for h in highlights]


@app.post("/api/articles/{article_id}/highlights", response_model=HighlightOut, status_code=201)
async def create_highlight(
    article_id: int,
    body: HighlightCreate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    highlight = Highlight(
        article_id=article_id,
        selected_text=body.selected_text,
        prefix_context=body.prefix_context,
        suffix_context=body.suffix_context,
        color=body.color,
        note=body.note,
        created_at=datetime.now(timezone.utc),
    )
    db.add(highlight)
    db.commit()
    db.refresh(highlight)
    return HighlightOut.model_validate(highlight)


@app.put("/api/articles/{article_id}/highlights/{highlight_id}", response_model=HighlightOut)
async def update_highlight(
    article_id: int,
    highlight_id: int,
    body: HighlightUpdate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    highlight = (
        db.query(Highlight)
        .filter(Highlight.id == highlight_id, Highlight.article_id == article_id)
        .first()
    )
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    if body.color is not None:
        highlight.color = body.color
    if body.note is not None:
        highlight.note = body.note
    db.commit()
    db.refresh(highlight)
    return HighlightOut.model_validate(highlight)


@app.delete("/api/articles/{article_id}/highlights/{highlight_id}")
async def delete_highlight(
    article_id: int,
    highlight_id: int,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    highlight = (
        db.query(Highlight)
        .filter(Highlight.id == highlight_id, Highlight.article_id == article_id)
        .first()
    )
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    db.delete(highlight)
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Ask AI — streaming Q&A on a specific article
# ---------------------------------------------------------------------------

@app.post("/api/articles/{article_id}/ask")
async def ask_article(
    article_id: int,
    body: AskRequest,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    context = (article.content_text or "").strip()
    if not context and article.content_html:
        # Rough HTML → text fallback (strip tags)
        context = re.sub(r"<[^>]+>", " ", article.content_html)
        context = re.sub(r"\s+", " ", context).strip()
    context = context[:6000]

    system_prompt = (
        "You are an expert reading assistant. The user is reading the article below and asks you questions about it.\n\n"
        "Guidelines:\n"
        "- Answer using ONLY information present in the article — never invent or assume anything.\n"
        "- Detect the language of the user's question and reply in that exact language.\n"
        "- Respond in the most natural way for the question: flowing prose for open questions, "
        "a list only when the question genuinely calls for enumeration, a direct quote when the user "
        "wants a specific passage. Let the question shape the format — never impose one.\n"
        "- Be concise and direct. No greetings, no filler, no meta-commentary.\n"
        "- Use Markdown sparingly: **bold** for key terms, > for quoting the article directly.\n"
        "- If the information is not in the article, say so in one sentence without speculating.\n\n"
        f"Article — {article.title}\n\n{context}"
    )

    async def generate():
        async with _ask_semaphore:
            kind, url, api_key, model = resolve_provider()
            try:
                if kind == "openai":
                    headers = {"Content-Type": "application/json"}
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    async with httpx.AsyncClient(timeout=60) as client:
                        async with client.stream(
                            "POST",
                            url,
                            headers=headers,
                            json={
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": body.question},
                                ],
                                "stream": True,
                                "max_tokens": 1024,
                                "temperature": 0.3,
                            },
                        ) as resp:
                            async for line in resp.aiter_lines():
                                if not line.startswith("data: "):
                                    continue
                                data = line[6:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk["choices"][0]["delta"].get("content", "")
                                    if delta:
                                        yield f"data: {json.dumps({'text': delta})}\n\n"
                                except Exception:
                                    pass
                else:
                    # Ollama — streaming via /api/chat
                    async with httpx.AsyncClient(timeout=60) as client:
                        async with client.stream(
                            "POST",
                            f"{url}/api/chat",
                            json={
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": body.question},
                                ],
                                "stream": True,
                                "options": {"temperature": 0.3, "num_predict": 1024},
                            },
                        ) as resp:
                            async for line in resp.aiter_lines():
                                if not line.strip():
                                    continue
                                try:
                                    chunk = json.loads(line)
                                    delta = chunk.get("message", {}).get("content", "")
                                    if delta:
                                        yield f"data: {json.dumps({'text': delta})}\n\n"
                                    if chunk.get("done"):
                                        break
                                except Exception:
                                    pass
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Reading statistics
# ---------------------------------------------------------------------------

def _compute_streak(dates: List[str]) -> int:
    """Return current consecutive reading streak in days."""
    if not dates:
        return 0
    today = datetime.now(timezone.utc).date()
    unique = sorted(
        {datetime.strptime(d, "%Y-%m-%d").date() for d in dates if d},
        reverse=True,
    )
    if not unique:
        return 0
    # Streak must start from today or yesterday
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


@app.get("/api/stats", response_model=StatsOut)
async def get_stats(db: Session = Depends(get_db), _: None = _auth):
    # Basic counts
    total_read = db.query(Article).filter(Article.read_at.isnot(None)).count()
    total_unread = db.query(Article).filter(Article.read_at.is_(None)).count()
    total_bookmarked = db.query(Article).filter(Article.bookmarked == True).count()

    # Streak: get all distinct read dates
    date_rows = (
        db.query(func.strftime("%Y-%m-%d", Article.read_at).label("d"))
        .filter(Article.read_at.isnot(None))
        .distinct()
        .all()
    )
    all_dates = [row.d for row in date_rows if row.d]
    streak_days = _compute_streak(all_dates)

    # Daily read counts — last 30 days
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

    # Average score of read articles
    avg_row = (
        db.query(func.avg(Article.score))
        .filter(Article.read_at.isnot(None), Article.score.isnot(None))
        .scalar()
    )
    avg_score_read = round(float(avg_row), 2) if avg_row is not None else None

    # Top tags from read articles (last 2000 to cap memory usage)
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

    # Highlights count (graceful if table missing)
    try:
        total_highlights = db.query(Highlight).count()
    except Exception:
        total_highlights = 0

    # Articles per category (read articles only)
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
    article.score_details_json = json.dumps(score_data.score_details)
    article.tags_json = json.dumps(score_data.tags)
    article.summary_bullets_json = json.dumps(score_data.summary_bullets)
    article.reason = score_data.reason
    article.scoring_status = "done"
    article.next_score_attempt_at = None
    article.score_last_error = None
    article.score_locked_at = None
    article.scored_at = datetime.now(timezone.utc)
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
        "score_details": json.loads(article.score_details_json or "{}"),
        "tags": json.loads(article.tags_json or "[]"),
        "summary_bullets": json.loads(article.summary_bullets_json or "[]"),
        "reason": article.reason,
        "read_at": article.read_at.isoformat() if article.read_at else None,
        "bookmarked": article.bookmarked,
        "extraction_failed": article.extraction_failed,
        "created_at": article.created_at.isoformat(),
        "feed_name": feed.name if feed else "",
        "feed_category": feed.category if feed else "",
        "user_feedback": article.user_feedback,
        "reading_time": article.reading_time,
        "scoring_status": article.scoring_status,
        "score_attempts": article.score_attempts,
        "scored_at": article.scored_at.isoformat() if article.scored_at else None,
    }
    await _broadcast_new_article(article_dict)

    return {"status": "ok"}
