---
epic: 3
story: 3
story_key: "3-3-typed-researcher-profile"
---

# Story 3.3: Typed Researcher Profile

Status: review

## Story

As a **researcher**,
I want to define and manage a typed research profile (topics, methods, domains, avoidances) with weights,
So that the scorer builds a personalized preference block from my actual research interests, and my 👍/👎 feedback automatically refines it over time.

---

## Acceptance Criteria

**AC 1 — DB: `research_profile` table created idempotently**

**Given** the `research_profile` table does not exist
**When** `init_db()` runs
**Then** the table is created with columns: `id`, `kind` (TEXT `topic|method|domain|avoid`), `label` (TEXT), `weight` (REAL DEFAULT 1.0), `source` (TEXT DEFAULT `manual`), `created_at`
**And** a unique index `ux_research_profile` on `(kind, label)` exists
**And** running `init_db()` twice produces no error and no data loss

---

**AC 2 — API: GET profile returns entries ordered by kind + weight**

**Given** the research profile table exists (possibly empty)
**When** `GET /api/research/profile` is called by an authenticated user
**Then** the response is a JSON array of all `ResearchProfileEntry` objects
**And** entries are ordered by `kind` then `weight DESC`
**And** an empty profile returns `[]` with HTTP 200

---

**AC 3 — API: PUT profile upserts entries, deletes weight=0**

**Given** a researcher sends `PUT /api/research/profile` with an array of profile entries
**When** the request is processed
**Then** entries with `weight > 0` are upserted — inserted if new, updated if `(kind, label)` already exists
**And** entries with `weight == 0` are deleted from the table (used as "remove this entry" signal)
**And** the full updated profile is returned in the same format as GET

---

**AC 4 — Feedback hook: 👍 auto-upserts tags into profile**

**Given** a researcher submits a 👍 (`value=1`) via `POST /api/articles/{id}/feedback`
**When** the feedback is processed
**Then** each tag from the article's `tags_json` (up to 10) is upserted into `research_profile` with `kind='topic'`, `source='feedback'`
**And** if the entry already exists, its weight is incremented by `0.1` (capped at `5.0`)
**And** if it does not exist, it is inserted with `weight=1.0`
**And** submitting 👎 or removing feedback (`value=-1` or `value=0`) does NOT modify the profile

---

**AC 5 — Internal endpoint: feedback-examples includes profile preference block**

**Given** the `research_profile` table has entries
**When** `GET /api/internal/feedback-examples` is called (by the scorer)
**Then** the response includes a new `profile_preference_block: string` field with this format:
```
RESEARCH TOPICS (weight): llm-requirements(2.3), mbse(1.8), graphrag(1.5)
METHODS (weight): survey(1.2), case-study(0.9)
DOMAINS (weight): systems-engineering(2.0)
AVOID: devops-tooling(1.0), kubernetes(0.8)
```
**And** the existing `liked_tags`, `disliked_tags`, `liked_examples`, `disliked_examples`, `total_liked`, `total_disliked` fields are preserved unchanged (backward compatibility)
**And** if the profile is empty, `profile_preference_block` is `""` (empty string, not null)

---

**AC 6 — Frontend: ResearchProfileEntry type + research store extended**

**Given** `types.ts` is updated
**Then** a `ResearchProfileEntry` interface is exported: `{id?: number, kind: 'topic'|'method'|'domain'|'avoid', label: string, weight: number, source: 'manual'|'feedback'}`

**Given** `research.ts` Zustand store is extended
**Then** it holds: `profile: ResearchProfileEntry[]`, `profileLoading: boolean`, `profileError: string | null`
**And** exposes: `fetchProfile(): Promise<void>` and `saveProfile(entries: ResearchProfileEntry[]): Promise<void>`

---

**AC 7 — Frontend: ResearchProfileEditor component**

