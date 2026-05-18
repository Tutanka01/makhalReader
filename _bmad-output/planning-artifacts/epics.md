---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/architecture.md"
project_name: "Baṣīra"
user_name: "Arona"
date: "2026-04-22"
---

# Baṣīra - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Baṣīra, decomposing the requirements from the PRD and Architecture into implementable stories.

---

## Requirements Inventory

### Functional Requirements

FR1: System can ingest articles from RSS feeds including arXiv, Semantic Scholar, ACL Anthology, OpenReview, and DOI landing pages via the existing poller scheduler.
FR2: System can extract structured paper metadata (abstract, authors, methods, datasets, metrics) from paper source URLs using source-specific handlers.
FR3: System can classify each ingested article with a `contribution_type` value (method, benchmark, survey, empirical, theory, position, tool, incident, tutorial, news, other).
FR4: System can classify each ingested article with a `re_document_type` value (elicitation, extraction, method, none) to identify requirement-rich sources.
FR5: System can store extracted paper metadata in a `paper_meta_json` field alongside the existing article record.
FR6: System can apply a configurable content length cap for scoring, with an automatic increase when an article is classified as a paper.
FR7: System can score articles using a configurable scoring profile selected via the `PROMPT_PROFILE` environment variable, supporting at minimum `infra`, `research`, and `unified` profiles.
FR8: System can return a multi-dimensional score object per article including: scalar, relevance, novelty, rigor, contribution_type, re_document_type, tags, summary_bullets, and reason.
FR9: System can store the structured score metadata in a `score_meta_json` field per article.
FR10: Researcher can filter the article list by `contribution_type` and `re_document_type` in addition to existing filters.
FR11: System can display `contribution_type` and `re_document_type` badges on article cards in the list and reader views.
FR12: System can generate and store a vector embedding for each article using a local embedding model.
FR13: System can retrieve the k nearest neighbor articles for any given article by embedding similarity.
FR14: System can cluster recent articles by semantic similarity and return cluster summaries (centroid topic, size, representative articles, top tags).
FR15: Researcher can view related articles for any open article in a dedicated panel within the reader view.
FR16: System can retroactively generate embeddings for all existing articles via an admin endpoint.
FR17: Researcher can define a typed research profile specifying tracked topics, methods, domains, and avoidance signals with individual weights.
FR18: System can automatically update the research profile with feedback-inferred entries derived from the researcher's 👍/👎 history.
FR19: Scorer can use the typed researcher profile to build a structured preference block for LLM prompts, replacing the flat tag-frequency aggregation.
FR20: Researcher can view and edit the research profile through a dedicated settings panel in the frontend.
FR21: Researcher can export the research profile as a versioned YAML file for external use or version control.
FR22: Researcher can initiate a literature review synthesis for a user-defined topic, time window, and minimum rigor threshold.
FR23: System can retrieve semantically relevant articles for the specified topic using embedding search.
FR24: System can cluster retrieved articles and generate per-cluster synthesis including: synthesis paragraph, comparison table (work | method | dataset | key result), research gaps (3 bullets max), and most-citable work recommendation.
FR25: Researcher can view the generated literature review as a structured, formatted document within the frontend.
FR26: Researcher can export the generated review as Markdown.
FR27: System can persist generated literature reviews in a `literature_reviews` table for future retrieval and reference.
FR28: Researcher (or external pipeline) can export all articles with `re_document_type ∈ {elicitation, extraction, method}` as structured JSON via a dedicated API endpoint, filtered by date range.
FR29: Administrator can trigger rescoring of articles from a specified date forward, allowing rubric changes to be applied retroactively.
FR30: System can add new paper-focused RSS feeds (arXiv cs.SE, cs.RO; Semantic Scholar feeds) as default feeds alongside existing infra/AI feeds.

### Non-Functional Requirements

