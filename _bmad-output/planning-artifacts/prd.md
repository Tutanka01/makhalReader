---
stepsCompleted: [step-01-init, step-02-discovery, step-02b-vision, step-02c-executive-summary, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish]
inputDocuments:
  - "_bmad-output/planning-artifacts/product-brief-daily_news_wrap.md"
  - "_bmad-output/planning-artifacts/product-brief-daily_news_wrap-distillate.md"
  - "Session BMAD Brief + Repository Analysis (prior turn)"
  - "backend/api/database.py"
  - "backend/scorer/scorer.py"
  - "backend/scorer/prompt.py"
  - "backend/extractor/extractor.py"
  - "backend/poller/main.py"
  - "backend/api/main.py"
  - "docker-compose.yml"
workflowType: 'prd'
classification:
  projectType: 'brownfield-web-app-augmentation'
  domain: 'AI-assisted research tooling / knowledge management'
  complexity: 'high'
  projectContext: 'brownfield'
---

# Product Requirements Document
# Baṣīra — Research-Oriented Intelligent Literature Monitor

**Author:** Arona  
**Date:** 2026-04-22  
**Status:** Draft v1.0  
**Project Type:** Brownfield augmentation — existing RSS reader system  

---

## Executive Summary

The existing system is an operational self-hosted RSS reader that uses LLM scoring to surface high-value technical articles. The system works well for its original DevOps/infrastructure audience but actively misclassifies research artifacts — surveys, benchmark papers, position papers, and cross-disciplinary methods papers score poorly despite being the backbone of a PhD-level literature review.

This PRD specifies the incremental augmentation of the existing system into **Baṣīra** (بَصِيرَة — *deep insight*): a **research-oriented intelligent literature monitoring system**. The augmentation preserves the entire existing architecture (6 Docker services, SQLite WAL, FastAPI, React/Vite) and adds a research-awareness layer through seven stories: a router refactor (prerequisite), research-aware scoring, paper-level enrichment, semantic retrieval, typed researcher profile, literature-review mode, and ARISE pipeline export.

The system's primary user is a PhD-level researcher/engineer working on AI-driven Requirements Engineering, MBSE with Arcadia/Capella, Systems-of-Systems, and agentic/GraphRAG architectures. All LLM operations support three tiers: local Ollama (M5 Max, 36 GB), university GPU server (`https://llm.eva.univ-pau.fr/v1`, VPN), and OpenRouter (cloud fallback). No article content may leave the machine without explicit configuration.

---

## Product Vision

**What makes Baṣīra special:** Every other literature monitoring tool requires the researcher to either maintain a curated list manually (Semantic Scholar alerts, Zotero feeds) or accept a general-purpose search with no personalization. The underlying reader already solves the triage problem with personalized LLM scoring. Baṣīra extends that intelligence to understand *what kind of contribution* a paper makes, *how novel* it is relative to the researcher's tracked topics, and *how it relates* to everything else already read — enabling synthesis, not just curation.

**Core insight:** Ingest-time enrichment (cheap, structured, one-shot) plus query-time retrieval (embeddings + LLM synthesis) is strictly more powerful than scoring-at-ingest-only. The existing system does the expensive thing at ingest (LLM call) but nothing at query time. Baṣīra keeps the ingest score and adds the query-time intelligence.

**Why now:** The researcher has an active, working system with real reading history. Adding a research profile, enrichment, and retrieval on top of existing data creates immediate value from day one — the embedding index can retroactively process the entire article history on first run. With an M5 Max (36 GB), local inference is fast enough to make this practical without any cloud cost.

---

## Success Criteria

### User Success

- The researcher can discover related papers to any article they are reading within Baṣīra, without leaving the reader.
- The researcher can generate a draft literature-review synthesis for any topic within Baṣīra, grouping by contribution cluster and identifying research gaps, in under 60 seconds.
- Research-relevant articles (papers on tracked topics) consistently appear in the score ≥ 7 tier, not buried in the 3–5 range as they are today.
- The researcher can export a filtered set of requirement-rich documents (re_document_type ≠ none) as structured JSON for consumption by downstream ARISE-style pipelines.

### Business / Research Success

