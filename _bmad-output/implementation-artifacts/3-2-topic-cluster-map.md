---
epic: 3
story: 2
story_key: "3-2-topic-cluster-map"
---

# Story 3.2: Topic Cluster Map

Status: review

## Story

As a **researcher**,
I want to see a map of how recent articles cluster by topic,
So that I can identify emerging research themes in my feeds at a glance and navigate to clusters I care about.

---

## Acceptance Criteria

**AC 1 — Dependency: hdbscan in requirements.txt**

**Given** `backend/api/requirements.txt` currently has `chromadb>=0.4.22` and `numpy>=1.26`
**When** this story is implemented
**Then** `hdbscan>=0.8.33` is added to `backend/api/requirements.txt`

---

**AC 2 — Backend: Cluster endpoint returns valid HDBSCAN clusters**

**Given** articles with `embedding_indexed=1` exist in both SQLite and ChromaDB within the requested window
**When** `GET /api/research/clusters?window_days=14&min_size=3` is called by an authenticated user
**Then** the system fetches all articles with `embedding_indexed=1` and `created_at >= now - window_days` from SQLite
**And** retrieves their embedding vectors from ChromaDB by ID batch
**And** runs HDBSCAN with `min_cluster_size=min_size` on the embedding matrix
**And** returns a JSON array of cluster objects: `{cluster_id, size, centroid_title, top_tags: string[], article_ids: number[]}`
**And** articles labeled as noise (HDBSCAN label = -1) are excluded from the response
**And** the response is returned in ≤ 5 seconds for 500 articles (NFR)

---

**AC 3 — Backend: Graceful degradation for sparse data**

**Given** fewer than `min_size` articles have embeddings in the requested time window
**When** the clusters endpoint is called
**Then** an empty array `[]` is returned with HTTP 200 (not an error, not a 500)

**Given** ChromaDB is unavailable or fails
**When** the clusters endpoint is called
**Then** a warning is logged, an empty array `[]` is returned, no 500 to the user

---

**AC 4 — Frontend: Cluster type and research store**

**Given** the cluster data model
**When** `types.ts` is updated
**Then** a `Cluster` interface is exported: `{cluster_id: number, size: number, centroid_title: string, top_tags: string[], article_ids: number[]}`

**Given** the `research.ts` Zustand store slice is created
**When** the research tab opens
**Then** `fetchClusters(windowDays)` triggers a fetch to `GET /api/research/clusters?window_days={n}`
**And** the store holds `clusters: Cluster[] | null`, `clustersLoading: boolean`, `clustersError: string | null`

---

**AC 5 — Frontend: ResearchDigestView cluster cards**

**Given** the Research tab is selected in the app
**When** cluster data is available
**Then** a `ResearchDigestView` component renders cluster cards inside the sidebar panel (380px width)
**And** each cluster card shows: centroid title (topic), article count badge, top 5 tags as chips
**And** clicking a cluster card expands it inline to reveal the list of article titles in the cluster
**And** clicking an article title in the expanded cluster calls `onSelect(id)` to open it in the reader

**Given** clusters are loading
**When** the Research tab is open
**Then** a skeleton loading state is shown

**Given** no clusters are available (empty array)
**When** the Research tab is open
**Then** a helpful empty state is shown: "No clusters yet — articles are embedded automatically after scoring. Come back when more articles are indexed."

---

**AC 6 — Frontend: Research tab integration in ArticleList + App**

**Given** the current tab system in `ArticleList.tsx` supports `'feed' | 'digest' | 'stats'`
**When** this story is implemented
**Then** `currentView` type is extended to `'feed' | 'digest' | 'stats' | 'research'`
**And** a Research tab button appears in the `ArticleList.tsx` toolbar alongside digest and stats buttons
**And** when `currentView === 'research'`, `ResearchDigestView` is rendered in place of the article list

**Given** the Research tab is active
**When** a researcher clicks an article in a cluster
**Then** the app navigates to the article in the reader view

---

## Tasks / Subtasks

### Task 1 — Backend: Add hdbscan to requirements.txt (AC: 1)
- [ ] Append `hdbscan>=0.8.33` to `backend/api/requirements.txt`