NFR1: Article ingest-to-score latency p50 ≤ 3 minutes, p95 ≤ 8 minutes under normal load.
NFR2: Embedding generation per article ≤ 500ms; retroactive indexing of 5000 articles ≤ 30 minutes.
NFR3: Related-paper API response ≤ 2 seconds for k=10 over a 10,000-article corpus.
NFR4: Literature-review synthesis for 24 articles across 4 clusters ≤ 60 seconds end-to-end.
NFR5: Token cost per article after full enrichment pipeline ≤ 2× baseline.
NFR6: All article content, embeddings, and research profile data stored locally; no data leaves system unless OpenRouter explicitly configured.
NFR7: ARISE export endpoint requires session authentication; no unauthenticated access.
NFR8: All new internal service-to-service endpoints require `X-Internal-Secret` header.
NFR9: Embedding service failure must not block article ingest or scoring; graceful degradation required.
NFR10: Paper handler failures must fall back to existing extraction strategy without losing the article.
NFR11: All new DB migrations must execute idempotently; no data loss on re-run.
NFR12: `PROMPT_PROFILE=infra` must produce scoring behavior ±5% accuracy vs pre-augmentation baseline.
NFR13: Each new scorer profile is a standalone Markdown file in `backend/scorer/prompts/`; no code change to add or modify a profile.
NFR14: `api/main.py` router split must be completed before any research endpoints are added.
NFR15: ARISE export JSON schema must include: `{id, title, url, published_at, re_document_type, contribution_type, paper_meta, content_text, score_meta, feed_name, tags}`.
NFR16: ChromaDB persistence is file-based at `/data/chroma/`; no separate database server required.

### Additional Requirements

- ARCH1: `api/main.py` router split is a hard prerequisite (Story 1); all new routes go only in `routers/` subdirectory.
- ARCH2: Three-tier LLM routing: local Ollama (M5 Max) → university GPU server (VPN, `https://llm.eva.univ-pau.fr/v1`) → OpenRouter; 5-minute health-check cache for VPN tier.
- ARCH3: Embedder runs as `asyncio.create_task` background task within `api` service (non-blocking, fire-and-forget); never awaited inline with scoring.
- ARCH4: All new DB columns nullable; additive `try/except ALTER TABLE` migration pattern — no breaking changes.
- ARCH5: ChromaDB in-process (`chromadb` Python package in `api` service); no 7th Docker service.
- ARCH6: Two-stage ingest pipeline: cheap Ollama enrichment (abstract → `paper_meta_json`) runs BEFORE expensive scoring call.
- ARCH7: `structlog` added to `api` service; scorer logs `tokens_used` + `llm_tier_used` per call.
- ARCH8: New env vars: `UNI_OLLAMA_URL`, `UNI_OLLAMA_MODEL`, `OLLAMA_EMBED_MODEL`, `PROMPT_PROFILE`, `SCORER_MAX_CHARS`, `SS_RATE_LIMIT_SECONDS`.
- ARCH9: Admin endpoint `POST /api/admin/reindex-all` required for retroactive embedding on first Story 4 deploy.

### UX Design Requirements

N/A — No UX Design document exists for this project. UI decisions are captured in Architecture frontend section.

---

### FR Coverage Map

```
FR1:  Epic 2 — Ingest from arXiv/SS/ACL/OpenReview/DOI feeds
FR2:  Epic 2 — Paper metadata extraction (abstract, methods, datasets, metrics)
FR3:  Epic 2 — contribution_type classification
FR4:  Epic 2 — re_document_type classification
FR5:  Epic 2 — paper_meta_json storage
FR6:  Epic 2 — Configurable SCORER_MAX_CHARS, paper-aware auto-raise
FR7:  Epic 2 — PROMPT_PROFILE env var, prompts/ folder
FR8:  Epic 2 — Multi-dimensional ScoreResult (novelty, rigor, contrib_type, re_doc_type)
FR9:  Epic 2 — score_meta_json storage
FR10: Epic 2 — Article list filter by contribution_type / re_document_type
FR11: Epic 2 — ContribTypeBadge + ReDocTypeBadge on article cards
FR12: Epic 3 — Vector embedding generation (nomic-embed-text, ChromaDB)
FR13: Epic 3 — k-NN related article retrieval by embedding similarity
FR14: Epic 3 — HDBSCAN clustering + cluster summaries
FR15: Epic 3 — RelatedPanel in ReaderView
FR16: Epic 3 — Retroactive embedding admin endpoint
FR17: Epic 3 — Typed research profile CRUD (topic/method/domain/avoid)
FR18: Epic 3 — Feedback-inferred profile updates (source=feedback)
FR19: Epic 3 — Scorer preference block from typed profile
FR20: Epic 3 — ResearchProfileEditor settings panel
FR21: Epic 3/4 — Research profile YAML export
FR22: Epic 3 — Literature review synthesis initiation
FR23: Epic 3 — Embedding search for relevant articles
FR24: Epic 3 — Per-cluster synthesis (paragraph, comparison table, gaps, top-cite)
FR25: Epic 3 — LitReviewView structured display
FR26: Epic 3 — Markdown export of review
FR27: Epic 3 — literature_reviews table persistence
FR28: Epic 4 — ARISE JSON export endpoint
FR29: Epic 4 — Admin rescore endpoint
FR30: Epic 2 — Add arXiv cs.SE/cs.RO + Semantic Scholar default feeds
```