| Metric | Target | Measurement Method |
|---|---|---|
| Research-relevant articles in score ≥ 7 tier | +40% vs baseline over 2-week window | Compare 👍 rate on papers vs baseline period |
| `re_document_type` classification macro-F1 | ≥ 0.80 | 50-item manually labeled test set |
| Related-paper recall@10 | ≥ 0.60 | 20 seed articles with known related work (manual ground truth) |
| Literature review usefulness (self-rated 1–5) | ≥ 4.0 mean on coverage + accuracy | Researcher self-assessment after each generated review |
| Token cost per article (ingest) | ≤ 2× baseline | Log tokens in scorer per article |
| DevOps article score quality (no regression) | Existing 👍/👎 feedback accuracy ±5% | Weekly comparison to pre-augmentation baseline |

### Technical Success

- All additive DB migrations execute idempotently on the existing `makhal.db` without data loss.
- `PROMPT_PROFILE=infra` produces identical scoring behavior to the current system (backward compatibility test).
- Embedding index can be populated from all existing articles in a single background task without blocking the polling cycle.
- All new LLM calls have a working Ollama fallback — no new dependency on external APIs.

---

## Product Scope

### MVP — Stories 1–3 (Core research intelligence)

**Story 1 — API Router Refactor (prerequisite)**
- Split `backend/api/main.py` (1266 LOC) into `routers/`: articles, feeds, highlights, ask, stats, admin, internal, research
- Zero behavior change; pure code organization
- Required before any new endpoints can be added cleanly

**Story 2 — Research-Aware Scoring**
- `PROMPT_PROFILE` env var (`infra | research | unified`, default `unified`)
- Prompt files stored in `backend/scorer/prompts/` folder
- Extended `ScoreResult`: scalar + `contribution_type`, `re_document_type`, `novelty`, `rigor`, `relevance_to_topics`
- New DB columns: `score_meta_json TEXT`, `re_document_type VARCHAR(24)`, `contribution_type VARCHAR(24)` (all nullable)
- Content cap: configurable `SCORER_MAX_CHARS` env var (default 6000, auto-raised to 12000 when `is_paper=true`)
- Extended internal score endpoint to persist structured fields

**Story 3 — Paper-Aware Enrichment**
- Paper handler dispatcher in `extractor.py` (mirrors existing `extract_arxiv` strategy)
- New handlers: Semantic Scholar Graph API, OpenReview, ACL Anthology, DOI/Crossref + Unpaywall
- Cheap Ollama enrichment pass on every abstract: outputs `paper_meta_json` (methods, datasets, metrics, contribution_type, re_document_type, confidence)
- New DB column: `paper_meta_json TEXT` (nullable)
- New default feeds: arXiv cs.SE, cs.RO; Semantic Scholar RSS for tracked topics

### Growth — Stories 4–6 (Knowledge layer + synthesis)

**Story 4 — Semantic Retrieval**
- Embedder background task in `api` service (Ollama `nomic-embed-text` → ChromaDB at `/data/chroma/`)
- Runs after score-time; retroactive indexing of existing articles via admin endpoint
- New API endpoints: `GET /api/articles/{id}/related?k=10`, `GET /api/research/clusters?window_days=14&min_size=3`
- Frontend: Related panel in `ReaderView`; Cluster map in a new Research tab

**Story 5 — Typed Researcher Profile**
- New `research_profile` table: `(id, kind, label, weight, source, created_at)`
  - `kind ∈ {topic, method, domain, avoid}`
  - `source ∈ {manual, feedback}` — feedback-inferred entries from 👍/👎 history
- CRUD API: `GET/PUT /api/research/profile`
- Scorer's `build_preference_block` renders from typed profile (replaces flat tag-frequency block)
- Frontend: Settings → Research Profile editor panel

**Story 6 — Literature-Review Mode**
- New `literature_reviews` table: `(id, topic, window_days, body_json, created_at)`
- New endpoint: `POST /api/research/review` — embedding retrieval → HDBSCAN clustering → per-cluster LLM synthesis
- Synthesis format per cluster: synthesis paragraph, comparison table (work | method | dataset | key result), gaps bullets, most-citable recommendation
- Frontend: `LitReviewView` tab — topic input + time window + rigor filter → grouped Markdown synthesis with cluster cards

