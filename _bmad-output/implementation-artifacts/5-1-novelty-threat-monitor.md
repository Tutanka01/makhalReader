---
epic: 5
story: 1
story_key: "5-1-novelty-threat-monitor"
---

# Story 5.1: Novelty Threat Monitor

Status: draft

## Story

As a **PhD researcher**,
I want the system to automatically compare new high-scored papers against my stated thesis contribution and flag any significant overlap,
So that I can immediately assess whether a paper threatens my originality claim and understand exactly how my contribution remains distinct.

## Acceptance Criteria

1. **Given** a `thesis_contribution` table exists and has a non-empty statement row
   **When** `POST /api/research/threats/scan` is called (manually or by the weekly scheduler)
   **Then** all articles scored ≥ 7 ingested in the last `window_days` (default 14) that have not yet been assessed are passed to the LLM one by one
   **And** each assessment is stored as a row in `novelty_alerts` with: `article_id`, `overlap_score` (0.0–1.0), `positioning_note` (2–3 sentences explaining overlap and difference), `checked_at`
   **And** on any LLM failure the article is skipped (not stored), logged as a warning, and the scan continues

2. **Given** a `novelty_alerts` row exists with `overlap_score >= 0.6`
   **When** `GET /api/articles` returns that article as an `ArticleListItem`
   **Then** the `ArticleListItem` includes `threat_overlap: float | null` derived from the most recent alert for that article

3. **Given** an authenticated user
   **When** `GET /api/research/threats?since_days=30&min_overlap=0.5` is called
   **Then** a JSON array of threat assessments is returned, each containing: `article_id`, `title`, `url`, `score`, `overlap_score`, `positioning_note`, `checked_at`
   **And** results are sorted by `overlap_score` descending

4. **Given** the researcher wants to update their contribution statement
   **When** `PUT /api/research/profile/contribution` is called with `{"statement": "..."}` (max 2000 chars)
   **Then** the `thesis_contribution` table is updated (upsert — only one row ever exists)
   **And** `GET /api/research/profile/contribution` returns the current statement and `updated_at`

5. **Given** a paper has `threat_overlap >= 0.6` in its `ArticleListItem`
   **When** the `ArticleCard` renders
   **Then** a red `⚠ Overlap` badge with the percentage is shown alongside the contribution type badge
   **And** hovering the badge shows the `positioning_note` in a tooltip

6. **Given** no `thesis_contribution` row exists
   **When** `POST /api/research/threats/scan` is called
   **Then** HTTP 400 is returned with `{"detail": "No thesis contribution statement configured. Use PUT /api/research/profile/contribution first."}`

---

## Tasks / Subtasks

- [ ] Backend: Add DB tables and ORM models to `backend/api/database.py` (AC: 1, 4)
  - [ ] Add `ThesisContribution` ORM class (singleton: id=1, statement TEXT, updated_at DATETIME)
  - [ ] Add `NoveltyAlert` ORM class (id, article_id FK, overlap_score REAL, positioning_note TEXT, checked_at DATETIME)
  - [ ] Add `CREATE TABLE IF NOT EXISTS` migrations for both tables to `init_db()._migrations`

- [ ] Backend: Add Pydantic models to `backend/api/models.py` (AC: 3, 4)
  - [ ] `ThesisContributionOut` (statement, updated_at)
  - [ ] `ThesisContributionUpdate` (statement: str, max_length=2000)
  - [ ] `NoveltyAlertOut` (article_id, title, url, score, overlap_score, positioning_note, checked_at)
  - [ ] `ThreatScanResponse` (scanned: int, alerts_created: int, skipped: int)

- [ ] Backend: Add `threat_overlap` to `ArticleListItem` in `backend/api/models.py` (AC: 2)
  - [ ] Add `threat_overlap: Optional[float] = None` field

- [ ] Backend: Update `_row_to_list_item` in `backend/api/routers/articles.py` (AC: 2)
  - [ ] Join `novelty_alerts` on article_id in the query, pass `threat_overlap` from the most recent alert row

- [ ] Backend: Add endpoints to `backend/api/routers/research.py` (AC: 1, 3, 4, 6)
  - [ ] `GET /api/research/profile/contribution` → returns current statement (or null)
  - [ ] `PUT /api/research/profile/contribution` → upsert statement
  - [ ] `POST /api/research/threats/scan` → trigger LLM scan (async, returns `ThreatScanResponse`)
  - [ ] `GET /api/research/threats` → list recent alerts (query params: `since_days=30`, `min_overlap=0.0`)

- [ ] Frontend: Add `threat_overlap` to `ArticleListItem` in `frontend/src/types.ts` (AC: 5)
  - [ ] `threat_overlap?: number | null`

- [ ] Frontend: Create `ThreatBadge.tsx` in `frontend/src/components/` (AC: 5)
  - [ ] Renders only when `threat_overlap >= 0.6`
  - [ ] Red badge: `⚠ {Math.round(overlap*100)}% overlap`
  - [ ] Tooltip on hover showing positioning_note (fetched from the alerts endpoint or passed as prop)

- [ ] Frontend: Add `ThreatBadge` to `ArticleCard.tsx` alongside `ContribTypeBadge` (AC: 5)

