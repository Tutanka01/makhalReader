---
epic: 2
story: 3
story_key: "2-3-research-feed-seeding-and-article-filters"
---

# Story 2.3: Research Feed Seeding & Article Filters

Status: review

## Story

As a **researcher**,
I want paper-focused feeds pre-configured in the system and the ability to filter my article list by contribution type and RE document type,
So that research papers appear automatically in my reading list and I can triage them by their academic contribution category.

## Acceptance Criteria

1. **Given** the system initializes with default feeds
   **When** `init_db()` / startup runs on a fresh database
   **Then** the following arXiv feeds are present alongside existing defaults:
   - arXiv cs.SE (Software Engineering): `https://export.arxiv.org/rss/cs.SE`
   - arXiv cs.RO (Robotics / Systems): `https://export.arxiv.org/rss/cs.RO`
   - arXiv cs.AI already exists — no duplicate should be added
   **And** a "Requirements Engineering" curated feed is added:
   - arXiv cs.SE (already covers RE) combined with a note that Semantic Scholar API enrichment (Story 2.2) handles the SS side

2. **Given** an authenticated researcher views the article list
   **When** they apply a `contribution_type` filter (e.g., `survey`)
   **Then** only articles with `contribution_type = 'survey'` are returned
   **And** existing filters (score range, feed category, read status, sort) compose correctly with the new filters

3. **Given** an authenticated researcher views the article list
   **When** they apply a `re_document_type` filter
   **Then** when `re_document_type=arise`, only articles where `re_document_type IN (elicitation, extraction, method)` are returned
   **And** when `re_document_type=none`, articles with `re_document_type = 'none'` are returned

4. **Given** article cards are rendered in the list view
   **When** an article has a non-null `contribution_type`
   **Then** a `ContribTypeBadge` component is shown with a distinct color per category:
   - `method` → blue, `survey` → purple, `benchmark` → orange, `empirical` → green
   - `theory` → indigo, `position` → yellow, `tool` → teal, `incident` → red
   - `tutorial` → gray, `news` → slate, `other` → neutral

5. **Given** article cards are rendered
   **When** an article has `re_document_type ∈ {elicitation, extraction, method}`
   **Then** a `ReDocTypeBadge` is displayed in amber/gold to signal ARISE relevance
   **And** articles with `re_document_type = none` or null show no `ReDocTypeBadge`

6. **Given** `ContribTypeBadge` and `ReDocTypeBadge` components exist
   **When** `TypeScript` types are updated
   **Then** `types.ts` includes: `ContribType`, `REDocType`, `PaperMeta`, `ScoreMeta` interfaces matching the architecture specification
   **And** `Article` and `ArticleListItem` interfaces include `contribution_type: ContribType | null` and `re_document_type: REDocType | null`
   **And** `ArticleFilter` interface includes `contributionType: ContribType | null` and `ariseOnly: boolean`

7. **Given** the article list toolbar
   **When** it renders
   **Then** a contribution type chip-selector is visible (scrollable, compact) below the existing score/sort filters
   **And** an "ARISE" toggle button highlights articles relevant to Requirements Engineering extraction
   **And** the header still shows "Baṣīra" (not the legacy "MakhalReader" text that must be fixed)

---

## Tasks / Subtasks

- [x] Backend: Add missing arXiv research feeds to `DEFAULT_FEEDS` in `backend/api/main.py` (AC: 1)
  - [x] Add `cs.SE`: `{"url": "https://export.arxiv.org/rss/cs.SE", "name": "arXiv cs.SE (RE/SE)", "category": "Papers"}`
  - [x] Add `cs.RO`: `{"url": "https://export.arxiv.org/rss/cs.RO", "name": "arXiv cs.RO (Robotics/MBSE)", "category": "Papers"}`
  - [x] Fix: rename "MakhalReader" header text in `ArticleList.tsx` header to "Baṣīra" (noticed during story)

- [x] Backend: Add `contribution_type` and `re_document_type` filter params to `list_articles` in `backend/api/routers/articles.py` (AC: 2, 3)
  - [x] Add `contribution_type: Optional[str] = Query(None)` parameter
  - [x] Add `re_document_type: Optional[str] = Query(None)` parameter
  - [x] When `contribution_type` is set: `query = query.filter(Article.contribution_type == contribution_type)`
  - [x] When `re_document_type == "arise"`: filter `Article.re_document_type.in_(["elicitation", "extraction", "method"])`
  - [x] When `re_document_type` is any other value: `query = query.filter(Article.re_document_type == re_document_type)`