### Vision — Story 7 (ARISE bridge)

**Story 7 — ARISE Export & Admin Tooling**
- `POST /api/research/export-arise?since=ISO_DATE` — exports articles where `re_document_type ∈ {elicitation, extraction, method}` as structured JSON
- `POST /api/admin/rescore?since=ISO_DATE` — queues rescoring of articles after rubric change
- `GET /api/research/profile/export` — exports research profile as a versioned YAML file for git tracking

---

## User Journeys

### Journey 1: Daily Research Triage

**Actor:** Researcher, morning reading session  
**Pre-condition:** System has polled overnight; 20–40 new articles available

1. Opens Baṣīra; sees article list sorted by `scalar` score descending
2. Articles from arXiv cs.AI, cs.SE, Semantic Scholar now appear in the 7–9 range alongside infra posts
3. Each article card shows: score, `contribution_type` badge (METHOD / SURVEY / BENCHMARK), `re_document_type` badge (ELICITATION / EXTRACTION — for ARISE-relevant items), and structured summary bullets
4. Researcher reads a paper on LLM-based requirement extraction, marks it 👍
5. The feedback updates the `research_profile` table, adding weight to "requirement-extraction" topic

### Journey 2: Literature Review Sprint

**Actor:** Researcher, writing a related-work section  
**Pre-condition:** 3+ weeks of articles accumulated; researcher is writing a section on GraphRAG for MBSE

1. Opens Literature-Review tab; enters topic "GraphRAG for model-based systems engineering"
2. Sets window to 60 days, minimum rigor 0.6
3. Clicks Generate
4. System: embedding search retrieves 24 related articles; HDBSCAN produces 4 clusters
5. System generates per-cluster synthesis (LLM call per cluster, ~30s total)
6. Researcher sees: 4 cluster sections with synthesis, comparison table, gaps, and most-citable picks
7. Researcher exports the review as Markdown for pasting into their LaTeX paper
8. Saves the review to `literature_reviews` table for future reference

### Journey 3: ARISE Pipeline Feeding

**Actor:** Researcher / automated ARISE pipeline  
**Pre-condition:** Articles have been ingested and enriched with `re_document_type`

1. ARISE script calls `POST /api/research/export-arise?since=2026-04-01`
2. System returns JSON array: `[{title, url, re_document_type, contribution_type, paper_meta, content_text, score_meta, published_at}, ...]`
3. ARISE pipeline ingests the export, classifies requirement statements, builds traceability graph
4. New requirement-rich documents detected automatically going forward as poll cycles run

### Journey 4: Related Work Discovery

**Actor:** Researcher, reading a specific paper  
**Pre-condition:** Embedder has indexed the article history

1. Researcher opens a paper on Capella transformation rules
2. Related panel (right sidebar) shows 8 nearest neighbors with similarity scores and contribution type badges
3. Researcher clicks a related paper — opens in the reader instantly
4. Related panel updates to show neighbors of the newly opened paper

---

## Domain & Technical Context

### Brownfield System Inventory

The system is fully operational. The following table maps the relevant existing extension points:

| Extension Point | File | Current Behavior | Augmentation |
|---|---|---|---|
| Scoring rubric | `backend/scorer/prompt.py` | Single hard-coded DevOps profile | Replace with loader; add `prompts/unified.md` |
| Scoring result | `backend/scorer/scorer.py::ScoreResult` | `{score, tags, summary_bullets, reason}` | Add `contribution_type`, `re_document_type`, `novelty`, `rigor`, `relevance_to_topics` |
| Content cap | `scorer.py` line 246 | Hard-coded 3000 chars | `SCORER_MAX_CHARS` env var, paper-aware |
| Extractor dispatcher | `extractor.py` Strategy 0 | ArXiv only | Add SS, OpenReview, ACL, DOI handlers |
| DB migrations | `api/database.py::init_db` | Additive try/except pattern | Add 6 new nullable columns + 3 new tables |
| Feedback profile | `api/main.py::internal_feedback_examples` | Tag-frequency aggregation | Return typed profile from `research_profile` table |
| Article list API | `api/main.py::list_articles` | Sort by score/date | Add filter by `re_document_type`, `contribution_type` |
| Frontend router | `App.tsx` | Articles / Digest / Stats tabs | Add Research / Lit-Review tabs |