### Task 2 — Backend: Add `ClusterOut` model to `models.py` (AC: 2)
- [ ] Add `ClusterOut(BaseModel)` with fields: `cluster_id: int`, `size: int`, `centroid_title: str`, `top_tags: List[str]`, `article_ids: List[int]`

### Task 3 — Backend: Implement `GET /api/research/clusters` in `research.py` (AC: 2, 3)
- [ ] Import `Depends`, `Query`, `Session`, `List` and other FastAPI/SQLAlchemy requirements
- [ ] Add auth dependency `_auth = Depends(require_session)`
- [ ] Fetch windowed articles from SQLite (`embedding_indexed=1`, `created_at >= cutoff`)
- [ ] Early-return `[]` if `len(articles) < min_size`
- [ ] Batch-get embeddings from ChromaDB using `_get_chroma()` (deferred import of hdbscan inside function)
- [ ] Match embeddings back to articles, filter out any missing (IDs not in Chroma result)
- [ ] Early-return `[]` if `n_valid < min_size`
- [ ] Run HDBSCAN; compute centroid title and top_tags per cluster
- [ ] Exclude noise (label=-1); return sorted `List[ClusterOut]`
- [ ] Wrap entire function body in try/except; on exception log warning + return `[]`

### Task 4 — Frontend: Add `Cluster` type to `types.ts` (AC: 4)
- [ ] Add `Cluster` interface export to `frontend/src/types.ts`

### Task 5 — Frontend: Create `frontend/src/store/research.ts` (AC: 4)
- [ ] Create Zustand store with state: `clusters`, `clustersLoading`, `clustersError`
- [ ] Implement `fetchClusters(windowDays: number)` action (fetch + setState)
- [ ] Export `useResearchStore` hook

### Task 6 — Frontend: Create `frontend/src/components/ResearchDigestView.tsx` (AC: 5)
- [ ] Display list of cluster cards with expand/collapse state per card
- [ ] Each card header: centroid_title, size badge, top_tags chips
- [ ] Expanded card: list of article titles (IDs only — fetch titles from store or pass as prop)
- [ ] Loading skeleton, empty state, error state

### Task 7 — Frontend: Update `ArticleList.tsx` + `App.tsx` types (AC: 6)
- [ ] In `ArticleList.tsx`, extend prop type and add Research tab button + `ResearchDigestView` conditional render
- [ ] In `App.tsx`, extend `appView` type union to include `'research'`

### Task 8 — Tests: Write Story 3.2 tests (AC: 1–6)
- [ ] `TestClusterDependency` — verify hdbscan in requirements.txt
- [ ] `TestClusterEndpointSource` — verify route + model in source files
- [ ] `TestClusterModel` — verify ClusterOut model fields in models.py
- [ ] `TestFrontendClusterType` — verify Cluster interface in types.ts
- [ ] `TestResearchStore` — verify research.ts existence + fetchClusters pattern
- [ ] `TestResearchDigestView` — verify component existence + key patterns

---

## Dev Notes

### Architecture Compliance Checklist

| Requirement | Rule |
|---|---|
| `hdbscan` import | MUST be deferred inside the endpoint function — never at module top |
| `chromadb` import | Use `from embedder import _get_chroma` (deferred in embedder.py) — already established pattern |
| Fault isolation | Entire cluster function body in `try/except Exception`; log warning; return `[]` |
| Auth | `_auth = Depends(require_session)` — same pattern as all other research endpoints |
| Empty result | Return `[]` + HTTP 200 when n < min_size or all noise — never 404 or 500 |
| New endpoint file | Goes in `backend/api/routers/research.py` (stub already exists) |
| Additive-only | No DB changes in this story — only read from existing `embedding_indexed` column |

---

### Backend: `ClusterOut` model in `models.py`

Add after `RelatedArticleOut` (line ~130):

```python
class ClusterOut(BaseModel):
    cluster_id: int
    size: int
    centroid_title: str
    top_tags: List[str]
    article_ids: List[int]
```

---