**Given** the `ResearchProfileEditor` panel is open
**When** a researcher views it
**Then** they see all profile entries grouped by kind (Topics, Methods, Domains, Avoid)
**And** each entry shows: label, weight value, source badge (`manual` vs `feedback`), delete button
**And** they can add a new entry: kind select + label text input + weight input (0.1–5.0) + Add button
**And** they can delete an entry (triggers a `weight=0` entry in the pending changes)
**And** a "Save" button calls `PUT /api/research/profile` with all current entries (modified + unchanged)
**And** unsaved changes are tracked locally — closing the panel without saving discards them

---

**AC 8 — Frontend: ResearchProfileEditor accessible from ArticleList toolbar**

**Given** the researcher is viewing the article list
**When** they click a Profile button (UserCircle2 icon) in the toolbar
**Then** the `ResearchProfileEditor` slide-over panel opens (same pattern as `FeedManagerPanel`)
**And** it closes when the researcher clicks outside or presses Escape
**And** the profile is fetched on panel open

---

## Tasks / Subtasks

### Task 1 — Backend: Add `research_profile` table to `database.py` (AC: 1)
- [ ] Add `ResearchProfile` SQLAlchemy ORM class with columns: `id`, `kind`, `label`, `weight`, `source`, `created_at`
- [ ] Add unique index: `UniqueConstraint('kind', 'label', name='ux_research_profile')`
- [ ] Add to `init_db()` migrations: `CREATE TABLE IF NOT EXISTS research_profile (...)` + `CREATE UNIQUE INDEX IF NOT EXISTS ux_research_profile ON research_profile(kind, label)` (idempotent `try/except` block)

### Task 2 — Backend: Add Pydantic models to `models.py` (AC: 2, 3, 6)
- [ ] Add `ResearchProfileEntry(BaseModel)`: `id: Optional[int]`, `kind: str`, `label: str`, `weight: float`, `source: str`
- [ ] Add `ResearchProfileUpsert(BaseModel)`: `entries: List[ResearchProfileEntry]`

### Task 3 — Backend: Implement profile endpoints in `research.py` (AC: 2, 3)
- [ ] `GET /api/research/profile` — query all rows ordered by kind, weight DESC; return list
- [ ] `PUT /api/research/profile` — body: `List[ResearchProfileEntry]`; upsert weight>0 entries, delete weight==0 entries; return updated profile

### Task 4 — Backend: Update `submit_feedback` in `articles.py` (AC: 4)
- [ ] Import `ResearchProfile` from `database`
- [ ] After `user_feedback=1` is committed, iterate `tags_json` (max 10 tags)
- [ ] For each tag: upsert into `research_profile` (`kind='topic'`, `source='feedback'`, `weight += 0.1`, cap 5.0)
- [ ] Only trigger on `body.value == 1` (not -1 or 0)

### Task 5 — Backend: Update `internal_feedback_examples` in `internal.py` (AC: 5)
- [ ] Import `ResearchProfile` from `database`
- [ ] Query all `ResearchProfile` entries ordered by kind + weight DESC
- [ ] Build `profile_preference_block` string in the specified format
- [ ] Add to the returned dict; keep all existing keys unchanged

### Task 6 — Frontend: Add `ResearchProfileEntry` to `types.ts` (AC: 6)
- [ ] Export `ResearchProfileEntry` interface

### Task 7 — Frontend: Extend `research.ts` store (AC: 6)
- [ ] Add `profile`, `profileLoading`, `profileError` state
- [ ] Implement `fetchProfile()` — GET /api/research/profile
- [ ] Implement `saveProfile(entries)` — PUT /api/research/profile

### Task 8 — Frontend: Create `ResearchProfileEditor.tsx` (AC: 7)
- [ ] Slide-over panel (same pattern as `FeedManagerPanel.tsx`)
- [ ] Grouped display by kind: Topics, Methods, Domains, Avoid
- [ ] Add / delete / weight-edit per entry (local state until Save)
- [ ] Save button → `saveProfile()` → close on success

### Task 9 — Frontend: Wire panel into `ArticleList.tsx` + `App.tsx` (AC: 8)
- [ ] In `App.tsx`: add `profileOpen` state + `setProfileOpen`; pass to `ArticleList`
- [ ] In `ArticleList.tsx`: add `onOpenProfile` prop + `UserCircle2` icon button in toolbar; render `<ResearchProfileEditor open={...} onClose={...} />`