- [x] Frontend: Update `frontend/src/types.ts` (AC: 6)
  - [x] Add `ContribType` union type
  - [x] Add `REDocType` union type
  - [x] Add `PaperMeta` interface
  - [x] Add `ScoreMeta` interface
  - [x] Add `contribution_type: ContribType | null` and `re_document_type: REDocType | null` to `ArticleListItem`
  - [x] Add `contribution_type: ContribType | null`, `re_document_type: REDocType | null`, `paper_meta: PaperMeta`, `score_meta: ScoreMeta` to `Article`
  - [x] Add `contributionType: ContribType | null` and `ariseOnly: boolean` to `ArticleFilter`

- [x] Frontend: Create `frontend/src/components/ContribTypeBadge.tsx` (AC: 4)
  - [x] Map each ContribType to a Tailwind color class
  - [x] Render as a compact pill badge with uppercase abbreviated label (e.g., "METHOD", "SURVEY")

- [x] Frontend: Create `frontend/src/components/ReDocTypeBadge.tsx` (AC: 5)
  - [x] Render only for `re_document_type ∈ {elicitation, extraction, method}`
  - [x] Amber/gold color with label abbreviation (e.g., "ELIX", "EXTR", "RE-M")
  - [x] Returns null for `none` or null values

- [x] Frontend: Update `frontend/src/components/ArticleCard.tsx` (AC: 4, 5)
  - [x] Import and render `ContribTypeBadge` and `ReDocTypeBadge` inline with tags
  - [x] Update `ArticleListItem` destructuring to use new fields

- [x] Frontend: Update `frontend/src/store/articles.ts` (AC: 2, 3, 7)
  - [x] Add `contributionType: null` and `ariseOnly: false` to initial filter state
  - [x] Update `buildQueryParams` to emit `contribution_type` and `re_document_type=arise` query params
  - [x] Update `prependArticle` to respect new filter fields

- [x] Frontend: Update `frontend/src/components/ArticleList.tsx` (AC: 7)
  - [x] Fix "MakhalReader" → "Baṣīra" in header (line 149)
  - [x] Add contribution type chip-selector (compact horizontal scroll) to toolbar
  - [x] Add "ARISE" toggle button to toolbar

---

## Dev Notes

### Backend: Feed Seeding

The `DEFAULT_FEEDS` list in `backend/api/main.py` already has arXiv feeds: `cs.AI`, `cs.LG`, `cs.DC`, `cs.NI`, `cs.CR`, `cs.OS` in the "Papers" category. The story adds:
- `cs.SE` (Software Engineering — the primary venue for Requirements Engineering, MBSE, model-driven engineering, testing)
- `cs.RO` (Robotics — relevant to MBSE, Systems-of-Systems, mission-critical systems)

Add these two entries to the **"ArXiv — Research Papers"** section in `DEFAULT_FEEDS`:
```python
{"url": "https://export.arxiv.org/rss/cs.SE", "name": "arXiv cs.SE (RE/SE)",         "category": "Papers"},
{"url": "https://export.arxiv.org/rss/cs.RO", "name": "arXiv cs.RO (Robotics/MBSE)",  "category": "Papers"},
```

**Note on Semantic Scholar RSS**: SS does not expose a public RSS feed for arbitrary topic searches. The paper enrichment pipeline (Story 2.2) handles SS papers by detecting `semanticscholar.org/paper/` URLs and calling the SS Graph API. No separate SS RSS feed is needed; papers arrive via arXiv feeds and are enriched.

The startup seeding is idempotent: `existing_urls = {url for (url,) in db.query(Feed.url).all()}` already deduplicates by URL.

---

### Backend: API Filter Implementation

In `backend/api/routers/articles.py`, extend `list_articles`:

```python
@router.get("/api/articles", response_model=List[ArticleListItem])
async def list_articles(
    # ... existing params ...
    contribution_type: Optional[str] = Query(None),
    re_document_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    # ... existing query setup ...

    if contribution_type is not None:
        query = query.filter(Article.contribution_type == contribution_type)

    if re_document_type is not None:
        if re_document_type == "arise":
            query = query.filter(
                Article.re_document_type.in_(["elicitation", "extraction", "method"])
            )
        else:
            query = query.filter(Article.re_document_type == re_document_type)

    # ... existing sort/order/limit ...
```

**Composability**: The new filters add SQLAlchemy `.filter()` calls after all existing filters. They compose naturally — no special handling needed. The `search` code path already has early-return behavior that bypasses status/score filters; the new filters should be added before the ordering step, **after** the search clause check, so they apply whether or not `search` is active.

