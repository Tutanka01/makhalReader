---
epic: 2
story: 1
story_key: "2-1-research-aware-scoring-engine"
---

# Story 2.1: Research-Aware Scoring Engine

Status: review

## Story

As a **researcher**,
I want the scoring system to return a multi-dimensional result (novelty, rigor, contribution type, RE document type) and store it per article,
So that I can filter and sort my reading list by research dimensions, not just a single scalar score.

## Acceptance Criteria

1. **Given** the existing `ScoreResult` pydantic model has fields `{score, tags, summary_bullets, reason}`
   **When** this story is implemented
   **Then** `ScoreResult` is extended with: `contribution_type: str | None`, `re_document_type: str | None`, `novelty: float | None` (0–1), `rigor: float | None` (0–1), `relevance_to_topics: float | None` (0–1)
   **And** all new fields are optional/nullable for backward compatibility with existing scorer responses

2. **Given** the `articles` database table exists
   **When** additive migrations run via `init_db()`
   **Then** three new nullable columns exist: `score_meta_json TEXT`, `re_document_type VARCHAR(24)`, `contribution_type VARCHAR(24)`
   **And** running `init_db()` twice on an already-migrated database produces no error and no data loss

3. **Given** a `SCORER_MAX_CHARS` env var is set (e.g., `6000`)
   **When** an article is being scored
   **Then** the content preview is truncated to `SCORER_MAX_CHARS` characters
   **And** when `paper_meta_json` on the `ScoreRequest` contains `"is_paper": true`, the cap is automatically raised to `min(SCORER_MAX_CHARS * 2, 12000)` characters

4. **Given** the scorer returns a `ScoreResult` with `contribution_type` and `re_document_type`
   **When** `POST /api/internal/articles/{id}/score` is called with the extended score body
   **Then** `score_meta_json` is stored as a JSON blob on the article record
   **And** `re_document_type` and `contribution_type` columns are populated from the score result
   **And** `ArticleOut` response includes a parsed `score_meta` dict
   **And** `ArticleListItem` response includes `contribution_type` and `re_document_type` string fields

5. **Given** `PROMPT_PROFILE=infra` is configured
   **When** any article is scored
   **Then** `contribution_type` and `re_document_type` may be null — the infra rubric does not require them
   **And** the scalar score behavior is unchanged from pre-augmentation baseline

## Tasks / Subtasks

- [x] Extend `ScoreResult` and `ScoreRequest` in `backend/scorer/scorer.py` (AC: 1, 3)
  - [x] Add `SCORER_MAX_CHARS = int(os.getenv("SCORER_MAX_CHARS", "6000"))` env var
  - [x] Add optional `paper_meta_json: Optional[str] = None` field to `ScoreRequest`
  - [x] Add 5 new optional fields to `ScoreResult`: `contribution_type`, `re_document_type`, `novelty`, `rigor`, `relevance_to_topics`
  - [x] Update `validate_score_result` to extract new fields from LLM JSON response
  - [x] Update `score_article` endpoint: apply `SCORER_MAX_CHARS` content cap; auto-raise cap when `paper_meta_json` contains `"is_paper": true`
  - [x] Update score POST payload in `score_article` to include all new fields

- [x] Add new columns to `Article` ORM model and `init_db()` migrations in `backend/shared/database.py` (AC: 2)
  - [x] Add `score_meta_json = Column(Text, nullable=True)` to `Article` class
  - [x] Add `contribution_type = Column(String(24), nullable=True)` to `Article` class
  - [x] Add `re_document_type = Column(String(24), nullable=True)` to `Article` class
  - [x] Add three idempotent `ALTER TABLE` statements to `init_db()._migrations` list

