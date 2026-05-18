---
epic: 2
story: 2
story_key: "2-2-paper-aware-enrichment-pipeline"
---

# Story 2.2: Paper-Aware Enrichment Pipeline

Status: review

## Story

As a **researcher**,
I want the system to automatically extract structured metadata from paper sources (arXiv, Semantic Scholar, OpenReview, ACL Anthology, DOI) before scoring,
So that the scorer receives rich structured context about each paper's methods, datasets, and contribution type.

## Acceptance Criteria

1. **Given** the extractor service has an existing `extract_arxiv` handler
   **When** this story is implemented
   **Then** `extractor.py` contains a `paper_handlers` dispatcher list mapping URL detection functions to source-specific async handlers:
   - `arxiv.org/abs/` → existing arXiv handler (refactored from `extract_arxiv`)
   - `semanticscholar.org/paper/` → Semantic Scholar Graph API handler
   - `openreview.net/forum` → OpenReview API v2 handler
   - `aclanthology.org/` → ACL Anthology handler (uses SS API with `ACL:{id}`)
   - `doi.org/` → Crossref API handler

2. **Given** an article URL matches a paper source pattern
   **When** `enrich_paper_meta(url, extraction_result, client)` is called from `backend/poller/paper_enricher.py`
   **Then** it returns a dict containing at minimum: `is_paper: true`, `source`, `paper_id`, `doi` (if available), `abstract`, `authors`, `year`, `methods: []`, `datasets: []`, `metrics: []`
   **And** it makes a cheap single Ollama call (`OLLAMA_MODEL`) to classify the abstract into: `contribution_type`, `re_document_type`, `confidence` (0–1)
   **And** the result is stored as `paper_meta_json` on the article record

3. **Given** the Semantic Scholar API or any external API is unavailable or returns non-200
   **When** enrichment runs
   **Then** the enricher falls back to the already-extracted content without error
   **And** `paper_meta_json` is set to `{"is_paper": true, "source": "fallback"}` — the article is not lost

4. **Given** a non-paper URL (blog post, Hacker News thread, newsletter)
   **When** `enrich_paper_meta` is called
   **Then** it returns `{}` (empty dict) within 50ms — no external API calls are made
   **And** `paper_meta_json` is left null on the article record

5. **Given** the `articles` database table
   **When** this story's migration runs
   **Then** a `paper_meta_json TEXT` nullable column exists
   **And** running `init_db()` twice produces no error and no data loss
   **And** `ArticleOut` response includes a parsed `paper_meta: dict` field

6. **Given** `SS_RATE_LIMIT_SECONDS=1.0` is configured
   **When** multiple articles from the same poll cycle trigger SS API calls
   **Then** SS API calls are spaced ≥ 1 second apart (enforced via `asyncio.Lock` + timestamp in extractor)
   **And** enrichment does not block the polling scheduler from running on schedule

7. **Given** the poller calls `enrich_paper_meta` after extraction and before `create_article`
   **When** `create_article` is called
   **Then** `paper_meta_json`, `contribution_type` (from Ollama classification), and `re_document_type` are included in the create payload
   **And** the scorer receives the pre-populated `paper_meta_json` field and uses it to adjust its content cap

8. **CRITICAL — Bug Fix from Story 2.1**: `backend/api/database.py` is missing the ORM columns and migrations for `score_meta_json`, `contribution_type`, `re_document_type` that were added in Story 2.1 only to `backend/shared/database.py`. These MUST be added to `backend/api/database.py` in this story to fix the silent data loss bug.

---

## Tasks / Subtasks

- [x] **CRITICAL FIX**: Add missing Story 2.1 columns to `backend/api/database.py` (AC: 8)
  - [x] Add `score_meta_json = Column(Text, nullable=True)` to `Article` ORM model
  - [x] Add `contribution_type = Column(String(24), nullable=True)` to `Article` ORM model
  - [x] Add `re_document_type = Column(String(24), nullable=True)` to `Article` ORM model
  - [x] Add all 3 to `init_db()._migrations` with `try/except` idempotent pattern

