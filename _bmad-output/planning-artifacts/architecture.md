---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - "_bmad-output/planning-artifacts/product-brief-daily_news_wrap.md"
  - "_bmad-output/planning-artifacts/product-brief-daily_news_wrap-distillate.md"
  - "_bmad-output/planning-artifacts/prd.md"
  - "Session BMAD Brief + Repository Analysis (prior turn)"
  - "backend/api/database.py"
  - "backend/api/main.py"
  - "backend/api/models.py"
  - "backend/scorer/scorer.py"
  - "backend/scorer/prompt.py"
  - "backend/extractor/extractor.py"
  - "backend/poller/main.py"
  - "docker-compose.yml"
  - "frontend/src/types.ts"
  - "frontend/src/App.tsx"
workflowType: 'architecture'
project_name: 'daily_news_wrap'
user_name: 'Arona'
date: '2026-04-22'
architect: 'Winston'
---

# Architecture Decision Document
# Baṣīra — Research-Oriented Intelligent Literature Monitor

**Architect:** Winston (via bmad-agent-architect)  
**Date:** 2026-04-22  
**Status:** Complete v1.0  
**Type:** Brownfield augmentation — additive-only, no rewrite  

---

## Project Context Analysis

### Requirements Overview

**Functional Requirements — Architectural Read:**

The 30 FRs from the PRD organize into 6 capability areas, each mapping to a distinct layer:

| FR Group | FRs | Architectural Layer |
|---|---|---|
| Article Ingestion & Enrichment | FR1–FR6 | extractor service + poller service |
| Scoring & Ranking | FR7–FR11 | scorer service + api (article list) |
| Semantic Retrieval & Clustering | FR12–FR16 | embedder (new, in api) + api/routers/research.py |
| Researcher Profile | FR17–FR21 | api/routers/research.py + new DB table |
| Literature-Review Mode | FR22–FR27 | api/routers/research.py + frontend LitReviewView |
| ARISE Export & Admin | FR28–FR30 | api/routers/research.py + api/routers/admin.py |

The FRs imply no new external services beyond what already exists in the Docker Compose topology for MVP Stories 1–3. Stories 4–6 add a background task (embedder) and ChromaDB file store, but no new containers.

**Non-Functional Requirements — Architectural Drivers:**

- **NFR1–NFR4 (Performance):** Article ingest p50 ≤ 3 min; embedding ≤ 500ms; related-paper API ≤ 2s; lit-review ≤ 60s. These drive the decision to run the embedder as a non-blocking background task (not inline with scoring), and to use HDBSCAN (no k required, no cluster-count pre-selection needed).
- **NFR6–NFR8 (Privacy):** All content stays local unless OPENROUTER_API_KEY is set. This mandates Ollama-first for all new LLM operations (enrichment, embeddings). External API calls are always gated on env var presence.
- **NFR9–NFR11 (Reliability):** Embedder and paper-handler failures must not block ingest. Requires `try/except` wrappers around all new network calls with graceful degradation to existing behavior.
- **NFR12–NFR14 (Maintainability):** `PROMPT_PROFILE=infra` must be backward-compatible. `api/main.py` router split is a hard prerequisite.

**Scale & Complexity:**
- Project complexity: **High** (cross-service augmentation, multi-modal LLM pipeline, new persistence layer, new frontend modes)
- Primary domain: AI-assisted research tooling
- Estimated new architectural components: 8 (router split, prompt loader, structured scorer, paper dispatcher, cheap enricher, embedder task, chroma store, lit-review synthesizer)
- Cross-cutting concerns: error isolation (each new component is fault-tolerant), privacy (Ollama-first), backward-compatibility (PROMPT_PROFILE=infra path)

### Technical Constraints & Dependencies

**Hard constraints inherited from existing system:**
- SQLite WAL as sole authoritative persistent store — no Postgres, no MySQL
- 6-service Docker Compose topology — no new required containers for Stories 1–3
- Python 3.12 / FastAPI / SQLAlchemy throughout backend
- React 18 / TypeScript / Vite / Tailwind / Zustand on frontend
- Additive-only DB migrations via `try/except ALTER TABLE` pattern in `init_db()`

**New hard dependencies introduced:**
- `chromadb` Python package (Stories 4+) — file-based, no server
- `sentence-transformers` or Ollama embedding API — local, no external API
- `hdbscan` Python package (Stories 4+) — CPU-only clustering

**Soft dependencies (optional, enrichment only):**
- Semantic Scholar Graph API (unauthenticated, 100 req/5min)
- Crossref/Unpaywall for DOI metadata

