---
epic: 4
story: 1
story_key: "4-1-arise-export-endpoint"
---

# Story 4.1: ARISE Export Endpoint

Status: review

<!-- Ultimate context engine analysis completed — comprehensive developer guide created -->

## Story

As a **researcher** (or an automated ARISE pipeline),
I want to export all articles classified as requirement-rich (`re_document_type ∈ {elicitation, extraction, method}`) as structured JSON,
So that downstream ARISE pipelines can ingest pre-classified, enriched requirement documents without manual curation.

---

## Acceptance Criteria

**AC 1 — `POST /api/research/export-arise` returns NFR15-shaped JSON**

**Given** an authenticated user calls `POST /api/research/export-arise` with JSON body `{ "since": "2026-01-01T00:00:00Z" }` (ISO-8601 datetime, timezone-aware preferred)  
**When** the request is processed  
**Then** the response body is a **JSON array** (top-level list, not wrapped) of objects  
**And** only articles where **`re_document_type` ∈ `('elicitation', 'extraction', 'method')`** AND **`published_at >= since`** are included  
**And** **`published_at` is not `NULL` in the database** — rows with `published_at IS NULL` must be **excluded** from the export (they cannot satisfy `published_at >= since` in SQL; do not special-case include them)  

**And** each exported object contains **exactly** these keys (no extras, no omissions):  
`id`, `title`, `url`, `published_at`, `re_document_type`, `contribution_type`, `paper_meta`, `content_text`, `score_meta`, `feed_name`, `tags`  

**And** `paper_meta` and `score_meta` are **JSON objects** — if `paper_meta_json` or `score_meta_json` is `NULL` or invalid JSON, use **`{}`** (never `null` for these two keys per product AC)  

**And** `tags` is a **JSON array of strings** parsed from `tags_json`; if missing/invalid, use `[]`  

**And** `feed_name` is the **`feeds.name`** for `Article.feed_id` (same join pattern as list articles)  

**And** `content_text` is the article’s `content_text` column value, or **`""`** if `NULL`  

**And** `title` / `url` / `feed_name` are strings (use `""` if somehow null in DB — defensive)  

**And** `published_at` is serialized as an **ISO-8601 string** in the response when present; if the column is null the row should not appear (see filter above)  

**And** `re_document_type` and `contribution_type` reflect DB values (non-null for `re_document_type` given the filter)  

[Source: `_bmad-output/planning-artifacts/epics.md` Story 4.1; NFR15 in same file ~L70; `architecture.md` API table ~L240]

---

**AC 2 — Empty result**

**Given** no articles match `since` + `re_document_type` filter  
**When** the export endpoint is called  
**Then** HTTP **200** with body **`[]`**

---

**AC 3 — Auth**

**Given** the request has **no** valid session  
**When** the export endpoint is called  
**Then** HTTP **401** (same `require_session` dependency as other `/api/research/*` routes)

---

**AC 4 — Validation**

**Given** `since` is missing, wrong type, or not a valid datetime  
**When** the request is processed  
**Then** HTTP **422** with a clear Pydantic validation error (use a dedicated request model, e.g. `AriseExportRequest`)

---

**AC 5 — NFR15 audit**

**Given** a successful export row  
**When** compared to NFR15  
**Then** the object’s key set is **exactly** the NFR15 minimum:  
`{ id, title, url, published_at, re_document_type, contribution_type, paper_meta, content_text, score_meta, feed_name, tags }`  

[Source: `_bmad-output/planning-artifacts/prd.md` ~L338]

---

## Tasks / Subtasks

### Task 1 — Backend: Pydantic models (`models.py`) (AC: 1, 4, 5)
- [x] Add `AriseExportRequest(BaseModel)` with field `since: datetime` (use Pydantic v2 `AwareDatetime` **or** `datetime` with UTC normalization in a validator — document chosen approach)
- [x] Add `AriseArticleOut(BaseModel)` with **only** the 11 NFR15 fields, correct types:
  - `id: int`, `title: str`, `url: str`, `published_at: datetime`, `re_document_type: str`, `contribution_type: Optional[str]` (or `str` with `""` default — **pick one** and apply consistently in the builder), `paper_meta: Dict[str, Any]`, `content_text: str`, `score_meta: Dict[str, Any]`, `feed_name: str`, `tags: List[str]`
- [x] Add a **factory/helper** method or module-level function `def build_arise_row(article: Article, feed_name: str) -> AriseArticleOut` that enforces `{}` / `[]` / `""` rules — keeps the route handler thin

### Task 2 — Backend: Route (`routers/research.py`) (AC: 1–5)
- [x] Add `POST /api/research/export-arise` with `response_model=List[AriseArticleOut]` **or** return `JSONResponse` built from validated models (either is fine if OpenAPI shows correct schema)
- [x] Use `_auth = Depends(require_session)` — **same** pattern as `/profile`, `/clusters`, `/review`
- [x] Query: `db.query(Article, Feed.name.label("feed_name")).join(Feed, Article.feed_id == Feed.id).filter(Article.re_document_type.in_(("elicitation", "extraction", "method")), Article.published_at.isnot(None), Article.published_at >= since)` — order by `published_at ASC` or `id ASC` (document choice; prefer stable **id ASC** for reproducible exports)
- [x] **Do not** duplicate the ARISE type tuple as a third divergent constant — **import or mirror** `backend/api/routers/articles.py` `_ARISE_RE_TYPES` (preferred: export `ARISE_RE_DOCUMENT_TYPES` from `articles.py` or a tiny `constants.py` and import in both `articles.py` and `research.py` to avoid drift)