- [x] Add `paper_meta_json` column to both DB files (AC: 5)
  - [x] `backend/api/database.py`: Add `paper_meta_json = Column(Text, nullable=True)` to `Article` + `ALTER TABLE` migration
  - [x] `backend/shared/database.py`: Add `paper_meta_json = Column(Text, nullable=True)` to `Article` + `ALTER TABLE` migration

- [x] Extend `ExtractResponse` and refactor extractor (AC: 1)
  - [x] Add `paper_meta: Optional[dict] = None` field to `ExtractResponse` (use `Optional[Any]` if dict causes linter issues)
  - [x] Create `paper_handlers` list: `[(detection_fn, handler_fn), ...]`
  - [x] Refactor `extract_arxiv` into the handler format: `async def _extract_arxiv_handler(html, url, client) -> dict`
  - [x] Implement `_extract_semantic_scholar_handler(html, url, client) -> dict` (calls SS Graph API)
  - [x] Implement `_extract_openreview_handler(html, url, client) -> dict` (calls OpenReview API v2)
  - [x] Implement `_extract_acl_anthology_handler(html, url, client) -> dict` (uses SS API with `ACL:{id}`)
  - [x] Implement `_extract_doi_handler(html, url, client) -> dict` (calls Crossref API)
  - [x] Add SS rate-limiting: `_SS_LOCK = asyncio.Lock()`, `_ss_last_call: float = 0.0`, `SS_RATE_LIMIT_SECONDS` env var
  - [x] In `/extract` endpoint: detect paper URL, run appropriate handler, set `paper_meta` in `ExtractResponse`

- [x] Create `backend/poller/paper_enricher.py` (AC: 2, 3, 4)
  - [x] `is_paper_url(url: str) -> bool` — fast pattern match, no API calls
  - [x] `_classify_with_ollama(abstract: str, client) -> dict` — makes single Ollama chat call
  - [x] `enrich_paper_meta(url: str, extraction_result: dict, client) -> dict` — full enrichment logic

- [x] Update `backend/api/models.py` (AC: 5)
  - [x] Add `paper_meta_json: Optional[str] = None` to `InternalArticleCreate`
  - [x] Add `contribution_type: Optional[str] = None` and `re_document_type: Optional[str] = None` to `InternalArticleCreate`
  - [x] Add `paper_meta_json: Optional[str] = None` to `ArticleOut`
  - [x] Add `paper_meta: Dict[str, Any] = {}` computed field to `ArticleOut`
  - [x] Update `ArticleOut.parse_json_fields` to parse `paper_meta_json` → `paper_meta`

- [x] Update `backend/api/routers/internal.py` (AC: 7)
  - [x] In `internal_create_article`: persist `paper_meta_json`, `contribution_type`, `re_document_type` from incoming payload to `Article(...)` constructor

- [x] Update `backend/poller/main.py` (AC: 7)
  - [x] Import `enrich_paper_meta`, `is_paper_url` from `paper_enricher`
  - [x] In `process_feed`: call `await enrich_paper_meta(article_url, extracted, client)` after extraction
  - [x] Add `paper_meta_json`, `contribution_type`, `re_document_type` to `create_article` payload when enrichment returns non-empty
  - [x] Extend `score_article_rate_limited` with `paper_meta_json: Optional[str] = None` parameter, pass it in scorer POST body

- [x] Update `.env.example` and `.env`
  - [x] Add `SS_RATE_LIMIT_SECONDS=1.0` to both files with comments

- [x] Write tests in `backend/scorer/tests/`
  - [x] `test_paper_enricher.py` — unit tests for `is_paper_url`, `enrich_paper_meta` with mocked responses
  - [x] These tests should be hermetic: mock `httpx.AsyncClient` with `unittest.mock`

---

## Dev Notes

### ⚠️ CRITICAL BUG — Story 2.1 Silent Data Loss

**Problem**: `backend/api/database.py` is the file used by the `api` Docker service (WORKDIR `/app`, `COPY . .` from `./backend/api`). The `backend/shared/database.py` is NOT used by the API service — it is a canonical reference used by test code only.

