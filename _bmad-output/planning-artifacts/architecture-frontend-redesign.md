---
title: "Architecture: Baṣīra Frontend Redesign — ProjectOS Design Language"
status: "draft"
created: "2026-05-18"
updated: "2026-05-18"
inputs:
  - "product-brief-basira-frontend-redesign.md"
  - "plateforme-projets (1).html"
  - "frontend/src/App.tsx"
  - "frontend/src/types.ts"
  - "frontend/src/components/* (all 21 components)"
  - "frontend/package.json"
  - "frontend/index.html"
type: "frontend brownfield reskin"
scope: "zero backend changes, zero new features"
---

# Architecture Decision Document
# Baṣīra — Frontend Redesign (ProjectOS Design Language)

**Date:** 2026-05-18  
**Type:** Brownfield reskin — additive token layer, structural shell refactor  
**Constraint:** No backend changes. No new API endpoints. No new features.

---

## 1. Architectural Overview

The redesign has two orthogonal concerns:

1. **Design token layer** — Replace the current Tailwind custom-token approach with CSS custom properties matching the ProjectOS palette. Components that render correctly with the token swap need no other changes.

2. **App shell refactor** — The current `App.tsx` layout (`380px ArticleList + flex-1 ReaderView`) is replaced with a proper 3-zone shell: `240px Sidebar + 48px Topbar + flex-1 Content`. This requires extracting navigation from `ArticleList` into a new `Sidebar` component.

Everything else — business logic, API calls, state management, SSE, keyboard shortcuts — remains unchanged.

---

## 2. Key Architectural Decisions

### ADR-1: Hybrid CSS approach — CSS variables layer on top of Tailwind

**Decision:** Inject ProjectOS CSS custom properties as a `:root` block in `index.html` (or a `tokens.css` file imported in `main.tsx`). Keep Tailwind for layout utilities. Map Tailwind's existing custom tokens (`bg-bg-base`, `text-text-primary`, etc.) to the new CSS variable values in `tailwind.config.js`.

**Rationale:** 
- A full Tailwind removal is out of scope and high-risk.
- The existing `tailwind.config.js` already defines custom token names (`bg-base`, `text-primary`, etc.). We remap those tokens to ProjectOS hex values without touching component JSX.
- CSS variables are needed for ProjectOS patterns that Tailwind doesn't cover (transitions, pseudo-elements, sidebar width var reference).

**Implementation:**
```js
// tailwind.config.js — remap existing token names to ProjectOS values
colors: {
  'bg-base':      'var(--bg)',           // was #0f0f0f (dark) → #FFFFFF
  'bg-surface':   'var(--bg-secondary)', // → #F7F6F3
  'bg-elevated':  'var(--bg-active)',    // → #E8E7E3
  'bg-hover':     'var(--bg-hover)',     // → #EFEFED
  'border-default':'var(--border)',      // → #E8E6E1
  'text-primary': 'var(--text)',         // → #191919
  'text-secondary':'var(--text-secondary)', // → #6B6B6B
  'text-muted':   'var(--text-muted)',   // → #9B9B9B
  'accent':       'var(--accent)',       // → #2F6FED
}
```

**Trade-off accepted:** Components that use raw hex values or non-token Tailwind classes will need manual cleanup — expected in ~5 components (AskAIPanel, HighlightPopover, ScoreBar).

---

### ADR-2: Extract navigation into a new `Sidebar` component

**Decision:** Create `frontend/src/components/Sidebar.tsx`. Move the view-switching logic (`appView` state, `onViewChange` prop) from `ArticleList` into `App.tsx` (already owns it) with `Sidebar` as the new rendering destination.

**Rationale:** `ArticleList` currently owns navigation (view tabs, profile button, logout) while also rendering articles. This is the root cause of the layout's inflexibility. Separating concerns is necessary for the 3-zone shell to work.

