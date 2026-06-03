# REVIEW.md — Baṣīra Multi-Tenant SaaS Refactor
## Staff Engineer Code Review · 2026-06-03
### Generated from: OpenCode + Qwen-coder agent output

---

## 1. Executive Summary

**Shippable? NO — two blockers must be resolved first.**

The refactor is structurally sound (~85–90% complete) but two issues prevent production deployment:

| # | Risk | Severity |
|---|------|----------|
| 1 | `articles.ts` — 8 fetch calls missing `credentials: 'include'` — every article interaction silently returns 401 in a real browser | **CRITICAL** |
| 2 | `POST /api/internal/poll/user/{user_id}` missing — Onboarding Step 4 cannot trigger immediate scoring; Journey 1 cannot complete | **CRITICAL** |
| 3 | React Router not implemented (Epic 8.1) — URL routing is still view-state enum; deep-linking broken | **HIGH** |
| 4 | No v1→v2 migration integration test — impossible to verify NFR-T6 (±5% scoring accuracy) | **HIGH** |
| 5 | `prompt_builder.py` cluster ID not sanitized — NFR-T5 violated in edge case | **MEDIUM** |

Core isolation (NFR-T1) is **PASS**. Backward compatibility (NFR-T4) is **PASS**. Auth hardening is **PASS**. The data model and migrations are well-executed.

---

## 2. FR-MT Coverage Matrix

### Epic 1 — User Identity & Auth

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 1.1 Create `organizations` + `users` | FR-MT-1 | **Done** | `database.py:51–104` |
| 1.2 Email+password auth | FR-MT-2 | **Done** | `auth.py:75–100`, `User.authenticate()` at `database.py:95–103` |
| 1.3 `user_id` FK on `auth_sessions` | FR-MT-3 | **Done** | `database.py:148–160`; backfill at migration line 449 |
| 1.4 `POST /auth/register` | FR-MT-4 | **Done** | `routers/auth.py:46–73`; invite_code validated against org |
| 1.5 `GET /auth/me` | FR-MT-5 | **Done** | `routers/auth.py:117–119` |
| 1.6 `require_session()` returns User dict | FR-MT-6 | **Done** | `auth.py:153–179`; returns dict not ORM |
| 1.7 Frontend email+password LoginView | FR-MT-6 | **Done** | `LoginView.tsx:203–234`; register mode at line 9–14 |

**Epic 1 verdict: ✅ DONE (7/7)**

---

### Epic 2 — Data Isolation: Scores & Engagement

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 2.1 `article_scores` table | FR-MT-7 | **Done** | `database.py:162–179`; composite PK `(user_id, article_id)` |
| 2.2 `GET /api/articles` join on `article_scores` | FR-MT-8 | **Done** | `articles.py:145` — filters `ArticleScore.user_id == user_id` |
| 2.3 `GET /api/articles/{id}` user-scoped | FR-MT-8 | **Done** | `articles.py:217` — outerjoin with user_id filter |
| 2.4 Score write → `article_scores` | FR-MT-9 | **Done** | `internal.py:268`; `user_id` in `InternalScoreUpdate` |
| 2.5 Read/bookmark/feedback → `article_scores` | FR-MT-10 | **Done** | `articles.py:246, 290, 367` |
| 2.6 SSE broadcast user-scoped | FR-MT-11 | **Done** | `main.py:297`; filters `_sse_queues` by `user_id` |
| 2.7 `user_id` in ScoreRequest flow | FR-MT-9 | **Done** | `internal.py:218`; score update at `268` |
| **REGRESSION** articles.ts fetch calls | FR-MT-10 | **Regressed** | `store/articles.ts:85,109,144,160,177,210,236,254` — 8 raw `fetch()` missing `credentials:'include'`; all 401 in browser |

**Epic 2 verdict: ⚠️ PARTIAL — backend correct, frontend broken (articles.ts)**

