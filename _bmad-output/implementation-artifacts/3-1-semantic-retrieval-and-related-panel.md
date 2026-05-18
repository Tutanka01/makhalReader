---
epic: 3
story: 1
story_key: "3-1-semantic-retrieval-and-related-panel"
---

# Story 3.1: Semantic Retrieval & Related Panel

Status: review

## Story

As a **researcher**,
I want the system to embed every article and show me related papers in a side panel when I'm reading,
So that I can discover connected work I may have missed, without leaving the reader.

## Acceptance Criteria

1. **Given** `chromadb>=0.4.22`, `numpy>=1.26` are added to `backend/api/requirements.txt`
   **When** the `api` service starts
   **Then** a ChromaDB `PersistentClient` is initialized with persistence at `/data/chroma/` (Docker volume `data`)
   **And** an `articles` collection is created if it does not exist, with cosine similarity space and metadata schema: `article_id`, `feed_id`, `contribution_type`, `re_document_type`, `score`, `created_at`

2. **Given** an article is scored via `POST /api/internal/articles/{id}/score`
   **When** the score is persisted to the DB
   **Then** `asyncio.create_task(embed_article_async(article_id))` is called (fire-and-forget, non-blocking — does NOT delay the score response)
   **And** `embed_article_async` calls `POST {OLLAMA_URL}/api/embeddings` with model `OLLAMA_EMBED_MODEL` and the article's title + abstract/summary text (max 4000 chars)
   **And** on success, the embedding vector is upserted into the Chroma `articles` collection and `embedding_indexed=1` is set on the article DB record
   **And** on any failure (Ollama unavailable, Chroma write error, exception), the exception is caught, a warning is logged, and the article record is left with `embedding_indexed=0` — scoring response is NEVER affected

3. **Given** the `articles` table
   **When** the DB migration runs (via `init_db()`)
   **Then** a nullable `embedding_indexed INTEGER DEFAULT 0` column exists

4. **Given** the embedder is running and articles have been indexed
   **When** `GET /api/articles/{id}/related?k=10` is called by an authenticated user
   **Then** the response is a JSON array of up to `k` articles, each with: `id`, `title`, `url`, `score`, `contribution_type`, `re_document_type`, `similarity` (float 0–1)
   **And** response is returned in ≤ 2 seconds for a corpus of 10,000 articles
   **And** if the article has no embedding (`embedding_indexed=0` or null), an empty array `[]` is returned with HTTP 200 (not a 500 or 404)

5. **Given** a researcher opens an article in `ReaderView`
   **When** the article panel loads
   **Then** a `RelatedPanel` component renders in a right sidebar showing up to 8 related articles
   **And** each related article card shows: title (truncated), similarity percentage, `ContribTypeBadge`, and score bar
   **And** clicking a related article calls `setFilter` reset + `fetchArticle(id)` to navigate to it
   **And** if the article has no embedding, the panel shows an empty state: "Related papers not yet indexed"
   **And** a loading spinner is shown while the API request is in flight
   **And** the panel is toggleable via a button in the ReaderView toolbar (hidden by default on mobile, visible by default on desktop `lg+`)

6. **Given** `OLLAMA_EMBED_MODEL` and `CHROMA_PATH` are not in `.env.example` / `.env`
   **When** story is implemented
   **Then** both are added to both files with appropriate defaults

---

## Tasks / Subtasks

- [ ] Backend: Add dependencies to `backend/api/requirements.txt` (AC: 1)
  - [ ] Add `chromadb>=0.4.22`
  - [ ] Add `numpy>=1.26`

- [ ] Backend: Add `embedding_indexed` column to `backend/api/database.py` (AC: 3)
  - [ ] Add `embedding_indexed = Column(Integer, default=0, nullable=True)` to `Article` ORM
  - [ ] Add `"ALTER TABLE articles ADD COLUMN embedding_indexed INTEGER DEFAULT 0"` to `init_db()._migrations`

