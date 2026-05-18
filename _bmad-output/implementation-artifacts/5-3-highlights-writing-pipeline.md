---
epic: 5
story: 3
story_key: "5-3-highlights-writing-pipeline"
---

# Story 5.3: Highlights → Writing Pipeline

Status: draft

## Story

As a **PhD researcher**,
I want to tag my reading highlights with a thesis section and then export them as an LLM-synthesized writing block,
So that my daily reading directly feeds into my thesis chapters instead of accumulating as disconnected annotations.

## Acceptance Criteria

1. **Given** the `highlights` table
   **When** DB migrations run
   **Then** a nullable `thesis_section TEXT` column exists on the `highlights` table
   **And** existing highlights have `thesis_section = NULL` (no backfill required)

2. **Given** a highlight exists
   **When** `PATCH /api/highlights/{id}` is called with `{"thesis_section": "P1 Construction"}`
   **Then** the `thesis_section` is persisted on the highlight row
   **And** the updated `HighlightOut` (including `thesis_section`) is returned
   **And** if `thesis_section` is not one of the valid values, HTTP 422 is returned

3. **Given** highlights exist with matching `thesis_section`
   **When** `POST /api/research/export-highlights` is called with `{"thesis_section": "P1 Construction", "window_days": 90, "max_highlights": 30}`
   **Then** all highlights tagged for that section (from articles in the last `window_days`) are retrieved, ordered by article score descending
   **And** an LLM synthesis call is made with the highlights as context
   **And** the response is a JSON object: `{thesis_section, highlight_count, article_count, synthesis_text, source_articles: [{id, title, url}]}`
   **And** the response is returned as a streaming SSE response (same pattern as `ask.py`)

4. **Given** fewer than 2 highlights exist for the requested section and window
   **When** `POST /api/research/export-highlights` is called
   **Then** HTTP 422 is returned with `{"detail": "Not enough highlights for synthesis (found N, minimum 2)."}`

5. **Given** the reader has an article open in `ReaderView`
   **When** the user opens `HighlightPopover` to edit an existing highlight
   **Then** a dropdown `Thesis Section` appears with all valid section values plus a "None" option
   **And** selecting a section calls `PATCH /api/highlights/{id}` immediately (auto-save, no submit button)

6. **Given** highlights are tagged across sections
   **When** the user navigates to the `WriteAssistPanel`
   **Then** a section picker shows all 9 valid sections with counts of tagged highlights per section
   **And** selecting a section and clicking "Synthesize" triggers the export endpoint and streams the result into a text area
   **And** a "Copy to clipboard" button and "Export as Markdown" download button are present

---

## Tasks / Subtasks

- [ ] Backend: Add `thesis_section` to `Highlight` ORM and migrations in `backend/api/database.py` (AC: 1)
  - [ ] Add `thesis_section = Column(Text, nullable=True)` to `Highlight` class
  - [ ] Add `"ALTER TABLE highlights ADD COLUMN thesis_section TEXT"` to `init_db()._migrations`

- [ ] Backend: Update `HighlightUpdate` and `HighlightOut` in `backend/api/models.py` (AC: 2)
  - [ ] Add `thesis_section: Optional[str] = None` to `HighlightUpdate`
  - [ ] Add `thesis_section: Optional[str] = None` to `HighlightOut`
  - [ ] Add `_VALID_THESIS_SECTIONS` constant and a validator on `HighlightUpdate.thesis_section`
  - [ ] Add `HighlightExportRequest` model: `{thesis_section: str, window_days: int = 90, max_highlights: int = 30}`
  - [ ] Add `HighlightExportOut` model: `{thesis_section, highlight_count, article_count, synthesis_text, source_articles}`

- [ ] Backend: Add `PATCH /api/highlights/{id}` endpoint to `backend/api/routers/highlights.py` (AC: 2)
  - [ ] Partial update: only fields present in the request body are updated
  - [ ] Validates `thesis_section` against `_VALID_THESIS_SECTIONS`

- [ ] Backend: Add `POST /api/research/export-highlights` endpoint to `backend/api/routers/research.py` (AC: 3, 4)
  - [ ] Query highlights by `thesis_section` + `window_days` JOIN articles on `article_id`
  - [ ] Enforce minimum 2 highlights guard
  - [ ] Build LLM prompt from highlights (see Dev Notes)
  - [ ] Stream LLM response via SSE (same pattern as `backend/api/routers/ask.py`)

- [ ] Backend: Add `GET /api/research/export-highlights/sections` to `backend/api/routers/research.py` (AC: 6)
  - [ ] Returns: `[{thesis_section, count}]` for all sections that have at least 1 highlight, including sections with 0 tagged (for display in picker)

- [ ] Frontend: Update `HighlightOut` type in `frontend/src/types.ts` (AC: 5)
  - [ ] Add `thesis_section?: string | null`