---

### Epic 3 — Feed Subscriptions

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 3.1 `user_feed_subscriptions` table | FR-MT-13 | **Done** | `database.py:181–188`; composite PK `(user_id, feed_id)` |
| 3.2 `GET /api/feeds` returns user subs | FR-MT-14 | **Done** | `feeds.py:20`; join on `user_id` |
| 3.3 `POST/DELETE /api/feeds/{id}/subscribe` | FR-MT-15 | **Done** | `feeds.py:197, 214` |
| 3.4 `GET /api/internal/feeds` with `subscriber_user_ids` | FR-MT-17 | **Done** | `internal.py:86` |
| 3.5 Poller fan-out per subscriber | FR-MT-17 | **Done** | `poller/main.py:81–87`; per-user semaphore dict; fan-out confirmed |
| 3.6 `GET /api/feeds/catalog` | FR-MT-16 | **Done** | `feeds.py:43` |
| 3.7 Frontend FeedManagerPanel subscribe/unsubscribe | FR-MT-15 | **Done** | (confirmed wired to correct endpoints) |

**Epic 3 verdict: ✅ DONE (7/7)**

---

### Epic 4 — TenantConfig & Research Profile

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 4.1 `user_config` table | FR-MT-19 | **Done** | `database.py:190–209`; all fields including prompt_cache |
| 4.2 `user_id` on `research_profile` | FR-MT-23 | **Done** | `database.py:245`; unique `(user_id, kind, label)` |
| 4.3 Research profile endpoints scoped | FR-MT-23 | **Done** | `research.py` — uses `current_user["id"]` |
| 4.4 `_VALID_THESIS_SECTIONS` replaced by DB | FR-MT-22 | **Done** | `profile.py:81` → `get_valid_thesis_sections(db, current_user["id"])` |
| 4.5 `GET/PUT /api/profile/config` | FR-MT-20 | **Done** | `profile.py:133, 142`; invalidates prompt cache on PUT |
| 4.6 `GET/POST/DELETE /api/profile/sections` | FR-MT-22 | **Done** | `profile.py:76, 84, 107` |
| 4.7 Section validation in handler (DB-backed) | FR-MT-22 | **Done** | Handler-level, not Pydantic model |
| 4.8 Frontend ResearchProfileEditor + thesis panel | FR-MT-20 | **Done** | Confirmed in sidebar/settings components |

**Epic 4 verdict: ✅ DONE (8/8)**

---

### Epic 5 — Dynamic Scoring Prompt

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 5.1 `PromptBuilder` in `prompt_builder.py` | FR-MT-28 | **Done** | `scorer/prompt_builder.py:1–111`; `sanitize()` at line 27 |
| 5.2 `ScoreRequest` + `user_context` field | FR-MT-29 | **Done** | `scorer/scorer.py` — `user_context: Optional[...]` |
| 5.3 Scorer branches on `user_context` presence | FR-MT-29 | **Done** | `scorer.py:58–67` `_resolve_system_prompt()` |
| 5.4 Prompt caching in `user_config` | FR-MT-29 | **Done** | `prompt_cache_text`, `prompt_cache_hash` columns; cache built in `_resolve_cached_prompt()` |
| 5.5 API fetches user_config + builds context | FR-MT-30 | **Done** | `internal.py:388` `/api/internal/users/{id}/scoring-context` |
| 5.6 `build_preference_block()` user-scoped | FR-MT-31 | **Done** | `internal.py:116`; accepts `user_id` query param (internal route, protected by X-Internal-Secret) |
| 5.7 Threat scan uses `user_config.thesis_contribution` | FR-MT-35 | **Done** | Reads from `user_config` not singleton table |
| 5.8 `test_prompt_builder.py` exists | FR-MT-28 | **Partial** | File confirmed present; cross-tenant leakage test **not verified** by reading |
| **GAP** Cluster ID (`c["id"]`) not sanitized | NFR-T5 | **Partial** | `prompt_builder.py:95`; `sanitize()` applied to name+desc but NOT `id` field |