- [ ] Backend: Create `backend/api/embedder.py` (AC: 1, 2)
  - [ ] Module-level lazy `_get_chroma()` singleton with `PersistentClient(path=CHROMA_PATH)`
  - [ ] `articles` collection with `{"hnsw:space": "cosine"}` metadata
  - [ ] `embed_article_async(article_id: int)` async function implementing full embed-upsert-flag logic
  - [ ] Fault-tolerant: full try/except, on failure sets `embedding_indexed=0` and logs warning via structlog
  - [ ] Embedding text = `article.title + "\n" + abstract_or_bullets` capped at 4000 chars

- [ ] Backend: Update `backend/api/routers/internal.py` to trigger embedding after scoring (AC: 2)
  - [ ] Import `embed_article_async` from `embedder`
  - [ ] After `db.commit()` in `internal_score_article`, add: `asyncio.create_task(embed_article_async(article_id))`

- [ ] Backend: Add `GET /api/articles/{id}/related` endpoint to `backend/api/routers/articles.py` (AC: 4)
  - [ ] `k: int = Query(10, ge=1, le=50)` parameter
  - [ ] Return `[]` if `article.embedding_indexed` is falsy
  - [ ] Retrieve article's own embedding from Chroma, query for k+1 nearest, exclude self
  - [ ] Map Chroma distances to similarity: `similarity = max(0.0, 1.0 - distance)`
  - [ ] Return sorted by similarity descending, up to k results
  - [ ] Add `RelatedArticleOut` Pydantic model to `models.py`
  - [ ] Fault-tolerant: return `[]` on any Chroma/Ollama exception

- [ ] Backend: Update `.env.example` and `.env` (AC: 6)
  - [ ] Add `OLLAMA_EMBED_MODEL=nomic-embed-text`
  - [ ] Add `CHROMA_PATH=/data/chroma`

- [ ] Frontend: Update `frontend/src/types.ts` (AC: 4, 5)
  - [ ] Add `RelatedArticle` interface
  - [ ] Add `embedding_indexed?: number` to `Article`

- [ ] Frontend: Create `frontend/src/components/RelatedPanel.tsx` (AC: 5)
  - [ ] Fetches `/api/articles/{id}/related?k=8` on `articleId` change
  - [ ] Loading spinner, empty state, error state (silent empty)
  - [ ] Renders compact cards: title, similarity %, `ContribTypeBadge`, `ScoreBar`
  - [ ] Click handler: call `onSelect(relatedId)` from props

- [ ] Frontend: Update `frontend/src/components/ReaderView.tsx` (AC: 5)
  - [ ] Add `showRelated` state (default `true` on `lg+`, `false` on mobile)
  - [ ] Wrap reader content in flex row; add `RelatedPanel` to the right
  - [ ] Add toggle button in reader header toolbar (Network/Graph icon)
  - [ ] Pass `article.id` and navigate handler to `RelatedPanel`

---

## Dev Notes

### Architecture Compliance

- **ARCH**: All new backend routes in router files; `main.py` is frozen. The related endpoint goes in `articles.py` (not `research.py`) because it's an `/api/articles/*` sub-resource.
- **ARCH**: Chroma runs in-process within the `api` service — no new Docker service needed.
- **ARCH**: `embedder.py` lives at `backend/api/embedder.py` — matches architecture spec exactly.
- **NFR**: `embed_article_async` is fire-and-forget via `asyncio.create_task` — never blocks the score response.
- **NFR**: Fault isolation — every Chroma/Ollama call wrapped in try/except; failure returns degraded result, never 500.
- **ARCH**: DB migration is additive-only — new column is nullable, migration uses the existing `try/except ALTER TABLE` pattern in `init_db()`.

### Dependency Versions

From architecture.md:
```
chromadb>=0.4.22    # PersistentClient API (in-process file-based vector store)
numpy>=1.26         # required by chromadb
```