### Cross-Cutting Concerns

1. **Fault isolation** — every new I/O operation (SS API, OpenReview, embedder, Chroma) wrapped in try/except; failure produces a degraded but valid result, never a 500 to the user.
2. **Privacy gate** — all external calls gated on env var presence; Ollama path is always valid.
3. **Backward compatibility** — `PROMPT_PROFILE=infra` produces identical output to pre-augmentation system; all new DB columns nullable.
4. **Rate control** — existing `SCORE_DELAY_SECONDS` mechanism extended; cheap enrichment (Ollama, local) not rate-limited; external API calls (SS, DOI) rate-limited to 1 req/s.
5. **Observability** — all new components emit structured logs via `structlog` (already in poller); scorer logs tokens per call.

---

## Starter Template Evaluation

**This is a brownfield project.** No starter template is applicable — the entire stack already exists and is operational.

**Existing stack baseline (verified from codebase):**

| Component | Technology | Version Notes |
|---|---|---|
| Backend runtime | Python 3.12 | Pin to 3.12.x in Dockerfiles |
| API framework | FastAPI | Current in requirements; keep |
| ORM | SQLAlchemy (declarative) | Session pattern already in place |
| DB | SQLite WAL | Via `sqlite:///` + WAL PRAGMA |
| HTTP client (async) | httpx | AsyncClient pattern throughout |
| Scheduler | APScheduler (async) | In poller/main.py |
| Retry logic | tenacity | In poller/main.py |
| Logging | structlog | In poller; extend to api/scorer |
| Frontend build | Vite + React 18 | As-is |
| Styling | Tailwind CSS | As-is |
| State | Zustand | As-is |
| Reverse proxy | Caddy 2 | As-is |
| New: Vector store | ChromaDB | File-mode, Stories 4+ |
| New: Embedding model | nomic-embed-text (Ollama) | Stories 4+ |
| New: Clustering | hdbscan | Stories 4+ |

**No initialization command.** First implementation story is the `api/main.py` router split (Story 1), which is a pure code refactor with zero behavior change.

---

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

1. `api/main.py` router split MUST precede any new endpoints — enforced by PRD NFR14
2. `PROMPT_PROFILE` env var pattern — must be implemented before any prompt changes
3. Embedder placement: **background task in api service** (not 7th Docker service) for MVP
4. ChromaDB mount point: `/data/chroma/` on existing `data` volume
5. Additive migration pattern extension: all new columns nullable

**Important Decisions (Shape Architecture):**

6. Two-stage ingest: cheap Ollama enrichment (abstract → paper_meta) runs BEFORE expensive scoring
7. Scorer result shape extended: `ScoreResult` gets typed fields, stored in `score_meta_json`
8. Research profile: typed table (`research_profile`) replaces ad-hoc tag-frequency strings
9. Clustering: HDBSCAN with default `min_cluster_size=3`, no k pre-selection
10. Literature review: user-triggered only in v1, persisted in `literature_reviews` table

**Deferred Decisions (Post-MVP):**

- Neo4j / property graph — defer until embedding clustering validates utility
- Leiden community detection — defer until HDBSCAN validates the approach
- Multi-user research profiles — defer until single-user v1 ships
- Zotero integration — v3 roadmap

---

### Data Architecture

**Primary store: SQLite WAL** (unchanged, extended)

New columns on `articles` table (all nullable, additive migrations):

```sql
paper_meta_json TEXT          -- structured paper metadata (methods, datasets, metrics)
score_meta_json TEXT          -- structured score (novelty, rigor, relevance, contrib_type)
re_document_type VARCHAR(24)  -- 'elicitation'|'extraction'|'method'|'none'
contribution_type VARCHAR(24) -- 'method'|'benchmark'|'survey'|'empirical'|...
embedding_indexed INTEGER DEFAULT 0  -- 0=not indexed, 1=indexed in Chroma
```

New tables (CREATE IF NOT EXISTS):