**Epic 5 verdict: ⚠️ PARTIAL — 7.5/8; cluster ID sanitization gap + test not audited**

---

### Epic 6 — Highlights / Lit Reviews / Alerts Isolation

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 6.1 `user_id` on `highlights` + endpoints | FR-MT-36 | **Done** | `database.py:226`; `highlights.py:26, 72` filter `user_id` |
| 6.2 `user_id` on `literature_reviews` + endpoints | FR-MT-37 | **Done** | `database.py:262` |
| 6.3 `user_id` on `novelty_alerts` + threat scan | FR-MT-38 | **Done** | `database.py:298`; unique `(article_id, user_id)` |
| 6.4 `user_id` on `tracked_authors` | FR-MT-39 | **Partial** | `database.py:320` — `user_id` **nullable=True** ⚠️ (all others non-nullable); could produce orphaned rows |
| 6.5 `user_settings` + migrate from global `settings` | FR-MT-38 | **Done** | `database.py:211–219`; backfill to `user_id=1` |
| 6.6 `thesis_contribution` → `user_config` | FR-MT-35 | **Done** | Reads/writes `user_config.thesis_contribution`; old singleton deprecated |
| 6.7 Highlights sections from `user_config` | FR-MT-22 | **Done** | `profile.py:81` → `get_valid_thesis_sections()` |

**Epic 6 verdict: ⚠️ PARTIAL — 6.5/7; nullable `user_id` on `tracked_authors` is a schema defect**

---

### Epic 7 — ChromaDB Tenant Scoping

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 7.1 `_get_chroma(user_id)` → `articles_u{id}` | FR-MT-40 | **Done** | `embedder.py:29–45`; `f"articles_u{user_id}"` |
| 7.2 `embed_article_async(user_id, ...)` | FR-MT-41 | **Done** | `embedder.py:93`; writes to user collection |
| 7.3 All Chroma queries use user collection | FR-MT-42 | **Done** | `articles.py:318` related-articles; `research.py` clusters/litreview |
| 7.4 Migration: re-embed existing → `articles_u1` | FR-MT-43 | **Done** | `admin.py:96` `/api/admin/reindex` endpoint |
| 7.5 `user_id` passed to embedder via score endpoint | FR-MT-41 | **Done** | `internal.py` score handler passes `user_id` |

**Epic 7 verdict: ✅ DONE (5/5)**

---

### Epic 8 — Frontend Multi-User

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 8.1 React Router v6 | FR-MT-44 | **Missing** | `App.tsx:79` — still `useState<'feed'\|'digest'\|...>`; no React Router import anywhere |
| 8.2 `apiClient.ts` centralized | FR-MT-45 | **Done** | `apiClient.ts:42` `credentials:'include'`; `handleResponse()`:24 global 401→redirect |
| 8.3 `useCurrentUser` hook + `UserContext` | FR-MT-46 | **Done** | `UserContext.tsx:27` calls `apiClient.get('/auth/me')` |
| 8.4 Dynamic user in Sidebar | FR-MT-46 | **Done** | `Sidebar.tsx:184` — `{user?.display_name ?? 'User'}`; no hardcoded "AF"/"Arona" |
| 8.5 TS types: User, Org, TenantConfig, ScoringCluster | FR-MT-46 | **Done** | `types.ts:46–91`; all 4 types present |
| 8.6 `OnboardingFlow` component | FR-MT-49 | **Done** | `OnboardingWizard.tsx` with STEPS=['Thesis','Clusters','Feeds','First run'] |
| 8.7 Admin page — org members + feed catalog | FR-MT-47 | **Done** | `AdminPage` checks `user?.role === 'admin'`; backed by `admin.py:116` |
| **Regression** articles.ts raw fetch | FR-MT-10 | **Broken** | 8 fetch() calls bypass `apiClient`; `credentials:'include'` missing → 401 in browser |

