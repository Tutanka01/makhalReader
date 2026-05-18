---
epic: 5
story: 4
story_key: "5-4-reading-debt-dashboard"
---

# Story 5.4: Reading Debt Dashboard

Status: draft

## Story

As a **PhD researcher**,
I want a clear view of my unread high-value papers with estimated reading time and weekly progress,
So that my backlog is visible rather than invisible, I can set realistic reading goals, and I'm motivated to work through important papers before they age out of relevance.

## Acceptance Criteria

1. **Given** articles exist in the DB
   **When** `GET /api/stats/reading-debt` is called by an authenticated user
   **Then** a JSON object is returned with:
   - `unread_high` (count of unread articles with score ≥ 7)
   - `unread_critical` (count of unread articles with score ≥ 9)
   - `unread_high_minutes` (estimated total reading time in minutes for score ≥ 7 unread articles)
   - `weekly_goal` (from settings, default 10)
   - `weekly_progress` (articles read in the last 7 days)
   - `backlog_clear_days` (float: at current weekly rate, days until unread_high = 0; null if progress = 0)
   - `oldest_unread_high` (list of top 5 oldest unread articles with score ≥ 7: `{id, title, score, age_days}`)
   - `score_distribution` (list of `{bucket: "9-10"|"8-9"|"7-8"|"<7", unread_count}`)

2. **Given** a user wants to set a reading goal
   **When** `PUT /api/stats/reading-goal` is called with `{"weekly_goal": 15}`
   **Then** the goal is persisted in the `settings` table (key-value store)
   **And** subsequent calls to `GET /api/stats/reading-debt` reflect the new goal
   **And** `weekly_goal` must be an integer between 1 and 100; values outside this range return HTTP 422

3. **Given** `StatsView` is open in the browser
   **When** the "Reading Debt" section renders
   **Then** a large number shows unread papers with score ≥ 7 and their estimated total reading time
   **And** a horizontal progress bar shows `weekly_progress / weekly_goal` (green when ≥ 100%)
   **And** a line reads "At your current pace, clear in N days" (or "Set a goal and read to see estimate" when progress = 0)
   **And** the top 5 oldest high-value unread articles are listed as clickable cards that open the article in the reader

4. **Given** an article's `content_text` is available
   **When** reading time is estimated
   **Then** `minutes = max(3, len(content_text.split()) / 200)` rounded to nearest integer
   **And** for articles with `content_text IS NULL`, a default of 8 minutes is used
   **And** the total `unread_high_minutes` is the sum across all unread score ≥ 7 articles

---

## Tasks / Subtasks

- [ ] Backend: Add `settings` table to `backend/api/database.py` (AC: 2)
  - [ ] Add `Settings` ORM class: `key VARCHAR(64) PRIMARY KEY, value TEXT NOT NULL`
  - [ ] Add `CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)` to `init_db()._migrations`

- [ ] Backend: Add Pydantic models to `backend/api/models.py` (AC: 1, 2)
  - [ ] `ReadingDebtOut` with all fields from AC 1
  - [ ] `OldestUnreadItem`: `{id, title, score, age_days}`
  - [ ] `ScoreBucket`: `{bucket: str, unread_count: int}`
  - [ ] `ReadingGoalUpdate`: `{weekly_goal: int}` with validator `ge=1, le=100`

- [ ] Backend: Add `GET /api/stats/reading-debt` to `backend/api/routers/stats.py` (AC: 1, 4)
  - [ ] Query: all unread articles (read_at IS NULL) grouped by score band
  - [ ] Estimate reading time per article using content_text word count
  - [ ] Compute weekly_progress: articles where `read_at >= now() - 7 days`
  - [ ] Read `weekly_goal` from `settings` table (key="weekly_goal", default 10)
  - [ ] Compute `backlog_clear_days`: `(unread_high / (weekly_progress / 7))` if weekly_progress > 0 else null

- [ ] Backend: Add `PUT /api/stats/reading-goal` to `backend/api/routers/stats.py` (AC: 2)
  - [ ] Upsert into `settings` table: `INSERT OR REPLACE INTO settings (key, value) VALUES ('weekly_goal', ?)`

- [ ] Frontend: Update `frontend/src/types.ts` (AC: 3)
  - [ ] Add `ReadingDebt` interface matching `ReadingDebtOut`
  - [ ] Add `OldestUnreadItem` interface

