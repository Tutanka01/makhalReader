---
title: "Product Brief: Baṣīra — Frontend Redesign (ProjectOS Design Language)"
status: "draft"
created: "2026-05-18"
updated: "2026-05-18"
inputs:
  - "plateforme-projets (1).html"
  - "ProjectOS_CahierDesCharges.md"
  - "frontend/src/App.tsx"
  - "frontend/src/types.ts"
  - "frontend/src/components/* (all 21 components)"
  - "_bmad-output/planning-artifacts/product-brief-daily_news_wrap.md"
  - "_bmad-output/planning-artifacts/architecture.md"
scope: "frontend-only redesign — zero backend changes"
---

# Product Brief: Baṣīra — Frontend Redesign

## The Problem

Baṣīra's backend is now production-grade: research-aware scoring, semantic retrieval, lit-review synthesis, highlight annotations, SSE real-time delivery. The frontend hasn't kept pace. The current UI is functional but rough — a collapsible 380px panel masquerading as a sidebar, view-switching buried inside a list component, Tailwind utility classes stacked ad hoc without a coherent visual language. The result is an interface that undersells everything the system can do.

**Concretely:**
- The layout feels like a dev prototype — no persistent navigation, no topbar, no visual hierarchy between "I am reading a paper" and "I am exploring my library."
- Score badges, contrib-type chips, and RE-doc badges are each styled independently. Nothing feels like it belongs to the same design system.
- The stats view, lit-review mode, and digest view have no structural consistency with the article list — each is a one-off panel.
- The research profile editor and feed manager open as overlays, but their internal design is inconsistent with the rest of the app.

The fix isn't a rewrite — it's a skin: a coherent design token system, a proper app shell, and consistent component patterns applied uniformly to the 21 components already in the codebase.

## The Solution

Apply the **ProjectOS design language** — extracted from `plateforme-projets (1).html` — as a design token layer across the full Baṣīra frontend. This is a brownfield reskin, not a redesign from scratch.

**What ProjectOS brings to Baṣīra:**

| Pattern | ProjectOS Source | Baṣīra Application |
|---|---|---|
| Warm-white color palette | `--bg: #FFFFFF`, `--bg-secondary: #F7F6F3`, `--sidebar-bg: #FBFAF8` | Replace current `bg-bg-base/surface/elevated` token set |
| DM Sans + DM Mono typography | `font-family: 'DM Sans'` + `'DM Mono'` for numbers | Article titles, scores, publication dates |
| Fixed 240px sidebar with nav sections | `.sidebar` → `.sidebar-section` → `.nav-item` | App-level nav: Feed · Digest · Lit Review · Stats + feed categories with unread counts |
| Breadcrumb topbar + action area | `.topbar` with `.breadcrumb` + `.topbar-actions` | Persistent topbar across all views, with search + sidebar toggle |
| Stat cards (4-col grid) | `.stats-row` → `.stat-card` | Stats view: total read, unread, bookmarks, streak |
| Pill badges with semantic colors | `.pill-green/.pill-orange/.pill-red` | Score tier, contrib type, RE doc type — unified badge system |
| Slide-in detail panels | `.doverlay` + `.dpanel` + `@keyframes si` | Feed manager, research profile editor, related articles panel |
| Clean table rows with hover | `.project-table` | Article list (compact table mode) |
| Tag chips | `.tag`, `.tag-client`, `.tag-perso` | Feed category chips, contribution type chips |
| Minimal progress bars (5px) | `.pbar` + `.pfill` | Score bar, reading progress |
| Monospace for numbers | `font-family: 'DM Mono'` | All numeric values: scores, dates, counts |
| Section headers + "View all" | `.section-hd` + `.section-title` | List section headers throughout the app |

## Scope — Features In, Features Out

This brief covers exactly the features currently built and in the codebase. Nothing new is added.

### Views to redesign