Story 2.1 added `score_meta_json`, `contribution_type`, `re_document_type` to **`backend/shared/database.py`** but NOT to **`backend/api/database.py`**. This means:
- `article.contribution_type = score_data.contribution_type` in `internal_score_article` sets a regular Python attribute (not persisted)
- `article.score_meta_json = ...` same — silent data loss

**Fix required in this story** — add to `backend/api/database.py`:

**ORM model** (`Article` class):
```python
# Research dimensions — populated by scorer (Story 2.1)
score_meta_json = Column(Text, nullable=True)
contribution_type = Column(String(24), nullable=True)
re_document_type = Column(String(24), nullable=True)
# Paper enrichment — populated before scoring (Story 2.2)
paper_meta_json = Column(Text, nullable=True)
```

**`init_db()._migrations`** — append these 4 statements to the existing list:
```python
"ALTER TABLE articles ADD COLUMN score_meta_json TEXT",
"ALTER TABLE articles ADD COLUMN contribution_type VARCHAR(24)",
"ALTER TABLE articles ADD COLUMN re_document_type VARCHAR(24)",
"ALTER TABLE articles ADD COLUMN paper_meta_json TEXT",
```

---

### Extractor: `paper_handlers` Architecture

The `paper_handlers` is a **list of 2-tuples** `(detection_fn, async_handler_fn)`:
- `detection_fn(url: str) -> bool` — fast, synchronous, no I/O
- `handler_fn(html: Optional[str], url: str, client: httpx.AsyncClient) -> dict` — async, may call external APIs

The `/extract` endpoint calls `_detect_paper_handler(url)` first. If a handler is found:
1. Fetch the HTML if not already fetched
2. Call the handler with `(html, url, client)`
3. If the handler returns a dict with `"text"`, use it for the response
4. Set `paper_meta` field in `ExtractResponse` from the handler's return value

The `paper_meta` dict returned by handlers has this schema:
```python
{
    "is_paper": True,
    "source": "arxiv",          # "arxiv" | "semanticscholar" | "openreview" | "acl" | "doi" | "fallback"
    "paper_id": "2401.12345",   # source-specific ID
    "doi": "10.48550/arXiv.2401.12345",  # None if not available
    "abstract": "...",
    "authors": ["Alice Smith", "Bob Jones"],
    "year": 2024,
    "methods": [],              # list of strings, populated from SS API if available
    "datasets": [],             # list of strings
    "metrics": [],              # list of strings
    "fields_of_study": [],      # list of strings from SS API
}
```

---

### Extractor: Handler Implementations

**`_extract_arxiv_handler`** (refactor of existing `extract_arxiv`):
- Reuse all existing HTML parsing logic verbatim
- Add call to SS Graph API: `GET https://api.semanticscholar.org/graph/v1/paper/arXiv:{id}?fields=title,abstract,authors,year,externalIds,tldr,fieldsOfStudy`
- SS API returns `authors[].name`, `year`, `externalIds.DOI`, `fieldsOfStudy[].category.name`
- If SS call succeeds: enrich `paper_meta` with these fields
- If SS call fails/times out: return `paper_meta` with what HTML-parse gave us (fallback)
- **Rate limit all SS calls via `_ss_rate_limited_get(client, url)` helper**

**`_extract_semantic_scholar_handler`**:
- Detect S2 paper ID from URL: `semanticscholar.org/paper/{slug}/{40-char-hex-id}`
- Extract S2 paper ID with regex: `r"semanticscholar\.org/paper/[^/]+/([a-f0-9]{40})"` 
- API call: `GET https://api.semanticscholar.org/graph/v1/paper/{s2_id}?fields=title,abstract,authors,year,externalIds,tldr,fieldsOfStudy`
- If SS API fails: fall back to HTML extraction with readability
- Return `paper_meta` with source `"semanticscholar"`, paper_id = `s2_id`, doi from `externalIds.DOI`

**`_extract_openreview_handler`**:
- Extract forum ID from URL: `openreview.net/forum?id={forum_id}`
- API call: `GET https://api2.openreview.net/notes?forum={forum_id}&select=id,content` (no auth, public papers)
- The response `.notes[0].content` has: `title.value`, `abstract.value`, `authors.value`, `keywords.value`
- Return `paper_meta` with source `"openreview"`, paper_id = forum_id, abstract from content