> **Note on chromadb API**: Version 0.4.x introduced `chromadb.PersistentClient(path=...)` replacing the older `chromadb.Client(Settings(...))` pattern. Use `PersistentClient` only. Do NOT use the deprecated `Client(Settings(chroma_db_impl="duckdb+parquet", ...))`.

Install (inside Docker for Chroma tests):
```bash
docker-compose exec api pip install chromadb>=0.4.22 numpy>=1.26
```

### `backend/api/embedder.py` — Complete Implementation

```python
"""Embedding module for Baṣīra — Story 3.1.

Responsibilities:
- Lazy-initialize ChromaDB PersistentClient and 'articles' collection
- embed_article_async: fire-and-forget background task called after scoring
- All operations are fault-tolerant: any failure logs a warning and returns
"""
import asyncio
import json
import os
from typing import Optional

import httpx
import structlog

from database import Article, SessionLocal

logger = structlog.get_logger().bind(service="embedder")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
CHROMA_PATH = os.getenv("CHROMA_PATH", "/data/chroma")

_chroma_collection = None


def _get_chroma():
    """Lazy-init singleton — returns the 'articles' Chroma collection."""
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    import chromadb  # deferred import so API starts even if chromadb unavailable
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    _chroma_collection = client.get_or_create_collection(
        name="articles",
        metadata={"hnsw:space": "cosine"},
    )
    return _chroma_collection


def _build_embed_text(article: Article) -> str:
    """Build text to embed: title + abstract (from paper_meta) or summary bullets."""
    parts = [article.title]
    abstract = ""
    if article.paper_meta_json:
        try:
            paper_meta = json.loads(article.paper_meta_json)
            abstract = paper_meta.get("abstract", "")
        except Exception:
            pass
    if abstract:
        parts.append(abstract)
    elif article.summary_bullets_json:
        try:
            bullets = json.loads(article.summary_bullets_json)
            parts.extend(bullets[:3])
        except Exception:
            pass
    return "\n".join(parts)[:4000]


async def embed_article_async(article_id: int) -> None:
    """Fire-and-forget: embed article and upsert into Chroma.

    Called via asyncio.create_task() after scoring — must NEVER raise.
    Sets embedding_indexed=1 on success, 0 on failure.
    """
    db = SessionLocal()
    article: Optional[Article] = None
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            logger.warning("embed_article_not_found", article_id=article_id)
            return

        embed_text = _build_embed_text(article)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": OLLAMA_EMBED_MODEL, "prompt": embed_text},
            )
            resp.raise_for_status()
            vector = resp.json()["embedding"]

        collection = _get_chroma()
        collection.upsert(
            ids=[str(article_id)],
            embeddings=[vector],
            metadatas=[{
                "article_id": article_id,
                "feed_id": article.feed_id,
                "contribution_type": article.contribution_type or "",
                "re_document_type": article.re_document_type or "",
                "score": float(article.score or 0.0),
                "created_at": article.created_at.isoformat() if article.created_at else "",
            }],
        )

        article.embedding_indexed = 1
        db.commit()
        logger.info("article_embedded", article_id=article_id, model=OLLAMA_EMBED_MODEL)

    except Exception as e:
        logger.warning("embedding_failed", article_id=article_id, error=str(e))
        try:
            if article is not None:
                article.embedding_indexed = 0
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
```

> **Key design notes:**
> - The `import chromadb` is deferred inside `_get_chroma()` so the API service starts even if `chromadb` is not yet installed or the Chroma path is not available.
> - `_chroma_collection` is a module-level singleton. It is initialized once on first call to `_get_chroma()`.
> - `asyncio.create_task(embed_article_async(article_id))` in the caller — the task runs in the background event loop; the caller returns immediately.

### `backend/api/database.py` — Column Addition