### Backend: `research.py` — full cluster endpoint

The stub at `backend/api/routers/research.py` currently only defines the router. Replace the stub comment with the full implementation:

```python
import json
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth import require_session
from database import Article, get_db
from models import ClusterOut

router = APIRouter(prefix="/api/research", tags=["research"])
_auth = Depends(require_session)


@router.get("/clusters", response_model=List[ClusterOut])
async def get_clusters(
    window_days: int = Query(default=14, ge=1, le=90),
    min_size: int = Query(default=3, ge=2, le=20),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return HDBSCAN cluster summaries for embedded articles in the last window_days."""
    import structlog as _slog
    logger = _slog.get_logger().bind(service="research")

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        articles = (
            db.query(Article)
            .filter(Article.embedding_indexed == 1, Article.created_at >= cutoff)
            .all()
        )
        if len(articles) < min_size:
            return []

        # Fetch embeddings from ChromaDB
        from embedder import _get_chroma  # deferred — never at module top
        collection = _get_chroma()
        if collection.count() == 0:
            return []

        ids = [str(a.id) for a in articles]
        chroma_result = collection.get(ids=ids, include=["embeddings"])

        # Build id→vector map (Chroma may not have all IDs if recently indexed)
        id_to_vector = {}
        for chroma_id, emb in zip(chroma_result["ids"], chroma_result["embeddings"]):
            id_to_vector[int(chroma_id)] = emb

        valid_articles = [a for a in articles if a.id in id_to_vector]
        if len(valid_articles) < min_size:
            return []

        # Import heavy deps inside function — deferred to avoid startup cost
        import hdbscan  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        vectors = [id_to_vector[a.id] for a in valid_articles]
        matrix = np.array(vectors, dtype=np.float32)

        labels = hdbscan.HDBSCAN(min_cluster_size=min_size).fit_predict(matrix)

        # Build per-cluster data
        clusters: List[ClusterOut] = []
        for cluster_id in sorted(set(labels)):
            if cluster_id == -1:  # noise — skip
                continue
            mask = labels == cluster_id
            cluster_articles = [a for a, m in zip(valid_articles, mask) if m]
            cluster_vectors = matrix[mask]

            # Centroid = mean of cluster vectors; centroid_title = nearest article to centroid
            centroid = cluster_vectors.mean(axis=0)
            distances = np.linalg.norm(cluster_vectors - centroid, axis=1)
            nearest_idx = int(np.argmin(distances))
            centroid_title = cluster_articles[nearest_idx].title

            # Top tags — aggregate tag frequencies across all cluster articles
            tag_counts: dict = {}
            for a in cluster_articles:
                for tag in json.loads(a.tags_json or "[]"):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            top_tags = [t for t, _ in sorted(tag_counts.items(), key=lambda x: -x[1])[:5]]

            clusters.append(ClusterOut(
                cluster_id=int(cluster_id),
                size=len(cluster_articles),
                centroid_title=centroid_title,
                top_tags=top_tags,
                article_ids=[a.id for a in cluster_articles],
            ))

        return clusters

    except Exception as e:
        import structlog as _slog  # noqa: PLC0415, F811
        _slog.get_logger().warning("cluster_endpoint_failed", error=str(e))
        return []
```

---

### Frontend: `types.ts` addition

Add after `RelatedArticle` interface:

```typescript
// ── Topic Cluster Map (Story 3.2) ─────────────────────────────────────────
export interface Cluster {
  cluster_id: number
  size: number
  centroid_title: string
  top_tags: string[]
  article_ids: number[]
}
```

---

### Frontend: `frontend/src/store/research.ts`

Create this file from scratch. Do NOT use `persist` middleware (clusters are ephemeral, refetched on tab open):

