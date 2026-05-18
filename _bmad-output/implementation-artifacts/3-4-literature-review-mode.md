---
epic: 3
story: 4
story_key: "3-4-literature-review-mode"
---

# Story 3.4: Literature-Review Mode

Status: review

<!-- Ultimate context engine analysis completed — comprehensive developer guide created -->

## Story

As a **researcher**,
I want to generate a structured literature-review synthesis for any topic across my reading history,
So that I can rapidly draft related-work sections with per-cluster synthesis, comparison tables, and research gap analysis — all from papers I've already read.

---

## Acceptance Criteria

**AC 1 — DB: `literature_reviews` table (idempotent)**

**Given** the `literature_reviews` table does not exist  
**When** `init_db()` runs  
**Then** the table is created with columns: `id` (INTEGER PK AUTOINCREMENT), `topic` (TEXT NOT NULL), `window_days` (INTEGER NOT NULL), `min_rigor` (REAL NOT NULL DEFAULT 0.0), `body_json` (TEXT NOT NULL), `created_at` (DATETIME)  
**And** running `init_db()` twice produces no error and no data loss  

[Source: `_bmad-output/planning-artifacts/architecture.md` — SQLite schema block; `epics.md` Story 3.4]

---

**AC 2 — API: `POST /api/research/review` (generate + persist)**

**Given** the embedder has indexed articles (`embedding_indexed = 1`) and Chroma contains their vectors  
**When** an authenticated client calls `POST /api/research/review` with JSON body `{ "topic": string, "window_days": int, "min_rigor": float }`  
**Then** the server:

1. **Embeds** the `topic` string using the same mechanism as `embedder.py` (`POST {OLLAMA_URL}/api/embeddings`, model `OLLAMA_EMBED_MODEL`) — if embedding fails, return HTTP `503` with a clear message (do not crash).
2. **Queries Chroma** for the top **50** nearest article IDs by cosine distance (reuse `_get_chroma()` from `embedder.py`; deferred import pattern preserved).
3. **Loads** matching `Article` rows from SQLite and **filters** to:
   - `embedding_indexed == 1`
   - `created_at >= now() - window_days` (use timezone-aware UTC, same pattern as `get_clusters` in `research.py`)
   - `score_meta_json` parses to a dict whose `rigor` key (if present) is `>= min_rigor`; if `rigor` is **missing** or **null**, treat rigor as **`0.0`** for filtering purposes (strict threshold semantics).
4. If **fewer than 3** articles remain after step 3 → **`HTTP 422`** with detail exactly:  
   `"Not enough indexed articles match the criteria. Try a broader topic or lower rigor threshold."`
5. **Clusters** the remaining candidate embeddings with **HDBSCAN** `min_cluster_size=3` (deferred `import hdbscan`, `numpy` — same pattern as `GET /api/research/clusters`). **Exclude** noise label `-1` from cluster list.
6. **Fallback when all labels are noise** but step 4 passed (≥3 candidates): treat **all filtered candidates** as a **single synthetic cluster** with `cluster_label` = first 80 chars of `topic` (trimmed), so synthesis always has at least one cluster row (prevents empty `body_json` clusters array).
7. **For each** (non-empty) cluster, performs **one** LLM completion that returns structured JSON for:
   - `synthesis` (string paragraph)
   - `comparison_table` (array of objects: `work`, `method`, `dataset`, `key_result` — strings, may be empty strings if unknown)
   - `gaps` (array of strings, max 3 items enforced server-side after parse)
   - `top_cite` (string — one recommended work to read first)
   - Plus persist `article_ids: int[]` for that cluster (member article IDs) in the stored JSON (required for navigation from UI — extends architecture `ReviewCluster` with `article_ids`).
