import asyncio
import json
import os
from typing import AsyncGenerator

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from auth import purge_expired_sessions, require_session
from database import Feed, ResearchProfile, SessionLocal, init_db
from routers import (
    articles,
    auth,
    discovery,
    feeds,
    highlights,
    ask,
    stats,
    admin,
    internal,
    profile,
    research,
    onboarding,
    poll,
    sources,
)
from routers.profile import templates_router
from routers.internal import cleanup_old_articles
from scheduler import start_scheduler, stop_scheduler
from sse import _sse_queues, broadcast_new_article

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger().bind(service="api")

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_cors_origin = os.getenv("CORS_ORIGIN", "")
_cors_origins = [_cors_origin] if _cors_origin else []

app = FastAPI(title="Baṣīra API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Internal-Secret"],
)

app.include_router(auth.router)
app.include_router(articles.router)
app.include_router(feeds.router)
app.include_router(highlights.router)
app.include_router(ask.router)
app.include_router(stats.router)
app.include_router(admin.router)
app.include_router(internal.router)
app.include_router(profile.router)
app.include_router(research.router)
app.include_router(onboarding.router)
app.include_router(poll.router)
app.include_router(sources.router)
app.include_router(discovery.router)
app.include_router(templates_router)

# ---------------------------------------------------------------------------
# Default feeds seeded at startup
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Research profile taxonomy — seeded once at first startup (table empty)
# Weights encode tier priority: 5.0=Tier1 critical → 1.0=avoid
# ---------------------------------------------------------------------------