---

## Epic List

### Epic 1: Codebase Foundation — Clean & Extensible API
The existing monolithic API is refactored into a router structure and the prompt system is made configurable, with zero regression to existing behavior. This delivers the structural prerequisite that makes all research features possible.
**FRs covered:** None directly (prerequisite refactor)
**NFRs addressed:** NFR12, NFR13, NFR14

### Epic 2: Research-Aware Triage — Papers Score Where They Deserve
Research papers (surveys, methods, benchmarks) surface in the score ≥ 7 tier. Each article card shows contribution type and RE document type badges. Paper metadata is enriched and stored. Paper-focused feeds are seeded. The researcher's daily triage is transformed.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR30
**NFRs addressed:** NFR1, NFR5, NFR6, NFR10, NFR11

### Epic 3: Semantic Knowledge Layer — Discover Connections & Synthesize
The researcher can find related papers alongside any article, explore topic clusters, generate draft literature-review syntheses in under 60 seconds, and maintain a typed research profile that progressively improves scoring accuracy.
**FRs covered:** FR12, FR13, FR14, FR15, FR16, FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27
**NFRs addressed:** NFR2, NFR3, NFR4, NFR8, NFR9, NFR16

### Epic 4: ARISE Pipeline Bridge & Admin Tooling
The researcher or an external ARISE script can pull a structured JSON export of all requirement-rich documents. Rubric changes can be applied retroactively. The research profile is git-trackable via YAML export.
**FRs covered:** FR21 (finalized), FR28, FR29
**NFRs addressed:** NFR7, NFR8, NFR15

---

## Epic 1: Codebase Foundation — Clean & Extensible API

The existing monolithic API is refactored into a router structure and the prompt system is made configurable, delivering a zero-regression foundation for all research intelligence features.

### Story 1.1: API Router Refactor

As a **developer agent**,
I want the `backend/api/main.py` monolith split into a `routers/` directory with one file per route group,
So that new research endpoints can be added cleanly without touching the app factory, and the codebase is maintainable at scale.

**Acceptance Criteria:**

**Given** the existing `backend/api/main.py` (1266 LOC, 30+ routes) is operational  
**When** the router split is complete  
**Then** `main.py` contains only: FastAPI app factory, startup/shutdown lifecycle hooks, session auth routes (`/api/login`, `/api/logout`, `/api/me`), and `app.include_router()` calls — total ≤ 100 LOC  
**And** the following router files exist and each handles only their designated routes:
- `backend/api/routers/__init__.py`
- `backend/api/routers/articles.py` — all `/api/articles/*` routes
- `backend/api/routers/feeds.py` — all `/api/feeds/*` routes
- `backend/api/routers/highlights.py` — all `/api/articles/*/highlights` routes
- `backend/api/routers/ask.py` — `/api/articles/*/ask` route
- `backend/api/routers/stats.py` — `/api/stats` route
- `backend/api/routers/admin.py` — `/api/admin/*` routes
- `backend/api/routers/internal.py` — all `/api/internal/*` routes

**Given** the router split is deployed  
**When** any existing API endpoint is called (articles list, feed CRUD, scoring, highlights, stats, ask-AI, SSE)  
**Then** the response is byte-for-byte identical to the pre-split behavior (zero behavior change)  
**And** all existing SSE connections and streaming responses continue to work

**Given** the split is complete  
**When** `structlog` is imported in `main.py`  
**Then** structured JSON logging is active in the `api` service (matching the existing poller pattern), with `request_id` and `service=api` fields on every log line

**Given** a developer wants to add a new route  
**When** they need to add a research endpoint  
**Then** there is a clear `backend/api/routers/research.py` placeholder file (empty router, registered in `main.py`) ready to receive new routes

---

### Story 1.2: Prompt Profile Loader

As a **researcher**,
I want the scoring system to load its rubric from a Markdown file selected by the `PROMPT_PROFILE` environment variable,
So that I can switch between research and DevOps scoring modes without any code change, and the existing behavior is preserved exactly when `PROMPT_PROFILE=infra`.

**Acceptance Criteria:**

**Given** the existing `backend/scorer/prompt.py` contains a hard-coded `SYSTEM_PROMPT` string  
**When** this story is implemented  
**Then** `prompt.py` is refactored to a loader: it reads `PROMPT_PROFILE` env var (default `unified`) and returns the contents of `backend/scorer/prompts/{PROMPT_PROFILE}.md`