- [ ] Frontend: Update `HighlightPopover.tsx` (AC: 5)
  - [ ] Add `ThesisSectionSelect` dropdown (or segmented button group) below the color picker
  - [ ] On change: call `PATCH /api/highlights/{id}` with `{thesis_section}` — auto-save
  - [ ] Options: all 9 valid sections + "None" (sets to null)

- [ ] Frontend: Create `WriteAssistPanel.tsx` in `frontend/src/components/` (AC: 6)
  - [ ] Section picker with counts from `/api/research/export-highlights/sections`
  - [ ] "Synthesize" button → POST to `/api/research/export-highlights`, stream SSE into textarea
  - [ ] Streaming loading state (progressive text rendering)
  - [ ] "Copy" button + "Export .md" download button
  - [ ] Character count and source articles listed below the synthesis

- [ ] Frontend: Add `WriteAssistPanel` to the sidebar or as a top-level route in `App.tsx`

---

## Dev Notes

### Valid Thesis Sections

```python
_VALID_THESIS_SECTIONS = {
    "P1 Construction",      # Requirements extraction & formalization
    "P2 Consistency",       # Model inconsistency detection
    "P3 Model Drift",       # Continuous synchronization
    "P4 Trust",             # Explainability & certifiability
    "P5 Blueprint Query",   # Semantic retrieval over MBSE
    "Lit Review / Gap",     # Literature review & gap identification
    "Motivation",           # Problem statement & motivation
    "Related Work",         # Related work positioning
    "Counter-argument",     # Limitations & counter-arguments
}
```

These map directly to the 5 pipeline phases (P1–P5) plus 4 thesis writing sections.

### LLM Synthesis Prompt

```
You are a PhD thesis writing assistant. You help draft synthesis paragraphs from reading highlights.

THESIS SECTION: {thesis_section}
RESEARCHER DOMAIN: AI-driven model-based engineering for cyber-physical systems.

HIGHLIGHTED PASSAGES (from {article_count} papers, best scored first):
{formatted_highlights}

Write a cohesive academic synthesis paragraph of 180–250 words that:
1. Synthesizes the key findings across these passages with proper academic hedging ("X et al. show...", "Several studies suggest...")
2. Uses in-text citation placeholders like [Author Year] derived from the paper titles where possible
3. Ends with a forward-looking gap sentence that sets up the researcher's own contribution
4. Is ready to paste into a {thesis_section} section with minimal editing

Output only the paragraph — no preamble, no explanation.
```

**Formatted highlights block** (each highlight):
```
[Score {score:.1f}] {article_title} ({published_year})
> "{selected_text}"
{note if present}
---
```

Cap total prompt at 6000 chars — truncate oldest/lowest-scored highlights first.

### `PATCH /api/highlights/{id}` Pattern

The existing `highlights.py` router has `PUT /api/highlights/{id}` for full replacement. Add `PATCH` for partial update:

```python
@router.patch("/api/highlights/{highlight_id}", response_model=HighlightOut)
async def patch_highlight(
    highlight_id: int,
    update: HighlightUpdate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    h = db.query(Highlight).filter(Highlight.id == highlight_id).first()
    if not h:
        raise HTTPException(404)
    if update.color is not None:
        h.color = update.color
    if update.note is not None:
        h.note = update.note
    if update.thesis_section is not None:
        h.thesis_section = update.thesis_section  # None clears it
    db.commit()
    return HighlightOut.model_validate(h)
```

Note: to clear `thesis_section`, the client sends `{"thesis_section": null}`. Pydantic parses JSON null as Python `None`, which is valid since the field is `Optional[str]`.

### SSE Streaming Pattern

Follow `backend/api/routers/ask.py` for the streaming response. The synthesis endpoint returns `StreamingResponse` with `media_type="text/event-stream"`. The frontend consumes it the same way `AskAIPanel.tsx` does — an `EventSource` or `fetch` with `getReader()`.

### Section Count Query

```python
from sqlalchemy import func

counts = (
    db.query(Highlight.thesis_section, func.count(Highlight.id).label("count"))
    .filter(Highlight.thesis_section.isnot(None))
    .group_by(Highlight.thesis_section)
    .all()
)
```

Return all 9 valid sections in the response, with `count: 0` for untagged ones (fill from the constant set).

### Test Strategy

- `test_patch_highlight_thesis_section`: valid section → persisted; invalid section → 422
- `test_patch_clears_section`: send `{"thesis_section": null}` → column set to NULL
- `test_export_minimum_guard`: 1 highlight → 422
- `test_export_builds_correct_prompt`: verify highlight text appears in LLM call payload
- `test_section_counts_include_zero_sections`: endpoint returns all 9 sections even when some have 0 highlights