_SEED_PROFILE: list[dict] = [
    # ── Tier 1 — Core Thesis (weight 5.0) ───────────────────────────────────
    {"kind": "topic", "label": "AI-driven MBSE",                            "weight": 5.0},
    {"kind": "topic", "label": "Cyber-Physical Systems engineering",         "weight": 5.0},
    {"kind": "topic", "label": "Digital Twin construction and synchronization","weight": 5.0},
    {"kind": "topic", "label": "Engineering blueprint",                      "weight": 5.0},
    {"kind": "topic", "label": "AI-assisted system modeling",                "weight": 5.0},
    {"kind": "topic", "label": "Lifecycle-aware system modeling",            "weight": 5.0},
    {"kind": "topic", "label": "Engineering knowledge synthesis",            "weight": 5.0},
    {"kind": "topic", "label": "MBSE + AI integration",                     "weight": 5.0},
    # ── Tier 2 — Modeling & Representation (weight 3.5) ─────────────────────
    {"kind": "topic", "label": "Multi-view modeling",                       "weight": 3.5},
    {"kind": "topic", "label": "System architecture modeling",               "weight": 3.5},
    {"kind": "topic", "label": "Semantic modeling",                         "weight": 3.5},
    {"kind": "topic", "label": "Model consistency",                         "weight": 3.5},
    {"kind": "topic", "label": "Model transformation",                      "weight": 3.5},
    {"kind": "topic", "label": "Model synchronization",                     "weight": 3.5},
    {"kind": "topic", "label": "Model traceability",                        "weight": 3.5},
    {"kind": "topic", "label": "Model-driven engineering",                  "weight": 3.5},
    {"kind": "topic", "label": "Metamodeling",                              "weight": 3.5},
    {"kind": "topic", "label": "Ontology engineering",                      "weight": 3.5},
    {"kind": "topic", "label": "Semantic interoperability",                 "weight": 3.5},
    {"kind": "topic", "label": "Model quality",                             "weight": 3.5},
    # ── Tier 3 — Requirements Engineering (weight 3.5) ──────────────────────
    {"kind": "topic", "label": "Requirements Engineering",                  "weight": 3.5},
    {"kind": "topic", "label": "NLP-based requirements elicitation",        "weight": 3.5},
    {"kind": "topic", "label": "Requirements traceability",                 "weight": 3.5},
    {"kind": "topic", "label": "Requirements formalization",                "weight": 3.5},
    {"kind": "topic", "label": "Requirements quality",                      "weight": 3.5},
    {"kind": "topic", "label": "Requirements-to-model traceability",        "weight": 3.5},
    {"kind": "topic", "label": "Digital thread",                            "weight": 3.5},
    # ── Tier 4 — Knowledge & Reasoning (weight 3.0) ─────────────────────────
    {"kind": "topic", "label": "Knowledge graphs for engineering",          "weight": 3.0},
    {"kind": "topic", "label": "GraphRAG for systems or requirements",      "weight": 3.0},
    {"kind": "topic", "label": "Semantic retrieval over engineering artifacts","weight": 3.0},
    {"kind": "topic", "label": "Knowledge-grounded generation",             "weight": 3.0},
    {"kind": "topic", "label": "Engineering reasoning",                     "weight": 3.0},
    {"kind": "topic", "label": "Traceability graphs",                       "weight": 3.0},
    {"kind": "topic", "label": "Knowledge extraction from engineering documents","weight": 3.0},
    {"kind": "topic", "label": "Ontology-enhanced AI",                     "weight": 3.0},
    # ── Tier 5 — LLMs & Agents applied to engineering (weight 2.0) ──────────
    {"kind": "topic", "label": "LLM for engineering or modeling",           "weight": 2.0},
    {"kind": "topic", "label": "Multi-agent systems for MBSE",             "weight": 2.0},
    {"kind": "topic", "label": "RAG applied to system artifacts",           "weight": 2.0},
    {"kind": "topic", "label": "Structured generation for engineering",     "weight": 2.0},
    {"kind": "topic", "label": "Hallucination mitigation in technical generation","weight": 2.0},
    {"kind": "topic", "label": "Trustworthy LLM for safety-critical systems","weight": 2.0},
    # ── Tier 6 — Runtime & Synchronization (weight 3.5) ─────────────────────
    {"kind": "topic", "label": "Continuous model synchronization",          "weight": 3.5},
    {"kind": "topic", "label": "Runtime model alignment",                   "weight": 3.5},
    {"kind": "topic", "label": "Model drift detection",                     "weight": 3.5},
    {"kind": "topic", "label": "Digital thread construction",               "weight": 3.5},
    {"kind": "topic", "label": "Change impact analysis",                    "weight": 3.5},
    {"kind": "topic", "label": "Adaptive digital twins",                    "weight": 3.5},
    {"kind": "topic", "label": "Runtime monitoring of CPS",                 "weight": 3.5},
    # ── Tier 7 — Verification, Trust & Certification (weight 3.0) ───────────
    {"kind": "topic", "label": "Explainable AI for engineering",            "weight": 3.0},
    {"kind": "topic", "label": "Trustworthy AI",                            "weight": 3.0},
    {"kind": "topic", "label": "Formal verification for CPS",               "weight": 3.0},
    {"kind": "topic", "label": "Assurance cases",                           "weight": 3.0},
    {"kind": "topic", "label": "Safety-critical AI",                        "weight": 3.0},
    {"kind": "topic", "label": "Certification-aware AI",                    "weight": 3.0},
    {"kind": "topic", "label": "Human-in-the-loop validation",              "weight": 3.0},
    # ── Tier 8 — Industrial Context (weight 1.5) ────────────────────────────
    {"kind": "topic", "label": "Industry 4.0 with MBSE",                   "weight": 1.5},
    {"kind": "topic", "label": "Industrial digital twins",                  "weight": 1.5},
    {"kind": "topic", "label": "Systems-of-systems engineering",            "weight": 1.5},
    {"kind": "topic", "label": "Embedded systems engineering",              "weight": 1.5},
    # ── Tier 9 — Evaluation & Benchmarks (weight 1.5) ───────────────────────
    {"kind": "topic", "label": "Benchmarks for engineering AI",             "weight": 1.5},
    {"kind": "topic", "label": "Evaluation frameworks for MBSE/RE AI",     "weight": 1.5},
    {"kind": "topic", "label": "Dataset construction for systems engineering","weight": 1.5},
    # ── Avoid (weight 1.0 — triggers score penalty) ──────────────────────────
    {"kind": "avoid", "label": "DevOps",                                    "weight": 1.0},
    {"kind": "avoid", "label": "Kubernetes",                                "weight": 1.0},
    {"kind": "avoid", "label": "Cloud infrastructure",                      "weight": 1.0},
    {"kind": "avoid", "label": "Cybersecurity (non-CPS)",                   "weight": 1.0},
    {"kind": "avoid", "label": "Consumer AI chatbots",                      "weight": 1.0},
    {"kind": "avoid", "label": "Vibe coding and productivity tools",        "weight": 1.0},
    {"kind": "avoid", "label": "Generic Python or JS tutorials",            "weight": 1.0},
    {"kind": "avoid", "label": "Marketing and startup announcements",       "weight": 1.0},
    {"kind": "avoid", "label": "Social and political news",                 "weight": 1.0},
]


def _seed_research_profile(db) -> None:
    """Populate the research_profile table from the 9-tier taxonomy.

    Idempotent: does nothing if any row already exists (first-run only).
    """
    from datetime import datetime, timezone
    count = db.query(ResearchProfile).count()
    if count > 0:
        return
    for entry in _SEED_PROFILE:
        db.add(ResearchProfile(
            kind=entry["kind"],
            label=entry["label"],
            weight=entry["weight"],
            source="seed",
            created_at=datetime.now(timezone.utc),
        ))
    db.commit()
    logger.info("research_profile_seeded", count=len(_SEED_PROFILE))