- [x] Extend Pydantic models in `backend/api/models.py` (AC: 4)
  - [x] Add 5 new optional fields to `InternalScoreUpdate`: `contribution_type`, `re_document_type`, `novelty`, `rigor`, `relevance_to_topics`
  - [x] Add `score_meta_json: Optional[str] = None`, `contribution_type: Optional[str] = None`, `re_document_type: Optional[str] = None` to `ArticleOut`
  - [x] Add computed `score_meta: Optional[Dict[str, Any]] = None` field to `ArticleOut` and populate it in `parse_json_fields` validator
  - [x] Add `contribution_type: Optional[str] = None` and `re_document_type: Optional[str] = None` to `ArticleListItem`

- [x] Update `internal_score_article` in `backend/api/routers/internal.py` (AC: 4)
  - [x] Write `contribution_type` and `re_document_type` to article columns
  - [x] Build and write `score_meta_json` blob from the full score payload

- [x] Update `_row_to_list_item` in `backend/api/routers/articles.py` (AC: 4)
  - [x] Add `contribution_type=article.contribution_type` and `re_document_type=article.re_document_type` to the manual `ArticleListItem` constructor call

- [x] Update prompt files to include new JSON fields (AC: 1)
  - [x] Update `backend/scorer/prompts/research.md` response format to include `contribution_type`, `re_document_type`, `novelty`, `rigor`, `relevance_to_topics`
  - [x] Update `backend/scorer/prompts/unified.md` response format to include `novelty`, `rigor`, `relevance_to_topics`, `re_document_type` (already has `contribution_type`)

- [x] Update `.env.example` with `SCORER_MAX_CHARS` (AC: 3)

## Dev Notes

### `ScoreRequest` — Add `paper_meta_json`

The poller today sends `{article_id, title, content_text, rss_summary}`. Story 2.2 will add `paper_meta_json` to that payload (after enrichment). This story adds the field as **optional** to `ScoreRequest` so the poller changes in Story 2.2 are additive and backward compatible:

```python
class ScoreRequest(BaseModel):
    article_id: int
    title: str
    content_text: str
    rss_summary: str = ""
    paper_meta_json: Optional[str] = None  # NEW — Story 2.2 will populate this
```

### Content Cap Logic in `score_article`

Replace the current hardcoded `[:3000]` slice:

```python
# Determine content cap
cap = SCORER_MAX_CHARS
if req.paper_meta_json:
    try:
        pm = json.loads(req.paper_meta_json)
        if pm.get("is_paper"):
            cap = min(SCORER_MAX_CHARS * 2, 12000)
    except (json.JSONDecodeError, TypeError):
        pass  # malformed paper_meta — use default cap

content_preview = (req.content_text or req.rss_summary or "")[:cap]
```

Default `SCORER_MAX_CHARS=6000` doubles the current `3000` limit for all articles — this is intentional: the current 3k was undersized for research abstracts even without paper detection.

### `validate_score_result` — New Fields

Valid values for `contribution_type` (from prompts): `method | benchmark | survey | empirical | theory | position | tool | incident | tutorial | news | other`
Valid values for `re_document_type`: `elicitation | extraction | method | none`

```python
_VALID_CONTRIBUTION_TYPES = {
    "method", "benchmark", "survey", "empirical", "theory",
    "position", "tool", "incident", "tutorial", "news", "other",
}
_VALID_RE_DOC_TYPES = {"elicitation", "extraction", "method", "none"}

def validate_score_result(data: dict) -> ScoreResult:
    # ... existing score/tags/summary_bullets/reason extraction unchanged ...

    contribution_type = data.get("contribution_type")
    if contribution_type not in _VALID_CONTRIBUTION_TYPES:
        contribution_type = None

    re_document_type = data.get("re_document_type")
    if re_document_type not in _VALID_RE_DOC_TYPES:
        re_document_type = None

    def _clamp_float(val) -> Optional[float]:
        if val is None:
            return None
        try:
            return max(0.0, min(1.0, float(val)))
        except (TypeError, ValueError):
            return None

    return ScoreResult(
        # ... existing fields ...
        contribution_type=contribution_type,
        re_document_type=re_document_type,
        novelty=_clamp_float(data.get("novelty")),
        rigor=_clamp_float(data.get("rigor")),
        relevance_to_topics=_clamp_float(data.get("relevance_to_topics")),
    )
```