8. **LLM routing** for each cluster call (epics order): **University GPU** → **local Ollama** → **OpenRouter**:
   - **Tier 1:** If `UNI_OLLAMA_URL` and `UNI_OLLAMA_MODEL` are set, `POST {UNI_OLLAMA_URL}/chat/completions` (OpenAI-compatible), non-streaming, with 5-minute **health cache** (if health fails, fall through — do not block the request indefinitely).
   - **Tier 2:** `POST {OLLAMA_URL}/api/chat` (native Ollama API, `stream: false`) — mirror timeouts from `ask.py` / `scorer.py` (~60–120s per call).
   - **Tier 3:** OpenRouter `POST https://openrouter.ai/api/v1/chat/completions` if `OPENROUTER_API_KEY` looks valid (`sk-` prefix), same pattern as `backend/scorer/scorer.py`.
9. **Persists** one row in `literature_reviews` (`topic`, `window_days`, `min_rigor`, `body_json` = JSON array of cluster objects matching the response schema below, `created_at`).
10. **Returns** HTTP `200` with the full saved review object including new `id` and `created_at`.

**On per-cluster LLM failure:** catch exception, set that cluster's `synthesis` to `"[Synthesis unavailable — LLM error]"`, leave other fields best-effort (empty arrays / empty `top_cite` acceptable), **continue** remaining clusters, still **persist** the partial review and return it.

[Source: `epics.md` Story 3.4; `architecture.md` API table + `literature_reviews` schema; `backend/api/routers/research.py` clustering patterns; `.env` / README for `UNI_OLLAMA_*`]

---

**AC 3 — API: list + fetch past reviews (no regeneration)**

**Given** at least one literature review exists  
**When** `GET /api/research/reviews` is called (authenticated)  
**Then** the response is a JSON array of summary objects: `{ id, topic, window_days, min_rigor, created_at }` ordered by `created_at` descending  

**When** `GET /api/research/reviews/{review_id}` is called  
**Then** the full review is returned (same shape as `POST` response) loaded **only** from SQLite — **no** re-embedding, **no** LLM calls  

**When** `review_id` does not exist → `HTTP 404`

---

**AC 4 — Frontend: `LitReviewView` + store + types**

**Given** the researcher opens the **Lit Review** tab (new `appView` value, e.g. `'litreview'`, alongside existing feed/digest/stats/research)  
**When** the view loads  
**Then** they see: topic text input, `window_days` control (**14 / 30 / 60 / 90** — match or exceed epic; default 30), `min_rigor` slider **0.0–1.0** (step 0.05), **Generate** button  

**When** Generate is clicked  
**Then** a **skeleton** loading state is shown until `POST /api/research/review` completes (success or error toast / inline message)  

**When** the review succeeds  
**Then** the UI renders **cluster cards**; each card shows: `cluster_label`, synthesis paragraph, **comparison table** (columns Work | Method | Dataset | Key result), bullet list for `gaps`, **Top cite** line  
**And** clicking an article reference (if you expose titles under cluster — optional enhancement) or a dedicated "Open in reader" per `article_ids` navigates like `ResearchDigestView` (`onSelect` / `handleSelectArticle`)  

**And** an **Export Markdown** button builds a `.md` file client-side from the current review JSON and triggers browser download (`Blob` + temporary `<a download>`), filename safe from topic slug + date  

**When** the user returns to the tab  
**Then** a **Past Reviews** sidebar or list shows `topic` + `created_at` from `GET /api/research/reviews`  
**And** clicking an item calls `GET /api/research/reviews/{id}` and renders without regenerating  

[Source: `architecture.md` — `LitReviewView.tsx`, `research.ts` `reviews` + `generateReview`; `epics.md` AC]

---

**AC 5 — NFR4 note (informational, not a CI gate)**

End-to-end synthesis for ~24 articles across ~4 clusters should target **≤ 60s** on local Ollama tier when VPN tier is unavailable. Document expected bottlenecks (sequential per-cluster LLM calls); **optional** follow-up: parallelize cluster LLM calls with `asyncio.gather` + semaphore — **only** if it does not violate rate limits or overwhelm Ollama. Default implementation may be **sequential** for simplicity.