### Integration Points

**LLM Stack — three tiers (priority order):**

1. **Local Ollama** (Apple M5 Max, 36 GB RAM, 2 TB disk)
   - Primary for all enrichment and embedding operations (always available, always private)
   - `/api/embeddings` with `nomic-embed-text` — embedding generation
   - `/api/chat` with a small model (e.g., `qwen2.5:7b` or `mistral`) — cheap abstract enrichment
   - Can run `llama3.3:70b` or `qwen2.5:72b` locally for high-quality scoring if desired
   - Configured via existing `OLLAMA_URL` + `OLLAMA_MODEL`

2. **University GPU Server** (`https://llm.eva.univ-pau.fr/v1`, OpenAI-compatible API, VPN required)
   - GPU-accelerated; for heavier inference (lit-review synthesis, complex scoring)
   - Configured via new env var: `UNI_OLLAMA_URL=https://llm.eva.univ-pau.fr/v1`
   - Scorer/synthesizer tries this tier when VPN is active (health-checked before use)
   - New env var: `UNI_OLLAMA_MODEL` — model name as listed at `/v1/models`

3. **OpenRouter** (cloud fallback, requires `OPENROUTER_API_KEY`)
   - Used when VPN unavailable and local model quality is insufficient
   - Existing path — unchanged

**ChromaDB (new local dependency):**
- File-based persistence at `/data/chroma/` (same Docker volume as SQLite)
- No new Docker service needed; `chromadb` Python package added to `api` service requirements
- Collection per article corpus; metadata filtering by `feed_id`, `contribution_type`, `score`

**Semantic Scholar Graph API (external, optional):**
- Unauthenticated requests: 100/5min rate limit — sufficient for enrichment at current ingest rate
- Returns: abstract, authors, year, citation count, open-access PDF URL, references
- Fallback: use RSS abstract if API unavailable

**OpenAlex / Crossref (external, optional):**
- DOI metadata resolution via Crossref: title, abstract, authors, journal, open-access status
- Unpaywall for PDF URL resolution
- Both free, no API key required at research ingest volumes

---

## Innovation Patterns

### Pattern 1: Two-Stage Ingest Intelligence
Separate *cheap classification* (Ollama, ~100 tokens, deterministic) from *expensive scoring* (OpenRouter/Ollama, ~800 tokens, personalized). Classification runs first and gates scoring priority. High-`re_document_type` articles get elevated scoring priority; noise gets deprioritized before the expensive call.

### Pattern 2: Retroactive Knowledge Base
On first run of the embedder, index all existing articles. The researcher immediately has semantic retrieval over their entire reading history, not just new content. This is a one-time cost amortized over the entire existing corpus.

### Pattern 3: Feedback → Profile → Scoring Loop
👍/👎 feedback updates `research_profile` with `source=feedback` entries. These feed the scorer's preference block on the next poll cycle. The loop is: read → react → profile updates → next article scored with updated profile. No retraining, no fine-tuning — pure prompt engineering driven by structured feedback.

### Pattern 4: ARISE as Passive Consumer
The ARISE export endpoint makes this system a passive producer: it enriches and classifies articles continuously; ARISE (or any downstream pipeline) pulls what it needs on demand. No coupling, no webhook, no push — pull-based integration is more resilient and easier to debug.

---

## Functional Requirements

### Article Ingestion & Enrichment

- FR1: System can ingest articles from RSS feeds including arXiv, Semantic Scholar, ACL Anthology, OpenReview, and DOI landing pages via the existing poller scheduler.
- FR2: System can extract structured paper metadata (abstract, authors, methods, datasets, metrics) from paper source URLs using source-specific handlers.
- FR3: System can classify each ingested article with a `contribution_type` value (method, benchmark, survey, empirical, theory, position, tool, incident, tutorial, news, other).
- FR4: System can classify each ingested article with a `re_document_type` value (elicitation, extraction, method, none) to identify requirement-rich sources.
- FR5: System can store extracted paper metadata in a `paper_meta_json` field alongside the existing article record.
- FR6: System can apply a configurable content length cap for scoring, with an automatic increase when an article is classified as a paper.