**Given** `backend/scorer/prompts/` directory is created  
**When** the directory is populated  
**Then** it contains exactly three files:
- `infra.md` — verbatim copy of the current `SYSTEM_PROMPT` string (no edits)
- `research.md` — research-oriented rubric rewarding surveys, methods, benchmarks, theory papers
- `unified.md` — combined rubric that rewards both DevOps/infra and research content (default)

**Given** `PROMPT_PROFILE=infra` is set in `.env`  
**When** an article is scored  
**Then** the LLM receives the identical system prompt as the pre-augmentation system  
**And** scoring output on a held-out set of 5 known articles is statistically indistinguishable (±5% scalar score) from the pre-augmentation baseline

**Given** `PROMPT_PROFILE=research` is set  
**When** a survey paper is scored  
**Then** the system prompt instructs the LLM to reward survey/benchmark/method/theory contribution types  
**And** the scalar score for a known survey paper increases relative to `PROMPT_PROFILE=infra`

**Given** `PROMPT_PROFILE=unified` is set (or env var is absent)  
**When** the scorer starts  
**Then** `unified.md` is loaded without error and scoring proceeds normally

**Given** an invalid `PROMPT_PROFILE` value is set  
**When** the scorer service starts  
**Then** it raises a clear startup error: `"PROMPT_PROFILE '{value}' not found in backend/scorer/prompts/"` and exits non-zero

---

## Epic 2: Research-Aware Triage — Papers Score Where They Deserve

Research papers surface in the score ≥ 7 tier alongside infra posts. Article cards show contribution type and RE document type badges. Paper metadata is enriched. Paper-focused feeds are seeded.

### Story 2.1: Research-Aware Scoring Engine

As a **researcher**,
I want the scoring system to return a multi-dimensional result (novelty, rigor, contribution type, RE document type) and store it per article,
So that I can filter and sort my reading list by research dimensions, not just a single scalar score.

**Acceptance Criteria:**

**Given** the existing `ScoreResult` pydantic model has fields `{score, tags, summary_bullets, reason}`  
**When** this story is implemented  
**Then** `ScoreResult` is extended with: `contribution_type: str | None`, `re_document_type: str | None`, `novelty: float | None` (0–1), `rigor: float | None` (0–1), `relevance_to_topics: float | None` (0–1)  
**And** all new fields are optional/nullable for backward compatibility with existing scorer responses

**Given** the `articles` database table exists  
**When** additive migrations run via `init_db()`  
**Then** three new nullable columns exist: `score_meta_json TEXT`, `re_document_type VARCHAR(24)`, `contribution_type VARCHAR(24)`  
**And** running `init_db()` twice on an already-migrated database produces no error and no data loss

**Given** a `SCORER_MAX_CHARS` env var is set (e.g., `6000`)  
**When** an article is being scored  
**Then** the content preview is truncated to `SCORER_MAX_CHARS` characters  
**And** when `paper_meta_json` on the article contains `"is_paper": true`, the cap is automatically raised to `min(SCORER_MAX_CHARS * 2, 12000)` characters

**Given** the scorer returns a `ScoreResult` with `contribution_type` and `re_document_type`  
**When** `POST /api/internal/articles/{id}/score` is called with the extended score body  
**Then** `score_meta_json` is stored as a JSON blob on the article record  
**And** `re_document_type` and `contribution_type` columns are populated from the score result  
**And** `ArticleOut` response includes parsed `score_meta` dict (matching existing `tags`/`summary_bullets` pattern)

**Given** `PROMPT_PROFILE=infra` is configured  
**When** any article is scored  
**Then** `contribution_type` and `re_document_type` may be null — the infra rubric does not require them  
**And** the scalar score behavior is unchanged from pre-augmentation baseline

---

### Story 2.2: Paper-Aware Enrichment Pipeline

As a **researcher**,
I want the system to automatically extract structured metadata from paper sources (arXiv, Semantic Scholar, OpenReview, ACL Anthology, DOI) before scoring,
So that the scorer receives rich structured context about each paper's methods, datasets, and contribution type.

**Acceptance Criteria:**

**Given** the extractor service has an existing `extract_arxiv` handler  
**When** this story is implemented  
**Then** `extractor.py` contains a `paper_handlers` dispatcher dict mapping URL patterns to source-specific handlers:
- `arxiv.org` → existing arXiv handler (refactored from `extract_arxiv`)
- `semanticscholar.org` → Semantic Scholar Graph API handler
- `openreview.net` → OpenReview handler
- `aclanthology.org` → ACL Anthology handler
- `doi.org` / any DOI URL → Crossref + Unpaywall handler