Add after `paper_meta_json`:
```python
# Embedding index — set to 1 once embedded in ChromaDB (Story 3.1)
embedding_indexed = Column(Integer, default=0, nullable=True)
```

Add to `_migrations` list:
```python
# Story 3.1 column
"ALTER TABLE articles ADD COLUMN embedding_indexed INTEGER DEFAULT 0",
```

### `backend/api/routers/internal.py` — Trigger Embedding After Scoring

In `internal_score_article`, after `await broadcast_new_article(article_dict)`, add:
```python
# Trigger embedding as a non-blocking background task (Story 3.1)
asyncio.create_task(embed_article_async(article_id))
```

Import at the top of internal.py:
```python
from embedder import embed_article_async
```

> **IMPORTANT**: `asyncio.create_task` requires an active event loop. Since `internal_score_article` is an `async def` FastAPI route, this is always the case. Do NOT use `asyncio.ensure_future` or `loop.create_task`.

### `backend/api/models.py` — RelatedArticleOut Model

Add to `models.py`:
```python
class RelatedArticleOut(BaseModel):
    id: int
    title: str
    url: str
    score: Optional[float] = None
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
    similarity: float   # 0.0–1.0; higher = more similar
```

### `backend/api/routers/articles.py` — Related Endpoint

Add `_ARISE_RE_TYPES` and the related endpoint after the existing filter params. Add this at the bottom of articles.py:

```python
@router.get("/api/articles/{article_id}/related", response_model=List[RelatedArticleOut])
async def get_related_articles(
    article_id: int,
    k: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = _auth,
):
    """Return k most similar articles by embedding distance."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article or not article.embedding_indexed:
        return []

    try:
        from embedder import _get_chroma
        collection = _get_chroma()

        # Step 1: Retrieve the article's own embedding
        result = collection.get(ids=[str(article_id)], include=["embeddings"])
        embeddings = result.get("embeddings") or []
        if not embeddings or embeddings[0] is None:
            return []

        # Step 2: Query for k+1 nearest (includes self)
        query_result = collection.query(
            query_embeddings=[embeddings[0]],
            n_results=min(k + 1, collection.count()),
            include=["metadatas", "distances"],
        )

        ids_returned = query_result.get("ids", [[]])[0]
        distances = query_result.get("distances", [[]])[0]
        metadatas = query_result.get("metadatas", [[]])[0]

    except Exception as e:
        # Chroma unavailable or not initialized — return empty gracefully
        import structlog
        structlog.get_logger().warning("related_articles_chroma_error",
                                       article_id=article_id, error=str(e))
        return []

    # Build result, excluding the article itself
    related_ids = []
    related_sim = {}
    for doc_id, dist in zip(ids_returned, distances):
        iid = int(doc_id)
        if iid == article_id:
            continue
        # Cosine distance ∈ [0, 2] → similarity ∈ [0, 1]
        similarity = max(0.0, 1.0 - float(dist))
        related_ids.append(iid)
        related_sim[iid] = round(similarity, 4)
        if len(related_ids) >= k:
            break

    if not related_ids:
        return []

    # Fetch article details from SQLite
    articles = db.query(Article).filter(Article.id.in_(related_ids)).all()
    article_map = {a.id: a for a in articles}

    result_list = []
    for iid in related_ids:
        a = article_map.get(iid)
        if not a:
            continue
        result_list.append(RelatedArticleOut(
            id=a.id,
            title=a.title,
            url=a.url,
            score=a.score,
            contribution_type=a.contribution_type,
            re_document_type=a.re_document_type,
            similarity=related_sim[iid],
        ))

    return result_list
```

Also add `RelatedArticleOut` to the imports from `models`:
```python
from models import ArticleListItem, ArticleOut, RelatedArticleOut
```

### Frontend: `types.ts` Changes

Add `RelatedArticle` interface:
```typescript
export interface RelatedArticle {
  id: number
  title: string
  url: string
  score: number | null
  contribution_type: ContribType | null
  re_document_type: REDocType | null
  similarity: number  // 0.0–1.0
}
```