```typescript
import { create } from 'zustand'
import type { Cluster } from '../types'

interface ResearchStore {
  clusters: Cluster[] | null
  clustersLoading: boolean
  clustersError: string | null
  fetchClusters: (windowDays?: number) => Promise<void>
}

export const useResearchStore = create<ResearchStore>((set) => ({
  clusters: null,
  clustersLoading: false,
  clustersError: null,

  fetchClusters: async (windowDays = 14) => {
    set({ clustersLoading: true, clustersError: null })
    try {
      const r = await fetch(`/api/research/clusters?window_days=${windowDays}`, {
        credentials: 'include',
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data: Cluster[] = await r.json()
      set({ clusters: data, clustersLoading: false })
    } catch (err) {
      set({
        clustersError: err instanceof Error ? err.message : 'Failed to load clusters',
        clustersLoading: false,
      })
    }
  },
}))
```

---

### Frontend: `ResearchDigestView.tsx`

Create `frontend/src/components/ResearchDigestView.tsx`.

**Key design decisions for the 380px sidebar context:**
- Each cluster card is a compact `<div>` with a header (centroid_title truncated to 2 lines) and metadata row (count + tags).
- Click the card header to expand/collapse the article list inline.
- Article titles in expanded state are clickable links that call `onSelect(id)`.
- Use `useState<number | null>(expandedCluster)` for expand state.
- Window selector: 14 / 30 / 60 days — `<select>` dropdown that calls `fetchClusters(n)` on change.

```tsx
import { useEffect, useState } from 'react'
import { useResearchStore } from '../store/research'

interface ResearchDigestViewProps {
  onSelect: (id: number) => void
}

const WINDOW_OPTIONS = [14, 30, 60] as const

export default function ResearchDigestView({ onSelect }: ResearchDigestViewProps) {
  const { clusters, clustersLoading, clustersError, fetchClusters } = useResearchStore()
  const [windowDays, setWindowDays] = useState(14)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    fetchClusters(windowDays)
  }, [windowDays])

  // ... render logic
}
```

**Article title resolution for expanded list:**
`article_ids` contains only IDs. The titles of individual cluster articles are NOT fetched by the cluster endpoint — only `centroid_title` is provided. To show article titles in the expanded list, you need to either:

**Option A (recommended):** Fetch titles from the existing articles store — `useArticlesStore().articles` already holds `ArticleListItem[]` with titles. Map `article_ids` against the store. For articles not in the store (e.g., read/archived), show a truncated ID or omit.

**Option B:** Add a `titles` field to `ClusterOut` (backend change). **Do NOT do this** — it bloats the response unnecessarily. Use Option A.

Implementation:
```tsx
const { articles } = useArticlesStore()
const articleMap = useMemo(
  () => new Map(articles.map(a => [a.id, a])),
  [articles]
)
// In expanded list:
{cluster.article_ids.map(id => {
  const a = articleMap.get(id)
  return (
    <button key={id} onClick={() => onSelect(id)} className="...">
      {a ? a.title : `Article #${id}`}
    </button>
  )
})}
```

---

### Frontend: `ArticleList.tsx` changes

**Props type extension** (line 16):
```typescript
// Change:
currentView: 'feed' | 'digest' | 'stats'
onViewChange: (v: 'feed' | 'digest' | 'stats') => void

// To:
currentView: 'feed' | 'digest' | 'stats' | 'research'
onViewChange: (v: 'feed' | 'digest' | 'stats' | 'research') => void
```

**Research tab button** — add alongside the existing digest and stats buttons in the toolbar area. Follow the exact same button styling pattern as the existing icons:
```tsx
<button
  onClick={() => onViewChange(currentView === 'research' ? 'feed' : 'research')}
  className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
    currentView === 'research' ? 'text-violet-400' : 'text-text-secondary hover:text-text-primary'
  }`}
  title="Research Clusters"
>
  <Network className="w-4 h-4" />  {/* or BrainCircuit, or Layers */}
</button>
```

Import the icon from `lucide-react`. Use `Network` if available, else `Layers`, else `BrainCircuit`.

**Render `ResearchDigestView` in the conditional block:**
```tsx
// Add after the stats block (~line 242):
{currentView === 'research' && (
  <ResearchDigestView onSelect={onSelect} />
)}
```

Also guard the existing search, refresh, filter controls with `currentView === 'feed'` (they already have this guard — no change needed).

---

### Frontend: `App.tsx` changes

Only one change needed — extend the `appView` type:

```typescript
// Line 61: change 'feed' | 'digest' | 'stats' to include 'research'
const [appView, setAppView] = useState<'feed' | 'digest' | 'stats' | 'research'>('feed')
```

The type change propagates automatically to ArticleList via the prop types.

---

### Dependency Version Guidance

`hdbscan>=0.8.33`:
- Pure Python (Cython compiled), CPU-only — no GPU, no CUDA.
- Depends on `numpy`, `scikit-learn`, `scipy`, `joblib` — all standard scientific Python.
- `fit_predict(matrix)` returns a `numpy.ndarray` of integer labels; -1 = noise.
- **Important:** `hdbscan` may require Cython at build time. If the Docker image doesn't have Cython, use `hdbscan==0.8.33` (pinned to a pre-built wheel). The `>=` constraint works if the base image supports compilation. As a fallback, use `pip install hdbscan --no-build-isolation`.
- Alternative: if `hdbscan` package fails to install, consider `scikit-learn`'s `HDBSCAN` (added in sklearn 1.3.0): `from sklearn.cluster import HDBSCAN`. Since `scikit-learn` is already a dependency of `hdbscan` itself, either works. **Prefer the `hdbscan` standalone package** as specified in the architecture.

---

### Previous Story Intelligence (from Story 3.1)

**Files and patterns established:**

| File | Relevant Pattern |
|---|---|
| `backend/api/embedder.py` | `_get_chroma()` singleton — import this, never re-create the client |
| `backend/api/routers/articles.py` | `from embedder import _get_chroma` is deferred inside the function — do the same in `research.py` |
| `backend/api/routers/internal.py` | `from embedder import embed_article_async` is a top-level import there (not deferred) — for `research.py`, keep `_get_chroma` deferred since hdbscan too must be deferred |
| `frontend/src/components/RelatedPanel.tsx` | `useEffect + fetch + useState` pattern; loading/error/empty state structure |
| `frontend/src/types.ts` | `RelatedArticle` was added after `Article`; follow same placement convention |
| `backend/api/models.py` | `RelatedArticleOut` added before `FeedWithCount` — add `ClusterOut` similarly |

**From Story 2.3:**

| Pattern | How to reuse |
|---|---|
| `ContribTypeBadge` + `ReDocTypeBadge` in cluster article list | Use them to visually enrich expanded article rows (optional — if article is in store) |
| `useArticlesStore().articles` for article metadata | Already loaded in the main view — use this to resolve titles in expanded cluster |

**Git history note:**
The most recent commits are pre-Baṣīra changes (pre-Story 1.1). All Baṣīra story implementations are uncommitted local changes. The dev agent should NOT attempt a `git commit` — implementation only.

---

### Test Strategy

Create `backend/scorer/tests/test_cluster_map.py` with host-runnable tests:

```
TestClusterDependency       — hdbscan in requirements.txt
TestClusterModel            — ClusterOut fields in models.py
TestClusterEndpointSource   — /clusters route in research.py, deferred imports
TestFrontendClusterType     — Cluster interface in types.ts
TestResearchStore           — research.ts file exists + fetchClusters pattern
TestResearchDigestView      — component file + key structural patterns
```

Integration tests (skipped on host, Docker only):
```
TestClusterAPI              — HTTP test: returns 200 + list for empty corpus
TestHDBSCANIntegration      — seeds Chroma with test vectors, verifies cluster output
```

Use same `SKIP_INTEGRATION` + `_check_integration_deps` pattern from `test_semantic_retrieval.py`.

---

### Critical Implementation Rules

1. **Deferred imports**: Both `import hdbscan` and `import numpy as np` MUST be inside the `get_clusters` function body — never at the module top of `research.py`. The API must start even if hdbscan is not installed (fault tolerance: returns `[]` in that case via the try/except).

2. **`_get_chroma()` ownership**: `_get_chroma()` is defined in `embedder.py`. Do NOT copy or redefine it in `research.py`. Import it: `from embedder import _get_chroma` — this import must also be inside the function body (deferred).