**`Sidebar` props interface:**
```ts
interface SidebarProps {
  currentView: AppView                        // 'feed' | 'digest' | 'stats' | 'research' | 'litreview'
  onViewChange: (v: AppView) => void
  feeds: Feed[]
  unreadByCategory: Record<string, number>    // computed from articles store
  onOpenFeedManager: () => void
  onOpenProfile: () => void
  onLogout: () => void
}
```

**`Sidebar` structure (mirrors ProjectOS `.sidebar`):**
```
Sidebar
├── Logo block (◉ Baṣīra + beta badge)
├── Section: PRINCIPAL
│   ├── NavItem: Feed         [unread count]
│   ├── NavItem: Digest
│   ├── NavItem: Lit Review
│   └── NavItem: Stats
├── Divider
├── Section: FEEDS
│   └── NavItem per category  [article count]
├── Divider
├── Footer
│   ├── NavItem: Research Profile (profile icon)
│   ├── NavItem: Feed Manager (settings icon)
│   └── User: Arona · [logout]
```

---

### ADR-3: Add a `Topbar` component above the content area

**Decision:** Create `frontend/src/components/Topbar.tsx` — a `48px` fixed-height bar across the content area (not the sidebar). Rendered by `App.tsx`.

**Rationale:** ProjectOS's topbar gives structural continuity across all views. Currently Baṣīra has no persistent topbar — the reader has its own mini-toolbar, and other views have nothing. This causes visual fragmentation.

**`Topbar` props:**
```ts
interface TopbarProps {
  breadcrumb: string           // e.g. "Feed", "Literature Review"
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onSearch?: (q: string) => void  // optional — wires up when search is implemented
}
```

**Note:** The search bar in Topbar is decorative (renders the input) in this redesign. Actual search logic is a future feature — do not wire up backend calls.

---

### ADR-4: CategoryTabs → sidebar nav items

**Decision:** `CategoryTabs.tsx` is deprecated. Feed category navigation moves into the `Sidebar` FEEDS section as `.nav-item` rows with unread counts. The component file is kept but rendered `null` — do not delete in this PR (other places may reference it).

**Rationale:** Horizontal tab bars waste vertical space and don't scale beyond 5 categories. ProjectOS sidebar nav items with counts are strictly better for this use case.

**Migration:** `ArticleList` receives the selected category via prop (already does — `category` in `ArticleFilter`). The `Sidebar` now controls category selection. `ArticleList` becomes a pure list renderer.

---

### ADR-5: Slide-in panels — unified animation and structure

**Decision:** All three overlay panels (`FeedManagerPanel`, `ResearchProfileEditor`, `RelatedPanel`) adopt identical animation and structural markup. Extract a `SlidePanel` base component.

```ts
// frontend/src/components/SlidePanel.tsx
interface SlidePanelProps {
  open: boolean
  onClose: () => void
  width?: number       // default 510, RelatedPanel uses 400
  title: string
  children: ReactNode
}
```

**Animation (matches ProjectOS exactly):**
```css
@keyframes slide-in-right {
  from { transform: translateX(30px); opacity: 0; }
  to   { transform: translateX(0);    opacity: 1; }
}
```

**Applies to:** `FeedManagerPanel`, `ResearchProfileEditor`, `RelatedPanel`. `AskAIPanel` is embedded in `ReaderView` and not a slide-in — keep as-is.

---

### ADR-6: Badge/pill unification

**Decision:** Replace the three independent badge components (`ContribTypeBadge`, `ReDocTypeBadge`, `ScoreBar`) with a consistent token-based class system. No new component is created — just align class names and colors to the ProjectOS `.tag` / `.pill` system via Tailwind utilities.

**Color mapping:**
```
score ≥ 8        → pill variant: success  (bg-success-bg text-success)
score 6-7        → pill variant: accent   (bg-accent-light text-accent)
score ≤ 5        → pill variant: muted    (bg-bg-active text-text-muted)
method           → tag variant: accent
survey/benchmark → tag variant: purple
tool/tutorial    → tag variant: success
news/other       → tag variant: muted
elicitation/extraction/method (ARISE) → pill variant: warning (amber border)
```