| View / Component | Current State | Redesign Target |
|---|---|---|
| **App shell** (App.tsx) | Flex row: 380px list + reader | Fixed 240px sidebar + topbar + content area |
| **Sidebar nav** | Embedded in ArticleList | Standalone `Sidebar.tsx` — Feed / Digest / Lit Review / Stats + feed sections |
| **ArticleList** | Left panel, owns nav | Becomes pure list — receives `currentView` prop, renders articles |
| **ArticleCard** | Dense card with Tailwind utilities | Clean table row or card following ProjectOS `.kcard` / `.project-table tr` pattern |
| **ReaderView** | Full-right panel, own topbar | Keep layout, reskin topbar to match app topbar style |
| **AskAIPanel** | Chat panel, ad hoc style | Reskin to ProjectOS surface + border tokens |
| **HighlightPopover / HighlightList** | Functional, unstyled | Apply pill + card tokens |
| **FeedManagerPanel** | Slide-in overlay | Match `.doverlay` + `.dpanel` slide-in pattern exactly |
| **ResearchProfileEditor** | Slide-in overlay | Same as FeedManagerPanel |
| **RelatedPanel** | Right panel | Reskin as `.dpanel`-style with `.kcard` article entries |
| **LitReviewView** | Standalone view | Apply `.page` layout + stat cards for cluster summary |
| **StatsView** | Standalone view | Apply `.stats-row` 4-col grid + section tables |
| **ResearchDigestView / DigestCard** | Standalone, ad hoc | Apply `.kcard` + `.stat-card` pattern |
| **CategoryTabs** | Horizontal tab bar | Replace with sidebar nav-item rows (unread counts as `.nav-count`) |
| **ScoreBar** | Custom bar | Adopt `.pbar` + `.pfill` (5px, accent color) |
| **ContribTypeBadge / ReDocTypeBadge** | Independent chips | Unify to `.tag` / `.pill` system with ProjectOS semantic colors |
| **LoginView** | Centered form | Apply surface + border tokens, DM Sans typography |
| **OfflineBanner** | Top banner | Apply `.alert-orange` pattern |

### Explicitly out of scope

- Backend changes of any kind
- New features (no new views, no new API calls)
- Mobile layout overhaul (responsive tweaks are acceptable, mobile-first is not the goal)
- Dark mode (ProjectOS is light-only; Baṣīra dark mode is deferred)

## Design Token Specification

The complete ProjectOS CSS variable set, renamed for the Baṣīra codebase:

```css
:root {
  /* Backgrounds */
  --bg:           #FFFFFF;
  --bg-secondary: #F7F6F3;   /* warm off-white — card surfaces, table headers */
  --bg-hover:     #EFEFED;   /* interactive hover */
  --bg-active:    #E8E7E3;   /* active / selected state */
  --sidebar-bg:   #FBFAF8;   /* sidebar background */

  /* Borders */
  --border:       #E8E6E1;
  --border-strong:#D4D0C8;

  /* Text */
  --text:         #191919;   /* near-black — primary */
  --text-secondary:#6B6B6B;
  --text-muted:   #9B9B9B;

  /* Accent */
  --accent:       #2F6FED;
  --accent-light: #EBF1FD;

  /* Semantic */
  --success:      #0F7B6C;  --success-bg: #E3F5F2;
  --warning:      #B45309;  --warning-bg: #FEF3C7;
  --danger:       #C0392B;  --danger-bg:  #FDECEA;
  --purple:       #6B4FBB;  --purple-bg:  #EDE9FF;

  /* Layout */
  --sidebar-w:    240px;
  --header-h:     48px;
  --radius:       6px;
  --radius-lg:    10px;

  /* Shadows */
  --shadow:    0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,.08), 0 2px 4px rgba(0,0,0,.04);
}
```