3. **ChromaDB batch get**: Use `collection.get(ids=[...], include=["embeddings"])` not `collection.query()`. The `get()` call accepts a list of IDs and returns them directly — more efficient than querying by metadata.

4. **HDBSCAN label dtype**: `labels` is a `numpy.ndarray` of `numpy.int64`. When comparing `labels == cluster_id`, this works normally. When passing to the response model, cast: `int(cluster_id)` to convert from `numpy.int64` to Python `int` for JSON serialization.

5. **Matrix dtype**: Always cast embeddings to `np.float32` for HDBSCAN: `matrix = np.array(vectors, dtype=np.float32)`. HDBSCAN accepts both float32 and float64 but float32 is faster.

6. **Article title lookup in frontend**: Do NOT add titles to the ClusterOut response. Use `useArticlesStore().articles` to resolve IDs → titles on the frontend. Articles not in the store show as `"Article #ID"` — this is acceptable.

7. **`App.tsx` type extension**: Only the type union needs to change — `'feed' | 'digest' | 'stats' | 'research'`. The `setAppView` call site and all passing to `ArticleList` works automatically.

8. **`import structlog` in research.py**: Use lazy import inside try/except or declare at top of function, not at module top, to keep the research.py module lightweight. Actually — `structlog` IS available (it's in requirements.txt), so a top-level `import structlog` is acceptable in research.py. Just don't import hdbscan/numpy at top level.

9. **Icon for Research tab**: Check if `Network` exists in the installed version of lucide-react. If not, use `Layers`. Both are available in recent versions. DO NOT install a new icon library.

---

---

## Dev Agent Record

**Implementation completed: 2026-04-22**
**Status: review**

### Files Created
- `backend/api/routers/research.py` — Full implementation (replaced stub) with `GET /api/research/clusters` endpoint
- `frontend/src/store/research.ts` — Zustand `useResearchStore` with `clusters`, `clustersLoading`, `clustersError`, `fetchClusters`
- `frontend/src/components/ResearchDigestView.tsx` — Cluster cards with expand/collapse, window selector (14/30/60d), article title resolution via `useArticlesStore`
- `backend/scorer/tests/test_cluster_map.py` — 57 host-runnable tests + 7 Docker integration tests (correctly skipped on host)

### Files Modified
- `backend/api/requirements.txt` — Added `hdbscan>=0.8.33`
- `backend/api/models.py` — Added `ClusterOut` Pydantic model
- `frontend/src/types.ts` — Added `Cluster` interface
- `frontend/src/components/ArticleList.tsx` — Extended view type union, added Research/Clusters tab button (`Network` icon), added `ResearchDigestView` conditional render
- `frontend/src/App.tsx` — Extended `appView` type to include `'research'`; wired `onNavigate={handleSelectArticle}` to both desktop and mobile `ReaderView` instances

### Test Results
```
184 passed, 22 skipped (full regression suite, excl. pre-existing broken migration test)
57 passed, 7 skipped (Story 3.2 tests only)
```

### Architecture Compliance
- ✅ `import hdbscan` + `import numpy as np` deferred inside `get_clusters()` body — never at module top
- ✅ `from embedder import _get_chroma` deferred inside function body — never at module top
- ✅ `numpy.int64` cast to Python `int` before returning cluster_id
- ✅ `matrix = np.array(vectors, dtype=np.float32)` — float32 for HDBSCAN performance
- ✅ Noise label `-1` excluded from response
- ✅ Full `try/except Exception` wrapping — returns `[]` on any failure, never 500
- ✅ Auth via `_auth = Depends(require_session)`
- ✅ Centroid title = nearest article to cluster mean vector
- ✅ Top tags = top-5 by frequency aggregated across all cluster articles
- ✅ Article title lookup in frontend via `useArticlesStore` (Option A — no backend change)
- ✅ `onNavigate` prop wired in `App.tsx` for both desktop + mobile `ReaderView`

### Activation Note
`hdbscan` requires Cython at build time. If the Docker build fails on `hdbscan`, try:
```dockerfile
RUN pip install hdbscan --no-build-isolation
```

*Generated: 2026-04-22 — Dev Agent Record added*
