<div align="center">

# بَصِيرَة — Baṣīra

**Research-oriented intelligent reading and literature monitor.**

*Scores what matters. Surfaces what you'd have missed. Synthesizes the state of the art.*

---

[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20Python%203.12-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite-61DAFB?style=flat-square&logo=react)](https://react.dev)
[![Docker](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED?style=flat-square&logo=docker)](https://docs.docker.com/compose/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20WAL-003B57?style=flat-square&logo=sqlite)](https://sqlite.org)
[![PWA](https://img.shields.io/badge/PWA-Offline%20Ready-5A0FC8?style=flat-square&logo=pwa)](https://web.dev/progressive-web-apps/)

</div>

---

## What it is

**Baṣīra** (بَصِيرَة — Arabic for *deep insight*, *discernment*) is a self-hosted RSS reader built for PhD-level research monitoring. It was designed for a specific dual use case: continuous literature surveillance and daily DevOps/infra reading.

Every article is scored, tagged, and summarized before you open it. Research papers are enriched with Semantic Scholar metadata — contribution type, RE document type, novelty, rigor — and separated from blog posts at the data layer. When you want to understand a research area, the State of the Art search queries Semantic Scholar and OpenAlex directly, reranks by citation weight and recency, and synthesizes an LLM-generated literature review with a comparison table of the top 5 papers and identified research gaps.

The system runs entirely on your own hardware; nothing leaves the machine unless you configure OpenRouter.

---

## How it works

```
RSS / arXiv / Semantic Scholar feeds
        │
        ▼
    Poller (APScheduler · every 6h)
        │  fetch + 3-layer deduplication
        ▼
    Extractor (trafilatura / readability)
        │  full-text + Semantic Scholar paper metadata
        ▼
    Scorer (LLM — three-tier routing)
        │  score 0–10 · tags · summary · contribution_type · rigor · novelty
        ▼
    Embedder (nomic-embed-text via Ollama)
        │  ChromaDB vector index for semantic search
        ▼
    API + SQLite  ──SSE──►  React frontend (real-time)
                                │
                    ┌───────────┴───────────┐
                    │                       │
          In-corpus lit review       State-of-the-art search
          (semantic search over      (Semantic Scholar + OpenAlex
           your reading history)      → rerank → LLM synthesis)
```

---

## Quick start

```bash
# 1. Copy and configure your environment
cp .env.example .env
# → Set AUTH_PASSWORD (required)
# → Set OPENROUTER_API_KEY (optional — Ollama works without it)
# → Set OLLAMA_MODEL to a model you have pulled locally

# 2. Pull the embedding model
ollama pull nomic-embed-text

# 3. Launch
docker compose up -d --build
```

App is live at **http://localhost**. No database to provision. No migrations to run.

---

## Scoring

The rubric is a Markdown file selected at runtime via `PROMPT_PROFILE`:

| Profile | Use case |
|---------|----------|
| `infra` | DevOps/platform engineering only |
| `research` | PhD literature monitoring — rewards surveys, methods, benchmarks, theory |
| `unified` | **Default.** Dual-mode — scores both infra posts and research papers correctly |

Switch by setting `PROMPT_PROFILE=research` in your `.env`. No rebuild needed — prompt files are volume-mounted.

The scorer returns a multi-dimensional result:

```
score                0–10 scalar
tags                 1–5 technical tags
summary_bullets      2–3 sentence summary
reason               one-line score rationale
contribution_type    method | benchmark | survey | empirical | theory | position | tool | …
re_document_type     elicitation | extraction | method | none   (ARISE pipeline signal)
novelty              0–1 float
rigor                0–1 float
relevance_to_topics  0–1 float
```

---

## Scoring tiers

```
8–10  ·  Exceptional   →  Daily Digest · top of the list
6–7   ·  Good          →  Worth reading when time allows
4–5   ·  Decent        →  Available on scroll
0–3   ·  Noise         →  Filtered out by default
```

**Feedback loop:** 👍/👎 on any article updates a structured preference profile built from tag-frequency aggregation across your full history. Every subsequent score pulls from that profile (LLM-Rec / NAACL 2024 approach: +15–22% ranking accuracy vs. raw title lists).

---

## Literature review

### In corpus

Embeds your topic query, retrieves the most semantically similar articles from your reading history via ChromaDB, clusters them with HDBSCAN, and synthesizes a per-cluster LLM analysis. Best for synthesizing what you've already read.

### State of the art (external search)

Queries **Semantic Scholar** and **OpenAlex** (free, no scraping, no ToS issues) directly, reranks results by a blend of search relevance (40%), citation count (35%), and recency (25%), then synthesizes a structured state-of-the-art review:

- **Synthesis** — 2–3 paragraphs on research streams, methods, and evolution
- **Relevance to thesis** — how this body of work connects to AI-driven MBSE/CPS
- **Comparison table** — top 5 papers by work, method, dataset, key result
- **Research gaps** — open problems targeted at AI-driven SE integration
- **Paper corpus** — full list with citation count, venue, abstract excerpt, direct link
- **Export to Markdown** — one-click `.md` download for your thesis notes

Fallback chain: Semantic Scholar → OpenAlex → merged results when either source is thin.

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
          ┌───────────────────────────────┼───────────────────────┐
          │                               │                       │
   ┌──────▼──────┐                ┌───────▼──────┐       ┌───────▼──────┐
   │   Poller     │                │  Extractor   │       │    Scorer    │
   │  feedparser  │                │ trafilatura  │       │  Uni GPU /   │
   │  APScheduler │                │ readability  │       │  Ollama /    │
   └─────────────┘                │ SS metadata  │       │ OpenRouter   │
                                  └─────────────┘       └─────────────┘
```

6 Docker services · 1 internal network (`basira-net`) · SQLite on a Docker volume · ChromaDB in-process (`/data/chroma`) · 0 mandatory external dependencies

---

## Configuration reference

All configuration lives in `.env` (copied from `.env.example`):

```bash
# ── LLM ─────────────────────────────────────────────────────
OPENROUTER_API_KEY=           # Optional cloud fallback
SCORER_MODEL=google/gemini-2.5-flash-lite

OLLAMA_URL=http://host.docker.internal:11434   # macOS / Linux
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text            # Required for semantic search + lit review

UNI_OLLAMA_URL=https://llm.example.univ.fr/v1  # University GPU — VPN required
UNI_OLLAMA_MODEL=                              # e.g. gemma-4-31b-it-q8_0
UNI_OLLAMA_API_KEY=                            # Bearer token for university API

# ── Scoring ──────────────────────────────────────────────────
PROMPT_PROFILE=unified         # infra | research | unified
SCORER_MAX_CHARS=6000          # Auto-doubled for confirmed papers (max 12 000)

# ── External literature search ────────────────────────────────
SS_API_KEY=                    # Optional — raises SS rate limit from 1 to 10 req/s
# OA_CONTACT_EMAIL=            # Optional — identifies you in OpenAlex polite pool

# ── App ──────────────────────────────────────────────────────
DB_PATH=/data/basira.db
FETCH_INTERVAL_MINUTES=360
API_SECRET=<random>

# ── Auth ─────────────────────────────────────────────────────
AUTH_PASSWORD=<strong password>
HTTPS_ONLY=false               # true in production
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

### Content pipeline
- 3-layer deduplication: canonical URL · title fingerprint · `<link rel="canonical">`
- Full-text extraction (not RSS summaries) via trafilatura + readability
- Semantic Scholar enrichment for arXiv / ACL / DOI papers (abstract, authors, year, fields)
- OPML import (Feedly, NewsBlur, …)

### Research tools
- **Highlights** — color labels and notes, persistent across sessions
- **Ask-AI** — stream an answer about the article you're reading
- **Daily Digest** — top articles from the last 24–72 h, tiered by score (≥5 threshold)
- **Semantic search** — find related articles by embedding similarity (nomic-embed-text)
- **Topic clusters** — HDBSCAN clustering of your embedded reading history
- **Researcher profile** — topic/method/domain preference store, auto-updated from feedback
- **In-corpus lit review** — semantic retrieval → cluster → per-cluster LLM synthesis → export
- **State-of-the-art search** — Semantic Scholar + OpenAlex → reranked paper corpus → LLM synthesis → comparison table → research gaps → Markdown export
- **ARISE export** — structured JSON export of RE-tagged papers for downstream pipelines

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
| Embeddings | nomic-embed-text via Ollama · ChromaDB (in-process, persistent) |
| Scoring | Multi-tier: University GPU (OpenAI-compatible) → Ollama (local) → OpenRouter |
| Lit review | HDBSCAN clustering · Semantic Scholar API · OpenAlex API |
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

## Maintenance notes

- **Conference deadlines** — update `backend/api/conferences.py` each September when venues announce new cycles
- **Scoring prompts** — files in `backend/scorer/prompts/` are volume-mounted; edit without rebuilding
- **Embedding model** — `ollama pull nomic-embed-text` required on the host running Ollama

---

<div align="center">

*بَصِيرَة — deep insight*

</div>