### Score POST Payload Extension

In `score_article`, update the POST to the API:
```python
await client.post(
    f"{API_BASE}/api/internal/articles/{req.article_id}/score",
    json={
        "score": result.score,
        "tags": result.tags,
        "summary_bullets": result.summary_bullets,
        "reason": result.reason,
        # New fields — None values are included; API accepts Optional
        "contribution_type": result.contribution_type,
        "re_document_type": result.re_document_type,
        "novelty": result.novelty,
        "rigor": result.rigor,
        "relevance_to_topics": result.relevance_to_topics,
    },
    headers=INTERNAL_HEADERS,
    timeout=30,
)
```

### `score_meta_json` — What Goes In It

`score_meta_json` is the canonical store for all research-dimension data. The API endpoint (`internal_score_article`) builds it:

```python
score_meta = {
    "contribution_type": score_data.contribution_type,
    "re_document_type": score_data.re_document_type,
    "novelty": score_data.novelty,
    "rigor": score_data.rigor,
    "relevance_to_topics": score_data.relevance_to_topics,
}
# Only store non-None values to keep the blob minimal
article.score_meta_json = json.dumps(
    {k: v for k, v in score_meta.items() if v is not None}
)
```

If all fields are None (e.g., `PROMPT_PROFILE=infra`), `score_meta_json` becomes `"{}"` — never `NULL`.

**Note:** `contribution_type` and `re_document_type` are ALSO stored as dedicated columns (for SQL filtering in Story 2.3). `score_meta_json` holds the full research-dimension blob (novelty, rigor, etc.) that doesn't need to be queryable.

### `ArticleOut` — `score_meta` Computed Field

Add to `parse_json_fields` validator:
```python
try:
    self.score_meta = json.loads(self.score_meta_json or "{}")
except Exception:
    self.score_meta = {}
```

### Database Migration Pattern — CRITICAL

The existing pattern in `init_db()` uses `try/except` around each ALTER statement:
```python
_migrations = [
    "ALTER TABLE articles ADD COLUMN title_fingerprint VARCHAR(16)",
    # New Story 2.1 additions:
    "ALTER TABLE articles ADD COLUMN score_meta_json TEXT",
    "ALTER TABLE articles ADD COLUMN re_document_type VARCHAR(24)",
    "ALTER TABLE articles ADD COLUMN contribution_type VARCHAR(24)",
]
```
**Do NOT use** `IF NOT EXISTS` — SQLite doesn't support it for `ALTER TABLE`. The existing `try/except` with `conn.commit()` inside the try is the correct idempotent pattern. **Match it exactly** for new migrations.

### Prompt File Updates — `research.md`

Replace the current `## RESPONSE FORMAT` section (keeping everything above it unchanged):

```markdown
## RESPONSE FORMAT

Reply with a valid JSON object ONLY. No text before or after, no markdown, no code block.

{
  "score": <integer or decimal between 0 and 10>,
  "tags": [<1 to 5 precise technical tags, preferably in English>],
  "summary_bullets": [<2 to 3 short sentences summarizing the key contribution>],
  "reason": "<one sentence explaining the score>",
  "contribution_type": <null | "method" | "benchmark" | "survey" | "empirical" | "theory" | "position" | "tool" | "incident" | "tutorial" | "news" | "other">,
  "re_document_type": <null | "elicitation" | "extraction" | "method" | "none">,
  "novelty": <null | float 0.0–1.0 — how novel relative to known work in this domain>,
  "rigor": <null | float 0.0–1.0 — methodological rigor: evaluation quality, reproducibility, statistical validity>,
  "relevance_to_topics": <null | float 0.0–1.0 — relevance to the reader's tracked research topics>
}
```

Where:
- `re_document_type` is `"elicitation"` or `"extraction"` if the paper is a primary source or dataset of real requirements, `"method"` if it introduces an RE method, `"none"` otherwise.
- Set `novelty` and `rigor` to null only if genuinely impossible to assess (e.g., non-paper blog posts).

### Prompt File Updates — `unified.md`