**Given** an article URL matches a paper source pattern  
**When** `enrich_paper_meta(url, extracted_content)` is called  
**Then** it returns a dict containing at minimum: `is_paper: true`, `paper_id`, `doi` (if available), `abstract`, `methods: []`, `datasets: []`, `metrics: []`  
**And** it makes a cheap single Ollama call (`OLLAMA_MODEL`) to classify the abstract into: `contribution_type`, `re_document_type`, `confidence` (0–1)  
**And** the result is stored as `paper_meta_json` on the article record

**Given** the Semantic Scholar API is unavailable or returns a non-200  
**When** enrichment runs  
**Then** the enricher falls back to the already-extracted content without error  
**And** `paper_meta_json` is set to `{"is_paper": true, "source": "fallback"}` — article is not lost

**Given** a non-paper URL (e.g., a blog post, Hacker News thread)  
**When** enrichment runs  
**Then** `enrich_paper_meta` returns `{}` (empty dict) within 50ms (no API call made)  
**And** `paper_meta_json` is left null on the article record

**Given** the `articles` database table  
**When** the migration runs  
**Then** a `paper_meta_json TEXT` nullable column exists  
**And** `ArticleOut` response includes a parsed `paper_meta` dict field

**Given** `SS_RATE_LIMIT_SECONDS=1.0` is configured  
**When** multiple articles are enriched in the same poll cycle  
**Then** Semantic Scholar API calls are spaced ≥ 1 second apart  
**And** enrichment does not block the polling scheduler from running on schedule

**Given** the poller calls `enrich_paper_meta` before `create_article`  
**When** `create_article` is called  
**Then** the `paper_meta_json`, `contribution_type` (from cheap enrichment), and `re_document_type` are included in the create payload  
**And** the scorer receives these pre-populated fields and can use them to adjust its scoring behavior

---

### Story 2.3: Research Feed Seeding & Article Filters

As a **researcher**,
I want paper-focused feeds pre-configured in the system and the ability to filter my article list by contribution type and RE document type,
So that research papers appear automatically in my reading list and I can triage them by their academic contribution category.

**Acceptance Criteria:**

**Given** the system initializes with default feeds  
**When** `init_db()` runs on a fresh database  
**Then** the following new feeds are present alongside existing defaults:
- arXiv cs.SE (Software Engineering): `https://arxiv.org/rss/cs.SE`
- arXiv cs.RO (Robotics): `https://arxiv.org/rss/cs.RO`
- arXiv cs.AI: present (if not already in defaults)
- Semantic Scholar feed for tracked topics (at minimum: requirements engineering, MBSE)

**Given** an authenticated researcher views the article list  
**When** they apply a `contribution_type` filter (e.g., `survey`)  
**Then** only articles with `contribution_type = 'survey'` are returned  
**And** existing filters (score range, feed, date) compose correctly with the new filters

**Given** an authenticated researcher views the article list  
**When** they apply a `re_document_type` filter (e.g., `elicitation`)  
**Then** only articles where `re_document_type = 'elicitation'` are returned  
**And** filtering by `re_document_type=none` returns articles with no RE classification

**Given** article cards are rendered in the list view  
**When** an article has a non-null `contribution_type`  
**Then** a `ContribTypeBadge` component displays the type with a distinct color per category:
- `method` → blue, `survey` → purple, `benchmark` → orange, `empirical` → green
- `theory` → indigo, `position` → yellow, `tool` → teal, `incident` → red, `tutorial` → gray, `news` → slate, `other` → neutral

**Given** article cards are rendered  
**When** an article has `re_document_type ∈ {elicitation, extraction, method}`  
**Then** a `ReDocTypeBadge` is displayed with a distinct amber/gold color to signal ARISE relevance  
**And** articles with `re_document_type = none` show no badge

**Given** `ContribTypeBadge` and `ReDocTypeBadge` components exist  
**When** `TypeScript` types are updated  
**Then** `types.ts` includes: `ContribType`, `REDocType`, `PaperMeta`, `ScoreMeta` interfaces matching the architecture specification

---

## Epic 3: Semantic Knowledge Layer — Discover Connections & Synthesize

The researcher can find related papers, explore topic clusters, generate literature-review syntheses, and maintain a typed research profile that improves scoring over time.

### Story 3.1: Semantic Retrieval & Related Panel