**`_extract_acl_anthology_handler`**:
- Extract ACL ID from URL: e.g., `aclanthology.org/2024.acl-long.1` → ACL ID = `"2024.acl-long.1"`
- SS Graph API call: `GET https://api.semanticscholar.org/graph/v1/paper/ACL:{acl_id}?fields=title,abstract,authors,year,externalIds`
- If SS call fails: HTML parse via readability for content, return minimal `paper_meta`

**`_extract_doi_handler`**:
- Extract DOI from URL: strip `https://doi.org/` prefix → raw DOI string
- Crossref API call: `GET https://api.crossref.org/works/{doi}` (no auth needed)
- Response `.message` has: `title[0]`, `abstract`, `author[].family + given`, `published.date-parts[0][0]`
- Note: Crossref `abstract` may contain JATS XML tags — strip them with BeautifulSoup
- Return `paper_meta` with source `"doi"`, doi = doi string, paper_id = doi

---

### Extractor: SS Rate Limiting

Add these module-level globals at the top of `extractor.py`:
```python
import asyncio
import time  # standard library, already available

_SS_LOCK = asyncio.Lock()
_ss_last_call: float = 0.0
SS_RATE_LIMIT_SECONDS = float(os.getenv("SS_RATE_LIMIT_SECONDS", "1.0"))
```

Add this helper function:
```python
async def _ss_rate_limited_get(
    client: httpx.AsyncClient, url: str, params=None
) -> Optional[httpx.Response]:
    """Rate-limited GET for Semantic Scholar API. Thread-safe via asyncio.Lock."""
    global _ss_last_call
    async with _SS_LOCK:
        now = time.monotonic()
        elapsed = now - _ss_last_call
        if elapsed < SS_RATE_LIMIT_SECONDS:
            await asyncio.sleep(SS_RATE_LIMIT_SECONDS - elapsed)
        try:
            resp = await client.get(url, params=params, timeout=10)
            return resp
        except Exception:
            return None
        finally:
            _ss_last_call = time.monotonic()
```

---

### Poller: `paper_enricher.py`

Create `backend/poller/paper_enricher.py`:

```python
"""
Paper metadata enricher for Baṣīra poller.

Runs AFTER the extractor (which does HTML-based extraction) and BEFORE
create_article. Makes a single cheap Ollama call to classify the abstract.
Returns {} for non-paper URLs within 50ms (no external API calls).
"""
import json
import os
from typing import Optional

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

_PAPER_PATTERNS = [
    "arxiv.org/abs/",
    "semanticscholar.org/paper/",
    "openreview.net/forum",
    "aclanthology.org/",
    "doi.org/",
]

_CLASSIFICATION_PROMPT = (
    "Given this research paper abstract, return a JSON object with ONLY these three fields:\n"
    "- \"contribution_type\": one of "
    "\"method\", \"benchmark\", \"survey\", \"empirical\", "
    "\"theory\", \"position\", \"tool\", \"other\"\n"
    "- \"re_document_type\": one of "
    "\"elicitation\", \"extraction\", \"method\", \"none\" "
    "(is this paper about Requirements Engineering?)\n"
    "- \"confidence\": float 0.0 to 1.0\n\n"
    "Abstract:\n{abstract}\n\n"
    "Reply with valid JSON only. No markdown, no code block, no extra text."
)


def is_paper_url(url: str) -> bool:
    """Return True if URL matches any known paper source pattern.
    Fast path: no I/O, must complete in < 1ms.
    """
    lower = url.lower()
    return any(p in lower for p in _PAPER_PATTERNS)


async def _classify_with_ollama(
    abstract: str, client: httpx.AsyncClient
) -> dict:
    prompt = _CLASSIFICATION_PROMPT.format(abstract=abstract[:2000])
    resp = await client.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"].strip()
    # Strip markdown code fence if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


async def enrich_paper_meta(
    url: str,
    extraction_result: dict,
    client: httpx.AsyncClient,
) -> dict:
    """
    Enrich paper metadata with Ollama classification.

    - For non-paper URLs: returns {} in < 50ms (no API calls).
    - For paper URLs with paper_meta from extractor: calls Ollama to classify.
    - On any failure: returns minimal fallback dict {is_paper: true, source: "fallback"}.
    """
    if not is_paper_url(url):
        return {}

    paper_meta: dict = dict(extraction_result.get("paper_meta") or {})
    if not paper_meta.get("is_paper"):
        # Extractor couldn't get structured data — minimal fallback
        return {"is_paper": True, "source": "fallback"}

    abstract = paper_meta.get("abstract") or extraction_result.get("content_text") or ""
    if not abstract:
        return {"is_paper": True, "source": paper_meta.get("source", "fallback")}

    try:
        classification = await _classify_with_ollama(abstract, client)
        # Only update with valid keys, ignore garbage
        for key in ("contribution_type", "re_document_type", "confidence"):
            if key in classification:
                paper_meta[key] = classification[key]
    except Exception:
        pass  # graceful degradation — paper_meta still contains structural data

    return paper_meta
```