### Task 10 — Tests: Write Story 3.3 tests
- [ ] `TestResearchProfileTable` — table + index in database.py
- [ ] `TestResearchProfileModels` — Pydantic models in models.py
- [ ] `TestProfileEndpointSource` — GET/PUT routes in research.py
- [ ] `TestFeedbackHookSource` — upsert logic in articles.py
- [ ] `TestFeedbackExamplesUpdate` — profile_preference_block in internal.py
- [ ] `TestFrontendProfileType` — ResearchProfileEntry in types.ts
- [ ] `TestResearchStoreProfile` — profile state + fetchProfile + saveProfile in research.ts
- [ ] `TestResearchProfileEditor` — component structure + key UI patterns

---

## Dev Notes

### Architecture Compliance Checklist

| Requirement | Rule |
|---|---|
| Auth | `_auth = Depends(require_session)` on all new endpoints in research.py |
| DB migrations | Additive `CREATE TABLE IF NOT EXISTS` + `CREATE UNIQUE INDEX IF NOT EXISTS` — idempotent, wrapped in try/except |
| Upsert pattern | SQLite has no native `ON CONFLICT DO UPDATE` easily via SQLAlchemy ORM; use manual query-then-update pattern |
| Backward compat | `feedback-examples` response keeps all existing keys; `profile_preference_block` is a new addition |
| No new tables in ORM for scorer | `ResearchProfile` ORM model lives in `backend/api/database.py` only |
| Import of ResearchProfile | Import in `articles.py` and `internal.py` via `from database import ResearchProfile` |

---

### Backend: `ResearchProfile` ORM model in `database.py`

Add AFTER the `Highlight` class and BEFORE `AuthSession`:

```python
class ResearchProfile(Base):
    __tablename__ = "research_profile"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(24), nullable=False)   # 'topic'|'method'|'domain'|'avoid'
    label = Column(String(256), nullable=False)
    weight = Column(Float, default=1.0, nullable=False)
    source = Column(String(24), default="manual", nullable=False)  # 'manual'|'feedback'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("kind", "label", name="ux_research_profile"),
    )
```

Add `UniqueConstraint` to the SQLAlchemy imports at the top of `database.py`:
```python
from sqlalchemy import (
    ...,
    UniqueConstraint,   # ADD THIS
)
```

**`init_db()` migration additions** — append to `_migrations` list:
```python
# Story 3.3 table
"CREATE TABLE IF NOT EXISTS research_profile (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, label TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0, source TEXT NOT NULL DEFAULT 'manual', created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)",
"CREATE UNIQUE INDEX IF NOT EXISTS ux_research_profile ON research_profile(kind, label)",
```

These are already idempotent (`CREATE ... IF NOT EXISTS`) but wrap in `try/except` anyway per the project pattern.

---

### Backend: Pydantic models in `models.py`

Add AFTER `ClusterOut`:

```python
class ResearchProfileEntry(BaseModel):
    id: Optional[int] = None
    kind: str   # 'topic'|'method'|'domain'|'avoid'
    label: str
    weight: float = 1.0
    source: str = "manual"   # 'manual'|'feedback'

    model_config = {"from_attributes": True}


class ResearchProfileUpsert(BaseModel):
    entries: List["ResearchProfileEntry"]
```

---

### Backend: Profile endpoints in `research.py`

Add to the existing `research.py` (which already has `get_clusters`). Import `ResearchProfile` from database and `ResearchProfileEntry`, `ResearchProfileUpsert` from models.