### Scoring & Ranking

- FR7: System can score articles using a configurable scoring profile selected via the `PROMPT_PROFILE` environment variable, supporting at minimum `infra`, `research`, and `unified` profiles.
- FR8: System can return a multi-dimensional score object per article including: scalar, relevance, novelty, rigor, contribution_type, re_document_type, tags, summary_bullets, and reason.
- FR9: System can store the structured score metadata in a `score_meta_json` field per article.
- FR10: Researcher can filter the article list by `contribution_type` and `re_document_type` in addition to existing filters.
- FR11: System can display `contribution_type` and `re_document_type` badges on article cards in the list and reader views.

### Semantic Retrieval & Clustering

- FR12: System can generate and store a vector embedding for each article using a local embedding model.
- FR13: System can retrieve the k nearest neighbor articles for any given article by embedding similarity.
- FR14: System can cluster recent articles by semantic similarity and return cluster summaries (centroid topic, size, representative articles, top tags).
- FR15: Researcher can view related articles for any open article in a dedicated panel within the reader view.
- FR16: System can retroactively generate embeddings for all existing articles via an admin endpoint.

### Researcher Profile

- FR17: Researcher can define a typed research profile specifying tracked topics, methods, domains, and avoidance signals with individual weights.
- FR18: System can automatically update the research profile with feedback-inferred entries derived from the researcher's 👍/👎 history.
- FR19: Scorer can use the typed researcher profile to build a structured preference block for LLM prompts, replacing the flat tag-frequency aggregation.
- FR20: Researcher can view and edit the research profile through a dedicated settings panel in the frontend.
- FR21: Researcher can export the research profile as a versioned YAML file for external use or version control.

### Literature-Review Mode

- FR22: Researcher can initiate a literature review synthesis for a user-defined topic, time window, and minimum rigor threshold.
- FR23: System can retrieve semantically relevant articles for the specified topic using embedding search.
- FR24: System can cluster retrieved articles and generate per-cluster synthesis including: synthesis paragraph, comparison table (work | method | dataset | key result), research gaps (3 bullets max), and most-citable work recommendation.
- FR25: Researcher can view the generated literature review as a structured, formatted document within the frontend.
- FR26: Researcher can export the generated review as Markdown.
- FR27: System can persist generated literature reviews in a `literature_reviews` table for future retrieval and reference.

### ARISE Export & Admin

- FR28: Researcher (or external pipeline) can export all articles with `re_document_type ∈ {elicitation, extraction, method}` as structured JSON via a dedicated API endpoint, filtered by date range.
- FR29: Administrator can trigger rescoring of articles from a specified date forward, allowing rubric changes to be applied retroactively.
- FR30: System can add new paper-focused RSS feeds (arXiv cs.SE, cs.RO; Semantic Scholar feeds) as default feeds alongside existing infra/AI feeds.

---

## Non-Functional Requirements

### Performance

- NFR1: Article ingest-to-score latency (from RSS publication to article visible with score) p50 ≤ 3 minutes, p95 ≤ 8 minutes, measured under normal load (63 feeds, FETCH_INTERVAL_MINUTES=720).
- NFR2: Embedding generation per article ≤ 500ms on CPU-only Ollama; total indexing of 5000 existing articles ≤ 30 minutes for retroactive pass.
- NFR3: Related-paper API response ≤ 2 seconds for k=10 over a 10,000-article corpus.
- NFR4: Literature-review synthesis for 24 articles across 4 clusters ≤ 60 seconds end-to-end.
- NFR5: Token cost per article after full enrichment pipeline ≤ 2× baseline (baseline = current single scorer call).

### Security & Privacy

- NFR6: All article content, embeddings, and research profile data are stored locally; no data leaves the system unless OpenRouter is explicitly configured via `OPENROUTER_API_KEY`.
- NFR7: The ARISE export endpoint requires session authentication (same as all other protected routes); no unauthenticated access.
- NFR8: All new internal service-to-service endpoints require the `X-Internal-Secret` header, consistent with existing internal routes.

### Reliability

