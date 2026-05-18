<div align="center">

# بَصِيرَة — Baṣīra

**Research-oriented intelligent reading and literature monitor.**

*Scores what matters. Surfaces what you'd have missed.*

---

[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20Python%203.12-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite-61DAFB?style=flat-square&logo=react)](https://react.dev)
[![Docker](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED?style=flat-square&logo=docker)](https://docs.docker.com/compose/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20WAL-003B57?style=flat-square&logo=sqlite)](https://sqlite.org)
[![PWA](https://img.shields.io/badge/PWA-Offline%20Ready-5A0FC8?style=flat-square&logo=pwa)](https://web.dev/progressive-web-apps/)

</div>

---

## What it is

**Baṣīra** (بَصِيرَة — Arabic for *deep insight*, *discernment*) is a self-hosted RSS reader augmented with a multi-tier LLM pipeline. It was built for a dual use case: daily DevOps/infra reading and continuous PhD-level literature monitoring.

Every article is scored, tagged, and summarized before you open it. Research papers are enriched with metadata — contribution type, RE document type, novelty, rigor — and separated from blog posts at the data layer. The system runs entirely on your own hardware; nothing leaves the machine unless you configure OpenRouter.

---

## How it works

```
RSS / arXiv / Semantic Scholar
        │
        ▼
    Poller (APScheduler)
        │  fetch + deduplicate
        ▼
    Extractor (trafilatura / readability)
        │  full-text + paper metadata
        ▼
    Scorer (LLM — three-tier routing)
        │  score 0–10 · tags · summary · contribution_type · re_document_type
        ▼
    API + SQLite  ──SSE──►  React frontend (real-time)
```

**Three-tier LLM routing** (in priority order):

| Tier | Backend | When used |
|------|---------|-----------|
| 1 | Local Ollama (M5 Max, 36 GB) | Always available, free, private |
| 2 | University GPU server (VPN) | Heavier inference — synthesis, lit-review |
| 3 | OpenRouter (Gemini / Claude) | Cloud fallback, optional |

---

## Quick start

```bash
# 1. Copy and configure your environment
cp .env.example .env
# → Set AUTH_PASSWORD (required)
# → Set OPENROUTER_API_KEY (optional — Ollama works without it)
# → Set OLLAMA_MODEL to a model you have pulled

# 2. Launch
docker compose up -d --build
```

App is live at **http://localhost**. No database to provision. No migrations to run.

---

## Scoring profiles

The rubric is a Markdown file selected at runtime via `PROMPT_PROFILE`:

| Profile | Use case |
|---------|----------|
| `infra` | DevOps/platform engineering only (original behavior) |
| `research` | PhD literature monitoring — rewards surveys, methods, benchmarks, theory |
| `unified` | **Default.** Dual-mode — scores both infra posts and research papers correctly |

Switch by setting `PROMPT_PROFILE=research` in your `.env`. No rebuild needed.

The scorer returns a multi-dimensional result:

```
score            0–10 scalar
tags             1–5 technical tags
summary_bullets  2–3 sentence summary
reason           one-line score rationale
contribution_type  method | benchmark | survey | empirical | theory | position | tool | …
re_document_type   elicitation | extraction | method | none   ← ARISE pipeline signal
novelty          0–1 float (research only)
rigor            0–1 float (research only)
relevance_to_topics  0–1 float (research only)
```

---

## Scoring tiers

```
8–10  ·  Exceptional   →  Daily Digest · top of the list
6–7   ·  Good          →  Worth reading when time allows
4–5   ·  Decent        →  Available on scroll
0–3   ·  Noise         →  Filtered out by default
```

**Feedback loop:** 👍/👎 on any article updates a structured preference profile built from tag-frequency aggregation across your full history. Every subsequent score pulls from that profile. Based on LLM-Rec / NAACL 2024: +15–22% ranking accuracy vs. raw title lists.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Caddy (reverse proxy / TLS)             │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
        ┌──────▼──────┐            ┌──────▼──────┐
        │   Frontend   │            │     API      │
        │  React + Vite│            │   FastAPI    │
        │  TypeScript  │            │  SQLite WAL  │
        │    (PWA)     │            │  routers/*   │
        └─────────────┘            └──────┬───────┘
                                          │
              ┌───────────────────────────┼──────────────────────┐
              │                           │                      │
       ┌──────▼──────┐            ┌───────▼──────┐      ┌───────▼──────┐
       │   Poller     │            │  Extractor   │      │    Scorer    │
       │  feedparser  │            │ trafilatura  │      │  Ollama /    │
       │  APScheduler │            │ readability  │      │ Uni server / │
       └─────────────┘            └─────────────┘      │ OpenRouter   │
                                                        └─────────────┘
```

6 Docker services · 1 internal network (`basira-net`) · SQLite on a Docker volume · 0 mandatory external dependencies

---

## Configuration reference

All configuration lives in `.env` (copied from `.env.example`):

```bash
# ── LLM ─────────────────────────────────────────────────────
OPENROUTER_API_KEY=        # Optional cloud fallback
SCORER_MODEL=google/gemini-2.5-flash-lite

OLLAMA_URL=http://host.docker.internal:11434   # macOS
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text            # For semantic search (Story 3+)

UNI_OLLAMA_URL=https://llm.eva.univ-pau.fr/v1  # University GPU — VPN required
UNI_OLLAMA_MODEL=                              # Set after: curl $UNI_OLLAMA_URL/models

# ── Scoring ──────────────────────────────────────────────────
PROMPT_PROFILE=unified    # infra | research | unified
SCORER_MAX_CHARS=6000     # Auto-doubled for confirmed papers (max 12 000)

# ── App ──────────────────────────────────────────────────────
DB_PATH=/data/basira.db
FETCH_INTERVAL_MINUTES=360
API_SECRET=<random>

# ── Auth ─────────────────────────────────────────────────────
AUTH_PASSWORD=<strong password>
HTTPS_ONLY=false          # true in production
CORS_ORIGIN=http://localhost

# ── Production ───────────────────────────────────────────────
CADDY_DOMAIN=reader.yourdomain.com   # Activates automatic HTTPS
```

---

## Features

### Reader
- 3-pane responsive layout (Sidebar, Topbar, Content) on desktop/iPad, SlidePanel on mobile
- Reading progress bar · adjustable font (14–22 px, persisted)
- Swipe left → mark read · Swipe right → bookmark
- Native dark theme (ProjectOS Design System) · PWA — installable, works offline
- Real-time article delivery via Server-Sent Events (no refresh needed)

### Keyboard shortcuts
```
j / k   →  next / previous article
r       →  toggle read / unread
b       →  bookmark
o       →  open original
/       →  search
[       →  toggle sidebar
?       →  help
```

### Content
- 3-layer deduplication: canonical URL · title fingerprint · `<link rel="canonical">`
- Full-text extraction (not RSS summaries) via trafilatura + readability
- OPML import (Feedly, NewsBlur, …)
- Highlights with color labels and notes
- Ask-AI: stream an answer about the article you're reading
- Daily Digest: top articles from the last 24–48 h, tiered by score

---

## Feed categories

Ships with a curated selection of high-signal feeds:

| Category | Sources |
|----------|---------|
| **Infra / Cloud** | Kubernetes Blog, CNCF, Cloudflare, Netflix TechBlog, LWN.net, Fly.io, Tailscale… |
| **AI / LLM** | Anthropic, HuggingFace, Lilian Weng, Sebastian Raschka, Chip Huyen… |
| **Security** | Google Project Zero, PortSwigger, Trail of Bits, lcamtuf, secret.club… |
| **High-signal** | Hacker News, Lobsters, Simon Willison, Julia Evans, Dan Luu… |
| **Research** | arXiv cs.SE, arXiv cs.AI, Semantic Scholar (RE, MBSE topics) |

---

## Tech stack

| Layer | Technologies |
|-------|-------------|
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS (ProjectOS UI) · Zustand · PWA |
| API | Python 3.12 · FastAPI · SQLAlchemy · SQLite WAL · structlog |
| Extraction | trafilatura · readability · BeautifulSoup · httpx async |
| Scoring | Multi-tier: Ollama (local) → University GPU → OpenRouter |
| Infrastructure | Docker Compose · Caddy · APScheduler · tenacity |

---

## Production deployment

```bash
git clone <repo> && cd daily_news_wrap
cp .env.example .env
# Edit .env: set CADDY_DOMAIN, AUTH_PASSWORD, OPENROUTER_API_KEY
# Set HTTPS_ONLY=true

docker compose up -d --build
```

Caddy provisions TLS automatically via Let's Encrypt. Nothing else to configure.

---

<div align="center">

*بَصِيرَة — deep insight · discernment*

</div>
