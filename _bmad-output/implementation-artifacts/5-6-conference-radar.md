---
epic: 5
story: 6
story_key: "5-6-conference-radar"
---

# Story 5.6: Conference Radar

Status: draft

## Story

As a **PhD researcher**,
I want a persistent view of upcoming submission deadlines for my core academic venues,
So that I always know how much time I have before the next ICSE, RE, or MODELS deadline without leaving Baṣīra to check conference websites.

## Acceptance Criteria

1. **Given** a static conference list is defined in the backend
   **When** `GET /api/research/conferences` is called by an authenticated user
   **Then** a JSON array of conference entries is returned, each containing: `venue`, `track`, `abstract_deadline` (ISO date or null), `paper_deadline` (ISO date), `notification_date` (ISO date or null), `conference_date` (ISO date), `url`, `note` (optional short note), `days_to_abstract` (int or null), `days_to_paper` (int — can be negative for past deadlines)
   **And** results are sorted by `paper_deadline` ascending (soonest first)
   **And** past deadlines (paper_deadline < today) are included but flagged with `is_past: true`

2. **Given** the conference list is returned by the API
   **When** the `ConferenceRadar` component renders
   **Then** upcoming deadlines (paper_deadline ≥ today) are shown first in a distinct section
   **And** past deadlines from the current cycle are shown in a collapsed "Past" section
   **And** each card shows: venue name, track, days-to-deadline countdown (bold red if ≤ 14 days, orange if ≤ 30, green if > 30), abstract deadline (if present), paper deadline, and a link icon opening the conference URL

3. **Given** a deadline is within 14 days
   **When** the researcher opens the sidebar
   **Then** the Conference Radar navigation item shows a red dot indicator badge
   **And** the urgent deadline is surfaced as a highlighted card at the top

4. **Given** the researcher wants to note which conferences they plan to submit to
   **When** they click the bookmark icon on a conference card
   **Then** the conference's `venue` key is stored in the `settings` table as a comma-separated list under `key="bookmarked_conferences"`
   **And** bookmarked conferences are pinned to the top of the radar view regardless of deadline order
   **And** the bookmark state persists across sessions

---

## Tasks / Subtasks

- [ ] Backend: Create `backend/api/conferences.py` with the static conference data (AC: 1)
  - [ ] Define `CONFERENCES: list[dict]` — full list of target venues (see Dev Notes)
  - [ ] `def get_conferences_with_countdown() -> list[ConferenceOut]` — computes `days_to_abstract`, `days_to_paper`, `is_past` relative to today's date

- [ ] Backend: Add Pydantic model to `backend/api/models.py` (AC: 1)
  - [ ] `ConferenceOut` (venue, track, abstract_deadline, paper_deadline, notification_date, conference_date, url, note, days_to_abstract, days_to_paper, is_past, bookmarked)

- [ ] Backend: Add `GET /api/research/conferences` endpoint to `backend/api/routers/research.py` (AC: 1, 4)
  - [ ] Call `get_conferences_with_countdown()`
  - [ ] Read bookmarked venues from `settings` table (key="bookmarked_conferences", comma-separated)
  - [ ] Set `bookmarked=True` on matching entries before returning

- [ ] Backend: Add `POST /api/research/conferences/bookmark` endpoint (AC: 4)
  - [ ] Body: `{"venue": "ICSE 2027", "bookmarked": true}`
  - [ ] Reads current CSV from settings, adds or removes venue, writes back
  - [ ] Returns updated full conference list (same shape as GET)

- [ ] Frontend: Update `frontend/src/types.ts`
  - [ ] Add `Conference` interface matching `ConferenceOut`

- [ ] Frontend: Create `ConferenceRadar.tsx` in `frontend/src/components/` (AC: 2, 3, 4)
  - [ ] `useEffect` on mount: fetch `GET /api/research/conferences`
  - [ ] Separate upcoming vs. past sections
  - [ ] Countdown display with urgency color coding (red/orange/green)
  - [ ] Bookmark toggle → POST /api/research/conferences/bookmark
  - [ ] Collapsible "Past deadlines" section (default collapsed)
  - [ ] External link icon for conference URL

- [ ] Frontend: Add `ConferenceRadar` to `Sidebar.tsx` as a navigation item (AC: 3)
  - [ ] Show red dot on nav item when any conference has `days_to_paper <= 14 && !is_past`

- [ ] Frontend: Add `ConferenceRadar` as a routed view in `App.tsx`

---

## Dev Notes

### Static Conference Data