```sql
CREATE TABLE IF NOT EXISTS research_profile (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,        -- 'topic'|'method'|'domain'|'avoid'
  label TEXT NOT NULL,
  weight REAL DEFAULT 1.0,
  source TEXT DEFAULT 'manual',  -- 'manual'|'feedback'
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_profile ON research_profile(kind, label);

CREATE TABLE IF NOT EXISTS literature_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic TEXT NOT NULL,
  window_days INTEGER NOT NULL,
  min_rigor REAL DEFAULT 0.0,
  body_json TEXT NOT NULL,   -- JSON: [{cluster_label, synthesis, comparison_table, gaps, top_cite}]
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Auxiliary store: ChromaDB** (Stories 4+)

- Persistence: `/data/chroma/` (Docker volume `data`, same as SQLite)
- Collection: `articles` — one document per article
- Metadata per document: `{article_id, feed_id, contribution_type, re_document_type, score, created_at}`
- Embedding model: `nomic-embed-text` via Ollama `/api/embeddings`
- Embedding dimensions: 768
- No separate Docker service; Chroma runs in-process within `api` service via `chromadb` package

**Data flow direction:**

```
poller → extractor → cheap_enricher → api.create_article
                                           ↓
                                      scorer → api.score_article
                                                     ↓
                                              embedder_task (async, non-blocking)
                                                     ↓
                                               Chroma index
```

All writes to SQLite are synchronous (existing pattern). Chroma indexing is fire-and-forget via `asyncio.create_task`.

---

### Authentication & Security

**Unchanged:** Session-based auth (cookie + `auth_sessions` table) already implemented. All new routes inherit the same `_auth = Depends(require_session)` dependency.

**New considerations:**

- ARISE export endpoint: requires session auth (same as all protected routes); explicitly NOT a public endpoint. ARISE scripts authenticate via the same session cookie (or a future API key — deferred).
- Internal research endpoints between api service components: no new service-to-service auth needed (research endpoints are within the `api` service, not cross-service).
- External API calls (Semantic Scholar, Crossref): outbound only; no auth key required at free tier. If SS API key is added later, store in `.env` following existing `OPENROUTER_API_KEY` pattern.

---

### API & Communication Patterns

**Existing pattern (preserved):** REST, snake_case JSON fields, direct response (no envelope wrapper), HTTP exceptions for errors, SSE for real-time article delivery.

**New endpoints** (all in new `backend/api/routers/research.py`):

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/articles/{id}/related?k=10` | session | k-nearest by embedding |
| GET | `/api/research/clusters?window_days=14&min_size=3` | session | HDBSCAN clusters |
| POST | `/api/research/review` | session | Synthesized lit-review |
| GET | `/api/research/profile` | session | Get typed profile |
| PUT | `/api/research/profile` | session | Upsert profile entries |
| GET | `/api/research/profile/export` | session | YAML export |
| POST | `/api/research/export-arise` | session | ARISE JSON export |
| POST | `/api/admin/rescore` | session | Queue rescoring |

**Extended existing endpoint:**

```
POST /api/internal/articles/{id}/score
```
Body extended: add `score_meta` dict (novelty, rigor, relevance_to_topics, contribution_type, re_document_type). New fields are optional for backward compat.

**Error handling pattern** (consistent with existing):
- 404 for not-found entities
- 422 for validation errors (Pydantic handles)
- 503 (not 500) for LLM service unavailability (embedder, synthesizer)
- Never propagate internal errors to user; log + degrade gracefully

**Rate limiting for new external calls:**
- Semantic Scholar API: 1 req/s, implemented as `asyncio.sleep(1.0)` in enricher (mirrors `SCORE_DELAY_SECONDS` pattern)
- DOI/Crossref: 1 req/s same pattern
- Ollama enrichment: no rate limit (local), but runs serially per article via the existing `_score_semaphore`

---

### Frontend Architecture

**Existing pattern (preserved):** Zustand store slices per domain, `useSSE` hook, component-per-view, Tailwind utility classes, TypeScript interfaces in `types.ts`.

**New components:**

```
frontend/src/
├── components/
│   ├── ResearchDigestView.tsx   -- groups articles by contribution_type
│   ├── LitReviewView.tsx        -- topic input → cluster synthesis view
│   ├── RelatedPanel.tsx         -- right-sidebar in ReaderView
│   ├── ResearchProfileEditor.tsx -- settings tab: typed profile CRUD
│   ├── ContribTypeBadge.tsx     -- badge: METHOD / SURVEY / BENCHMARK / ...
│   └── ReDocTypeBadge.tsx       -- badge: ELICITATION / EXTRACTION / METHOD
├── store/
│   └── research.ts              -- Zustand slice: profile, clusters, reviews
└── types.ts                     -- extend with PaperMeta, ScoreMeta, ResearchProfile, Cluster, Review
```

**State management additions** (Zustand slice `research.ts`):

```typescript
interface ResearchStore {
  profile: ResearchProfileEntry[]
  clusters: Cluster[] | null
  reviews: LiteratureReview[]
  fetchProfile: () => Promise<void>
  saveProfile: (entries: ResearchProfileEntry[]) => Promise<void>
  fetchClusters: (windowDays: number) => Promise<void>
  generateReview: (topic: string, windowDays: number, minRigor: number) => Promise<LiteratureReview>
}
```