**Epic 8 verdict: ❌ PARTIAL — 6/7; React Router missing; articles.ts broken**

---

### Epic 9 — Onboarding Wizard

| Story | FR | Status | Evidence |
|-------|----|--------|----------|
| 9.1 Step 1 — Thesis Setup → backend persist | FR-MT-49 | **Done** | `OnboardingWizard.tsx:253–286`; posts to `/api/onboarding/step1` → `onboarding.py:98` → writes `user_config` |
| 9.2 Step 2 — Cluster Builder with templates | FR-MT-50 | **Done** | `OnboardingWizard.tsx:288–338`; templates endpoint `onboarding.py:122` (NLP/AI, SE, Robotics, CV, General CS — hardcoded) |
| 9.3 Step 3 — Feed Selection | FR-MT-51 | **Done** | `OnboardingWizard.tsx:340–398`; uses `/api/feeds/catalog` + `/api/feeds/{id}/subscribe` |
| 9.4 Step 4 — First Run → SSE + preview | FR-MT-51 | **Broken** | `OnboardingWizard.tsx:175`; calls `/api/poll/trigger` (exists) but polls `/api/onboarding/preview` every 5s with 45s timeout — the **immediate per-user poll endpoint (`/api/internal/poll/user/{id}`) is missing from poller** |
| 9.5 `POST /api/internal/poll/user/{user_id}` | FR-MT-51 | **Missing** | Not in `poll.py`, not in `poller/main.py`; `poll.py:15` only exposes `POST /api/poll/trigger` with no `user_id` |
| 9.6 `POST /api/onboarding/complete` → `onboarding_done=1` | FR-MT-52 | **Done** | `onboarding.py:190` sets `onboarding_done=1` |
| 9.7 Cluster templates predefined | FR-MT-50 | **Done** | `onboarding.py:22–49`; 5 templates hardcoded (acceptable v1 scope) |

**Epic 9 verdict: ⚠️ PARTIAL — 5/7; Step 4 broken due to missing endpoint; Journey 1 cannot complete**

---

## 3. NFR-T1–T6 Verdicts

### NFR-T1 — Data Isolation: PASS ✅

**Method:** Spot-checked all major handler files for `user_id` filter presence.

| Table | Handler | Filter | Verdict |
|-------|---------|--------|---------|
| `article_scores` | `articles.py:145` | `ArticleScore.user_id == user_id` from `require_session` | ✅ |
| `user_feed_subscriptions` | `feeds.py:28` | `UserFeedSubscription.user_id == current_user["id"]` | ✅ |
| `research_profile` | `research.py` | `current_user["id"]` used consistently | ✅ |
| `highlights` | `highlights.py:26, 72` | `Highlight.user_id == current_user["id"]` | ✅ |
| `literature_reviews` | `research.py` | scoped to current_user | ✅ |
| `novelty_alerts` | `research.py` | `NoveltyAlert.user_id == user_id` | ✅ |
| `user_config` | `profile.py` | `UserConfig.user_id == current_user["id"]` | ✅ |

**IDOR check:** No endpoint on non-internal routes accepts `user_id` from URL path, query string, or body. Internal routes (`/api/internal/*`) accept `user_id` query param but are gated by `X-Internal-Secret` header — acceptable. No IDOR found.

**Legacy fallback:** `auth.py:161–162` — `user_id = 1` fallback for legacy sessions with NULL `user_id`. This is safe: only applies to pre-existing DB sessions, not exploitable via new requests.

---

### NFR-T2 — Scale / SQLite Concurrency: PASS ✅