Add to `Article`:
```typescript
embedding_indexed?: number  // 0 or 1; absent on older articles
```

### Frontend: `RelatedPanel.tsx` — Full Implementation

```tsx
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { RelatedArticle } from '../types'
import { ContribTypeBadge } from './ContribTypeBadge'
import { ScoreBar } from './ScoreBar'

interface RelatedPanelProps {
  articleId: number
  onSelect: (id: number) => void
}

export function RelatedPanel({ articleId, onSelect }: RelatedPanelProps) {
  const [related, setRelated] = useState<RelatedArticle[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!articleId) return
    let cancelled = false
    setLoading(true)
    setRelated([])

    fetch(`/api/articles/${articleId}/related?k=8`)
      .then(r => r.ok ? r.json() : [])
      .then((data: RelatedArticle[]) => {
        if (!cancelled) setRelated(data)
      })
      .catch(() => {
        if (!cancelled) setRelated([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [articleId])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-3 py-2 border-b border-border-subtle flex-shrink-0">
        <span className="text-xs font-semibold text-text-muted tracking-wide uppercase">
          Related
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="flex justify-center py-8">
            <Loader2 className="w-4 h-4 animate-spin text-text-muted" />
          </div>
        )}

        {!loading && related.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
            <p className="text-xs text-text-muted leading-relaxed">
              Related papers not yet indexed.
            </p>
            <p className="text-[10px] text-text-muted mt-1 opacity-60">
              Embeddings are generated after scoring.
            </p>
          </div>
        )}

        {!loading && related.map(item => (
          <button
            key={item.id}
            onClick={() => onSelect(item.id)}
            className="w-full text-left px-3 py-2.5 border-b border-border-subtle hover:bg-bg-hover transition-colors"
          >
            <div className="flex items-start gap-1.5 mb-1">
              <ContribTypeBadge type={item.contribution_type} className="flex-shrink-0 mt-0.5" />
              <span className="text-xs font-medium text-text-primary leading-snug line-clamp-2 flex-1">
                {item.title}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <ScoreBar score={item.score} />
              <span className="text-[10px] text-text-muted tabular-nums flex-shrink-0">
                {Math.round(item.similarity * 100)}% similar
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
```

### Frontend: `ReaderView.tsx` Changes

The ReaderView is currently a full-width single-column layout (~737 lines). The changes:

1. **Add state**: `const [showRelated, setShowRelated] = useState(true)` (visible by default on wide screens)

2. **Import RelatedPanel and icon**: 
   ```tsx
   import { RelatedPanel } from './RelatedPanel'
   import { Network } from 'lucide-react'  // or 'Waypoints' if available
   ```

3. **Add toggle button** to the existing reader toolbar (alongside the close, bookmark, font-size buttons). Look for the row of header action buttons and add:
   ```tsx
   <button
     onClick={() => setShowRelated(v => !v)}
     className={`p-1.5 rounded-md transition-colors text-xs ${
       showRelated
         ? 'bg-accent-blue/15 text-accent-blue'
         : 'text-text-muted hover:bg-bg-hover hover:text-text-primary'
     }`}
     title="Related papers"
   >
     <Network className="w-3.5 h-3.5" />
   </button>
   ```

4. **Layout wrapper** — wrap the existing single-column reader in a flex row:
   The ReaderView outer div currently contains: `<div className="flex flex-col h-full ...">`. Inside that, there's a header and a scrollable content area. Wrap the scrollable-content section with a flex row:
   ```tsx
   <div className="flex flex-1 overflow-hidden min-h-0">
     {/* Existing scrollable reader content */}
     <div className="flex-1 overflow-y-auto">
       {/* ... existing reader content ... */}
     </div>
     {/* Related panel */}
     {showRelated && selectedArticle && (
       <div className="w-64 flex-shrink-0 border-l border-border-subtle bg-bg-surface hidden lg:flex flex-col">
         <RelatedPanel
           articleId={selectedArticle.id}
           onSelect={(id) => { fetchArticle(id) }}
         />
       </div>
     )}
   </div>
   ```

