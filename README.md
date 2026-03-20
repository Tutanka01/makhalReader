<div align="center">

# ◉ MakhalReader

**An RSS reader that thinks before you do.**

*Built for engineers who have more to read than time to read it.*

---

[![Made with FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React%2018-61DAFB?style=flat-square&logo=react)](https://react.dev)
[![Docker](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED?style=flat-square&logo=docker)](https://docs.docker.com/compose/)
[![PWA](https://img.shields.io/badge/PWA-Offline%20Ready-5A0FC8?style=flat-square&logo=pwa)](https://web.dev/progressive-web-apps/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20WAL-003B57?style=flat-square&logo=sqlite)](https://sqlite.org)

</div>

---

## The problem

Classic RSS readers show **everything** — the throwaway blog post and the Cloudflare incident post-mortem sit side by side. You end up spending more time triaging than actually reading.

MakhalReader fixes that. Every article is **scored by an LLM before you ever open it.**

---

## How it works

```
RSS Feeds  →  Full-text    →  LLM Score (0–10)  →  Clean Reader
  32+          extraction      Gemini / Ollama       no clutter
 sources      trafilatura      tags · summary        no ads
```

By the time you open the app, the noise is already gone.

---

## One command to run

```bash
# 1. Configure your environment
cp .env.example .env
# → Set OPENROUTER_API_KEY (or leave blank to run fully local with Ollama)

# 2. Launch
docker compose up -d
```

App is live at **http://localhost**. That's it.

> No dependencies to install. No database to provision. No migrations to run.

---

## What actually matters

### LLM scoring — personalized, not generic

Every article gets a **score from 0 to 10** calibrated against a hardcoded technical profile
(Kubernetes internals, eBPF, LLM inference, CTF, homelab, post-mortems...).
The scorer knows the difference between a production incident retrospective and another
"10 tips to become a senior developer" listicle.

```
0–2  ·  Noise         →  Never shown
3–5  ·  Decent        →  Available if you look for it
6–7  ·  Good          →  Near the top
8–10 ·  Exceptional   →  Daily Digest
```

Auto-generated tags · bullet-point summaries · one-line score rationale — all visible in the UI.

**The scorer learns from your feedback.** 👍/👎 on any article updates a structured preference
profile built from tag-frequency aggregation across your full interaction history
(not just recent titles). Every subsequent score pulls from that profile —
capped at ~220 tokens, contrastive by design, grounded in research
(LLM-Rec / NAACL 2024: +15–22% ranking accuracy vs. raw title lists).

---

### Daily Digest

The **Digest** tab surfaces the best articles from the last 24–48h, tiered by score:

```
🔥 Exceptional  ·  score ≥ 9
⭐ Top           ·  score ≥ 7
👍 Good          ·  score ≥ 5
```

Your morning technical briefing, already curated.

---

### 3-layer deduplication

The same article routinely appears across Hacker News, Lobsters, and several aggregators.
MakhalReader stores it exactly once:

1. **Canonical URL** — normalized (tracking params stripped, `www.` removed, trailing slash unified)
2. **Title fingerprint** — catches syndicated content with different URLs
3. **`<link rel="canonical">`** — the source of truth wins

---

### Built for the iPad (and keyboard warriors)

The UI is **reader-first**: two-column layout on iPad and desktop, full-screen on mobile.
Every interaction that should be fast is fast.

- Virtualized sidebar with infinite scroll
- Clean reader, adjustable font (14–22px, persisted)
- Reading progress bar
- Swipe left → mark read · Swipe right → bookmark
- Native dark theme
- Full keyboard navigation

```
j / k   →  next / previous article
r       →  toggle read / unread
b       →  bookmark
o       →  open original
/       →  search
[       →  toggle sidebar
?       →  help
```

---

### Real-time via SSE

New articles appear **without a page reload** via Server-Sent Events.
The moment a score lands, the article surfaces at the top of the list — live.

---

### PWA — reads offline too

MakhalReader installs as a native app on iPad and iPhone.
Articles you've opened are cached — accessible without a network connection.

---

### 32 pre-configured feeds

Ships with a high-signal technical feed selection, ready to use on day one:

| Category | Sources |
|----------|---------|
| **Infra / Cloud** | Kubernetes Blog, CNCF, Cloudflare, Netflix TechBlog, LWN.net, fasterthanli.me, Fly.io, iximiuz, Tailscale… |
| **AI / LLM** | Anthropic, HuggingFace, Lilian Weng, Sebastian Raschka, Chip Huyen… |
| **Security** | Google Project Zero, PortSwigger, Trail of Bits, lcamtuf, secret.club… |
| **High-signal** | Hacker News, Lobsters, Simon Willison, Julia Evans, Dan Luu… |

Add custom feeds, import **OPML** (Feedly, NewsBlur…), organize by category.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Caddy (proxy / TLS)               │
└──────────────┬──────────────────────┬───────────────┘
               │                      │
        ┌──────▼──────┐        ┌──────▼──────┐
        │   Frontend   │        │     API      │
        │  React + Vite│        │   FastAPI    │
        │     (PWA)    │        │   SQLite     │
        └─────────────┘        └──────┬───────┘
                                      │
              ┌───────────────────────┼───────────────────┐
              │                       │                   │
       ┌──────▼──────┐        ┌───────▼──────┐   ┌───────▼──────┐
       │   Poller     │        │  Extractor   │   │    Scorer    │
       │  feedparser  │        │ trafilatura  │   │  Gemini via  │
       │  APScheduler │        │ readability  │   │  OpenRouter  │
       └─────────────┘        └─────────────┘   └─────────────┘
```

6 Docker containers · 1 internal network · 0 mandatory external dependencies

---

## Configuration

```bash
# .env — the only variables that matter

OPENROUTER_API_KEY=sk-or-v1-...            # LLM scoring (free tier available)
SCORER_MODEL=google/gemini-2.5-flash-lite  # Model used for scoring

# Optional: local Ollama fallback (no API key required)
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=mistral

# Polling frequency
FETCH_INTERVAL_MINUTES=15

# Anti-flood guardrails
MAX_NEW_ARTICLES_PER_FEED=5
MAX_ARTICLE_AGE_DAYS=7

# Production
CADDY_DOMAIN=reader.yourdomain.com    # Enables automatic HTTPS via Let's Encrypt
```

---

## Production deployment

```bash
# On your server
git clone <repo> && cd makhalReader
cp .env.example .env && vim .env   # Set CADDY_DOMAIN + OPENROUTER_API_KEY

docker compose up -d
```

Caddy handles TLS automatically. Nothing else to configure.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS · Zustand |
| Backend | Python 3.12 · FastAPI · SQLAlchemy · SQLite WAL |
| Extraction | trafilatura · readability · BeautifulSoup |
| Scoring | OpenRouter API (Gemini) · Ollama (Mistral) |
| Infrastructure | Docker Compose · Caddy · APScheduler · httpx async |
| PWA | Workbox · vite-plugin-pwa · Service Workers |

---

<div align="center">

*Read less. Understand more.*

</div>