Per-user semaphore confirmed in `poller/main.py:81–87`:
```python
_score_semaphores: dict[int, asyncio.Semaphore] = {}

def _get_or_create_semaphore(user_id: int) -> asyncio.Semaphore:
    if user_id not in _score_semaphores:
        _score_semaphores[user_id] = asyncio.Semaphore(1)
    return _score_semaphores[user_id]
```
Users score in parallel; not serialized globally. Meets NFR-T2.

---

### NFR-T3 — Time-to-Value < 8 min: FAIL ❌

Onboarding Step 4 triggers `/api/poll/trigger` then polls `/api/onboarding/preview` every 5s (45s timeout). The issue: `/api/poll/trigger` is a **global trigger** — it triggers polling for ALL active feeds globally, not per-user. The missing `POST /api/internal/poll/user/{user_id}` would have triggered a targeted per-user poll. Without it, a new user with 0 articles in their account has to wait for the global poll cycle to happen to coincide (up to 720 minutes by default). The 45s Step 4 timeout will always expire without showing articles for a brand-new user.

**Verdict: Journey 1 is broken end-to-end.**

---

### NFR-T4 — Backward Compatibility: PASS ✅

| Check | Result |
|-------|--------|
| `PROMPT_PROFILE=infra` fallback | `scorer.py:58–67` — when `user_context=None`, uses static `SYSTEM_PROMPT` loaded from file | ✅ |
| `AUTH_PASSWORD` → seed user_id=1 | `database.py:357–386` `_seed_default_user()` — creates user if table empty | ✅ |
| Migrations additive-only | No `DROP COLUMN`, no `ALTER ... MODIFY` found | ✅ |
| Backfill to user_id=1 | All 8 backfill functions present and idempotent | ✅ |
| `init_db()` idempotent | `try/except` pattern on all `ALTER TABLE` statements | ✅ |

---

### NFR-T5 — Prompt Isolation: PARTIAL ⚠️

`sanitize()` function at `prompt_builder.py:27` strips control chars, newlines, CR from user strings. Applied to: `thesis_title` (line 68), `thesis_question` (line 70), cluster `name` (line 91), cluster `description` (line 92). However, `c.get("id", "?")` at line 95 is the cluster ID, passed into the prompt template WITHOUT sanitization.

In normal flow cluster IDs are assigned by template, so practical risk is low. But a user who crafts a cluster via the API with a malicious `id` value could inject newlines or control sequences. Sanitization is incomplete per the spec.

**Not a full PASS.**

---

### NFR-T6 — No Regression on V1 Scoring: UNKNOWN ❓

No integration test found that:
1. Deploys v2 schema onto a v1 SQLite DB
2. Rescores a known set of articles with `PROMPT_PROFILE=infra`
3. Asserts score deltas ≤ ±5%

The fallback path (`scorer.py:58–67`) exists but is unverified by running. Cannot claim PASS without a test.

---

## 4. Findings List

### FINDING-01 — CRITICAL
**Title:** `articles.ts` — 8 fetch calls missing `credentials: 'include'`  
**File:** `frontend/src/store/articles.ts:85, 109, 144, 160, 177, 210, 236, 254`  
**What's wrong:** Every API call in the articles store uses raw `fetch()` without `credentials: 'include'`. The session cookie (HttpOnly) is not sent on these requests. In a real browser with cross-origin rules, all article operations return 401. The `apiClient.ts` exists and correctly sets credentials, but `articles.ts` does not use it.  
**How to reproduce:** Log in, open Network tab, click any article → observe 401 on `GET /api/articles/{id}`.  
**Fix direction:** Replace all raw `fetch()` in `articles.ts` with `apiClient.get/post/del()` calls, or at minimum add `credentials: 'include'` to every fetch options object.

---