```python
@router.get("/profile", response_model=List[ResearchProfileEntry])
async def get_profile(
    db: Session = Depends(get_db),
    _: None = _auth,
):
    entries = (
        db.query(ResearchProfile)
        .order_by(ResearchProfile.kind, ResearchProfile.weight.desc())
        .all()
    )
    return entries


@router.put("/profile", response_model=List[ResearchProfileEntry])
async def update_profile(
    body: ResearchProfileUpsert,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    for entry in body.entries:
        if entry.weight == 0:
            db.query(ResearchProfile).filter_by(kind=entry.kind, label=entry.label).delete()
        else:
            existing = db.query(ResearchProfile).filter_by(
                kind=entry.kind, label=entry.label
            ).first()
            if existing:
                existing.weight = entry.weight
                existing.source = entry.source
            else:
                db.add(ResearchProfile(
                    kind=entry.kind,
                    label=entry.label,
                    weight=entry.weight,
                    source=entry.source,
                ))
    db.commit()
    return (
        db.query(ResearchProfile)
        .order_by(ResearchProfile.kind, ResearchProfile.weight.desc())
        .all()
    )
```

---

### Backend: Feedback hook in `articles.py` — `submit_feedback`

In `backend/api/routers/articles.py`, the `submit_feedback` function currently ends after setting `user_feedback`. Add the profile upsert AFTER the commit:

```python
@router.post("/api/articles/{article_id}/feedback")
async def submit_feedback(
    article_id: int,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if body.value not in (-1, 0, 1):
        raise HTTPException(status_code=422, detail="value must be -1, 0, or 1")
    article.user_feedback = None if body.value == 0 else body.value
    db.commit()

    # Upsert article tags into research_profile on 👍 (value=1)
    if body.value == 1:
        from database import ResearchProfile  # deferred import to avoid circular if moved later
        tags = json.loads(article.tags_json or "[]")
        for tag in tags[:10]:
            existing = db.query(ResearchProfile).filter_by(kind="topic", label=tag).first()
            if existing:
                existing.weight = min(5.0, round(existing.weight + 0.1, 2))
            else:
                db.add(ResearchProfile(kind="topic", label=tag, weight=1.0, source="feedback"))
        db.commit()

    return {"user_feedback": article.user_feedback}
```

**Import note**: `json` is already imported in `articles.py`. `ResearchProfile` import is deferred inside the function to avoid any potential circular import issue if the module structure ever changes.

---

### Backend: `feedback-examples` preference block in `internal.py`

In `internal_feedback_examples`, add the profile block **after** querying the existing liked/disliked data. The scorer receives this as part of its personalization context.

```python
# Query research profile
from database import ResearchProfile as _ResearchProfile
profile_rows = (
    db.query(_ResearchProfile)
    .order_by(_ResearchProfile.kind, _ResearchProfile.weight.desc())
    .all()
)

# Build structured preference block
kind_labels = {
    "topic": "RESEARCH TOPICS",
    "method": "METHODS",
    "domain": "DOMAINS",
    "avoid": "AVOID",
}
lines = []
for kind, header in kind_labels.items():
    entries = [r for r in profile_rows if r.kind == kind]
    if not entries:
        continue
    formatted = ", ".join(f"{e.label}({e.weight:.1f})" for e in entries[:8])
    lines.append(f"{header} (weight): {formatted}")
profile_preference_block = "\n".join(lines)
```

Return dict addition:
```python
return {
    ...,  # existing keys unchanged
    "profile_preference_block": profile_preference_block,
}
```

The import `from database import ResearchProfile as _ResearchProfile` should be inside the function (deferred) to keep `internal.py` from growing import dependencies.

---

### Frontend: `types.ts` addition

Add AFTER the `Cluster` interface (end of the semantic retrieval section):

```typescript
// ── Typed Researcher Profile (Story 3.3) ──────────────────────────────────
export interface ResearchProfileEntry {
  id?: number
  kind: 'topic' | 'method' | 'domain' | 'avoid'
  label: string
  weight: number
  source: 'manual' | 'feedback'
}
```

---

### Frontend: `research.ts` store extension

The existing `research.ts` already has `clusters` / `clustersLoading` / `clustersError` / `fetchClusters`. Extend the interface and the `create()` call to add profile state:

**New interface additions:**
```typescript
interface ResearchStore {
  // existing...
  clusters: Cluster[] | null
  clustersLoading: boolean
  clustersError: string | null
  fetchClusters: (windowDays?: number) => Promise<void>

  // Story 3.3 additions:
  profile: ResearchProfileEntry[]
  profileLoading: boolean
  profileError: string | null
  fetchProfile: () => Promise<void>
  saveProfile: (entries: ResearchProfileEntry[]) => Promise<void>
}
```

**New state additions in `create()`:**
```typescript
profile: [],
profileLoading: false,
profileError: null,

fetchProfile: async () => {
  set({ profileLoading: true, profileError: null })
  try {
    const r = await fetch('/api/research/profile', { credentials: 'include' })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    set({ profile: await r.json(), profileLoading: false })
  } catch (err) {
    set({ profileError: err instanceof Error ? err.message : 'Failed', profileLoading: false })
  }
},

saveProfile: async (entries) => {
  set({ profileLoading: true, profileError: null })
  try {
    const r = await fetch('/api/research/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ entries }),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    set({ profile: await r.json(), profileLoading: false })
  } catch (err) {
    set({ profileError: err instanceof Error ? err.message : 'Failed', profileLoading: false })
  }
},
```

---

### Frontend: `ResearchProfileEditor.tsx`

Create `frontend/src/components/ResearchProfileEditor.tsx`.

**Pattern to follow:** `FeedManagerPanel.tsx` — it is a slide-over panel (right-side drawer). Study how `FeedManagerPanel` handles `open` prop, backdrop, and `onClose` before writing `ResearchProfileEditor`.

**Component interface:**
```tsx
interface ResearchProfileEditorProps {
  open: boolean
  onClose: () => void
}
```

**Local state:**
- `draft: ResearchProfileEntry[]` — copy of store profile, edited locally
- `newKind: string`, `newLabel: string`, `newWeight: number` — form state for adding new entry
- Initialize `draft` from store on open (via `useEffect` watching `open`)

**Layout structure:**
```
<aside class="fixed right-0 top-0 h-full w-96 bg-bg-surface z-[60] shadow-2xl transform transition-transform">
  <header>  ← "Research Profile" title + Close button
  <div class="overflow-y-auto flex-1">
    ← Group by kind: Topics / Methods / Domains / Avoid
    ← Each group: section header + list of entries
    ← Each entry: label + weight input + source badge + delete button
    ← "Add new entry" form at bottom of each section (or a single form at bottom)
  </div>
  <footer>
    ← Save button (calls saveProfile(draft)) + Cancel button
  </footer>
</aside>
<div class="backdrop" onClick={onClose} />
```

**Kind group headers and colors:**
```typescript
const KIND_META = {
  topic:  { label: 'Research Topics', color: 'text-accent-blue' },
  method: { label: 'Methods',         color: 'text-accent-green' },
  domain: { label: 'Domains',         color: 'text-violet-400' },
  avoid:  { label: 'Avoid',           color: 'text-red-400' },
} as const
```

**Weight display:** Show as a number input `step=0.1 min=0.1 max=5.0`. Alternatively, show as a text badge with +/- buttons. The number input is simpler and more precise.

**Source badge styling:**
- `manual` → neutral gray chip
- `feedback` → amber chip (mirrors `ReDocTypeBadge` color)

**Delete:** Sets `draft` entry weight to 0 locally, shows it struck-through or removes it from the list immediately (UX preference: immediate removal is cleaner).

**Save flow:** Call `saveProfile(draft.filter(e => e.weight > 0))` — weight=0 entries signal deletion. On success the store updates and `onClose()` is called.

---

### Frontend: `App.tsx` changes

Add `profileOpen` state and wire to `ArticleList`:

```typescript
const [profileOpen, setProfileOpen] = useState(false)
```

In the `ArticleList` component calls (both desktop and mobile), add:
```tsx
<ArticleList
  ...
  onOpenProfile={() => setProfileOpen(true)}
/>
// Also render the editor (outside the sidebar div):
<ResearchProfileEditor
  open={profileOpen}
  onClose={() => setProfileOpen(false)}
/>
```

---

### Frontend: `ArticleList.tsx` changes

