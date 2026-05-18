---
epic: 5
story: 5
story_key: "5-5-in-corpus-citation-graph"
---

# Story 5.5: In-Corpus Citation Graph

Status: draft

## Story

As a **PhD researcher**,
I want to know how many papers I've already ingested cite each other,
So that I can identify the foundational pillars of my literature corpus — the papers that everyone else builds on — and prioritize reading them.

## Acceptance Criteria

1. **Given** the `articles` table
   **When** migrations run
   **Then** two new nullable columns exist: `ss_paper_id TEXT` (the Semantic Scholar paper ID) and `cited_by_corpus_count INTEGER DEFAULT 0`

2. **Given** the paper enricher runs on a new article with arXiv or DOI metadata
   **When** the enrichment result is stored in `paper_meta_json`
   **Then** the `ss_paper_id` column is also populated directly from `paper_meta.paperId` (not just buried in the JSON blob)
   **And** this allows fast DB queries without JSON parsing

3. **Given** the citation indexer runs (via `POST /api/research/citations/index` or weekly scheduler)
   **When** processing a paper with a valid `ss_paper_id`
   **Then** the SS `/paper/{id}/references` endpoint is called to retrieve papers it cites
   **And** for each reference with a matching `ss_paper_id` in the DB, that article's `cited_by_corpus_count` is incremented by 1
   **And** `cited_by_corpus_count` for any article is never double-counted (a paper can only contribute once per citation relationship)
   **And** on SS API rate limit (429) the indexer sleeps 5 seconds and retries once before skipping

4. **Given** `cited_by_corpus_count > 0` for an article
   **When** `GET /api/articles` returns it as an `ArticleListItem`
   **Then** `cited_by_corpus_count: int` is included in the response (0 for uncited articles)
   **And** `?sort=cited_by_corpus` is a valid sort option that orders articles by `cited_by_corpus_count` descending

5. **Given** `cited_by_corpus_count >= 2`
   **When** `ArticleCard` renders the article
   **Then** a small teal badge shows "cited by N" (only when N ≥ 2 to reduce noise)

6. **Given** an authenticated user
   **When** `GET /api/research/citations/stats` is called
   **Then** a JSON response is returned with:
   - `indexed_papers` (count of articles with non-null ss_paper_id)
   - `total_citation_links` (sum of cited_by_corpus_count across all articles)
   - `top_cited` (top 10 articles by cited_by_corpus_count: `{id, title, score, cited_by_corpus_count}`)
   - `last_indexed_at` (datetime of most recent indexer run, or null)

---

## Tasks / Subtasks

- [ ] Backend: Add columns to `Article` ORM and migrations in `backend/api/database.py` (AC: 1)
  - [ ] Add `ss_paper_id = Column(String(64), nullable=True, index=True)` to `Article`
  - [ ] Add `cited_by_corpus_count = Column(Integer, default=0, nullable=False)` to `Article`
  - [ ] Add both `ALTER TABLE` migrations to `init_db()._migrations`
  - [ ] Add `CREATE INDEX IF NOT EXISTS ix_articles_ss_paper_id ON articles(ss_paper_id)` migration

- [ ] Backend: Update paper enricher in `backend/poller/paper_enricher.py` to write `ss_paper_id` (AC: 2)
  - [ ] After fetching SS metadata, include `ss_paper_id` in the internal article create/update call
  - [ ] Extend `InternalArticleCreate` in `models.py` to accept `ss_paper_id: Optional[str] = None`
  - [ ] In `internal_create_article` (internal.py), write `article.ss_paper_id = payload.ss_paper_id`

- [ ] Backend: Create `backend/api/citation_indexer.py` with the citation graph logic (AC: 3)
  - [ ] `async def index_citations(db: Session) -> CitationIndexResult`
  - [ ] Iterate all articles with `ss_paper_id IS NOT NULL`
  - [ ] For each: GET SS `/paper/{id}/references?fields=paperId&limit=100`
  - [ ] Cross-reference returned `paperId` values against `articles.ss_paper_id` in DB (single IN query)
  - [ ] For each match, increment `cited_by_corpus_count` (avoid double-counting via a `citation_links` tracking set in memory during the run)
  - [ ] Rate limiting: 1 request/second (asyncio.sleep(1)); retry once on 429 with 5s sleep
  - [ ] Store `last_indexed_at` in `settings` table (key="citations_last_indexed_at")

- [ ] Backend: Add Pydantic models to `backend/api/models.py` (AC: 4, 6)
  - [ ] Add `cited_by_corpus_count: int = 0` to `ArticleListItem`
  - [ ] `CitationIndexResult` (indexed_papers, total_citation_links, last_indexed_at)
  - [ ] `CitationStatsOut` (indexed_papers, total_citation_links, top_cited, last_indexed_at)
  - [ ] `TopCitedItem` (id, title, score, cited_by_corpus_count)

