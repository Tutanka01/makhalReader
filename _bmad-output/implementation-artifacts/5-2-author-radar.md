---
epic: 5
story: 2
story_key: "5-2-author-radar"
---

# Story 5.2: Author Radar

Status: draft

## Story

As a **PhD researcher**,
I want the system to automatically track key authors from my high-scored papers and surface their new publications,
So that I never miss a new paper from the 20–30 researchers who matter most to my thesis, without having to manually monitor Semantic Scholar or Google Scholar.

## Acceptance Criteria

1. **Given** an article with `score >= 7` and a non-empty `paper_meta_json` containing `authors` with Semantic Scholar author IDs
   **When** the article is scored and `embed_article_async` completes
   **Then** each author with a valid `authorId` is upserted into the `tracked_authors` table (fields: `ss_author_id`, `name`)
   **And** the article's contribution to that author's stats (`paper_count`, `avg_score`) is reflected via an UPDATE on existing rows

2. **Given** the `tracked_authors` table has rows
   **When** `GET /api/research/authors` is called
   **Then** a JSON array is returned, each entry containing: `ss_author_id`, `name`, `paper_count` (papers in corpus), `avg_score`, `alert_count` (new papers found by radar), sorted by `avg_score * paper_count` descending

3. **Given** the author radar runs (via `POST /api/research/authors/scan` or weekly scheduler)
   **When** a tracked author has published a paper not yet in the DB (checked via SS `/author/{id}/papers` endpoint, matched by `externalId.ArXiv` or DOI against existing `article.url` / `paper_meta_json`)
   **Then** the new paper's SS metadata is queued for ingestion — the poller's `process_paper_url` logic is reused to create and score it
   **And** the `tracked_author_alert` column on the new article is set to `True` to mark it as radar-discovered
   **And** `last_checked` on the `tracked_authors` row is updated to `now()`
   **And** on SS API failure the author is skipped with a warning log; the scan continues

4. **Given** an article was discovered via the author radar (`tracked_author_alert = True`)
   **When** `GET /api/articles` returns it as an `ArticleListItem`
   **Then** `tracked_author_alert: true` is included in the response
   **And** `ArticleCard` renders a small `👤 Radar` badge on the article

5. **Given** an authenticated user
   **When** `DELETE /api/research/authors/{ss_author_id}` is called
   **Then** the author is removed from `tracked_authors`
   **And** existing articles discovered by this author retain their `tracked_author_alert = True` flag (no cascade delete on articles)

---

## Tasks / Subtasks

- [ ] Backend: Add `TrackedAuthor` ORM model and migrations to `backend/api/database.py` (AC: 1, 2)
  - [ ] Add `TrackedAuthor` class (ss_author_id TEXT UNIQUE, name TEXT, paper_count INT, avg_score REAL, alert_count INT, last_checked DATETIME, created_at DATETIME)
  - [ ] Add `tracked_author_alert BOOLEAN DEFAULT 0` column to `Article` ORM
  - [ ] Add migrations to `init_db()._migrations` (CREATE TABLE + ALTER TABLE)

- [ ] Backend: Add Pydantic models to `backend/api/models.py` (AC: 2)
  - [ ] `TrackedAuthorOut` (ss_author_id, name, paper_count, avg_score, alert_count, last_checked)
  - [ ] `AuthorScanResponse` (authors_checked, new_articles_queued, skipped)

- [ ] Backend: Update `embed_article_async` in `backend/api/embedder.py` to upsert authors after embedding (AC: 1)
  - [ ] Parse `article.paper_meta_json` → extract `authors` list
  - [ ] For each author with `authorId` and `score >= 7`: upsert into `tracked_authors`
  - [ ] UPDATE `avg_score` and `paper_count` via running average formula: `new_avg = (old_avg * old_count + score) / (old_count + 1)`
  - [ ] Wrap in try/except — author upsert failure must NOT affect embedding

- [ ] Backend: Add `tracked_author_alert` to `ArticleListItem` in `backend/api/models.py` and `_row_to_list_item` in articles router (AC: 4)

- [ ] Backend: Add endpoints to `backend/api/routers/research.py` (AC: 2, 3, 5)
  - [ ] `GET /api/research/authors` → list tracked authors sorted by relevance score
  - [ ] `POST /api/research/authors/scan` → trigger radar scan (async background task)
  - [ ] `DELETE /api/research/authors/{ss_author_id}` → remove author from tracking

- [ ] Backend: Create `backend/api/author_radar.py` with the scan logic (AC: 3)
  - [ ] `scan_author(ss_author_id, name, db)` → fetch SS papers, find new ones, queue ingestion
  - [ ] Reuse SS API base URL from `paper_enricher.py` (`SS_API_BASE`)
  - [ ] `run_author_radar_scan(db)` → iterate all tracked authors, call `scan_author` for each