---

### Poller: `main.py` Changes

**1. Add import at top of file:**
```python
from paper_enricher import enrich_paper_meta, is_paper_url
```

**2. Extend `score_article_rate_limited`** — add `paper_meta_json` parameter:
```python
async def score_article_rate_limited(
    client: httpx.AsyncClient,
    article_id: int,
    title: str,
    content_text: str,
    rss_summary: str,
    paper_meta_json: Optional[str] = None,  # NEW
):
    async with _score_semaphore:
        try:
            resp = await client.post(
                f"{SCORER_BASE}/score",
                json={
                    "article_id": article_id,
                    "title": title,
                    "content_text": content_text or "",
                    "rss_summary": rss_summary or "",
                    "paper_meta_json": paper_meta_json,  # NEW
                },
                timeout=120,
            )
            resp.raise_for_status()
        finally:
            await asyncio.sleep(SCORE_DELAY_SECONDS)
```

**3. In `process_feed`, after extraction and before `create_article`** (insert this block):
```python
# Paper enrichment — runs before create_article, before scoring
paper_meta_json: Optional[str] = None
enrichment_contribution_type: Optional[str] = None
enrichment_re_document_type: Optional[str] = None

try:
    paper_meta = await enrich_paper_meta(article_url, extracted, client)
    if paper_meta:
        paper_meta_json = json.dumps(paper_meta)
        enrichment_contribution_type = paper_meta.get("contribution_type")
        enrichment_re_document_type = paper_meta.get("re_document_type")
        log.info("Paper enriched", article_url=article_url, source=paper_meta.get("source"))
except Exception as e:
    log.warning("Paper enrichment failed (non-blocking)", url=article_url, error=str(e))
```

**4. Extend `payload` dict** (in `create_article` call):
```python
payload = {
    # ... existing fields ...
    "paper_meta_json": paper_meta_json,           # NEW
    "contribution_type": enrichment_contribution_type,  # NEW
    "re_document_type": enrichment_re_document_type,    # NEW
}
```

**5. Pass `paper_meta_json` to scorer:**
```python
await score_article_rate_limited(
    client,
    article_id,
    extracted.get("title") or rss_title,
    extracted.get("content_text") or rss_summary,
    rss_summary,
    paper_meta_json=paper_meta_json,   # NEW
)
```

---

### API: `models.py` Changes

**`InternalArticleCreate`** — add three fields:
```python
class InternalArticleCreate(BaseModel):
    # ... existing fields ...
    paper_meta_json: Optional[str] = None
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
```

**`ArticleOut`** — add field and update validator:
```python
class ArticleOut(BaseModel):
    # ... existing fields including score_meta_json, contribution_type, re_document_type ...
    paper_meta_json: Optional[str] = None  # NEW

    # Computed fields (existing ones stay)
    paper_meta: Dict[str, Any] = {}  # NEW

    @model_validator(mode="after")
    def parse_json_fields(self) -> "ArticleOut":
        # ... existing parsing for tags, summary_bullets, images, score_meta ...
        try:
            self.paper_meta = json.loads(self.paper_meta_json or "{}")
        except Exception:
            self.paper_meta = {}
        return self
```