These are CSS class utilities, not a new component abstraction.

---

## 3. Component Impact Matrix

| Component | Change Type | Effort |
|---|---|---|
| `App.tsx` | **Structural** — add Sidebar + Topbar, narrow list zone to 0px (sidebar takes nav) | M |
| `Sidebar.tsx` | **New** — extracted from ArticleList + App nav logic | M |
| `Topbar.tsx` | **New** — breadcrumb + sidebar toggle + search placeholder | S |
| `SlidePanel.tsx` | **New** — base component for 3 overlay panels | S |
| `ArticleList.tsx` | **Refactor** — remove nav elements, keep list + filter logic | M |
| `ArticleCard.tsx` | **Reskin** — apply token classes, DM Mono for score/date | S |
| `ReaderView.tsx` | **Reskin** — topbar style update, token classes | S |
| `FeedManagerPanel.tsx` | **Reskin** — wrap with SlidePanel, internal layout tokens | S |
| `ResearchProfileEditor.tsx` | **Reskin** — wrap with SlidePanel, internal layout tokens | S |
| `RelatedPanel.tsx` | **Reskin** — wrap with SlidePanel (400px), card tokens | S |
| `LitReviewView.tsx` | **Reskin** — stat cards for cluster summary, token classes | S |
| `StatsView.tsx` | **Reskin** — `.stats-row` 4-col grid, section tables, DM Mono | M |
| `ResearchDigestView.tsx` | **Reskin** — kcard pattern for digest items | S |
| `DigestView.tsx` / `DigestCard.tsx` | **Reskin** — card tokens | S |
| `AskAIPanel.tsx` | **Reskin** — surface + border tokens only | S |
| `HighlightPopover.tsx` | **Reskin** — pill tokens for color selector | S |
| `HighlightList.tsx` | **Reskin** — table row pattern | S |
| `CategoryTabs.tsx` | **Deprecate** — render null, keep file | XS |
| `ScoreBar.tsx` | **Reskin** — pbar pattern (5px height, token fill) | XS |
| `LoginView.tsx` | **Reskin** — surface + border + DM Sans | S |
| `OfflineBanner.tsx` | **Reskin** — alert-orange pattern | XS |
| `PaperView.tsx` | **Reskin** — field layout tokens | S |

**Effort key:** XS = < 30 min, S = 30-90 min, M = 90-180 min

---

## 4. File Structure Changes

```
frontend/src/
├── assets/
│   └── tokens.css          ← NEW — ProjectOS CSS variables (:root block)
├── components/
│   ├── Sidebar.tsx          ← NEW
│   ├── Topbar.tsx           ← NEW
│   ├── SlidePanel.tsx       ← NEW
│   ├── ArticleCard.tsx      ← MODIFIED
│   ├── ArticleList.tsx      ← MODIFIED (nav removed)
│   ├── AskAIPanel.tsx       ← MODIFIED (reskin)
│   ├── CategoryTabs.tsx     ← DEPRECATED (render null)
│   ├── ContribTypeBadge.tsx ← MODIFIED (token classes)
│   ├── DigestCard.tsx       ← MODIFIED
│   ├── DigestView.tsx       ← MODIFIED
│   ├── FeedManagerPanel.tsx ← MODIFIED (uses SlidePanel)
│   ├── HighlightList.tsx    ← MODIFIED
│   ├── HighlightPopover.tsx ← MODIFIED
│   ├── LitReviewView.tsx    ← MODIFIED
│   ├── LoginView.tsx        ← MODIFIED
│   ├── OfflineBanner.tsx    ← MODIFIED
│   ├── PaperView.tsx        ← MODIFIED
│   ├── ReaderView.tsx       ← MODIFIED (topbar reskin)
│   ├── ReDocTypeBadge.tsx   ← MODIFIED
│   ├── RelatedPanel.tsx     ← MODIFIED (uses SlidePanel)
│   ├── ResearchDigestView.tsx ← MODIFIED
│   ├── ResearchProfileEditor.tsx ← MODIFIED (uses SlidePanel)
│   ├── ScoreBar.tsx         ← MODIFIED
│   └── StatsView.tsx        ← MODIFIED
├── App.tsx                  ← MODIFIED (shell + Sidebar + Topbar)
├── main.tsx                 ← MODIFIED (import tokens.css)
└── index.html               ← MODIFIED (DM Sans + DM Mono Google Fonts link)
```