- [ ] Frontend: Update `frontend/src/types.ts` (AC: 4)
  - [ ] Add `tracked_author_alert?: boolean` to `ArticleListItem`
  - [ ] Add `TrackedAuthor` interface

- [ ] Frontend: Add `👤 Radar` badge to `ArticleCard.tsx` when `tracked_author_alert === true` (AC: 4)

- [ ] Frontend: Create `AuthorRadarView.tsx` in `frontend/src/components/` (AC: 2, 5)
  - [ ] Table of tracked authors: name, paper_count, avg_score, alert_count, last_checked
  - [ ] "Scan now" button → POST /api/research/authors/scan
  - [ ] Delete button per row → DELETE /api/research/authors/{ss_author_id}
  - [ ] Empty state: "No tracked authors yet. Authors from papers scored 7+ are added automatically."

- [ ] Frontend: Add `AuthorRadarView` to sidebar navigation in `Sidebar.tsx` / `App.tsx`

---

## Dev Notes

### Semantic Scholar Author Data in `paper_meta_json`

The existing `paper_enricher.py` already fetches author data from SS and stores it in `paper_meta_json`. The structure is:

```json
{
  "authors": [
    {"authorId": "1234567", "name": "Jean-Michel Bruel"},
    {"authorId": "7654321", "name": "Benoit Combemale"}
  ],
  ...
}
```

`embed_article_async` runs after scoring — it already opens a DB session and reads the article. Adding author upsert there keeps the pipeline clean: score → embed → track authors.

### Author Upsert SQL Pattern

Use the SQLite `INSERT OR IGNORE` + `UPDATE` pattern (not `UPSERT` which requires newer SQLite):

```python
db.execute(text("""
    INSERT OR IGNORE INTO tracked_authors 
    (ss_author_id, name, paper_count, avg_score, alert_count, last_checked, created_at)
    VALUES (:ss_id, :name, 0, 0.0, 0, NULL, :now)
"""), {"ss_id": ss_id, "name": name, "now": datetime.now(timezone.utc)})

author = db.query(TrackedAuthor).filter_by(ss_author_id=ss_id).first()
new_count = author.paper_count + 1
new_avg = (author.avg_score * author.paper_count + article.score) / new_count
author.paper_count = new_count
author.avg_score = round(new_avg, 3)
db.commit()
```

### SS Author Papers Endpoint

```
GET https://api.semanticscholar.org/graph/v1/author/{authorId}/papers
    ?fields=title,externalIds,year,publicationDate
    &limit=10
```

Filter results to papers published in the last 90 days (by `publicationDate`). Check if `externalIds.ArXiv` matches any existing article URL pattern `arxiv.org/abs/{id}` in the DB.

Use the same `SS_BASE` and `SS_API_KEY` env vars from `paper_enricher.py`. Rate limit: 1 request/second (SS free tier). Add `asyncio.sleep(1)` between author checks.

### Ingestion of New Radar Papers

When a new paper is found:
1. Build an arXiv RSS-style URL: `https://arxiv.org/abs/{arxiv_id}`
2. Call the existing internal article creation path: `POST /api/internal/articles` — this triggers extraction + scoring automatically
3. Set `tracked_author_alert = True` on the created article

The simplest implementation: call the poller's logic by importing `process_feed_url` or just make an HTTP call to the API's internal endpoint with `tracked_author_alert=True` in the payload. Extend `InternalArticleCreate` in `models.py` to accept `tracked_author_alert: bool = False`.

### `TrackedAuthor` ORM

```python
class TrackedAuthor(Base):
    __tablename__ = "tracked_authors"
    id = Column(Integer, primary_key=True, index=True)
    ss_author_id = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False)
    paper_count = Column(Integer, default=0, nullable=False)
    avg_score = Column(Float, default=0.0, nullable=False)
    alert_count = Column(Integer, default=0, nullable=False)
    last_checked = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

### Relevance Ranking Formula

Sort order for `GET /api/research/authors`:
```python
# Higher avg_score AND more papers in corpus = more important author
relevance = author.avg_score * math.log1p(author.paper_count)
```

### Test Strategy

- `test_author_upsert_on_embed`: mock article with paper_meta_json authors → verify tracked_authors row created with correct avg_score
- `test_author_avg_score_update`: same author appears in two papers (score 8, then score 6) → avg_score = 7.0
- `test_scan_skips_existing_articles`: SS returns paper whose arxiv ID already exists in DB → not re-ingested
- `test_scan_author_ss_failure`: SS returns 429 → author skipped, scan continues
- `test_author_delete_preserves_articles`: delete tracked_author → articles with tracked_author_alert=True unchanged