**`ArticleListItem`** — no changes required (contribution_type and re_document_type already there).

---

### API: `routers/internal.py` Changes

In `internal_create_article`, extend the `Article(...)` constructor:
```python
article = Article(
    # ... existing fields ...
    paper_meta_json=article_data.paper_meta_json,       # NEW
    contribution_type=article_data.contribution_type,    # NEW (from enrichment)
    re_document_type=article_data.re_document_type,      # NEW (from enrichment)
)
```

Note: The scorer may OVERWRITE `contribution_type` and `re_document_type` later via `internal_score_article` — this is intentional. Enrichment sets a cheap first-pass classification; the scorer refines it with a more capable model and detailed rubric.

---

### `.env.example` and `.env` Updates

In **`.env.example`**, add after `SCORER_MAX_CHARS`:
```dotenv
# Semantic Scholar API rate limit (seconds between calls)
SS_RATE_LIMIT_SECONDS=1.0
```

In **`.env`**, add same line after `SCORER_MAX_CHARS=6000`.

---

### Extractor: `ExtractResponse` Extension

Add ONE field to the existing model:
```python
class ExtractResponse(BaseModel):
    title: str
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    images: List[str] = []
    author: Optional[str] = None
    read_time_minutes: int = 1
    extraction_failed: bool = False
    canonical_url: Optional[str] = None
    paper_meta: Optional[Any] = None   # NEW — structured paper metadata dict
```

Use `Optional[Any]` (with `from typing import Any` already in scope) to avoid Pydantic v2 issues with arbitrary dict types.

---

### Extractor: Integration Point in `/extract` endpoint

The current `/extract` endpoint has "Strategy 0" for arXiv at the top. Refactor this to use the `paper_handlers` dispatcher:

```python
# ── Strategy 0: Paper-source detection ───────────────────────────────────
# Check paper_handlers FIRST; they call structured APIs and return richer data.
paper_meta_result: dict = {}
_detected_handler = _detect_paper_handler(req.url)
if _detected_handler is not None:
    # Fetch HTML first (handler may or may not need it)
    html = await fetch_url(client, req.url)
    handler_result = await _detected_handler(html, req.url, client)
    if handler_result.get("text"):
        content_text = handler_result["text"]
        content_html = handler_result.get("raw_html")
        extracted_title = handler_result.get("title")
        author = handler_result.get("author")
        paper_meta_result = {
            k: v for k, v in handler_result.items()
            if k not in ("text", "raw_html", "title", "author")
        }
        # For arXiv specifically, also set canonical_url
        if paper_meta_result.get("source") == "arxiv":
            pid = paper_meta_result.get("paper_id", "")
            if pid:
                base_pid = re.sub(r"v\d+$", "", pid)
                canonical_url = f"https://arxiv.org/abs/{base_pid}"
        final_title = resolve_title(extracted_title, req.rss_title, content_text)
        return ExtractResponse(
            title=final_title,
            content_html=content_html,
            content_text=content_text,
            images=[],
            author=author,
            read_time_minutes=estimate_read_time(content_text or ""),
            extraction_failed=False,
            canonical_url=canonical_url,
            paper_meta=paper_meta_result,  # NEW
        )
    # Handler failed: fall through to generic extraction, but keep is_paper signal
    if handler_result.get("is_paper"):
        paper_meta_result = {"is_paper": True, "source": handler_result.get("source", "fallback")}
```

At the final `return ExtractResponse(...)` at the bottom of the endpoint, add:
```python
return ExtractResponse(
    # ... all existing fields ...
    paper_meta=paper_meta_result if paper_meta_result else None,  # NEW
)
```

---

### `_detect_paper_handler` Helper

```python
def _detect_paper_handler(url: str):
    """Return the matching async paper handler function, or None for non-paper URLs."""
    lower = url.lower()
    if ARXIV_ABS_RE.search(url):
        return _extract_arxiv_handler
    if "semanticscholar.org/paper/" in lower:
        return _extract_semantic_scholar_handler
    if "openreview.net/forum" in lower:
        return _extract_openreview_handler
    if "aclanthology.org/" in lower:
        return _extract_acl_anthology_handler
    if lower.startswith("https://doi.org/") or lower.startswith("http://doi.org/"):
        return _extract_doi_handler
    return None
```