---

## Tasks / Subtasks

### Task 1 — Backend: `LiteratureReview` ORM + migration (`database.py`) (AC: 1)
- [x] Add SQLAlchemy model `LiteratureReview` mapped to `literature_reviews`
- [x] Append idempotent DDL strings to `_migrations` in `init_db()`: `CREATE TABLE IF NOT EXISTS literature_reviews (...)` matching AC 1
- [x] Do **not** duplicate `research_profile` patterns incorrectly — this table has **no** unique constraint on topic (multiple reviews per topic over time are allowed)

### Task 2 — Backend: Pydantic models (`models.py`) (AC: 2, 3)
- [x] `ComparisonRow`: `work`, `method`, `dataset`, `key_result` (all `str`)
- [x] `ReviewClusterOut`: `cluster_label`, `synthesis`, `comparison_table: List[ComparisonRow]`, `gaps: List[str]`, `top_cite: str`, `article_ids: List[int]`
- [x] `LiteratureReviewCreate`: `topic: str`, `window_days: int` (ge=1, le=120), `min_rigor: float` (0.0–1.0)
- [x] `LiteratureReviewOut`: `id`, `topic`, `window_days`, `min_rigor`, `clusters: List[ReviewClusterOut]`, `created_at`
- [x] `LiteratureReviewSummaryOut`: `id`, `topic`, `window_days`, `min_rigor`, `created_at` (for list endpoint)

### Task 3 — Backend: LLM helper module **new file** `backend/api/lit_review_llm.py` (AC: 2)
- [x] Implement `async def synthesize_cluster_json(...) -> dict` returning parsed JSON dict with keys matching cluster schema (validate / coerce with Pydantic after parse)
- [x] Implement **three-tier try chain** with **5-minute TTL cache** for university server reachability (in-memory module globals are fine; use `time.monotonic()` or `datetime` for expiry)
- [x] Log `structlog` events: `lit_review_llm_tier` ∈ `{uni, local, openrouter}`, `cluster_label`, `latency_ms`, `error` (if any)
- [x] **Do not** import `chromadb` at module top level
- [x] Reuse JSON extraction pattern from `backend/scorer/scorer.py` (`extract_json_from_text` or equivalent small helper — **import shared utility** if one exists; otherwise duplicate minimal `json` / regex extraction **only** inside this module to avoid coupling api → scorer package layout issues — prefer **copy minimal 10-line helper** into `lit_review_llm.py` over fragile cross-package imports unless you verify `PYTHONPATH` in Docker)

### Task 4 — Backend: `POST /api/research/review`, `GET /api/research/reviews`, `GET /api/research/reviews/{id}` (`routers/research.py`) (AC: 2, 3)
- [x] Wire `_auth = Depends(require_session)` on all three routes
- [x] Implement pipeline described in AC 2; keep heavy imports **deferred** inside handlers or helper functions
- [x] Build **LLM user prompt** from cluster members: for each article include `title`, `url`, `summary_bullets` (first 3), `tags`, `score`, parsed `paper_meta` abstract snippet (truncated) — cap total tokens/chars per cluster (~8k chars) to avoid context overflow
- [x] System prompt: instruct model to output **only valid JSON** matching schema; temperature low (~0.2–0.3)
- [x] After successful DB insert, return `LiteratureReviewOut` with `clusters` parsed from stored `body_json`

### Task 5 — Frontend: types (`types.ts`) (AC: 4)
- [x] Add `ComparisonRow`, `ReviewCluster`, `LiteratureReview`, `LiteratureReviewSummary` interfaces matching backend snake_case field names for JSON

### Task 6 — Frontend: Zustand (`store/research.ts`) (AC: 4)
- [x] State: `reviews: LiteratureReviewSummary[] | null`, `currentReview: LiteratureReview | null`, `reviewsLoading`, `reviewGenerating`, `reviewsError`, `reviewError`
- [x] Actions: `fetchReviewList()`, `fetchReviewById(id)`, `generateReview(topic, windowDays, minRigor)` calling the new endpoints
- [x] On successful generate, append/update list and set `currentReview`