### FINDING-02 — CRITICAL
**Title:** Missing `POST /api/internal/poll/user/{user_id}` — Onboarding Step 4 non-functional  
**File:** `backend/api/routers/poll.py` (endpoint does not exist); `backend/poller/main.py` (no user-scoped trigger)  
**What's wrong:** `OnboardingWizard.tsx:175` calls `/api/poll/trigger` (global trigger) and polls `/api/onboarding/preview` every 5s for 45s. For a brand-new user, the global trigger fires polling for all feeds but with a 720-min default interval the 45s preview window reliably expires empty. The missing endpoint would have triggered a targeted per-user poll immediately.  
**How to reproduce:** Register new account, complete onboarding steps 1–3, reach Step 4 — see "No articles yet" for 45 seconds then wizard times out.  
**Fix direction:** Add `POST /api/internal/poll/user/{user_id}` to `poll.py` that triggers an immediate per-user feed poll. In the poller, handle a targeted poll that only processes feeds subscribed by `user_id` and queues those score requests.

---

### FINDING-03 — HIGH
**Title:** React Router not implemented — Epic 8.1 missing  
**File:** `frontend/src/App.tsx:79`  
**What's wrong:** `App.tsx` uses `useState<'feed' | 'digest' | 'stats' | ...>` for all navigation. No `react-router-dom` import exists anywhere in `frontend/src/`. URL routing is entirely absent — navigating directly to any view shows the default feed, back/forward buttons don't work.  
**Fix direction:** Install `react-router-dom`, replace view-state with `<Routes>/<Route>`, add route definitions for all views + auth flow.

---

### FINDING-04 — HIGH
**Title:** `tracked_authors.user_id` is nullable — schema defect  
**File:** `backend/api/database.py:320`  
**What's wrong:** `user_id = Column(Integer, nullable=True)` on `TrackedAuthor`. Every other user-scoped table uses `nullable=False`. This allows orphaned rows with `NULL` user_id that could be silently excluded or returned to all users depending on query filter logic.  
**Fix direction:** Change to `nullable=False`, ensure the backfill covers all rows. Verify the query in `research.py` filters `user_id == current_user["id"]` and doesn't accidentally fetch NULL rows.

---

### FINDING-05 — HIGH
**Title:** No v1→v2 migration integration test — NFR-T6 unverifiable  
**File:** `backend/scorer/tests/` (no test found)  
**What's wrong:** NFR-T6 requires ±5% scoring accuracy after migration. No integration test exists that applies the v2 migration to a v1 DB fixture, rescores a known article set, and asserts score delta. The fallback path in `scorer.py:58–67` is only verified by reading code, not by running.  
**Fix direction:** Create `tests/test_migration_compat.py` that loads a v1 DB fixture, runs `init_db()`, rescores 20 known articles with `PROMPT_PROFILE=infra`, and asserts scores are within ±5% of the pre-migration run.

---

### FINDING-06 — MEDIUM
**Title:** `prompt_builder.py` — cluster `id` field not sanitized  
**File:** `backend/scorer/prompt_builder.py:95`  
**What's wrong:** `sanitize()` is applied to `cluster["name"]` and `cluster["description"]` but `cluster["id"]` is embedded in the rendered prompt without sanitization. A user crafting a custom cluster via `PUT /api/profile/config` with a malicious `id` value could inject control sequences.  
**Fix direction:** Add `sanitize(c.get("id", "?"))` alongside the name/desc sanitization.

---

### FINDING-07 — MEDIUM
**Title:** Swallowed JSON parse errors in `research.py` — 3 silent `except: pass` blocks  
**File:** `backend/api/routers/research.py:116–130`  
**What's wrong:** `_build_cluster_user_block()` has three `except Exception: pass` blocks for JSON parsing of `score_meta_json`, `paper_meta_json`, and `tags_json`. Fields silently default to empty values with no log output — impossible to detect malformed data in production.  
**Fix direction:** Change to `except Exception: logger.warning(...)` at minimum.

---