As a **researcher**,
I want the system to embed every article and show me related papers in a side panel when I'm reading,
So that I can discover connected work I may have missed, without leaving the reader.

**Acceptance Criteria:**

**Given** `chromadb>=0.4.22`, `numpy>=1.26` are added to `backend/api/requirements.txt`  
**When** the `api` service starts  
**Then** a ChromaDB client is initialized with persistence at `/data/chroma/` (Docker volume `data`)  
**And** an `articles` collection is created if it does not exist (metadata schema: `article_id`, `feed_id`, `contribution_type`, `re_document_type`, `score`, `created_at`)

**Given** an article is scored via `POST /api/internal/articles/{id}/score`  
**When** the score is persisted  
**Then** `asyncio.create_task(embed_article_async(article_id))` is called (non-blocking, fire-and-forget)  
**And** `embed_article_async` calls `POST {OLLAMA_URL}/api/embeddings` with model `OLLAMA_EMBED_MODEL` and the article's title + abstract/summary text  
**And** on success, the 768-dim vector is upserted into the Chroma `articles` collection and `embedding_indexed=1` is set on the article DB record  
**And** on any failure (Ollama unavailable, Chroma write error), the exception is caught, a warning is logged, and the article record is left with `embedding_indexed=0` — scoring is NOT affected

**Given** the `articles` table  
**When** the migration runs  
**Then** a `embedding_indexed INTEGER DEFAULT 0` nullable column exists

**Given** the embedder is running and articles have been indexed  
**When** `GET /api/articles/{id}/related?k=10` is called by an authenticated user  
**Then** the response is a JSON array of up to `k` articles, each with: `id`, `title`, `url`, `score`, `contribution_type`, `re_document_type`, `similarity` (float 0–1)  
**And** the response is returned in ≤ 2 seconds for a corpus of 10,000 articles  
**And** if the article has no embedding (`embedding_indexed=0`), a 404-equivalent empty array is returned (not a 500)

**Given** a researcher opens an article in `ReaderView`  
**When** the article panel loads  
**Then** a `RelatedPanel` component renders in the right sidebar showing up to 8 related articles  
**And** each related article card shows: title, similarity percentage, `ContribTypeBadge`, and score  
**And** clicking a related article navigates to it in the reader and the panel refreshes for the new article  
**And** if the article has no embedding, the panel shows an empty state: "Related papers not yet indexed"

---

### Story 3.2: Topic Cluster Map

As a **researcher**,
I want to see a map of how recent articles cluster by topic,
So that I can identify emerging research themes in my feeds at a glance and navigate to clusters I care about.

**Acceptance Criteria:**

**Given** `hdbscan>=0.8.33` is added to `backend/api/requirements.txt`  
**When** `GET /api/research/clusters?window_days=14&min_size=3` is called by an authenticated user  
**Then** the system fetches all articles with `embedding_indexed=1` within the last `window_days` days  
**And** runs HDBSCAN with `min_cluster_size=min_size` on their embedding vectors  
**And** returns a JSON array of cluster objects: `{cluster_id, size, centroid_title, top_tags: string[], article_ids: number[]}`  
**And** articles labeled as noise by HDBSCAN (cluster_id = -1) are omitted from the response  
**And** response time is ≤ 5 seconds for 500 articles

**Given** fewer than `min_size` articles have embeddings in the window  
**When** the clusters endpoint is called  
**Then** an empty array `[]` is returned with HTTP 200 (not an error)

**Given** the frontend Research tab exists (stub from Story 1.1)  
**When** cluster data is available  
**Then** a `ResearchDigestView` component renders cluster cards, each showing: cluster topic (centroid_title), article count, top 5 tags as chips  
**And** clicking a cluster card expands it to show the list of article titles within that cluster  
**And** clicking an article title navigates to it in the reader

**Given** the `research.ts` Zustand slice exists  
**When** the Research tab is opened  
**Then** `fetchClusters(windowDays)` is called and cluster state is populated  
**And** a window selector (14 / 30 / 60 days) allows the researcher to adjust the clustering window  
**And** the Zustand `ResearchStore` interface matches the architecture specification

---

### Story 3.3: Typed Researcher Profile

As a **researcher**,
I want to define and manage a typed research profile (topics, methods, domains, avoidances) with weights,
So that the scorer builds a personalized preference block from my actual research interests, and my 👍/👎 feedback automatically refines it.

**Acceptance Criteria:**