- [ ] Frontend: Add `ThreatView` panel to the sidebar in `Sidebar.tsx` or as a new route in `App.tsx`
  - [ ] Shows list of recent threats sorted by overlap_score desc
  - [ ] "Scan now" button → POST /api/research/threats/scan
  - [ ] Contribution statement editor (textarea + save button)

---

## Dev Notes

### LLM Call Pattern

Follow `backend/api/routers/ask.py` for the direct LLM call pattern from within the API service (not the scorer service). The threat scan uses the same 3-tier routing: `UNI_OLLAMA_URL` → local `OLLAMA_URL` → `OPENROUTER_API_KEY`.

**System prompt for threat assessment:**
```
You are a research novelty analyst. You compare an academic paper's contribution against a PhD researcher's stated thesis contribution and assess overlap.

Respond with valid JSON only:
{
  "overlap_score": <float 0.0–1.0>,
  "positioning_note": "<2–3 sentences: what overlaps, and crucially how the researcher's contribution remains distinct>"
}

overlap_score guide:
0.0–0.3: No meaningful overlap — different domain, method, or problem
0.3–0.6: Partial overlap — similar topic but different approach or scope
0.6–0.8: Significant overlap — same problem space, requires differentiation
0.8–1.0: Critical — paper likely covers the researcher's core contribution
```

**User message template:**
```
RESEARCHER'S THESIS CONTRIBUTION:
{statement}

PAPER TO ASSESS:
Title: {article.title}
Summary: {"\n".join(article.summary_bullets)}
Tags: {", ".join(article.tags)}
Scorer reason: {article.reason}

Assess overlap.
```

### DB Schema Additions

Add to `backend/api/database.py`:

```python
class ThesisContribution(Base):
    __tablename__ = "thesis_contribution"
    id = Column(Integer, primary_key=True, default=1)  # singleton
    statement = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False)

class NoveltyAlert(Base):
    __tablename__ = "novelty_alerts"
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    overlap_score = Column(Float, nullable=False)
    positioning_note = Column(Text, nullable=False)
    checked_at = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint("article_id", name="ux_novelty_alert_article"),)
```

Add to `init_db()._migrations`:
```python
"CREATE TABLE IF NOT EXISTS thesis_contribution (id INTEGER PRIMARY KEY DEFAULT 1, statement TEXT NOT NULL, updated_at DATETIME NOT NULL)",
"CREATE TABLE IF NOT EXISTS novelty_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, overlap_score REAL NOT NULL, positioning_note TEXT NOT NULL, checked_at DATETIME NOT NULL)",
"CREATE UNIQUE INDEX IF NOT EXISTS ux_novelty_alert_article ON novelty_alerts(article_id)",
```

### Scan Logic

```python
async def _run_threat_scan(db: Session, window_days: int = 14) -> ThreatScanResponse:
    contribution = db.query(ThesisContribution).first()
    if not contribution:
        raise HTTPException(400, detail="No thesis contribution statement configured.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    already_checked = {r.article_id for r in db.query(NoveltyAlert.article_id).all()}

    candidates = (
        db.query(Article)
        .filter(Article.score >= 7.0, Article.created_at >= cutoff)
        .filter(Article.id.notin_(already_checked))
        .all()
    )
    scanned = skipped = alerts = 0
    for article in candidates:
        scanned += 1
        try:
            result = await _llm_assess_threat(contribution.statement, article)
            overlap = result.get("overlap_score", 0.0)
            note = result.get("positioning_note", "")
            db.add(NoveltyAlert(
                article_id=article.id,
                overlap_score=min(1.0, max(0.0, float(overlap))),
                positioning_note=note[:1000],
                checked_at=datetime.now(timezone.utc),
            ))
            db.commit()
            alerts += 1
        except Exception as e:
            logger.warning("threat_scan_llm_failed", article_id=article.id, error=str(e))
            skipped += 1
    return ThreatScanResponse(scanned=scanned, alerts_created=alerts, skipped=skipped)
```

### `_row_to_list_item` Update

The articles list query needs to LEFT JOIN `novelty_alerts`. Add a subquery or update `_row_to_list_item` to accept an optional `threat_overlap` parameter. The cleanest approach is a correlated subquery in the main articles query:

```sql
SELECT a.*, 
  (SELECT na.overlap_score FROM novelty_alerts na WHERE na.article_id = a.id 
   ORDER BY na.checked_at DESC LIMIT 1) AS threat_overlap
FROM articles a
```

Alternatively: add a second DB call in `_row_to_list_item` for simplicity at first, then optimize if N+1 becomes a concern.

### Test Strategy

- `test_contribution_upsert`: PUT twice → only one row in DB, updated_at advances
- `test_scan_returns_400_without_contribution`: no contribution row → 400
- `test_scan_skips_already_assessed`: article already in novelty_alerts → not re-scanned
- `test_overlap_score_clamped`: LLM returns 1.5 → stored as 1.0
- `test_threat_filter_by_min_overlap`: GET /threats?min_overlap=0.8 → only rows ≥ 0.8
- `test_article_list_includes_threat_overlap`: article with alert → `threat_overlap` in ListItem