### FINDING-08 — MEDIUM
**Title:** `research.ts` and `highlights.ts` — inconsistent API client usage  
**File:** `frontend/src/store/research.ts:54, 77`; `frontend/src/store/highlights.ts:33, 40`  
**What's wrong:** Both stores use raw `fetch(..., { credentials: 'include' })` correctly but bypass the centralized `apiClient` and its global 401 handler. If a session expires mid-session, these operations won't redirect to login.  
**Fix direction:** Migrate to `apiClient.get/post/del()`. Lower priority than articles.ts since credentials are at least present.

---

### FINDING-09 — LOW
**Title:** Onboarding cluster templates hardcoded in Python — not DB-driven  
**File:** `backend/api/routers/onboarding.py:22–49`  
**What's wrong:** The 5 cluster templates (NLP/AI, SE, Robotics, CV, General CS) are a hardcoded Python list. Updating templates requires a code deploy.  
**Fix direction:** Track as v2 work item. Move templates to a `cluster_templates` DB table or config file.

---

### FINDING-10 — LOW
**Title:** Seed user creation potential race condition on first boot  
**File:** `backend/api/database.py:357–386`  
**What's wrong:** `_seed_default_user()` reads `db.query(User).count()` then creates the user if count==0. Two concurrent `init_db()` calls could both observe count==0 and both attempt to insert user_id=1; the second fails with IntegrityError (silently caught). Non-issue for single-container deploy.  
**Fix direction:** Acceptable as-is for single-container. If scaling to multiple API replicas, use `INSERT OR IGNORE` semantics.

---

## 5. Three End-to-End Workflow Traces

### Workflow A: Register → Onboarding → First Scored Article

**Code path:**
1. `POST /auth/register` → `routers/auth.py:46` → creates User row, seeds `user_config` via `_backfill_user_config()` → sets session cookie ✅
2. App renders `OnboardingWizard` (since `onboarding_done=0`) ✅
3. Step 1: POST `/api/onboarding/step1` → `onboarding.py:98` → writes `thesis_title`, `thesis_question` to `user_config` ✅
4. Step 2: POST `/api/onboarding/step2` → `onboarding.py:130` → writes `scoring_clusters_json` to `user_config` ✅
5. Step 3: User subscribes to feeds via `/api/feeds/{id}/subscribe` → `feeds.py:197` → inserts `user_feed_subscriptions` rows ✅
6. Step 4: `OnboardingWizard.tsx:175` → POST `/api/poll/trigger` (global) → ❌ **BROKEN** — 45s timeout expires before articles scored for fresh user; per-user poll endpoint missing
7. `POST /api/onboarding/complete` → never fires; wizard cannot complete ❌

**VERDICT: BROKEN** at Step 4. Two issues compound: missing per-user poll endpoint, and 45s timeout too short for fresh LLM scoring (3–10s per article).

---

### Workflow B: Lab Admin Invites User → User Scoped to Org

**Code path:**
1. Admin creates org; `Organization` row exists with `code` (invite code) ✅
2. Admin calls `POST /api/admin/org/invite-code` → `admin.py:171` → regenerates `org.code` ✅
3. New researcher registers with email + password + invite_code ✅
4. `POST /auth/register` → `routers/auth.py:46–73` → looks up `Organization` by `code` → sets `user.org_id = org.id` ✅
5. `require_session` returns `org_id` in user dict ✅
6. New user's data isolated by `user_id`; org_id is metadata only (no cross-user sharing within org, per v1 scope) ✅

**VERDICT: WORKS** — invite code registration correctly scopes user to org.

---

### Workflow C: Existing Single-User DB Upgrade → Seed user_id=1 Sees Identical Data