Replace the current `## RESPONSE FORMAT` section:

```markdown
## RESPONSE FORMAT

Reply with a valid JSON object ONLY. No text before or after, no markdown, no code block.

For practitioner/infra articles, `contribution_type`, `re_document_type`, `novelty`, `rigor`, and `relevance_to_topics` should be null unless clearly applicable.
For research articles, all fields should be populated.

{
  "score": <integer or decimal between 0 and 10>,
  "tags": [<1 to 5 precise technical tags, preferably in English>],
  "summary_bullets": [<2 to 3 short sentences summarizing the key points or contribution>],
  "reason": "<one sentence explaining the score>",
  "contribution_type": <null | "method" | "benchmark" | "survey" | "empirical" | "theory" | "position" | "tool" | "incident" | "tutorial" | "news" | "other">,
  "re_document_type": <null | "elicitation" | "extraction" | "method" | "none">,
  "novelty": <null | float 0.0–1.0 — how novel relative to known work in this domain>,
  "rigor": <null | float 0.0–1.0 — methodological rigor: evaluation quality, reproducibility>,
  "relevance_to_topics": <null | float 0.0–1.0 — relevance to the reader's tracked research topics>
}
```

### `_row_to_list_item` — Minimal Change

The function manually constructs `ArticleListItem`. After adding two new optional fields to the model:

```python
def _row_to_list_item(row) -> ArticleListItem:
    article, feed_name = row
    return ArticleListItem(
        # ... all existing fields unchanged ...
        user_feedback=article.user_feedback,
        contribution_type=article.contribution_type,   # NEW
        re_document_type=article.re_document_type,     # NEW
    )
```

SQLAlchemy ORM attribute access on a nullable column returns `None` if the column was added by migration and the row predates it — this is safe.

### No Poller Changes in This Story

The poller's `score_article_rate_limited` function does NOT change in this story. It still sends only `{article_id, title, content_text, rss_summary}`. The new `paper_meta_json` field in `ScoreRequest` defaults to `None` — the cap will use `SCORER_MAX_CHARS` without paper-aware raising until Story 2.2 updates the poller.

### No Frontend Changes in This Story

`contribution_type` and `re_document_type` data will now flow to the frontend through `ArticleListItem`, but the `ContribTypeBadge` and `ReDocTypeBadge` React components and the filter UI are scoped to **Story 2.3**, not here.

### Test Strategy

Tests belong in `backend/scorer/tests/` (already has `__init__.py` + `test_prompt.py`). Add:

**`backend/scorer/tests/test_scorer_logic.py`** (no network calls):
- `validate_score_result` with all new fields present → correct extraction and clamping
- `validate_score_result` with invalid `contribution_type` → `None`
- `validate_score_result` with invalid `re_document_type` → `None`
- `validate_score_result` with `novelty > 1.0` → clamped to `1.0`
- `validate_score_result` with `novelty = null` (JSON null) → `None`
- Content cap: `SCORER_MAX_CHARS=100` → content truncated to 100 chars
- Paper-aware cap: `SCORER_MAX_CHARS=100`, `is_paper=true` → content truncated to 200 chars
- Paper-aware cap: `SCORER_MAX_CHARS=100`, `is_paper=true` but `min(200, 12000)=200` → 200 chars
- Paper-aware cap: `SCORER_MAX_CHARS=7000`, `is_paper=true` → `min(14000, 12000)=12000`
- Malformed `paper_meta_json` → fallback to default cap (no error)

**`backend/scorer/tests/test_database_migrations.py`** (requires `sqlalchemy`, so run in Docker or venv with deps):
- New columns exist after `init_db()` runs once
- `init_db()` runs twice without error
- Null values survive round-trip (insert article without new fields → read back → new fields are None)

These database tests may not be runnable in the host Python environment (SQLAlchemy is a Docker dep). Write them anyway and mark with a comment `# Run inside Docker: docker-compose exec api pytest ...` — they serve as executable specification.

### References