```python
# backend/api/conferences.py
from datetime import date, datetime, timezone

CONFERENCES = [
    {
        "venue": "ICSE 2027",
        "track": "Research",
        "abstract_deadline": "2026-08-30",
        "paper_deadline": "2026-09-06",
        "notification_date": "2026-12-10",
        "conference_date": "2027-04-12",
        "url": "https://conf.researchr.org/home/icse-2027",
        "note": "Primary SE venue",
    },
    {
        "venue": "RE 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2027-03-15",
        "notification_date": "2027-05-15",
        "conference_date": "2027-09-15",
        "url": "https://requirements-engineering.org",
        "note": "Core thesis venue",
    },
    {
        "venue": "MODELS 2026",
        "track": "Research",
        "abstract_deadline": "2026-05-10",
        "paper_deadline": "2026-05-17",
        "notification_date": "2026-07-14",
        "conference_date": "2026-10-01",
        "url": "https://conf.researchr.org/home/models-2026",
        "note": "MBSE core venue",
    },
    {
        "venue": "CAiSE 2027",
        "track": "Research",
        "abstract_deadline": "2026-11-15",
        "paper_deadline": "2026-11-22",
        "notification_date": "2027-02-01",
        "conference_date": "2027-06-07",
        "url": "https://caise2027.org",
        "note": "Information systems & SE",
    },
    {
        "venue": "REFSQ 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2026-10-15",
        "notification_date": "2026-12-15",
        "conference_date": "2027-04-07",
        "url": "https://refsq.org",
        "note": "Requirements engineering focus",
    },
    {
        "venue": "ECMFA 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2027-02-15",
        "notification_date": "2027-04-01",
        "conference_date": "2027-06-15",
        "url": "https://ecmfa.org",
        "note": "Model-driven engineering",
    },
    {
        "venue": "INCOSE IS 2027",
        "track": "Research",
        "abstract_deadline": "2026-11-01",
        "paper_deadline": "2026-11-15",
        "notification_date": "2027-01-15",
        "conference_date": "2027-06-28",
        "url": "https://www.incose.org/symp2027",
        "note": "Systems engineering core venue",
    },
    {
        "venue": "NeurIPS 2026",
        "track": "Research",
        "abstract_deadline": "2026-05-15",
        "paper_deadline": "2026-05-22",
        "notification_date": "2026-09-25",
        "conference_date": "2026-12-06",
        "url": "https://neurips.cc",
        "note": "AI methods — foundation models",
    },
    {
        "venue": "ICLR 2027",
        "track": "Research",
        "abstract_deadline": None,
        "paper_deadline": "2026-10-01",
        "notification_date": "2027-01-22",
        "conference_date": "2027-05-01",
        "url": "https://iclr.cc",
        "note": "LLM architecture research",
    },
    {
        "venue": "ACL 2027",
        "track": "Research",
        "abstract_deadline": "2026-12-08",
        "paper_deadline": "2026-12-15",
        "notification_date": "2027-03-15",
        "conference_date": "2027-07-27",
        "url": "https://2027.aclweb.org",
        "note": "NLP — NLP4RE papers",
    },
]
```

**Note:** Deadlines must be updated annually. Encode year in venue name (e.g., "ICSE 2027") to make staleness obvious. When a new year's deadlines are announced, add the new entry and keep the old one (it will be `is_past: true` and auto-collapse).

### Countdown Computation

```python
def get_conferences_with_countdown() -> list[dict]:
    today = date.today()
    result = []
    for conf in CONFERENCES:
        paper_dl = date.fromisoformat(conf["paper_deadline"])
        abstract_dl = date.fromisoformat(conf["abstract_deadline"]) if conf["abstract_deadline"] else None
        days_to_paper = (paper_dl - today).days
        days_to_abstract = (abstract_dl - today).days if abstract_dl else None
        result.append({
            **conf,
            "days_to_paper": days_to_paper,
            "days_to_abstract": days_to_abstract,
            "is_past": days_to_paper < 0,
        })
    return sorted(result, key=lambda c: c["paper_deadline"])
```

### Frontend Urgency Colors

```tsx
function urgencyClass(days: number): string {
  if (days <= 14) return 'text-red-500 font-bold'
  if (days <= 30) return 'text-orange-400 font-semibold'
  return 'text-green-500'
}

// Render:
<span className={urgencyClass(conf.days_to_paper)}>
  {conf.days_to_paper < 0
    ? `${Math.abs(conf.days_to_paper)}d ago`
    : `${conf.days_to_paper}d`}
</span>
```

### Bookmark Storage

The `settings` table (added in Story 5.4) stores bookmarks as a comma-separated string:

```python
# Read
raw = get_setting(db, "bookmarked_conferences", "")
bookmarked = set(v.strip() for v in raw.split(",") if v.strip())

# Write (add)
bookmarked.add(venue)
set_setting(db, "bookmarked_conferences", ",".join(sorted(bookmarked)))

# Write (remove)
bookmarked.discard(venue)
set_setting(db, "bookmarked_conferences", ",".join(sorted(bookmarked)))
```

This story depends on Story 5.4 (which adds the `settings` table and `get_setting`/`set_setting` helpers). If 5.6 is implemented before 5.4, inline the settings helpers directly into `conferences.py`.

### Red Dot in Sidebar

In `Sidebar.tsx`, after fetching conferences, compute:

```tsx
const hasUrgent = conferences.some(c => !c.is_past && c.days_to_paper <= 14)
// Render red dot on the ConferenceRadar nav item when hasUrgent is true
```

The conference fetch should be done at the `App` level (or a lightweight context) so the sidebar can show the dot without `ConferenceRadar` being mounted.

### No DB Required for Conference Data

The conference list is static Python data — no DB table, no migration. The only DB interaction is the `settings` table for bookmarks. This makes the feature zero-risk to implement and trivially rollback (just remove the endpoint and component).

### Maintenance Note (for README or .claude/todo.md)

Add a yearly reminder: **Update `backend/api/conferences.py` each September** when major venue deadlines are announced. This is the only maintenance this feature requires.

### Test Strategy

- `test_countdown_positive`: paper_deadline in future → days_to_paper > 0, is_past = False
- `test_countdown_negative`: paper_deadline in past → days_to_paper < 0, is_past = True
- `test_sort_order`: multiple venues → sorted by paper_deadline ascending
- `test_bookmark_add_remove`: bookmark ICSE → in settings; unbookmark → removed from settings
- `test_bookmark_persists_across_calls`: bookmark stored in DB → subsequent GET returns bookmarked=True
- `test_no_db_table_required`: endpoint works with empty settings table (no bookmarks)