**New types** (extend `types.ts`):

```typescript
interface PaperMeta {
  is_paper: boolean
  paper_id?: string
  doi?: string
  methods: string[]
  datasets: string[]
  metrics: string[]
  contribution_type: ContribType
  re_document_type: REDocType
  confidence: number
}

interface ScoreMeta {
  scalar: number
  relevance: number
  novelty: number
  rigor: number
  contribution_type: ContribType
  re_document_type: REDocType
}

type ContribType = 'method'|'benchmark'|'survey'|'empirical'|'theory'|'position'|'tool'|'incident'|'tutorial'|'news'|'other'
type REDocType = 'elicitation'|'extraction'|'method'|'none'

interface ResearchProfileEntry {
  id?: number
  kind: 'topic'|'method'|'domain'|'avoid'
  label: string
  weight: number
  source: 'manual'|'feedback'
}

interface Cluster {
  cluster_id: number
  size: number
  centroid_title: string
  top_tags: string[]
  article_ids: number[]
}

interface LiteratureReview {
  id?: number
  topic: string
  window_days: number
  clusters: ReviewCluster[]
  created_at: string
}

interface ReviewCluster {
  cluster_label: string
  synthesis: string
  comparison_table: ComparisonRow[]
  gaps: string[]
  top_cite: string
  article_ids: number[]
}
```

**Tab routing addition** in `App.tsx`:

```typescript
// Extend tab type
type Tab = 'articles' | 'digest' | 'research' | 'stats' | 'highlights'
// Research tab renders: <ResearchDigestView> | <LitReviewView> with subtab
```

---

### Infrastructure & Deployment

**Unchanged:** 6-service Docker Compose. All new Python dependencies added to relevant service `requirements.txt`. No Dockerfile structural changes.

**New Python dependencies by service:**

`backend/api/requirements.txt` additions:
```
chromadb>=0.4.22
hdbscan>=0.8.33
numpy>=1.26
```

`backend/extractor/requirements.txt` additions:
```
# None — SS/DOI handlers use existing httpx
```

`backend/scorer/requirements.txt` additions:
```
# None — prompt loader uses pathlib (stdlib)
```

**Volume extension:**

```yaml
# docker-compose.yml — api service, extend volumes:
volumes:
  - data:/data        # existing
  # /data/chroma/ created automatically by chromadb on first use
```

**Environment variables additions** (`.env.example`):

```bash
# ─── Baṣīra — System name ────────────────────────────────────────────────────
# The augmented system is named Baṣīra (بَصِيرَة — "deep insight")

# ─── LLM Tier 1: Local Ollama (Apple M5 Max, 36 GB) ─────────────────────────
# Existing vars — unchanged:
# OLLAMA_URL=http://host.docker.internal:11434
# OLLAMA_MODEL=mistral

# Embedding model (local Ollama — for ChromaDB indexing)
OLLAMA_EMBED_MODEL=nomic-embed-text

# ─── LLM Tier 2: University GPU Server (VPN required) ────────────────────────
# OpenAI-compatible API at Université de Pau
UNI_OLLAMA_URL=https://llm.eva.univ-pau.fr/v1
# Model name as returned by /v1/models (set after inspecting available models)
UNI_OLLAMA_MODEL=

# ─── LLM Tier 3: OpenRouter (cloud fallback) ─────────────────────────────────
# Existing var — unchanged:
# OPENROUTER_API_KEY=sk-or-v1-...
# SCORER_MODEL=google/gemini-2.5-flash-lite

# ─── Research scoring profile ─────────────────────────────────────────────────
PROMPT_PROFILE=unified           # 'infra' | 'research' | 'unified'

# Content cap for scoring (chars)
SCORER_MAX_CHARS=6000            # auto-raised to 12000 for papers

# Semantic Scholar rate limit
SS_RATE_LIMIT_SECONDS=1.0
```

**LLM routing logic** (scorer + synthesizer, new `llm_client.py` utility):

```python
# Priority: uni_server (if reachable) → local_ollama → openrouter
# Health check on UNI_OLLAMA_URL is cached for 5 minutes (avoid VPN latency on every call)
# If UNI_OLLAMA_URL is empty or health check fails → fall through to next tier
```

**Monitoring/logging additions:**
- `structlog` extended to `api` service (currently only in poller)
- Scorer logs `tokens_used` per call and `llm_tier_used` (`local|uni|openrouter`)
- Embedder logs `embedding_ms` per article