### Task 7 — Frontend: `LitReviewView.tsx` (AC: 4)
- [x] New component: props `onSelectArticle?: (id: number) => void` for navigation (parent passes `handleSelectArticle`)
- [x] Markdown export helper function (pure, testable)
- [x] Accessible loading and empty states; match Tailwind tokens used in `ResearchDigestView` / `ArticleList` (no new design system)

### Task 8 — Frontend: `ArticleList.tsx` + `App.tsx` (AC: 4)
- [x] Extend `currentView` / `appView` union with `'litreview'`
- [x] Add tab button (icon suggestion: `BookOpen` or `FileText` from `lucide-react`) label **Lit Review**
- [x] Render `LitReviewView` when selected; pass `onSelectArticle` from `App`

### Task 9 — Tests (`backend/scorer/tests/test_literature_review.py`) (AC: 1–3)
- [x] **Host-runnable** (text/source assertions): migration strings, route decorators, Pydantic model fields, presence of `lit_review_llm.py`, tier order comments in code, 422 message string exact match
- [x] **Docker / full-deps optional** (`pytest.mark.skipif` like `test_researcher_profile.py`): `TestClient` round-trip with mocked httpx or real Ollama disabled — **only** if stable in CI; otherwise skip integration

### Task 10 — Config: `.env.example` (AC: 2)
- [x] Add commented `UNI_OLLAMA_URL` and `UNI_OLLAMA_MODEL` lines (match `README.md` / `architecture.md`) so lit-review tier-1 is discoverable; no secrets committed

---

## Dev Notes

### Relevant architecture patterns and constraints

- **Auth:** All `/api/research/*` user-facing routes use `require_session` — same as `clusters` and `profile` endpoints. [Source: `backend/api/routers/research.py`]
- **Graceful degradation:** Chroma / HDBSCAN failures elsewhere return `[]` or soft-fail; for **this** story, embedding failure → **503** (user explicitly triggered expensive path). Partial LLM failure → placeholder synthesis string (per epic).
- **Snake_case JSON** end-to-end; no response envelope. [Source: `architecture.md` — API patterns]
- **`literature_reviews` table:** architecture states written/read by **`research.py` only** — keep ORM usage and queries inside that router module or dedicated helpers colocated with `research.py` imports. [Source: `architecture.md` — line ~709]
- **Three-tier priority** for **this** story per epics: **uni → local → OpenRouter** (note: `scorer.py` currently tries OpenRouter before Ollama — **do not change scorer** unless product owner agrees; **lit-review module** should follow epics order explicitly).

### Source tree components to touch

| Path | Purpose |
|------|---------|
| `backend/api/database.py` | `LiteratureReview` model + migrations |
| `backend/api/models.py` | Pydantic request/response models |
| `backend/api/lit_review_llm.py` | **New** — tiered LLM + JSON parse |
| `backend/api/routers/research.py` | New endpoints + pipeline orchestration |
| `frontend/src/types.ts` | TS interfaces |
| `frontend/src/store/research.ts` | Zustand actions/state |
| `frontend/src/components/LitReviewView.tsx` | **New** UI |
| `frontend/src/components/ArticleList.tsx` | Tab + view branch |
| `frontend/src/App.tsx` | `appView` state + wiring |
| `backend/scorer/tests/test_literature_review.py` | **New** tests |
| `.env.example` | Document `UNI_OLLAMA_URL`, `UNI_OLLAMA_MODEL` if not already present for lit-review (verify README cross-link) |

### Testing standards summary

- Mirror **Story 3.2 / 3.3** test file structure: env var defaults at top, `_check_api_deps()` for optional HTTP integration, source-level tests always run on host.
- Do **not** break existing pytest collection; keep `test_database_migrations.py` ignore if still broken in local venv (pre-existing).