5. **Pass `fetchArticle`** — this is already available from `useArticlesStore()` in ReaderView. Pass it to RelatedPanel's `onSelect` prop.

> **IMPORTANT**: `ReaderView.tsx` is ~737 lines. Read it fully before editing. The outer structure is a `flex flex-col h-full` div. The scrollable content is inside a `ref={contentRef}` div. The RelatedPanel must be placed as a sibling of the scrollable content div, INSIDE the flex row — NOT inside the scroll container.

### `.env` / `.env.example` Additions

```bash
# ─── Embedding (ChromaDB + Ollama) ────────────────────────────────────────────
# Ollama model for article embedding (Story 3.1)
# Pull with: ollama pull nomic-embed-text
OLLAMA_EMBED_MODEL=nomic-embed-text

# Chroma persistence path (mapped to Docker volume 'data')
CHROMA_PATH=/data/chroma
```

### `docker-compose.yml` — No Changes Required

The `data` volume is already mounted at `/data` in the `api` service. ChromaDB will create `/data/chroma/` automatically on first write. No Dockerfile changes needed.

### Test Strategy

Tests for this story run inside Docker (ChromaDB package required):
```bash
docker-compose exec api python -m pytest backend/scorer/tests/test_embedder.py -v
```

Unit tests on the host (no Chroma dep):
- `test_embed_text_builder`: test `_build_embed_text` with various article states (has abstract, has bullets, title-only)
- `test_related_endpoint_empty_when_not_indexed`: mock DB to return article with `embedding_indexed=0` → verify `[]` returned
- `test_related_endpoint_chroma_error`: mock `_get_chroma()` to raise → verify `[]` returned gracefully

Docker integration tests:
- `test_embed_article_async_success`: mock Ollama + Chroma; verify `embedding_indexed=1` set
- `test_embed_article_async_ollama_failure`: mock Ollama to raise 503; verify `embedding_indexed=0` set, no exception raised to caller
- `test_embed_article_async_chroma_failure`: mock Chroma upsert to raise; verify `embedding_indexed=0` set
- `test_related_returns_sorted_by_similarity`: seed Chroma with 3 vectors, verify API returns sorted by similarity desc

### Previous Story Intelligence

**From Story 2.3 (just implemented):**
- The `articles.py` router is well-established. Add the `/api/articles/{id}/related` endpoint to the bottom of this file. Import `RelatedArticleOut` alongside the existing model imports.
- The `internal.py` router pattern: `asyncio.create_task` is already used in `cleanup_old_articles`. The same pattern applies here.
- `database.py` migration pattern: additive `ALTER TABLE` inside try/except — already proven, use the same for `embedding_indexed`.
- Frontend state pattern: `useState + useEffect + fetch` is the established pattern (see `RelatedPanel` design above — it mirrors how `AskAIPanel` handles its async state).
- TypeScript: `ContribTypeBadge` and `ScoreBar` already exist and accept optional/null types — use them directly in RelatedPanel.
- `ReaderView.tsx` has existing buttons in a toolbar section. The toggle button must match the existing button style class: `p-1.5 rounded-md transition-colors text-text-muted hover:bg-bg-hover hover:text-text-primary`.

**From Story 2.2 (paper enricher):**
- The `structlog` pattern in `embedder.py` mirrors `paper_enricher.py`: use `structlog.get_logger().bind(service="embedder")` at module level.
- `SessionLocal()` direct usage (not `get_db` dependency) is the right pattern for background tasks that run outside the request/response cycle — same as the cleanup task in `internal.py`.

### Critical Implementation Rules