---

### Tests: `test_paper_enricher.py`

Path: `backend/scorer/tests/test_paper_enricher.py`
(Can run on host with no Docker deps — uses only stdlib + httpx mock)

Key test cases:
```python
# is_paper_url tests
def test_arxiv_detected():
    assert is_paper_url("https://arxiv.org/abs/2401.12345")

def test_blog_not_detected():
    assert not is_paper_url("https://blog.example.com/my-post")

def test_empty_returns_quickly():
    # enrich_paper_meta returns {} for non-paper URL
    import asyncio
    import httpx
    from unittest.mock import AsyncMock, MagicMock
    client = MagicMock(spec=httpx.AsyncClient)
    result = asyncio.run(
        enrich_paper_meta("https://news.ycombinator.com/item?id=123", {}, client)
    )
    assert result == {}
    client.post.assert_not_called()  # no Ollama call

def test_fallback_on_missing_paper_meta():
    import asyncio
    from unittest.mock import MagicMock
    import httpx
    client = MagicMock(spec=httpx.AsyncClient)
    # is_paper URL but no paper_meta from extractor
    result = asyncio.run(
        enrich_paper_meta(
            "https://arxiv.org/abs/2401.12345",
            {"content_text": None},  # no paper_meta key
            client,
        )
    )
    assert result == {"is_paper": True, "source": "fallback"}
    client.post.assert_not_called()

def test_ollama_classification_merged():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    import httpx
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "message": {
            "content": '{"contribution_type": "method", "re_document_type": "none", "confidence": 0.9}'
        }
    }
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp
    result = asyncio.run(
        enrich_paper_meta(
            "https://arxiv.org/abs/2401.12345",
            {
                "paper_meta": {
                    "is_paper": True,
                    "source": "arxiv",
                    "paper_id": "2401.12345",
                    "abstract": "We present a novel method for ...",
                }
            },
            client,
        )
    )
    assert result["contribution_type"] == "method"
    assert result["re_document_type"] == "none"
    assert result["confidence"] == 0.9
    assert result["is_paper"] is True
```

---

### Important: Extractor Dockerfile — No New Dependencies

The extractor's `requirements.txt` already includes `httpx==0.27.0`, `beautifulsoup4`, `fastapi`, `pydantic` — no new packages needed for the paper handlers.

The poller's `requirements.txt` also already has `httpx==0.27.0` — no new packages needed for `paper_enricher.py`.

---

### Previously Completed Work (Do NOT redo)

- `backend/scorer/scorer.py`: `ScoreRequest.paper_meta_json` already added (Story 2.1)
- `backend/scorer/scorer_logic.py`: `compute_content_cap` already uses `paper_meta_json` to raise cap for papers
- `backend/api/models.py`: `InternalScoreUpdate` already has research fields; `ArticleOut` already has `score_meta_json`, `contribution_type`, `re_document_type`, `score_meta` (but NOT `paper_meta_json` or `paper_meta` — these are NEW in this story)
- `backend/api/routers/internal.py` (`internal_score_article`): already writes `contribution_type`, `re_document_type`, `score_meta_json` from score result (but these writes silently fail until the DB bug is fixed in this story)
- `backend/api/routers/articles.py` (`_row_to_list_item`): already passes `contribution_type` and `re_document_type` to `ArticleListItem`

---

### Failure Mode Summary

| Failure | Expected behavior |
|---|---|
| SS Graph API returns 429 or 500 | `_ss_rate_limited_get` returns `None`, handler falls back to HTML parse, `paper_meta` contains `is_paper: true, source: "fallback"` |
| OpenReview API unavailable | `_extract_openreview_handler` catches exception, returns `{"is_paper": True, "source": "fallback"}` |
| Crossref API timeout | Same pattern — fallback |
| Ollama unavailable or malformed response | `enrich_paper_meta` catches exception in `_classify_with_ollama`, returns `paper_meta` without classification fields (scorer will still work, `contribution_type` may remain null until scorer fills it) |
| Extractor handler returns empty dict | Handler exception path: `paper_meta_result = {"is_paper": True, "source": "fallback"}`, full generic extraction continues for content |
| `enrich_paper_meta` raises | `process_feed` catches exception in `try/except`, `paper_meta_json` stays `None`, article is NOT lost, scoring proceeds normally |