- [ ] Backend: Update article list query to support `sort=cited_by_corpus` (AC: 4)
  - [ ] In `backend/api/routers/articles.py`, add `"cited_by_corpus"` to the valid sort options
  - [ ] Apply `order_by(Article.cited_by_corpus_count.desc())` when this sort is selected

- [ ] Backend: Add endpoints to `backend/api/routers/research.py` (AC: 3, 6)
  - [ ] `POST /api/research/citations/index` → trigger indexer (returns `CitationIndexResult`)
  - [ ] `GET /api/research/citations/stats` → return stats

- [ ] Frontend: Update `ArticleListItem` in `frontend/src/types.ts` (AC: 4, 5)
  - [ ] Add `cited_by_corpus_count?: number`

- [ ] Frontend: Add "cited by N" badge to `ArticleCard.tsx` (AC: 5)
  - [ ] Teal/cyan badge, only renders when `cited_by_corpus_count >= 2`
  - [ ] `<span>cited by {cited_by_corpus_count}</span>`

- [ ] Frontend: Add `sort=cited_by_corpus` option to sort selector in `ArticleList.tsx` (AC: 4)
  - [ ] Label: "Most cited in corpus"

---

## Dev Notes

### SS References Endpoint

```
GET https://api.semanticscholar.org/graph/v1/paper/{paperId}/references
    ?fields=paperId
    &limit=100
```

Response structure:
```json
{
  "data": [
    {"citedPaper": {"paperId": "abc123"}},
    ...
  ]
}
```

Extract `[ref["citedPaper"]["paperId"] for ref in data["data"] if ref.get("citedPaper")]`.

### Double-Count Prevention

The indexer resets `cited_by_corpus_count = 0` for ALL articles at the start of each full run, then recomputes from scratch. This avoids accumulation drift across multiple runs:

```python
# Step 1: reset all counts
db.query(Article).filter(Article.ss_paper_id.isnot(None)).update(
    {Article.cited_by_corpus_count: 0}, synchronize_session=False
)
db.commit()

# Step 2: build citation map
corpus_paper_ids = {
    row.ss_paper_id: row.id
    for row in db.query(Article.ss_paper_id, Article.id)
    .filter(Article.ss_paper_id.isnot(None)).all()
}
# Step 3: for each paper, fetch references, increment matches
```

This "reset and recompute" pattern is correct for a corpus of up to ~10k papers. One full run = at most 10k SS API calls, rate-limited to 1/sec = ~3 hours max. In practice, most articles are blog posts without `ss_paper_id`, so the actual count is much lower (hundreds).

### `ss_paper_id` Population in Enricher

In `paper_enricher.py`, the SS API response already returns `paperId` at the top level:
```json
{"paperId": "abc123", "title": "...", "authors": [...]}
```

Currently this is stored only inside `paper_meta_json`. Add one line to also write it to `InternalArticleCreate.ss_paper_id` before calling the API:

```python
paper_meta["ss_paper_id"] = ss_data.get("paperId")  # for direct column
payload["ss_paper_id"] = ss_data.get("paperId")
```

Then in `internal.py / internal_create_article`: `article.ss_paper_id = payload.ss_paper_id`.

### Avoiding Long Blocking Runs

The citation indexer can be slow (hours for large corpora). Make it a fire-and-forget background task:

```python
@router.post("/api/research/citations/index")
async def trigger_citation_index(background_tasks: BackgroundTasks, db=Depends(get_db), _=_auth):
    background_tasks.add_task(index_citations, db)
    return {"status": "indexing started"}
```

Use FastAPI's `BackgroundTasks` (not `asyncio.create_task`) since this is a long-running sync-heavy task.

### Article Sort Extension

Current sort logic in `articles.py` uses `if sort == "score": order_by(Article.score.desc())`. Add:

```python
elif sort == "cited_by_corpus":
    query = query.order_by(Article.cited_by_corpus_count.desc())
```

### Test Strategy

- `test_ss_paper_id_extracted_from_enrichment`: mock SS response → `ss_paper_id` column populated
- `test_citation_indexer_increments_count`: seed 2 articles with ss_paper_ids where A cites B → B.cited_by_corpus_count = 1
- `test_citation_indexer_reset_on_rerun`: run twice → counts not doubled
- `test_sort_by_cited_corpus`: articles with counts 0, 3, 1 → sort returns 3, 1, 0
- `test_badge_threshold`: cited_by_corpus_count=1 → no badge in response; count=2 → badge
- `test_429_retry`: mock SS to return 429 then 200 → success after retry; mock two 429s → article skipped