---

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Database Naming (existing conventions, extended):**
- Tables: `snake_case`, plural where a collection exists (`articles`, `feeds`, `highlights`, `research_profile` — note: singular because it's a profile, not a list of records)
- Columns: `snake_case` always (e.g., `re_document_type`, `paper_meta_json`, `contribution_type`)
- JSON blob columns: suffix `_json` (e.g., `tags_json`, `paper_meta_json`, `score_meta_json`)
- Indexes: `ix_{table}_{column}` for single-column, `ux_{table}` for unique constraints
- Enum columns: stored as `VARCHAR(24)` with application-level validation

**API Naming (existing conventions, extended):**
- Routes: `/api/{resource}` plural, kebab-case for multi-word (e.g., `/api/research/export-arise`)
- Internal routes: `/api/internal/{resource}` — require `X-Internal-Secret` header
- Query params: `snake_case` (e.g., `window_days`, `min_size`, `min_rigor`)
- Response fields: `snake_case` — match DB column names exactly where possible

**Code Naming:**
- Python: `snake_case` functions, `PascalCase` classes, `UPPER_CASE` module constants
- TypeScript: `camelCase` variables/functions, `PascalCase` components/interfaces/types
- Files (Python): `snake_case.py`; Files (TypeScript): `PascalCase.tsx` for components, `camelCase.ts` for stores/hooks/utils

**Enum values** (string literals, stored as-is in DB):
```python
CONTRIB_TYPES = {'method','benchmark','survey','empirical','theory','position','tool','incident','tutorial','news','other'}
RE_DOC_TYPES  = {'elicitation','extraction','method','none'}
PROFILE_KINDS = {'topic','method','domain','avoid'}
PROMPT_PROFILES = {'infra','research','unified'}
```

### Structure Patterns

**New file locations — strict mapping:**

```
backend/scorer/
├── scorer.py             -- unchanged interface; extended ScoreResult
├── prompt.py             -- now: loader only (3 lines)
└── prompts/
    ├── infra.md          -- original DevOps profile (backward compat)
    ├── research.md       -- research-only profile
    └── unified.md        -- combined profile (default)

backend/extractor/
└── extractor.py          -- add paper_handlers dict + enrich_paper_meta()

backend/api/
├── main.py               -- app factory + startup + auth routes ONLY (< 100 LOC after split)
├── database.py           -- extended with new columns/tables (additive only)
├── models.py             -- extended with PaperMeta, ScoreMeta, ResearchProfile* models
├── auth.py               -- unchanged
├── embedder.py           -- NEW: ChromaDB wrapper + background task
└── routers/
    ├── __init__.py
    ├── articles.py       -- all /api/articles/* routes
    ├── feeds.py          -- all /api/feeds/* routes
    ├── highlights.py     -- all /api/articles/*/highlights routes
    ├── ask.py            -- /api/articles/*/ask route
    ├── stats.py          -- /api/stats route
    ├── admin.py          -- /api/admin/* routes
    ├── internal.py       -- all /api/internal/* routes
    └── research.py       -- all /api/research/* routes (NEW)

frontend/src/
├── components/
│   ├── ArticleCard.tsx         -- add ContribTypeBadge, ReDocTypeBadge
│   ├── ReaderView.tsx          -- add RelatedPanel right sidebar
│   ├── ContribTypeBadge.tsx    -- NEW
│   ├── ReDocTypeBadge.tsx      -- NEW
│   ├── ResearchDigestView.tsx  -- NEW
│   ├── LitReviewView.tsx       -- NEW
│   ├── RelatedPanel.tsx        -- NEW
│   └── ResearchProfileEditor.tsx -- NEW
├── store/
│   └── research.ts             -- NEW Zustand slice
└── types.ts                    -- extended (not replaced)
```

**AI Agent Rule:** Any new backend route MUST live in a router file under `backend/api/routers/`. Zero exceptions. `main.py` is frozen to the app factory + auth routes after Story 1.

### Format Patterns

**API response formats (existing, extended):**

```python
# Standard success: direct object (no envelope)
# Error: raise HTTPException(status_code=..., detail="human message")

# New: paper_meta field on ArticleOut (parsed from paper_meta_json, same as tags)
# New: score_meta field on ArticleOut (parsed from score_meta_json)
```

**JSON blob storage pattern** (existing, extended for new blobs):

```python
# Store: json.dumps(obj)
# Read in API: parse in model_validator (Pydantic), same as existing tags/summary_bullets
# Example:
@model_validator(mode="after")
def parse_json_fields(self) -> "ArticleOut":
    self.paper_meta = json.loads(self.paper_meta_json or "{}")
    self.score_meta = json.loads(self.score_meta_json or "{}")
    ...
```

**Ollama API call pattern** (extended from scorer, applied to enricher + embedder):

```python
# Chat (enrichment): POST {OLLAMA_URL}/api/chat — stream=False, temperature=0.1
# Embeddings: POST {OLLAMA_URL}/api/embeddings — model=OLLAMA_EMBED_MODEL
# Both wrapped in try/except; failure returns None/empty; never raises to caller
```

### Communication Patterns

**Ingest pipeline orchestration:**

```python
# In poller.process_feed, after extract_article():
enriched = await enrich_paper_meta(client, article_url, extracted)
# enriched adds: paper_meta_json, re_document_type, contribution_type to payload
payload = {**base_payload, **enriched}

# After create_article() returns created=True:
asyncio.create_task(score_article_rate_limited(...))

# In api, after internal_score_article():
asyncio.create_task(embed_article_async(article_id))  # non-blocking
```

**SSE broadcast** (unchanged): score arrival triggers `_broadcast_new_article`; embedding completion is silent (no SSE needed).

**Error isolation contract:**

```python
# Every new async task follows this pattern:
async def enrich_paper_meta(...) -> dict:
    try:
        # ... actual logic
        return enrichment_dict
    except Exception as e:
        logger.warning("enrichment_failed", url=url, error=str(e))
        return {}   # Empty dict — caller uses .get() with defaults
```

### Process Patterns

**Loading states (frontend):**
- Lit-review generation: `isGenerating: boolean` in research store; skeleton card shown during generation
- Related panel: inline loading spinner; no global loading state
- Profile save: optimistic update with rollback on error

**Error handling (frontend):**
- API errors: toast notification with human-readable message (existing pattern from ArticleList)
- Lit-review LLM error: inline error state in LitReviewView with retry button
- Related panel API error: silent empty state (no visible error for secondary features)

---

## Project Structure & Boundaries

### Complete Project Directory Structure (Augmented)

```
daily_news_wrap/
├── .env.example                         # extended with PROMPT_PROFILE, SCORER_MAX_CHARS
├── docker-compose.yml                   # unchanged topology; api volumes extended
├── docker-compose.override.yml          # unchanged
├── README.md                            # to be updated post-augmentation
│
├── backend/
│   ├── api/
│   │   ├── Dockerfile                   # unchanged
│   │   ├── requirements.txt             # + chromadb, hdbscan, numpy
│   │   ├── main.py                      # REFACTORED: app factory + auth only
│   │   ├── database.py                  # EXTENDED: new columns + tables
│   │   ├── models.py                    # EXTENDED: PaperMeta, ScoreMeta, ResearchProfile*
│   │   ├── auth.py                      # unchanged
│   │   ├── embedder.py                  # NEW: Chroma wrapper + async task
│   │   └── routers/
│   │       ├── __init__.py              # NEW
│   │       ├── articles.py              # NEW: moved from main.py
│   │       ├── feeds.py                 # NEW: moved from main.py
│   │       ├── highlights.py            # NEW: moved from main.py
│   │       ├── ask.py                   # NEW: moved from main.py
│   │       ├── stats.py                 # NEW: moved from main.py
│   │       ├── admin.py                 # NEW: moved from main.py
│   │       ├── internal.py              # NEW: moved from main.py
│   │       └── research.py             # NEW: all research/ARISE endpoints
│   │
│   ├── extractor/
│   │   ├── Dockerfile                   # unchanged
│   │   ├── requirements.txt             # unchanged
│   │   └── extractor.py                 # EXTENDED: paper_handlers dict, enrich step
│   │
│   ├── scorer/
│   │   ├── Dockerfile                   # unchanged
│   │   ├── requirements.txt             # unchanged
│   │   ├── scorer.py                    # EXTENDED: ScoreResult fields, SCORER_MAX_CHARS
│   │   ├── prompt.py                    # REFACTORED: loader only
│   │   └── prompts/
│   │       ├── infra.md                 # NEW: original rubric verbatim
│   │       ├── research.md              # NEW: research-only rubric
│   │       └── unified.md               # NEW: combined rubric (default)
│   │
│   ├── poller/
│   │   ├── Dockerfile                   # unchanged
│   │   ├── requirements.txt             # unchanged
│   │   └── main.py                      # EXTENDED: calls enricher before create_article
│   │
│   └── shared/
│       └── database.py                  # reference copy; canonical is api/database.py
│
└── frontend/
    ├── src/
    │   ├── App.tsx                      # EXTENDED: Research tab added
    │   ├── types.ts                     # EXTENDED: PaperMeta, ScoreMeta, ResearchProfile*
    │   ├── components/
    │   │   ├── ArticleCard.tsx          # EXTENDED: ContribTypeBadge, ReDocTypeBadge
    │   │   ├── ReaderView.tsx           # EXTENDED: RelatedPanel right sidebar
    │   │   ├── ContribTypeBadge.tsx     # NEW
    │   │   ├── ReDocTypeBadge.tsx       # NEW
    │   │   ├── ResearchDigestView.tsx   # NEW
    │   │   ├── LitReviewView.tsx        # NEW
    │   │   ├── RelatedPanel.tsx         # NEW
    │   │   └── ResearchProfileEditor.tsx # NEW
    │   └── store/
    │       └── research.ts              # NEW Zustand slice
    └── ...
```

### Architectural Boundaries

**Service boundaries (unchanged):**
```
poller     → talks to: api (internal), extractor, scorer
extractor  → talks to: external URLs only
scorer     → talks to: OpenRouter OR Ollama, api (internal score endpoint)
api        → talks to: SQLite, Chroma (in-process), Ollama (enrichment + embeddings)
frontend   → talks to: api only (via Caddy proxy)
```

**New internal boundary — api service subsystems:**
```
api/main.py (factory)
  ├── routers/articles.py     → SQLite only
  ├── routers/feeds.py        → SQLite only
  ├── routers/highlights.py   → SQLite only
  ├── routers/ask.py          → SQLite + OpenRouter/Ollama (streaming)
  ├── routers/stats.py        → SQLite only
  ├── routers/admin.py        → SQLite only
  ├── routers/internal.py     → SQLite (writes from poller/scorer)
  ├── routers/research.py     → SQLite + Chroma + Ollama (synthesis)
  └── embedder.py             → Chroma + Ollama (background tasks)
```

**Data boundaries:**
- `articles` table: written by `internal.py` (poller path) and `internal.py` (scorer path); read by all other routers
- `research_profile` table: written and read by `research.py` only
- `literature_reviews` table: written and read by `research.py` only
- Chroma `articles` collection: written by `embedder.py` (background task); queried by `research.py`

### Requirements to Structure Mapping

| Story | FR Group | Primary Files |
|---|---|---|
| Story 1 | — (refactor) | `api/main.py` → `api/routers/` |
| Story 2 | FR7–FR11 | `scorer/prompt.py`, `scorer/prompts/`, `scorer/scorer.py`, `api/database.py`, `api/models.py`, `api/routers/internal.py` |
| Story 3 | FR1–FR6 | `extractor/extractor.py`, `poller/main.py`, `api/database.py` |
| Story 4 | FR12–FR16 | `api/embedder.py`, `api/routers/research.py`, `frontend/store/research.ts`, `frontend/components/RelatedPanel.tsx`, `api/requirements.txt` |
| Story 5 | FR17–FR21 | `api/database.py`, `api/routers/research.py`, `api/models.py`, `frontend/components/ResearchProfileEditor.tsx`, `frontend/store/research.ts` |
| Story 6 | FR22–FR27 | `api/routers/research.py`, `frontend/components/LitReviewView.tsx`, `frontend/store/research.ts` |
| Story 7 | FR28–FR30 | `api/routers/research.py`, `api/routers/admin.py` |

---

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
All technology choices are compatible with the existing stack. ChromaDB runs in-process (no network hop). HDBSCAN is CPU-only Python (no GPU dependency). Ollama embedding model runs on the same Ollama instance already configured for scoring. The only new runtime dependency is `chromadb` + `hdbscan` + `numpy` in the api service.

**Pattern Consistency:**
All new endpoints follow the existing REST pattern (direct response, snake_case, HTTPException for errors). All new DB operations follow the existing SQLAlchemy session pattern. The `try/except ALTER TABLE` migration pattern is used consistently for all 5 new columns. All new async tasks follow the `asyncio.create_task` fire-and-forget pattern already used for cleanup tasks.

**Structure Alignment:**
The router split directly implements the existing route structure — routes are moved, not rewritten. All new files follow established naming conventions. The prompt loader pattern is 3 lines and is strictly backward-compatible via `PROMPT_PROFILE=infra`.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**
- FR1–FR6 (enrichment): covered by extractor + poller extensions + new DB columns
- FR7–FR11 (scoring): covered by scorer refactor + extended ScoreResult + new article list filters
- FR12–FR16 (retrieval): covered by embedder.py + research router + RelatedPanel
- FR17–FR21 (profile): covered by research_profile table + research router + profile editor
- FR22–FR27 (lit-review): covered by research router synthesis + LitReviewView + literature_reviews table
- FR28–FR30 (ARISE/admin): covered by research router export + admin router rescore

**Non-Functional Requirements Coverage:**
- NFR1–NFR4 (performance): addressed by async non-blocking embedder, HDBSCAN (no k), Chroma local query
- NFR6–NFR8 (privacy): all new LLM calls gated on env vars; Ollama always valid path
- NFR9–NFR11 (reliability): try/except isolation on all new I/O; additive migrations; backward-compat scorer path
- NFR12–NFR14 (maintainability): prompt loader 3 LOC; router split enforced; PROMPT_PROFILE=infra = backward compat

### Gap Analysis Results

**No critical gaps identified.**

**Important — document before Story 4:**
- Chroma collection schema (metadata fields) must be agreed before first write; changing it requires collection rebuild
- Embedding retroactive indexing: need an admin endpoint `POST /api/admin/reindex-all` to batch-embed all existing articles on first deploy of Story 4

**Nice-to-have:**
- Integration test: run `PROMPT_PROFILE=infra` and verify scoring output matches baseline (before Story 2 merge)
- `structlog` not yet in `api` service — add in Story 1 alongside router split (zero extra effort)

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed (brownfield, 6 services, SQLite WAL)
- [x] Scale and complexity assessed (high, 8 new components)
- [x] Technical constraints identified (additive-only, local-first, backward-compat)
- [x] Cross-cutting concerns mapped (fault isolation, privacy gate, rate control)

**✅ Architectural Decisions**
- [x] Critical decisions documented (router split, embedder placement, Chroma mount, migration pattern)
- [x] Technology stack fully specified (chromadb, hdbscan, nomic-embed-text)
- [x] Integration patterns defined (fire-and-forget embedder, two-stage ingest, enricher-before-scorer)
- [x] Performance considerations addressed (non-blocking embedder, HDBSCAN, local Chroma)

**✅ Implementation Patterns**
- [x] Naming conventions established (snake_case DB/API, _json suffix for blobs, enum validation)
- [x] Structure patterns defined (routers/ split, prompts/ folder, embedder.py)
- [x] Communication patterns specified (asyncio.create_task, try/except isolation, SSE unchanged)
- [x] Process patterns documented (frontend loading states, error handling, optimistic updates)

**✅ Project Structure**
- [x] Complete directory structure defined with all new/modified files
- [x] Component boundaries established (each router touches specific tables)
- [x] Integration points mapped (story-to-file table)
- [x] Requirements to structure mapping complete (FR groups → story → files)

### Architecture Readiness Assessment

**Overall Status: READY FOR IMPLEMENTATION**

**Confidence Level: HIGH**

Key strengths:
1. Zero breaking changes to existing behavior — every augmentation is additive
2. Story 1 (router split) is low-risk and high-value: enables all subsequent work cleanly
3. `PROMPT_PROFILE=infra` guarantees backward compatibility — the researcher can test the new system without losing the existing scoring behavior
4. Fault isolation pattern is consistent: every new I/O boundary returns empty/default on failure

Areas for future enhancement:
- Leiden community detection for global synthesis (v2, after HDBSCAN validates clustering utility)
- Neo4j property graph for citation-level traceability (v3)
- Per-cluster confidence scores on literature review synthesis (v2)
- Webhook/push integration for ARISE pipeline (v2, instead of pull-based export)

### Implementation Handoff

**AI Agent Guidelines:**

1. **Story 1 first, always.** Do not add any new route to `main.py`. Move routes to `routers/`, then add new routes to `routers/research.py`.
2. **Never break `PROMPT_PROFILE=infra`.** The infra prompt file is a verbatim copy of the current `SYSTEM_PROMPT` string. Do not edit it.
3. **All new DB columns are nullable.** No `NOT NULL` constraints on new augmentation columns. No `DEFAULT` that could break existing rows.
4. **Embedder is fire-and-forget.** `asyncio.create_task(embed_article_async(article_id))` — never await it inline with scoring.
5. **Research router is the only new router.** `admin.py`, `internal.py`, etc. are moved from `main.py`, not new functionality.
6. **Test backward compat before merging Story 2.** Run `PROMPT_PROFILE=infra` and confirm scoring output on 5 known articles matches pre-augmentation behavior.

**First implementation story:**
```
Story 1: api/main.py router split
- Create backend/api/routers/__init__.py
- Move each route group to its router file
- Register all routers in main.py via app.include_router()
- Run all existing tests; verify zero behavior change
```