Actually — for `search`, the current code does:
```python
if search:
    like = f"%{search}%"
    query = query.filter(...)
else:
    if status == "unread": ...
    elif status == "read": ...
```
The new filters go **after** this entire if/else block, ensuring they apply in both search and non-search modes.

---

### Frontend Types

Add to `frontend/src/types.ts`:

```typescript
// Research classification types (Story 2.3)
export type ContribType =
  | 'method' | 'benchmark' | 'survey' | 'empirical'
  | 'theory' | 'position' | 'tool' | 'incident'
  | 'tutorial' | 'news' | 'other'

export type REDocType = 'elicitation' | 'extraction' | 'method' | 'none'

export interface PaperMeta {
  is_paper: boolean
  source?: string
  paper_id?: string
  doi?: string
  abstract?: string
  authors?: string[]
  year?: number
  methods: string[]
  datasets: string[]
  metrics: string[]
  fields_of_study?: string[]
  contribution_type?: ContribType
  re_document_type?: REDocType
  confidence?: number
}

export interface ScoreMeta {
  contribution_type?: ContribType
  re_document_type?: REDocType
  novelty?: number
  rigor?: number
  relevance_to_topics?: number
}
```

Update `ArticleListItem`:
```typescript
export interface ArticleListItem {
  // ... existing fields ...
  contribution_type: ContribType | null
  re_document_type: REDocType | null
}
```

Update `Article`:
```typescript
export interface Article {
  // ... existing fields ...
  contribution_type: ContribType | null
  re_document_type: REDocType | null
  paper_meta: PaperMeta         // parsed from paper_meta_json by backend
  score_meta: ScoreMeta         // parsed from score_meta_json by backend
}
```

Update `ArticleFilter`:
```typescript
export interface ArticleFilter {
  category: string | null
  sort: SortOption
  status: StatusOption
  bookmarked: boolean
  minScore: number
  contributionType: ContribType | null   // null = all types
  ariseOnly: boolean                     // true = only ARISE-relevant RE docs
}
```

---

### Frontend: `ContribTypeBadge.tsx`

Color mapping from the epics spec:
```
method    → blue     (#4493F8 / accent-blue)
survey    → purple   (violet-400 / #a78bfa)
benchmark → orange   (orange-400 / #fb923c)
empirical → green    (accent-green / #3FB950)
theory    → indigo   (indigo-400 / #818cf8)
position  → yellow   (accent-yellow / #D29922)
tool      → teal     (teal-400 / #2dd4bf)
incident  → red      (accent-red / #F85149)
tutorial  → gray     (text-muted)
news      → slate    (slate-400)
other     → neutral  (gray-500)
```

Implementation pattern:
```tsx
import type { ContribType } from '../types'

const CONTRIB_COLORS: Record<ContribType, string> = {
  method:    'bg-blue-500/20 text-blue-400 border-blue-500/30',
  survey:    'bg-violet-500/20 text-violet-400 border-violet-500/30',
  benchmark: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  empirical: 'bg-green-500/20 text-green-400 border-green-500/30',
  theory:    'bg-indigo-400/20 text-indigo-400 border-indigo-400/30',
  position:  'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  tool:      'bg-teal-400/20 text-teal-400 border-teal-400/30',
  incident:  'bg-red-500/20 text-red-400 border-red-500/30',
  tutorial:  'bg-gray-500/20 text-gray-400 border-gray-500/30',
  news:      'bg-slate-500/20 text-slate-400 border-slate-500/30',
  other:     'bg-gray-600/20 text-gray-500 border-gray-600/30',
}

const CONTRIB_LABELS: Record<ContribType, string> = {
  method: 'METHOD', survey: 'SURVEY', benchmark: 'BENCH',
  empirical: 'EMPIRICAL', theory: 'THEORY', position: 'POSITION',
  tool: 'TOOL', incident: 'INCIDENT', tutorial: 'TUTORIAL',
  news: 'NEWS', other: 'OTHER',
}

interface ContribTypeBadgeProps {
  type: ContribType | null | undefined
  className?: string
}

export function ContribTypeBadge({ type, className = '' }: ContribTypeBadgeProps) {
  if (!type) return null
  const colors = CONTRIB_COLORS[type] ?? CONTRIB_COLORS.other
  return (
    <span className={`
      inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold
      tracking-wide border ${colors} ${className}
    `}>
      {CONTRIB_LABELS[type] ?? type.toUpperCase()}
    </span>
  )
}
```

---

### Frontend: `ReDocTypeBadge.tsx`

Only renders for ARISE-relevant types (`elicitation`, `extraction`, `method`). Returns null for `none` or null.