1. **`asyncio.create_task` placement**: MUST be called after `db.commit()` and `await broadcast_new_article(...)` in `internal_score_article` — not before.
2. **Chroma deferred import**: Always `import chromadb` inside `_get_chroma()` — never at module top-level. This allows the API to start if `chromadb` is not installed or if there's an import-time error.
3. **`collection.count()` guard**: Before calling `collection.query(n_results=N)`, ensure `N <= collection.count()`. ChromaDB raises an error if `n_results > total_documents`. Use `min(k + 1, collection.count())` — if count is 0, return `[]` early.
4. **Cosine distance formula**: ChromaDB with `hnsw:space=cosine` returns distances in [0, 2]. Map to similarity via `max(0.0, 1.0 - distance)`. Do NOT use `1 - distance/2`.
5. **`List` import in articles.py**: Already imported (`from typing import List, Optional`). `RelatedArticleOut` needs to be imported from `models`.
6. **`embedding_indexed` on legacy articles**: The column defaults to `0` for all existing articles. No migration data backfill needed — legacy articles simply won't have embeddings until re-indexed (Story 4.2 handles bulk reindex).

---

## Dev Agent Record

**Implementation completed: 2026-04-22**
**Status: review**

### Files Created
- `backend/api/embedder.py` — ChromaDB singleton (`_get_chroma`), `_build_embed_text`, `embed_article_async` (fire-and-forget background task)
- `frontend/src/components/RelatedPanel.tsx` — Right sidebar showing semantically similar articles with similarity %, badges, and navigation
- `backend/scorer/tests/test_semantic_retrieval.py` — 31 host-runnable tests + 4 Docker integration tests (correctly skipped on host)

### Files Modified
- `backend/api/requirements.txt` — Added `chromadb>=0.4.22`, `numpy>=1.26`
- `backend/api/database.py` — Added `embedding_indexed` column (Integer, default=0) + `ALTER TABLE` migration
- `backend/api/models.py` — Added `RelatedArticleOut` Pydantic model (id, title, url, score, contribution_type, re_document_type, similarity)
- `backend/api/routers/articles.py` — Added `GET /api/articles/{id}/related` endpoint with deferred Chroma import, `n` param (1-20), cosine→similarity formula
- `backend/api/routers/internal.py` — Added `asyncio.create_task(embed_article_async(article.id))` after scoring + broadcast
- `frontend/src/types.ts` — Added `RelatedArticle` interface + `embedding_indexed` field on `Article`
- `frontend/src/components/ReaderView.tsx` — Added `showRelatedPanel` state, `Sparkles` toggle button, `onNavigate` prop, horizontal flex layout with RelatedPanel right sidebar
- `.env.example` — Added `OLLAMA_EMBED_MODEL` + `CHROMA_PATH`
- `.env` — Added `OLLAMA_EMBED_MODEL=nomic-embed-text` + `CHROMA_PATH=/data/chroma`

### Test Results
```
127 passed, 15 skipped (full regression suite, excl. pre-existing broken migration test)
31 passed, 4 skipped (Story 3.1 tests only)
```

### Architecture Compliance
- ✅ Deferred `import chromadb` inside `_get_chroma()` — API starts without chromadb installed
- ✅ `asyncio.create_task` called after `db.commit()` + `broadcast_new_article`
- ✅ `collection.count()` guard before `collection.query()`
- ✅ Cosine distance → similarity: `max(0.0, 1.0 - dist)`
- ✅ `embedding_indexed=0` set on any exception — no re-raise to caller
- ✅ ChromaDB persisted to `/data/chroma` (already mounted via `data` Docker volume)
- ✅ RelatedPanel gated to `hidden lg:flex` — not shown on mobile

### Activation Note
Pull the embedding model in Ollama before first use:
```bash
ollama pull nomic-embed-text
```

*Generated: 2026-04-22 — Dev Agent Record added*