DEFAULT_FEEDS = [
    # ── ArXiv — Requirements Engineering & Software Engineering ──────────
    {"url": "https://export.arxiv.org/rss/cs.SE",                       "name": "arXiv cs.SE (RE/SE)",           "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.FL",                       "name": "arXiv cs.FL (Formal Methods)",  "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.PL",                       "name": "arXiv cs.PL (Prog. Languages)", "category": "Papers"},
    # ── ArXiv — Systems Engineering & Robotics (MBSE) ────────────────────
    {"url": "https://export.arxiv.org/rss/cs.RO",                       "name": "arXiv cs.RO (Robotics/MBSE)",   "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.SY",                       "name": "arXiv cs.SY (Systems Control)", "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/eess.SY",                     "name": "arXiv eess.SY (Eng. Systems)",  "category": "Papers"},
    # ── ArXiv — AI / NLP / Agents (pertinents pour RE) ───────────────────
    {"url": "https://export.arxiv.org/rss/cs.AI",                       "name": "arXiv cs.AI",                   "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.LG",                       "name": "arXiv cs.LG",                   "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.CL",                       "name": "arXiv cs.CL (NLP/LLM)",         "category": "Papers"},
    {"url": "https://export.arxiv.org/rss/cs.MA",                       "name": "arXiv cs.MA (Multi-Agent)",      "category": "Papers"},
    # ── Venues de recherche ───────────────────────────────────────────────
    {"url": "https://aclanthology.org/anthology+abstracts.rss",          "name": "ACL Anthology",                  "category": "Papers"},
    {"url": "https://openreview.net/rss",                                "name": "OpenReview",                     "category": "Papers"},
    # ── AI / LLM — blogs de recherche (orientés méthodes et résultats) ───
    {"url": "https://lilianweng.github.io/feed.xml",                     "name": "Lilian Weng (OpenAI)",           "category": "AI"},
    {"url": "https://bair.berkeley.edu/blog/feed.xml",                   "name": "BAIR Blog",                      "category": "AI"},
    {"url": "https://huyenchip.com/feed",                                "name": "Huyen Chip (ML Systems)",        "category": "AI"},
    {"url": "https://eugeneyan.com/rss.xml",                             "name": "Eugene Yan (Applied ML)",        "category": "AI"},
    {"url": "https://magazine.sebastianraschka.com/feed",                "name": "Sebastian Raschka (LLM/Research)","category": "AI"},
    {"url": "https://www.anthropic.com/news/rss.xml",                    "name": "Anthropic Research",             "category": "AI"},
    {"url": "https://huggingface.co/blog/feed.xml",                      "name": "HuggingFace Blog",               "category": "AI"},
    {"url": "https://timdettmers.com/feed/",                             "name": "Tim Dettmers (Quantization)",    "category": "AI"},
    # ── Software Architecture & Engineering (SE proche RE) ────────────────
    {"url": "https://martinfowler.com/feed.atom",                        "name": "Martin Fowler",                  "category": "SE"},
    {"url": "https://queue.acm.org/rss/feeds/queuecontent.xml",          "name": "ACM Queue",                      "category": "SE"},
    {"url": "https://cacm.acm.org/browse-by-subject/rss/software-engineering","name": "CACM Software Engineering", "category": "SE"},
    # ── High-signal généraliste ───────────────────────────────────────────
    {"url": "https://simonwillison.net/atom/everything/",                "name": "Simon Willison",                 "category": "High-signal"},
    {"url": "https://news.ycombinator.com/rss",                          "name": "Hacker News",                    "category": "High-signal"},
    {"url": "https://www.deeplearning.ai/the-batch/feed/rss/",           "name": "The Batch (Andrew Ng)",          "category": "High-signal"},
]

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    init_db()
    # ChromaDB per-user migration (Story 7.4) — no-op if already migrated
    from embedder import _migrate_chroma_articles_to_per_user  # noqa: PLC0415
    _migrate_chroma_articles_to_per_user()
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
            logger.info("startup_feeds_added", count=added)
    finally:
        db.close()
    start_scheduler()


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()


# ---------------------------------------------------------------------------
# Health check — public (no auth, used by Docker and Caddy)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# SSE stream — protected
# ---------------------------------------------------------------------------

_auth = Depends(require_session)


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
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass


@app.get("/api/stream")
async def sse_stream(request: Request, current_user: dict = _auth):
    user_id = current_user["id"]
    client_id = str(id(request))
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_queues.setdefault(user_id, {})[client_id] = queue

    async def cleanup_generator():
        try:
            async for chunk in _sse_event_generator(request, queue):
                yield chunk
        finally:
            user_queues = _sse_queues.get(user_id)
            if user_queues:
                user_queues.pop(client_id, None)
                if not user_queues:
                    _sse_queues.pop(user_id, None)

    return StreamingResponse(
        cleanup_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