**Given** the `research_profile` table does not exist  
**When** `init_db()` runs  
**Then** the table is created with columns: `id`, `kind` (TEXT, `topic|method|domain|avoid`), `label` (TEXT), `weight` (REAL DEFAULT 1.0), `source` (TEXT DEFAULT `manual`), `created_at`  
**And** a unique index `ux_research_profile` on `(kind, label)` exists  
**And** running `init_db()` twice produces no error

**Given** the research profile table exists  
**When** `GET /api/research/profile` is called by an authenticated user  
**Then** the response is a JSON array of all `ResearchProfileEntry` objects  
**And** entries are ordered by `kind` then `weight DESC`

**Given** a researcher sends `PUT /api/research/profile` with an array of profile entries  
**When** the request is processed  
**Then** entries are upserted (insert or update on `(kind, label)` conflict)  
**And** the full updated profile is returned  
**And** entries with `weight=0` are deleted from the table

**Given** a researcher clicks 👍 on an article  
**When** the feedback is processed by `POST /api/internal/feedback`  
**Then** the `tags` from the article's `score_meta_json` are upserted into `research_profile` with `source='feedback'` and their weight incremented by 0.1 (capped at 5.0)  
**And** if a feedback-inferred entry already exists, its weight is incremented, not duplicated

**Given** the `research_profile` table has entries  
**When** the scorer calls `/api/internal/feedback-examples`  
**Then** the response includes a structured preference block built from `research_profile` entries, grouping by `kind`:
```
RESEARCH TOPICS (weight): llm-requirements(2.3), mbse(1.8), graphrag(1.5)
METHODS (weight): survey(1.2), case-study(0.9)
DOMAINS (weight): systems-engineering(2.0)
AVOID: devops-tooling(1.0), kubernetes(0.8)
```
**And** the existing tag-frequency block is preserved as a supplementary section for backward compatibility

**Given** the `ResearchProfileEditor` component renders in the Settings tab  
**When** a researcher views it  
**Then** they can see all profile entries grouped by kind (topics, methods, domains, avoid)  
**And** they can add a new entry by typing a label and selecting kind + weight  
**And** they can delete an entry (which sets `weight=0` on PUT)  
**And** changes are saved with an optimistic update that rolls back on API error

---

### Story 3.4: Literature-Review Mode

As a **researcher**,
I want to generate a structured literature-review synthesis for any topic across my reading history,
So that I can rapidly draft related-work sections with per-cluster synthesis, comparison tables, and research gap analysis — all from papers I've already read.

**Acceptance Criteria:**

**Given** the `literature_reviews` table does not exist  
**When** `init_db()` runs  
**Then** the table is created: `id`, `topic` (TEXT), `window_days` (INTEGER), `min_rigor` (REAL DEFAULT 0.0), `body_json` (TEXT), `created_at`

**Given** the embedder has indexed articles  
**When** `POST /api/research/review` is called with `{topic: string, window_days: int, min_rigor: float}`  
**Then** the system performs an embedding search for `topic` against the Chroma collection (top 50 candidates)  
**And** filters candidates by `min_rigor` (using `rigor` from `score_meta_json`)  
**And** runs HDBSCAN on candidate embeddings to produce clusters (`min_cluster_size=3`)  
**And** for each cluster, makes one LLM call to generate: synthesis paragraph, comparison table rows, up to 3 research gaps, and a top-cited work recommendation  
**And** the LLM call uses the three-tier routing: university GPU server → local Ollama → OpenRouter  
**And** the complete review is stored in `literature_reviews` table and returned in the response

**Given** fewer than 3 articles match the topic+rigor filter  
**When** the review endpoint is called  
**Then** HTTP 422 is returned with message: `"Not enough indexed articles match the criteria. Try a broader topic or lower rigor threshold."`

**Given** the LLM synthesis call fails for a cluster  
**When** the error is caught  
**Then** that cluster's `synthesis` field is set to `"[Synthesis unavailable — LLM error]"` and the review continues  
**And** the partial review (with error markers) is still stored and returned

**Given** a literature review has been generated  
**When** the researcher views the `LitReviewView` tab  
**Then** they see a topic input, `window_days` slider (14/30/60/90), and `min_rigor` slider (0.0–1.0)  
**And** clicking "Generate" shows a skeleton loading state while the review is generated  
**And** the completed review renders as cluster cards, each with: cluster label, synthesis paragraph, comparison table (work | method | dataset | key result), gaps list, top-cite recommendation  
**And** a "Export Markdown" button generates a `.md` file download of the full review