---

### Architecture Compliance

- ARCH4: All new columns nullable, additive `try/except ALTER TABLE` pattern — ✓
- ARCH6: Enrichment runs before `create_article` (before scoring) — ✓
- ARCH8: `SS_RATE_LIMIT_SECONDS` new env var — ✓
- NFR10: Paper handler failures fall back without losing the article — ✓
- NFR11: Migrations idempotent — ✓
- NFR8: No new unauthenticated external endpoints added — ✓ (all API calls are outbound from services)

---

*Generated: 2026-04-22 — Ultimate context engine analysis completed — comprehensive developer guide created*

---

## Dev Agent Record

### Implementation Notes

**Critical bug fixed**: `backend/api/database.py` was missing `score_meta_json`, `contribution_type`, `re_document_type` ORM columns and migrations from Story 2.1. All writes to those columns in `internal_score_article` were silently discarded (SQLAlchemy set a Python attribute not mapped to a column, `db.commit()` did not persist it). Fixed in this story alongside the new `paper_meta_json` column.

**Architecture**: Two-stage design as specified by ARCH6:
1. **Extractor** (`extractor.py`): `paper_handlers` dispatcher list with 5 handlers (arXiv HTML-parse + SS enrichment, SS Graph API, OpenReview API v2, ACL Anthology via SS `ACL:{id}`, Crossref). SS calls serialised via `asyncio.Lock` + monotonic timestamp. Returns structured `paper_meta` dict in `ExtractResponse`.
2. **Enricher** (`paper_enricher.py`): `enrich_paper_meta` merges extractor's `paper_meta` with a single Ollama chat classification (contribution_type, re_document_type, confidence). Non-paper URLs return `{}` in < 1ms; all failures degrade gracefully.
3. **Poller** (`main.py`): Enrichment called after extraction, before `create_article`. `paper_meta_json`, `contribution_type`, `re_document_type` included in create payload. `paper_meta_json` forwarded to scorer for content-cap adjustment.
4. **API** (`models.py`, `internal.py`): `paper_meta_json` persisted on article creation; `ArticleOut` exposes parsed `paper_meta` dict.

### Test Results

- `test_paper_enricher.py`: 24/24 passing (host, no Docker)
- `test_prompt.py`: 23/23 passing (regression)
- `test_scorer_logic.py`: 43/43 passing (regression)
- **Total: 90 tests, 0 failures**

### File List

- `backend/api/database.py` — added 4 ORM columns (score_meta_json, contribution_type, re_document_type, paper_meta_json) + 4 migrations
- `backend/shared/database.py` — added paper_meta_json ORM column + migration
- `backend/extractor/extractor.py` — added SS rate-limiting, 5 paper handlers, paper_handlers dispatcher, _detect_paper_handler, ExtractResponse.paper_meta field, updated /extract endpoint
- `backend/poller/paper_enricher.py` — NEW FILE: is_paper_url, _classify_with_ollama, enrich_paper_meta
- `backend/api/models.py` — InternalArticleCreate: +3 fields; ArticleOut: +paper_meta_json, +paper_meta computed field
- `backend/api/routers/internal.py` — internal_create_article: writes paper_meta_json, contribution_type, re_document_type
- `backend/poller/main.py` — import paper_enricher, enrichment block in process_feed, score_article_rate_limited +paper_meta_json param
- `.env.example` — added SS_RATE_LIMIT_SECONDS
- `.env` — added SS_RATE_LIMIT_SECONDS
- `backend/scorer/tests/test_paper_enricher.py` — NEW FILE: 24 unit tests
- `_bmad-output/implementation-artifacts/2-2-paper-aware-enrichment-pipeline.md` — this story file

### Change Log

- 2026-04-22: Story 2.2 implemented — Paper-Aware Enrichment Pipeline complete