**Typography:**
- Body: `'DM Sans', sans-serif` — 14px base, `-webkit-font-smoothing: antialiased`
- Monospace (scores, dates, counts): `'DM Mono', monospace`
- Google Fonts import: `DM Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600` + `DM Mono:wght@400;500`

## New App Shell Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Sidebar (240px fixed)          │  Main (flex-1)               │
│  ─────────────────────────────  │  ─────────────────────────── │
│  [◉ Baṣīra]              [beta] │  topbar (48px)               │
│                                 │  [breadcrumb]   [search][btn]│
│  PRINCIPAL                      │  ─────────────────────────── │
│  ◻ Feed               [14]      │                              │
│  ◻ Digest                       │  content area (flex-1 scroll)│
│  ◻ Lit Review                   │                              │
│  ◻ Stats                        │  ← ArticleList               │
│                                 │  ← ReaderView (replaces list)│
│  ──────────────────────────     │  ← LitReviewView             │
│                                 │  ← StatsView                 │
│  FEEDS                          │  ← ResearchDigestView        │
│  · AI/ML                [8]     │                              │
│  · Requirements Eng.    [3]     │                              │
│  · Systems Engineering  [5]     │                              │
│  · Blogs                [2]     │                              │
│                                 │                              │
│  ──────────────────────────     │                              │
│  [AF] Arona · Admin     [⋯]     │                              │
└─────────────────────────────────────────────────────────────────┘

Slide-in panels (right, overlay):
  FeedManagerPanel → 510px .dpanel
  ResearchProfileEditor → 510px .dpanel
  RelatedPanel → 400px .dpanel
```

## Colour Semantics for Baṣīra-Specific Elements

| Element | Color Token | Rationale |
|---|---|---|
| Score ≥ 8 (high) | `--success` / `--success-bg` | Positive signal |
| Score 6–7 (medium) | `--accent` / `--accent-light` | Neutral positive |
| Score ≤ 5 (low) | `--text-muted` / `--bg-active` | Suppressed |
| `contribution_type: method` | `--accent` | Methodological contribution |
| `contribution_type: survey/benchmark` | `--purple` | Synthesis work |
| `contribution_type: tool/tutorial` | `--success` | Practical value |
| `contribution_type: news/other` | `--text-muted` | Low signal |
| `re_document_type: elicitation/extraction/method` | `--warning` (ARISE-flagged) | Actionable for pipeline |
| Bookmarked | `--purple` star icon | Saved |
| Unread | Bold title + `--text` | Default reading state |
| Read | Normal weight + `--text-secondary` | Consumed |

## Success Criteria

| Signal | Target |
|---|---|
| Design token coverage | 100% of Tailwind `bg-bg-*` / `text-text-*` tokens replaced with CSS variables |
| Visual consistency audit | No component uses ad hoc color hex values — all use token variables |
| DM Sans applied everywhere | Zero fallback to system-ui/Inter in production build |
| Slide-in panel animation | All 3 panels use identical `@keyframes si` entry (translateX + opacity) |
| Sidebar nav functional | All 5 views (Feed · Digest · Lit Review · Stats · Reader) reachable from sidebar |
| CategoryTabs replaced | Feed categories render as sidebar nav-item rows with `.nav-count` unread badges |
| No regressions | Existing keyboard shortcuts (j/k/r/b/o/[/?/Esc), SSE updates, highlight flow all functional |
| Load time | No increase vs. baseline (DM Sans via Google Fonts — add `preconnect` hint) |

## What This Is Not

This brief is **not** a request to rebuild Baṣīra. The backend, the AI pipeline, the data model — none of it changes. This is a precision reskin: extract the design tokens and component patterns from a proven HTML prototype, apply them to 21 existing React components, and ship a frontend that looks as good as the intelligence it surfaces.

The ProjectOS template is the design reference, not the specification. Where its patterns don't fit (research badges, SSE indicators, lit-review clusters), we extend the token system coherently rather than forcing a pattern that doesn't belong.