### Project structure notes

- **No** `llm_client.py` exists yet in repo — this story **creates** `lit_review_llm.py` (scoped) rather than a global refactor, unless you unify later with Story 4.x admin tooling.
- Chroma query API: use `collection.query(query_embeddings=[vector], n_results=50, include=["distances"])` then map IDs to integers; verify against installed `chromadb` version in `requirements.txt`.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 3, Story 3.4, lines ~491–535]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — `literature_reviews` schema ~179–186; API table ~232–241; frontend types ~340–355; Zustand slice ~285–294]
- [Source: `backend/api/embedder.py` — embedding HTTP call pattern, `_get_chroma`, `_build_embed_text` ideas for topic string]
- [Source: `backend/api/routers/research.py` — `get_clusters` window filter, deferred `hdbscan`/`numpy`]
- [Source: `backend/api/routers/internal.py` — `score_meta_json` shape with `rigor`]
- [Source: `backend/scorer/scorer.py` — OpenRouter request shape]
- [Source: `backend/api/routers/ask.py` — Ollama `/api/chat` pattern, semaphore idea for optional rate limiting]

---

## Previous story intelligence (Story 3.3)

- **Profile feedback** uses `tags_json` (not `score_meta` tags) — lit-review should use **`Article` fields actually populated** (`title`, `summary_bullets_json`, `tags_json`, `paper_meta_json`, `score_meta_json`).
- **Research store** already holds `profile` + `clusters` — **extend** the same `research.ts` file; do not create a second store.
- **Deferred imports** are mandatory for `chromadb`, `hdbscan`, `numpy` in the API process.
- **Toolbar pattern:** `ArticleList` uses compact `text-[11px]` tab buttons — match for Lit Review tab.
- **Slide-overs:** `ResearchProfileEditor` uses fixed right panel + backdrop — Lit Review is a **main column view**, not necessarily a slide-over.

---

## Clarifications saved for product (non-blocking)

1. Epic AC says **POST** `/api/research/review` while architecture table matches — **confirmed**.
2. If **university** tier uses OpenAI-compatible `/v1/chat/completions`, confirm auth headers (Bearer token env var may be needed in future — not in current `.env.example`; document `UNI_OLLAMA_API_KEY` as **optional** follow-up if 401 observed in the wild).

---

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

None.

### Completion Notes List

- Implemented `LiteratureReview` ORM + migration, Pydantic models, `lit_review_llm.py` (uni → Ollama → OpenRouter, 5-minute uni health cache, JSON extraction), and `research.py` routes: `POST /api/research/review`, `GET /api/research/reviews`, `GET /api/research/reviews/{review_id}`.
- Pipeline: topic embedding (503 on failure), Chroma top-50, window + rigor filter (missing rigor → 0.0), strict 422 copy, HDBSCAN `min_cluster_size=3`, synthetic single cluster if all noise, per-cluster LLM with partial error placeholder.
- Frontend: types, extended `research.ts`, `LitReviewView` with past list, generate, export markdown, article links; `ArticleList` + `App` `litreview` tab.
- Tests: `backend/scorer/tests/test_literature_review.py` (23 passed, 1 skipped on host). Full suite: 254 passed, 28 skipped (`test_database_migrations` ignored).

### File List

- `backend/api/database.py`
- `backend/api/models.py`
- `backend/api/lit_review_llm.py` (new)
- `backend/api/routers/research.py`
- `frontend/src/types.ts`
- `frontend/src/store/research.ts`
- `frontend/src/components/LitReviewView.tsx` (new)
- `frontend/src/components/ArticleList.tsx`
- `frontend/src/App.tsx`
- `backend/scorer/tests/test_literature_review.py` (new)
- `.env.example`
- `_bmad-output/implementation-artifacts/3-4-literature-review-mode.md`

---

*Generated: 2026-04-22 — Ultimate context engine analysis completed — comprehensive developer guide created*