- [ ] Frontend: Add `ReadingDebt` section to `StatsView.tsx` (AC: 3)
  - [ ] `useEffect` on mount: fetch `GET /api/stats/reading-debt`
  - [ ] Display: large counter for unread_high, subtitle with estimated hours (`Math.round(minutes/60)h`)
  - [ ] Weekly progress bar: `weekly_progress / weekly_goal * 100%`
  - [ ] Backlog clear estimate string
  - [ ] Score distribution mini-chart (4 horizontal bars, one per bucket)
  - [ ] Top 5 oldest unread list: click → navigate to article in reader (call `fetchArticle(id)` from store)
  - [ ] Inline goal editor: number input for `weekly_goal` with PUT on blur

---

## Dev Notes

### `Settings` ORM

```python
class Settings(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
```

Access pattern:
```python
def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(Settings).filter_by(key=key).first()
    return row.value if row else default

def set_setting(db: Session, key: str, value: str) -> None:
    db.merge(Settings(key=key, value=value))
    db.commit()
```

`db.merge()` is SQLAlchemy's upsert-by-primary-key — correct for this single-key pattern.

### Reading Debt Query

```python
from sqlalchemy import func, case

unread = (
    db.query(
        Article.id,
        Article.title,
        Article.score,
        Article.content_text,
        Article.created_at,
    )
    .filter(Article.read_at.is_(None), Article.score.isnot(None))
    .all()
)

unread_high = [a for a in unread if a.score >= 7]
unread_critical = [a for a in unread if a.score >= 9]

def est_minutes(content_text):
    if not content_text:
        return 8
    return max(3, round(len(content_text.split()) / 200))

total_minutes = sum(est_minutes(a.content_text) for a in unread_high)
```

This is an in-Python computation after a single query — acceptable for a corpus up to ~50k articles. If performance becomes an issue, move to a SQL aggregate with a fixed 8-min default.

### Weekly Progress Query

```python
from datetime import timedelta
week_ago = datetime.now(timezone.utc) - timedelta(days=7)
weekly_progress = (
    db.query(func.count(Article.id))
    .filter(Article.read_at >= week_ago)
    .scalar()
) or 0
```

### Backlog Clear Days Formula

```python
if weekly_progress > 0:
    articles_per_day = weekly_progress / 7.0
    backlog_clear_days = round(len(unread_high) / articles_per_day, 1)
else:
    backlog_clear_days = None
```

### Score Distribution Buckets

```python
buckets = {
    "9-10": len([a for a in unread if a.score >= 9]),
    "8-9":  len([a for a in unread if 8 <= a.score < 9]),
    "7-8":  len([a for a in unread if 7 <= a.score < 8]),
    "<7":   len([a for a in unread if a.score < 7]),
}
```

Return as `[{bucket, unread_count}]` in descending priority order.

### Oldest Unread Top 5

```python
now = datetime.now(timezone.utc)
oldest = sorted(unread_high, key=lambda a: a.created_at)[:5]
oldest_out = [
    OldestUnreadItem(
        id=a.id,
        title=a.title,
        score=a.score,
        age_days=(now - a.created_at.replace(tzinfo=timezone.utc)).days,
    )
    for a in oldest
]
```

### Frontend Progress Bar

```tsx
const pct = Math.min(100, Math.round((debt.weekly_progress / debt.weekly_goal) * 100))
<div className="h-2 rounded-full bg-bg-subtle">
  <div
    className={`h-2 rounded-full transition-all ${pct >= 100 ? 'bg-accent-green' : 'bg-accent-blue'}`}
    style={{ width: `${pct}%` }}
  />
</div>
```

### Test Strategy

- `test_debt_empty_db`: no articles → all counts 0, backlog_clear_days null
- `test_reading_time_estimation`: article with 1000 words → 5 minutes; no content_text → 8 minutes
- `test_backlog_clear_days_null_when_no_progress`: weekly_progress=0 → null (not division by zero)
- `test_weekly_goal_upsert`: PUT twice → single settings row, second value wins
- `test_weekly_goal_validation`: goal=0 → 422; goal=101 → 422; goal=10 → 200
- `test_score_distribution_correctness`: seed articles at scores 9.5, 8.5, 7.5, 6.5 → verify bucket counts