- Current `backend/scorer/scorer.py`: `ScoreRequest` (L24-28), `ScoreResult` (L31-35), `validate_score_result` (L70-92), `score_article` endpoint (L240-284), content preview at L246
- Current `backend/shared/database.py`: `Article` model (L61-87), `init_db()` (L98-111), migration pattern (L101-110)
- Current `backend/api/models.py`: `InternalScoreUpdate` (L123-127), `ArticleOut` (L27-68), `ArticleListItem` (L71-104)
- Current `backend/api/routers/internal.py`: `internal_score_article` (L209-250), current write at L223-226
- Current `backend/api/routers/articles.py`: `_row_to_list_item` (L54-72)
- Epics spec: `_bmad-output/planning-artifacts/epics.md` — Story 2.1

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

- Initial test run failed: `scorer.py` imports `httpx`/`fastapi` which are Docker-only. Resolution: extracted pure logic (`_VALID_CONTRIBUTION_TYPES`, `_VALID_RE_DOC_TYPES`, `clamp_float`, `compute_content_cap`) into new `backend/scorer/scorer_logic.py` (zero dependencies). `scorer.py` imports from it; tests import from it directly. 43/43 unit tests pass on host Python 3.11.

### Completion Notes List

- `backend/scorer/scorer_logic.py` — new module: pure logic helpers extracted from scorer for testability without Docker deps. Contains `_VALID_CONTRIBUTION_TYPES`, `_VALID_RE_DOC_TYPES`, `clamp_float`, `compute_content_cap`.
- `backend/scorer/scorer.py` — `ScoreRequest` gains optional `paper_meta_json`; `ScoreResult` gains 5 optional research fields; `SCORER_MAX_CHARS` env var added; content cap uses `compute_content_cap()`; score POST payload extended with all new fields; OpenRouter headers renamed to Baṣīra.
- `backend/shared/database.py` — `Article` ORM model gains 3 nullable columns (`score_meta_json`, `contribution_type`, `re_document_type`); `init_db()._migrations` extended with 3 idempotent ALTER TABLE statements.
- `backend/api/models.py` — `InternalScoreUpdate` gains 5 optional fields; `ArticleOut` gains 3 raw columns + `score_meta` computed dict; `ArticleListItem` gains `contribution_type` + `re_document_type`.
- `backend/api/routers/internal.py` — `internal_score_article` writes new columns and builds `score_meta_json` blob; SSE broadcast dict includes new fields.
- `backend/api/routers/articles.py` — `_row_to_list_item` passes `contribution_type` and `re_document_type`.
- `backend/scorer/prompts/research.md` — RESPONSE FORMAT updated with 5 new JSON fields.
- `backend/scorer/prompts/unified.md` — RESPONSE FORMAT updated with 4 new JSON fields (already had `contribution_type`).
- `.env.example` — `SCORER_MAX_CHARS=6000` added.
- Tests: 66 passed (43 new logic tests + 23 prompt tests), 7 skipped (DB migration tests, run inside Docker). Zero linter errors on modified files.

### File List

- `backend/scorer/scorer_logic.py` — new
- `backend/scorer/scorer.py` — modified
- `backend/shared/database.py` — modified
- `backend/api/models.py` — modified
- `backend/api/routers/internal.py` — modified
- `backend/api/routers/articles.py` — modified
- `backend/scorer/prompts/research.md` — modified
- `backend/scorer/prompts/unified.md` — modified
- `backend/scorer/tests/test_scorer_logic.py` — new (43 tests)
- `backend/scorer/tests/test_database_migrations.py` — new (7 tests, Docker-only)
- `.env.example` — modified

### Change Log

- 2026-04-22: Implemented Story 2.1 — Research-Aware Scoring Engine. Extended ScoreResult/ScoreRequest, DB schema, API models, and internal routing to support multi-dimensional research scores (contribution_type, re_document_type, novelty, rigor, relevance_to_topics). Added SCORER_MAX_CHARS content cap with paper-aware doubling. Extracted pure scoring logic into scorer_logic.py for host-testability. 66 tests passing.