### Task 3 — Tests (`backend/scorer/tests/test_arise_export.py`) (AC: 1–5)
- [x] **Host-runnable:** assert route string `POST`, path `/export-arise`, `_auth` usage, `_ARISE` / `elicitation` filter in `research.py` source, Pydantic model names, empty-list 200 behavior described in comments
- [x] **Optional integration** (skip without deps): `TestClient` with auth cookie fixture if one exists; else `pytest.mark.skipif` like other research tests

### Task 4 — Docs touch (optional, minimal)
- [x] If `README.md` documents API routes, add **one line** for `POST /api/research/export-arise` — **only** if a “API reference” section already exists; otherwise skip (do not create new README sections unprompted)

---

## Dev Notes

### Architecture compliance

- Route lives under **`research` router** prefix → full path **`POST /api/research/export-arise`** [Source: `architecture.md`]
- **Session auth** only — ARISE scripts must authenticate like the web app (cookie session); no public API key in this story [Source: `architecture.md` ~L218–221]
- **snake_case** JSON fields [Source: `architecture.md` naming patterns]

### Existing code to reuse

- **Join feed name:** `db.query(Article, Feed.name.label("feed_name")).join(Feed, Article.feed_id == Feed.id)` — mirror `list_articles` in `backend/api/routers/articles.py` [Source: `articles.py` ~L99–101]
- **RE doc type filter values:** `_ARISE_RE_TYPES = ("elicitation", "extraction", "method")` [Source: `articles.py` ~L80]
- **Auth dependency:** `from auth import require_session` + `_auth = Depends(require_session)` [Source: `research.py`]

### SQL edge cases

- SQLite compares datetimes as strings when stored inconsistently — ensure `since` is compared as **timezone-aware UTC** and `Article.published_at` is stored as aware UTC (existing app pattern). If `published_at` is naive in DB, normalize in query using `func.datetime` **only** if you discover real data issues; default: assume ORM returns comparable datetimes.

### OpenAPI / client ergonomics

- POST + JSON body is the **epic** contract; `prd.md` mentions a query variant in one line — **implement POST body** as the source of truth for this story.

### Out of scope (Story 4.2+)

- **`admin.py` rescore/reindex`**, **`GET /api/research/profile/export`**, **`llm_client.py`** — do not implement here.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 4, Story 4.1, ~L543–571]
- [Source: `_bmad-output/planning-artifacts/prd.md` — NFR15 ~L338]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — API table ~L232–241]
- [Source: `backend/api/routers/research.py` — existing research endpoints pattern]
- [Source: `backend/api/routers/articles.py` — `_ARISE_RE_TYPES`, Feed join]

---

## Previous story intelligence (Story 3.4)

- **`research.py`** is already large — keep the export handler **short**; push row-building into `models.py` helper or a small private function at the bottom of `research.py`.
- **Deferred imports** are not needed for this story (no chromadb/hdbscan).
- **Tests** follow `test_literature_review.py` / `test_researcher_profile.py` style: env defaults at top, source assertions always on host.

---

## Clarifications saved for product (non-blocking)

1. **Script auth:** External ARISE jobs need a logged-in session today — document in README snippet: `curl -c cookies.txt -b cookies.txt -X POST .../export-arise` after login; future API key is explicitly deferred in architecture.
2. **`contribution_type` null:** If exporter requires non-null strings, coerce to `""`; if null is meaningful for ARISE, keep `null` — align with first consumer script expectation when known.

---

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

None.

### Completion Notes List

- Renamed shared filter constant to **`ARISE_RE_DOCUMENT_TYPES`** in `articles.py`; `research.py` imports it for `export_arise` (no duplicate tuple).
- Added **`AriseExportRequest`** (`since` normalized to UTC via validator), **`AriseArticleOut`**, and **`build_arise_row()`** in `models.py` (`paper_meta` / `score_meta` → `{}`, bad JSON → `{}`; `tags` → `[]`; defensive strings).
- **`POST /api/research/export-arise`**: join `Feed`, filter `re_document_type IN ARISE`, `published_at IS NOT NULL` and `>= since`, order **`Article.id.asc()`**, `response_model=List[AriseArticleOut]`, structlog `arise_export`.
- Tests: `backend/scorer/tests/test_arise_export.py` (11 passed). Full scorer suite: **265 passed**, 28 skipped (excluding `test_database_migrations`).
- README: no dedicated API route list — **Task 4 skipped** per story rule.

### File List

- `backend/api/models.py`
- `backend/api/routers/articles.py`
- `backend/api/routers/research.py`
- `backend/scorer/tests/test_arise_export.py` (new)
- `_bmad-output/implementation-artifacts/4-1-arise-export-endpoint.md`

---

*Generated: 2026-04-22 — Ultimate context engine analysis completed — comprehensive developer guide created*