**Code path:**
1. Deploy new Docker image on existing v1 DB (`/data/basira.db`)
2. `init_db()` → all `try/except ALTER TABLE` migrations execute: creates `organizations`, `users` tables; adds `user_id` columns to 5 tables; creates `article_scores`, `user_feed_subscriptions`, `user_config`, `user_settings` ✅
3. `_seed_default_user()` → `AUTH_PASSWORD` set, users table empty → creates user_id=1 ✅
4. All 8 `_backfill_*()` functions run → assign `user_id=1` to all existing rows ✅
5. `_backfill_article_scores()` → copies `score`, `read_at`, `bookmarked`, `user_feedback` from `articles` columns to `article_scores` for user_id=1 ✅
6. `_backfill_subscriptions()` → subscribes user_id=1 to all existing active feeds ✅
7. Existing session cookies: `auth_sessions.user_id` is NULL → `require_session` fallback at `auth.py:162` → `user_id = 1` ✅
8. `GET /api/articles` → joins `article_scores` where `user_id=1` → returns same articles as before ✅

**VERDICT: WORKS** — migration is clean and idempotent. Existing user sees identical data. Existing session cookies remain valid.

---

## 6. Prioritized Remediation Backlog

| Priority | ID | Story | Severity | Effort |
|----------|-----|-------|----------|--------|
| 1 | FIND-01 | Add `credentials:'include'` to all fetch() in `articles.ts` (or migrate to apiClient) | Critical | S — 30 min |
| 2 | FIND-02 | Implement `POST /api/internal/poll/user/{user_id}` in poll.py + poller user-scoped trigger | Critical | M — 2–4 h |
| 3 | FIND-02 | Increase onboarding Step 4 timeout from 45s → 120s + show per-article progress | Critical | S — 30 min |
| 4 | FIND-03 | Add React Router v6 — replace view-state with URL routes (Epic 8.1) | High | L — 1 day |
| 5 | FIND-04 | Fix `tracked_authors.user_id nullable=True` → `nullable=False` + verify query filter | High | S — 1 h |
| 6 | FIND-05 | Write `test_migration_compat.py` — v1 DB fixture → v2 migration → assert score ±5% | High | M — 3 h |
| 7 | FIND-08 | Migrate `research.ts` and `highlights.ts` to centralized `apiClient` | Medium | S — 2 h |
| 8 | FIND-06 | Sanitize `cluster["id"]` in `prompt_builder.py:95` | Medium | XS — 15 min |
| 9 | FIND-07 | Replace `except Exception: pass` with `except Exception: logger.warning(...)` in `research.py:116–130` | Medium | S — 30 min |
| 10 | FIND-10 | Add cross-tenant leakage assertion to `test_prompt_builder.py` | Medium | S — 1 h |
| 11 | FIND-09 | Track onboarding templates as v2: move to DB/config file | Low | L — deferred |

---

## Appendix: Silent Failures & Fake Implementation Sweep

**Grep results (backend):**
- `# TODO`: 0 hits in routers
- `raise NotImplementedError`: 0 hits
- `return []` as stub: 0 confirmed stubs (all fault-isolation patterns, properly logged)
- `except: pass` silently: 3 hits in `research.py:116–130` (classified Medium above)
- `print(` in production code: 1 hit at `database.py:383` (startup logging — acceptable)

**Dead/unwired code:**
- All routers in `main.py:13–25` registered via `include_router` ✅
- `OnboardingWizard` wired in `App.tsx` behind `onboarding_done === 0` gate ✅
- `AdminPage` wired behind `role === 'admin'` gate ✅

**Frontend↔API contract drift:**
- `UserInfo` type (`types.ts:46`) matches `/auth/me` response dict from `auth.py:168–176` ✅
- `TenantConfig` type (`types.ts:79–91`) — `model_preference` field matches API ✅
- `Organization` type (`types.ts:64–68`) has `members` array — `admin.py:116` returns members list ✅
- `ScoringCluster` type (`types.ts:70–77`) — fields `name`, `reward`, `weight`, `desc` ⚠️ **potential mismatch**: frontend uses `reward`, PRD spec and `prompt_builder.py` use `reward_level`. Verify `user_config.scoring_clusters_json` key name — if they differ, PromptBuilder will silently ignore the field.