- NFR9: Embedding service failure must not block article ingest or scoring; embedding is a non-blocking post-processing step with graceful degradation (article stored and scored without embedding; embedding queued for retry).
- NFR10: Paper handler failures (Semantic Scholar API unavailable, DOI lookup fails) must fall back to the existing extraction strategy without losing the article.
- NFR11: All new DB migrations must execute idempotently; running `init_db()` on an already-augmented database must produce no error and no data loss.

### Maintainability

- NFR12: `PROMPT_PROFILE=infra` must produce scoring behavior statistically indistinguishable (±5% feedback accuracy) from the pre-augmentation system on a held-out test set.
- NFR13: Each new scorer profile is a standalone Markdown file in `backend/scorer/prompts/` — no code change required to add or modify a profile.
- NFR14: The `api/main.py` router split must be completed (Story 1) before any research endpoints are added; no new endpoints may be added to the monolithic `main.py`.

### Integration

- NFR15: The ARISE export JSON schema must include at minimum: `{id, title, url, published_at, re_document_type, contribution_type, paper_meta, content_text, score_meta, feed_name, tags}` per article.
- NFR16: ChromaDB persistence is file-based at `/data/chroma/`; no separate database server is required; the existing `data` Docker volume is extended, not replaced.

---

## Technical Architecture Notes

> _Architectural decisions are deferred to the Architecture Document. The following are constraints the architecture must satisfy._

- Must maintain 6-service Docker Compose topology (api, poller, extractor, scorer, frontend, caddy) — no new required services for MVP Stories 1–3. Embedder runs as a background task within the `api` service.
- SQLite WAL remains the sole persistent store for article data; ChromaDB is an auxiliary index, not authoritative.
- All new Python dependencies are added to the relevant service's `requirements.txt`; no changes to Dockerfiles are required beyond dependency installation.
- The `research_profile` table is the authoritative source for scorer personalization in Stories 5+; tag-frequency aggregation in `/api/internal/feedback-examples` is preserved for backward compatibility but its output is supplemented (not replaced) until Story 5 is complete.

---

## Open Questions

1. **Embedder placement:** Background task inside `api` service vs. a 7th Docker service. Decision deferred to Architecture Document. Recommendation: background task first; extract to service if CPU contention is measured.
2. **Clustering algorithm:** HDBSCAN vs. spectral clustering for topic clusters. Validate empirically with first two weeks of data; default to HDBSCAN (density-based, handles noise class, no k required).
3. **Literature review trigger:** User-triggered only (v1) vs. automatic weekly digest (v2). v1 is user-triggered.
4. **`re_document_type` labeling:** The 50-item evaluation set must be hand-labeled by the researcher. This is a one-afternoon investment; without it, F1 measurement is impossible.
5. **Semantic Scholar API rate limit:** 100 req/5min unauthenticated. At `MAX_NEW_ARTICLES_PER_FEED=5` and 63 feeds, worst-case is 315 articles per poll cycle. SS lookup is only triggered for paper-source URLs (arXiv, SS, DOI), not blog posts — so practical rate is well within limits. Monitor and add API key if needed.

---

## Appendix: Existing System Summary (Brownfield Reference)

| Component | Current State |
|---|---|
| `backend/scorer/prompt.py` | Single-string SYSTEM_PROMPT, DevOps/infra profile, hardcoded |
| `backend/scorer/scorer.py` | `ScoreResult{score, tags, summary_bullets, reason}`, 3000-char truncation, builds tag-frequency preference block |
| `backend/extractor/extractor.py` | Strategy 0 (arXiv), 1 (direct), 2 (Google cache), 3 (Wayback). Substack + canonical URL support |
| `backend/poller/main.py` | APScheduler, 720min interval, MAX_NEW_PER_FEED=5, MAX_ARTICLE_AGE_DAYS=7, URL normalizer |
| `backend/api/main.py` | 1266 LOC monolith, 30+ routes, SSE broadcast, Ask-AI streaming |
| `backend/api/database.py` | SQLite WAL, tables: feeds, articles, highlights, auth_sessions. Additive migration pattern |
| `frontend/src/App.tsx` | Auth gate, tab routing (Articles, Digest, Stats, Highlights), Zustand stores |
