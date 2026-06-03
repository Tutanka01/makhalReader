# Baṣīra — Multi-Tenant Refactor Rules (NON-NEGOTIABLE)

## Context
We are converting a single-tenant, self-hosted literature monitor into a multi-tenant SaaS.
Read these before any task and treat them as the spec:
- `_bmad-output/planning-artifacts/prd-saas-multitenant.md`  (the multi-tenant PRD — FR-MT-* and NFR-T*)
- `_bmad-output/planning-artifacts/architecture.md`          (stack + structure rules)
- `basira-multitenant-prototype.html`                        (UI/UX reference for frontend stories)

Stack is fixed: Python 3.12 / FastAPI / SQLAlchemy / SQLite WAL, React 18 / TS / Vite / Tailwind / Zustand,
6-service Docker Compose. Do NOT rewrite the stack, do NOT add Postgres, do NOT add new containers.

## Golden rules
1. ADDITIVE-ONLY MIGRATIONS. All schema changes go through the existing try/except ALTER TABLE pattern in init_db(). Re-running init_db() must be idempotent (no error, no data loss).
2. ALL new user-scoped columns are NULLABLE first, then backfilled to user_id=1 (the seed user), then used. Never NOT NULL against existing rows.
3. NEVER break backward compat. PROMPT_PROFILE=infra must keep producing v1-identical scores. AUTH_PASSWORD must auto-create user_id=1 when the users table is empty. Deploy on an existing DB must need ZERO manual steps (NFR-T4).
4. ISOLATION (NFR-T1). Every query on a user-scoped table MUST filter on user_id = current_user.id. The user_id comes ONLY from the require_session dependency — NEVER from a URL param, query string, or request body.
5. ONE ROUTER PER FILE. Any new route lives in backend/api/routers/*.py. main.py is the app factory + auth only. No new route in main.py.
6. FAULT ISOLATION. One user's poll/score failure must never block another user. Wrap all new I/O in try/except with graceful degradation.
7. PROMPT SANITIZATION (NFR-T5). PromptBuilder sanitizes every user string (thesis, cluster names, venues) before interpolation. No user A content may ever appear in user B's prompt.

## Definition of Done (every story)
- Code compiles / type-checks (mypy for Python, tsc for TS).
- New behavior covered by a test (pytest for backend, vitest/RTL for frontend where relevant).
- Existing tests still pass.
- For any data change: a backward-compat check (load existing DB → user_id=1 sees identical data).
- A conventional commit: `feat(mt): <epic>.<story> <short summary>` referencing the FR-MT IDs.

## Workflow you must follow for EVERY story
1. Restate the story (Gherkin) and the FR-MT IDs it satisfies.
2. List the exact files you will touch (match architecture.md structure).
3. Show a short plan and WAIT for my "go" before editing.
4. Implement the smallest vertical slice.
5. Write/extend tests; run them; paste the output.
6. Run the backward-compat / isolation check relevant to the story.
7. Summarize the diff and the commit message. Then stop and wait for the next story.