```tsx
import type { REDocType } from '../types'

const RE_LABELS: Partial<Record<REDocType, string>> = {
  elicitation: 'ELIX',
  extraction:  'EXTR',
  method:      'RE-M',
}

interface ReDocTypeBadgeProps {
  type: REDocType | null | undefined
  className?: string
}

export function ReDocTypeBadge({ type, className = '' }: ReDocTypeBadgeProps) {
  if (!type || type === 'none') return null
  const label = RE_LABELS[type]
  if (!label) return null
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold
        tracking-wide border bg-amber-500/20 text-amber-400 border-amber-500/30 ${className}`}
      title={`RE Document Type: ${type}`}
    >
      {label}
    </span>
  )
}
```

---

### Frontend: `ArticleCard.tsx` Update

Insert badges between the tags row and the title. The badges are small enough to sit inline with the tags on the same row, or on a dedicated mini-row between tags and title.

Recommended placement: **add badges to the end of the tags row** if they fit, or as a separate tiny row. Given the compact design, add them as a second row of metadata before the title:

```tsx
import { ContribTypeBadge } from './ContribTypeBadge'
import { ReDocTypeBadge } from './ReDocTypeBadge'

// Inside the card content, after tags, before title:
{(article.contribution_type || (article.re_document_type && article.re_document_type !== 'none')) && (
  <div className="flex flex-wrap gap-1 mb-1.5">
    <ContribTypeBadge type={article.contribution_type} />
    <ReDocTypeBadge type={article.re_document_type} />
  </div>
)}
```

---

### Frontend: Store Changes (`articles.ts`)

**Initial filter state** — add two new fields:
```typescript
filter: {
  category: null,
  sort: 'score',
  status: 'unread',
  bookmarked: false,
  minScore: 0,
  contributionType: null,   // NEW
  ariseOnly: false,          // NEW
},
```

**`buildQueryParams`** — add:
```typescript
if (filter.contributionType) {
  params.set('contribution_type', filter.contributionType)
}
if (filter.ariseOnly) {
  params.set('re_document_type', 'arise')
}
```

**`prependArticle`** — add filter guards:
```typescript
if (filter.contributionType && article.contribution_type !== filter.contributionType) return {}
if (filter.ariseOnly && !['elicitation', 'extraction', 'method'].includes(article.re_document_type ?? '')) return {}
```

---

### Frontend: Toolbar Changes (`ArticleList.tsx`)

**Fix header**: Change line 149 from `MakhalReader` to `Baṣīra`.

**Filter UI** — add a second compact filter row below the existing one. Keep it minimal:

1. **Contribution type select** — a compact `<select>` (or scrollable chip row) for type filter.  
   Use a `<select>` for minimal vertical space:
   ```tsx
   <select
     value={filter.contributionType ?? ''}
     onChange={e => setFilter({ contributionType: (e.target.value || null) as ContribType | null })}
     className="text-xs px-2 py-1 rounded-md border border-border-default bg-bg-surface text-text-muted hover:text-text-primary focus:outline-none"
   >
     <option value="">All types</option>
     <option value="method">Method</option>
     <option value="survey">Survey</option>
     <option value="benchmark">Benchmark</option>
     <option value="empirical">Empirical</option>
     <option value="theory">Theory</option>
     <option value="position">Position</option>
     <option value="tool">Tool</option>
     <option value="news">News</option>
     <option value="other">Other</option>
   </select>
   ```

2. **ARISE toggle** — compact button:
   ```tsx
   <button
     onClick={() => setFilter({ ariseOnly: !filter.ariseOnly })}
     className={`flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-medium transition-colors ${
       filter.ariseOnly
         ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
         : 'border-border-default text-text-muted hover:text-text-primary hover:bg-bg-hover'
     }`}
     title="Show only ARISE-relevant RE documents (elicitation, extraction, method)"
   >
     ARISE
   </button>
   ```

The second filter row only renders when `currentView === 'feed'`, same as the main toolbar. It can be:
- Conditionally shown only when any research filter is set OR when Papers category is selected — to keep the UI clean for casual users
- OR always shown but visually lighter

**Recommendation**: Always show it but keep it visually subdued. A single thin row with the select + ARISE button + active filter count (if any) is enough.

**Empty state message** — update when research filters are active:
```
if (filter.contributionType || filter.ariseOnly) → "No articles match the selected research filter"
```

---

### Architecture Compliance

- NFR11: All new DB migrations already in place (no new columns for this story)
- ARCH1: New route params go in existing `articles.py` router — no router changes needed
- The filter URL params are additive and backward-compatible

---

### Important — No New Dependencies

- No new Python packages needed
- No new npm packages needed — all badge styling uses existing Tailwind classes (violet, orange, indigo, teal, amber are standard Tailwind colors, all included in Tailwind v3 which is already configured)

### Tailwind Colors Sanity Check

The project uses custom CSS variables for the core palette (`accent-blue`, `accent-green`, etc.). The badge colors use raw Tailwind colors (`violet-400`, `orange-400`, etc.) which are part of the default Tailwind v3 color palette and available without any additional configuration. Check `tailwind.config.js` to confirm there are no restrictions on which colors are available.

---

*Generated: 2026-04-22 — Ultimate context engine analysis completed — comprehensive developer guide created*

---

## Dev Agent Record

### Implementation Plan

Implemented in a single session following the task sequence. No deviations from the story spec.

### Completion Notes

**Date:** 2026-04-22

All acceptance criteria satisfied:

1. ✅ `cs.SE` and `cs.RO` added to `DEFAULT_FEEDS` in `backend/api/main.py`. The seeding is idempotent (URL-deduplication already in place). `cs.AI` verified to appear exactly once (no duplicate).

2. ✅ `contribution_type` and `re_document_type` query params added to `list_articles` in `backend/api/routers/articles.py`. Added `_ARISE_RE_TYPES` constant `("elicitation", "extraction", "method")`. The `re_document_type=arise` convenience alias uses `Article.re_document_type.in_()` to match all three ARISE-relevant types. Both filters apply after the existing `search`/`status`/`category`/`min_score` filters and compose naturally.

3. ✅ `types.ts` extended with `ContribType` (11-value union), `REDocType` (4-value union), `PaperMeta` interface, `ScoreMeta` interface. `Article`, `ArticleListItem`, and `ArticleFilter` all updated with new fields.

4. ✅ `ContribTypeBadge.tsx` created with 11-entry color map using standard Tailwind colors (violet, orange, indigo, teal, amber — all available in Tailwind v3 `extend` config).

5. ✅ `ReDocTypeBadge.tsx` created using `Set<REDocType>` for O(1) ARISE type lookup. Returns null for `none` or null, amber/gold for ELIX/EXTR/RE-M.

6. ✅ `ArticleCard.tsx` updated to import and render both badges in the tags row. Conditional renders only when there's at least one tag or badge to show.

7. ✅ `store/articles.ts` updated: initial filter state includes `contributionType: null` and `ariseOnly: false`; `buildQueryParams` emits the params; `prependArticle` guards against new articles that don't match active research filters. Added `ARISE_RE_TYPES` Set for efficient membership test.

8. ✅ `ArticleList.tsx` updated: "MakhalReader" header text changed to "Baṣīra"; new research filter row added below the main toolbar with a contribution type `<select>` and an ARISE toggle button. A "Clear" button appears when research filters are active. Empty state messages updated for research filter context.

9. ✅ Tests: `TestDefaultFeedsSources` (6 tests) run on host via source-text parsing, no import chain required. Integration tests (11 tests) skip gracefully on host with Docker skip marker; they run inside `docker-compose exec api pytest`.

**Test results:** 96 passed, 11 skipped, 0 failed (host). No regressions in prior stories.

### File List

| File | Change |
|------|--------|
| `backend/api/main.py` | Added cs.SE + cs.RO to DEFAULT_FEEDS |
| `backend/api/routers/articles.py` | Added contribution_type + re_document_type filter params; added _ARISE_RE_TYPES constant |
| `frontend/src/types.ts` | Added ContribType, REDocType, PaperMeta, ScoreMeta; updated Article, ArticleListItem, ArticleFilter |
| `frontend/src/components/ContribTypeBadge.tsx` | NEW — 11-type color-coded research badge |
| `frontend/src/components/ReDocTypeBadge.tsx` | NEW — ARISE-relevant amber RE document type badge |
| `frontend/src/components/ArticleCard.tsx` | Added ContribTypeBadge + ReDocTypeBadge to tags row |
| `frontend/src/store/articles.ts` | Added contributionType + ariseOnly filter state, buildQueryParams, prependArticle guards |
| `frontend/src/components/ArticleList.tsx` | Fixed "MakhalReader" → "Baṣīra"; added research filter row (select + ARISE toggle + clear) |
| `backend/scorer/tests/test_article_filters.py` | NEW — 6 host tests (source-text) + 11 Docker integration tests |

### Change Log

- 2026-04-22: Implemented Story 2.3 — Research Feed Seeding & Article Filters. Added cs.SE + cs.RO feeds, contribution_type and re_document_type API filters with ARISE convenience alias, ContribTypeBadge + ReDocTypeBadge frontend components, research filter toolbar, fixed MakhalReader header.