**Given** a researcher has generated at least one review  
**When** they return to the `LitReviewView`  
**Then** they see a "Past Reviews" list with topic + date for each stored review  
**And** clicking a past review loads it from the `literature_reviews` table without regenerating

**Given** end-to-end synthesis for 24 articles across 4 clusters  
**When** measured on the local Ollama tier (M5 Max)  
**Then** total response time is ≤ 60 seconds (NFR4)

---

## Epic 4: ARISE Pipeline Bridge & Admin Tooling

The researcher or an external ARISE script can pull a structured JSON export of all requirement-rich documents. Rubric changes can be applied retroactively. The research profile is git-trackable.

### Story 4.1: ARISE Export Endpoint

As a **researcher** (or an automated ARISE pipeline),
I want to export all articles classified as requirement-rich (`re_document_type ∈ {elicitation, extraction, method}`) as structured JSON,
So that downstream ARISE pipelines can ingest pre-classified, enriched requirement documents without manual curation.

**Acceptance Criteria:**

**Given** an authenticated user calls `POST /api/research/export-arise` with body `{since: "2026-01-01T00:00:00Z"}`  
**When** the request is processed  
**Then** the response is a JSON array of articles where `re_document_type IN ('elicitation', 'extraction', 'method')` and `published_at >= since`  
**And** each article object contains exactly: `id`, `title`, `url`, `published_at`, `re_document_type`, `contribution_type`, `paper_meta` (parsed from `paper_meta_json`), `content_text`, `score_meta` (parsed from `score_meta_json`), `feed_name`, `tags`  
**And** if `paper_meta` or `score_meta` is null, an empty object `{}` is used (never null in the response)

**Given** no articles match the `since` date + `re_document_type` filter  
**When** the export endpoint is called  
**Then** an empty array `[]` is returned with HTTP 200

**Given** an unauthenticated request reaches the ARISE export endpoint  
**When** the request is processed  
**Then** HTTP 401 is returned (consistent with all other protected routes)

**Given** the `since` parameter is missing or malformed  
**When** the request is processed  
**Then** HTTP 422 is returned with a clear validation error (Pydantic handles)

**Given** a researcher inspects the export schema  
**When** they compare it to NFR15  
**Then** all required fields from the NFR15 schema are present in the response: `{id, title, url, published_at, re_document_type, contribution_type, paper_meta, content_text, score_meta, feed_name, tags}`

---

### Story 4.2: Admin Tooling — Rescore, Reindex & Profile Export

As a **researcher / administrator**,
I want to retroactively rescore articles after changing my scoring rubric, reindex all articles into the embedding store, and export my research profile as a versioned YAML file,
So that I can apply improvements backwards across my reading history and keep my research profile under version control.

**Acceptance Criteria:**

**Given** an authenticated user calls `POST /api/admin/rescore` with body `{since: "2026-01-01T00:00:00Z"}`  
**When** the request is processed  
**Then** all articles with `published_at >= since` are queued for re-scoring via the existing internal score endpoint  
**And** the response returns `{queued: N, since: "..."}` immediately (async queue, not blocking)  
**And** rescoring jobs run with the same `SCORE_DELAY_SECONDS` rate limiting as the normal pipeline  
**And** existing score data is overwritten with the new score result

**Given** an authenticated user calls `POST /api/admin/reindex-all`  
**When** the request is processed  
**Then** all articles with `embedding_indexed=0` are queued for embedding generation  
**And** the response returns `{queued: N}` immediately  
**And** embedding jobs run as background tasks via `asyncio.create_task` without blocking the API

**Given** an authenticated user calls `GET /api/research/profile/export`  
**When** the request is processed  
**Then** the response is a YAML file download (`Content-Disposition: attachment; filename="research-profile-{date}.yaml"`)  
**And** the YAML contains all `research_profile` entries grouped by `kind`, with `label`, `weight`, and `source` per entry  
**And** a `version` field and `exported_at` timestamp are included at the top level

**Given** `POST /api/admin/rescore` or `POST /api/admin/reindex-all` are called  
**When** the request is authenticated  
**Then** the session auth check (`Depends(require_session)`) is enforced — no unauthenticated access  
**And** these routes live in `backend/api/routers/admin.py`, not in `main.py`

**Given** an `UNI_OLLAMA_URL` is configured and VPN is active  
**When** any LLM call is made during rescore or reindex  
**Then** the three-tier routing is used: `llm_client.py` checks university server health (cached 5 min) → falls through to local Ollama → falls through to OpenRouter  
**And** `llm_tier_used` is logged in structlog for every LLM call