---

## 5. Implementation Sequence

The redesign is broken into 4 sequential phases. Each phase produces a working, deployable state — no WIP branches.

### Phase 1 — Token foundation (no visual regressions)
1. Add `tokens.css` with full ProjectOS `:root` block
2. Import in `main.tsx`
3. Update `tailwind.config.js` to map existing token names to CSS variable references
4. Verify: existing UI still renders (colors shift to new palette, layout unchanged)
5. Add DM Sans + DM Mono to `index.html` `<head>`

### Phase 2 — App shell (Sidebar + Topbar)
1. Create `Sidebar.tsx` with ProjectOS nav structure
2. Create `Topbar.tsx`
3. Create `SlidePanel.tsx`
4. Refactor `App.tsx` to 3-zone layout
5. Remove nav elements from `ArticleList.tsx`
6. Deprecate `CategoryTabs.tsx` (render null)
7. Verify: all 5 views reachable, keyboard shortcuts intact, SSE functional

### Phase 3 — Component reskins
Work through components in dependency order (base → composite):
1. `ScoreBar`, `ContribTypeBadge`, `ReDocTypeBadge`, `OfflineBanner` (XS items first)
2. `ArticleCard`, `HighlightPopover`, `HighlightList`
3. `AskAIPanel`, `PaperView`
4. `ReaderView` (topbar only)
5. `FeedManagerPanel`, `ResearchProfileEditor`, `RelatedPanel` (wrap with SlidePanel)
6. `LitReviewView`, `StatsView`, `ResearchDigestView`, `DigestView`, `DigestCard`
7. `LoginView`

### Phase 4 — Polish pass
1. Audit: no raw hex values remain outside `tokens.css`
2. Audit: DM Mono applied to all numeric values (scores, dates, counts)
3. Audit: consistent border-radius usage (`--radius` vs `--radius-lg`)
4. Cross-browser check: Chrome, Firefox, Safari
5. Mobile smoke test (existing layout should still function on mobile — Sidebar collapses)

---

## 6. Mobile Consideration

The current app has a mobile layout (`flex lg:hidden`) that shows ArticleList or ReaderView full-screen. The sidebar must not break this.

**Decision:** On mobile (`< lg`), the sidebar is hidden by default (`display: none`). A hamburger button in a mobile topbar toggles it as a full-screen overlay. This is identical to the existing `sidebarOpen` toggle pattern — just rendered differently. No new mobile-specific logic is needed.

---

## 7. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Tailwind token remap causes unexpected class collisions | Medium | Phase 1 verification step — deploy and compare side-by-side |
| Sidebar nav state out of sync with ArticleList filter state | Low | `currentView` and `activeCategory` remain in `App.tsx` — both Sidebar and ArticleList receive them as props |
| DM Sans Google Fonts adds latency | Low | Add `<link rel="preconnect" href="https://fonts.googleapis.com">` to `index.html` |
| SSE connection drops on component remount during shell refactor | Low | `useSSE` hook is in App.tsx — above the shell restructure, unaffected |
| Highlight flow breaks during ReaderView reskin | Low | Highlight logic is in hooks, not JSX — reskin is CSS-only |

---

## 8. What Is Explicitly Not Changed

- `backend/` — zero changes
- `frontend/src/store/` — zero changes  
- `frontend/src/hooks/` — zero changes
- `frontend/src/types.ts` — zero changes
- All API calls, SSE handlers, auth logic
- Keyboard shortcut definitions (remain in `App.tsx`)
- Any feature logic — this is a visual layer only