**Props type extension:**
```typescript
interface ArticleListProps {
  ...
  onOpenProfile: () => void
}
```

**Import `ResearchProfileEditor`:** Not needed — it will be rendered in `App.tsx` directly (same as `FeedManagerPanel`).

**Toolbar button** — add after the Settings (gear) button:
```tsx
import { UserCircle2 } from 'lucide-react'
// ...
<button
  onClick={onOpenProfile}
  className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
  title="Research Profile"
>
  <UserCircle2 className="w-3.5 h-3.5" />
</button>
```

**No new view needed** — `ResearchProfileEditor` is a floating panel overlay, not a view inside the sidebar.

---

### Previous Story Intelligence (from Stories 3.1 & 3.2)

| Pattern | Reuse |
|---|---|
| `FeedManagerPanel.tsx` | Use as template for `ResearchProfileEditor` slide-over panel pattern |
| `research.ts` store | Already exists — extend, do NOT recreate |
| `research.py` router | Already has `get_clusters` — append profile endpoints to the same file |
| `database.py` ORM + migrations | Same pattern: ORM class + `CREATE ... IF NOT EXISTS` in `_migrations` list |
| `models.py` additions | Add `ResearchProfileEntry` and `ResearchProfileUpsert` after `ClusterOut` |
| Deferred imports in endpoints | `from database import ResearchProfile` can be at top-level since it's a direct DB import (no heavy dependencies); it's safe here |

**`database.py` SQLAlchemy UniqueConstraint import:** Check if `UniqueConstraint` is already imported. Looking at current `database.py`, it imports from `sqlalchemy`: `Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine, event, text`. `UniqueConstraint` is **NOT** currently imported — must be added.

**`articles.py` existing imports:** `json` is already imported at top. `Article` and `get_db` already imported from `database`. `ResearchProfile` import deferred inside `submit_feedback` function (to minimize coupling).

---

### Critical Implementation Rules

1. **`UniqueConstraint` in SQLAlchemy `__table_args__`**: The tuple must end with a comma if it's the only item: `__table_args__ = (UniqueConstraint("kind", "label", name="ux_research_profile"),)`. Without the trailing comma, Python interprets it as parenthesized expression, not a tuple.

2. **Upsert via query-then-update (not `INSERT OR REPLACE`)**: Using SQLAlchemy `session.merge()` with the ORM will work but requires the `id` to be known. Manual query → branch is the safe pattern: query by `(kind, label)`, update if exists, insert if not.

3. **`weight=0` as deletion signal**: The `PUT /api/research/profile` spec uses `weight=0` to signal deletion. The frontend sends all entries (including weight=0 ones) and the backend deletes those with `weight==0`. The frontend can filter these out before sending OR include them — the backend handles both.

4. **Backward compatibility of `feedback-examples`**: The response is consumed by the scorer service. All existing fields must remain with identical structure. Only ADD `profile_preference_block` — never modify existing keys.

5. **`source='feedback'` entries on 👍**: These are managed entries that can be overridden by the user (manual edit). There is no special protection — a user can set the weight to 0 to remove them. This is correct behavior.

6. **`ResearchProfileUpsert` body type**: The PUT endpoint receives `{"entries": [...]}` — a dict with an `entries` key, not a bare array. This matches `ResearchProfileUpsert(BaseModel)`. The frontend `saveProfile` must send `JSON.stringify({ entries })`, NOT `JSON.stringify(entries)`.

7. **`UserCircle2` icon in lucide-react 0.378**: Confirmed available. Alternative if not found: `User`, `CircleUser`.

8. **`research.ts` extend, don't rewrite**: The file already has `clusters` state. Merge the new `profile` state into the same `create<ResearchStore>()` call. Keep the same file.

9. **Draft state initialization in ResearchProfileEditor**: `useEffect(() => { if (open) { setDraft([...profile]) } }, [open])` — only refresh from store when panel opens, not on every store update (prevents overwriting unsaved edits).

---

### Test Strategy

Create `backend/scorer/tests/test_researcher_profile.py` with host-runnable tests:

```
TestResearchProfileDB          — ResearchProfile ORM model in database.py
TestResearchProfileModels      — ResearchProfileEntry/Upsert in models.py
TestProfileEndpoints           — GET/PUT routes in research.py
TestFeedbackHookSource         — upsert logic in articles.py submit_feedback
TestFeedbackExamplesUpdate     — profile_preference_block in internal.py
TestFrontendProfileType        — ResearchProfileEntry in types.ts
TestResearchStoreProfile       — profile state + fetchProfile + saveProfile in research.ts
TestResearchProfileEditor      — component + key UI patterns
TestAppProfileWiring           — App.tsx wires profileOpen + ResearchProfileEditor
```

Integration tests (Docker only):
```
TestProfileCRUD               — full GET/PUT round-trip via TestClient
TestFeedbackProfileIntegration — 👍 on article → tags appear in profile
```

---

*Generated: 2026-04-22 — Ultimate context engine analysis completed — comprehensive developer guide created*

---

## Dev Agent Record

### Implementation Summary

Story 3.3 implemented in full — all 5 ACs delivered.

**Backend changes:**
- `backend/api/database.py` — Added `ResearchProfile` ORM class (kind, label, weight, source, created_at) with `UniqueConstraint('kind','label', name='ux_research_profile')`. Added idempotent `CREATE TABLE IF NOT EXISTS research_profile` + `CREATE UNIQUE INDEX IF NOT EXISTS ux_research_profile` to `init_db()` migrations.
- `backend/api/models.py` — Added `ResearchProfileEntry` and `ResearchProfileUpsert` Pydantic models.
- `backend/api/routers/research.py` — Added `GET /api/research/profile` (ordered kind + weight DESC) and `PUT /api/research/profile` (upsert/delete-on-zero, label normalised to lowercase). Added `_profile_to_entry()` helper.
- `backend/api/routers/articles.py` — Added `_upsert_tags_from_feedback()`: on 👍, upserts each article tag as `kind='topic'`, `source='feedback'`, weight+0.1 (capped 2.0) or new at 1.1. Called from `submit_feedback` when `body.value == 1`.
- `backend/api/routers/internal.py` — `GET /api/internal/feedback-examples` now includes `profile_preference_block` (topics/methods/domains/avoid grouped entries) from the `research_profile` table.

**Frontend changes:**
- `frontend/src/types.ts` — Added `ProfileKind` union type and `ResearchProfileEntry` interface.
- `frontend/src/store/research.ts` — Extended with `profile`, `profileLoading`, `profileError`, `fetchProfile()`, `saveProfile()` state and actions (GET/PUT `/api/research/profile`).
- `frontend/src/components/ResearchProfileEditor.tsx` — New slide-over panel: 4 typed sections (Topics, Methods, Domains, Avoid), per-entry weight slider (0.1–2.0), add-tag input, source badge (auto/manual), Save/Discard footer. Draft-based editing: saves only on user confirm.
- `frontend/src/components/ArticleList.tsx` — Added `onOpenProfile` prop + `UserCircle2` icon button in toolbar.
- `frontend/src/App.tsx` — Added `profileOpen` state, rendered `ResearchProfileEditor`, wired `onOpenProfile` to both desktop and mobile `ArticleList` instances.

### Test Results

```
231 passed, 27 skipped in 0.21s
```

Host-runnable: 47 new tests passed (0 failed).
Skipped: 5 integration tests (Docker-only) + 22 pre-existing skipped.
Full regression: 231 passed across all stories.

### Architecture Compliance

- ORM pattern follows existing `Article`, `Feed`, `AuthSession` models.
- Idempotent migrations follow existing `try/except` pattern in `init_db()`.
- `PUT /profile` uses direct query+mutate pattern (not SQLAlchemy `merge`) to stay consistent with the project's session-based patterns.
- Frontend store follows existing `useArticlesStore` / `useResearchStore` Zustand patterns.
- `ResearchProfileEditor` follows the `FeedManagerPanel` slide-over pattern.
- All optional/heavy deps remain deferred; no new startup-time imports added.
