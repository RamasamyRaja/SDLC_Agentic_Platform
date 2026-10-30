# IMPLEMENTATION_STATUS

Date of verification: 2026-10-15. Everything under B was actually executed in the build sandbox; anything not executed is listed under C.

## A. Completed functionality

**Lifecycle (server-enforced state machine, `workflow_stage` + row-locked compare-and-set transitions)**
Requirement → Architecture plan → Architect plan approval → Implementation → Testing/QA → Merge request → Architect MR review → Deployment. Every transition is written to `workflow_events` with actor and message.

- **Architecture Agent** (`app/workflow/planning.py`): retrieval + reads real repo files; the LLM must give verbatim evidence quotes; quotes, modify/create targets and protected paths are verified programmatically; invalid plans are fed back for a bounded number of rounds, then the plan **fails** rather than being invented. Plan, evidence (files read + sha256), model name and repo commit are persisted.
- **Plan approval gate**: nothing can reach IMPLEMENTING except from an approved plan. Reject / request-revision require a comment, are persisted (`review_decisions`) and feed the next plan version.
- **Development Agent** (`development.py`, `gitops.py`, `fileops.py`): isolated `git worktree` on a new branch `rad/task-<id>-a<attempt>` based on the onboarded commit; edits restricted to plan-scope files; path traversal / symlink / protected-path refusal; changed files and diff come from `git add -A` + `git diff --cached`, not from the model's claims; zero changes → `IMPLEMENTATION_FAILED`. The old direct `modify_file` HTTP path and `execute_changes=True` agent run are closed (409); `agent/engineering.py` was removed.
- **QA** (`qa.py`): fixed per-language check table (no model-generated shell). Statuses PASSED / FAILED / TIMED_OUT / DEPENDENCY_MISSING / BLOCKED / SKIPPED / UNVERIFIED; verdict PASSED / PARTIAL / FAILED / NOT_RUN. A failing or not-run verdict can never read as validated; creating an MR from it needs an explicit `acknowledge_validation_risk`, recorded on the MR. Runners: `docker` (default, hardened) and `local` (opt-in, dev/test only).
- **Commit & MR** (`gitops.py`, `lifecycle.py`): real local commit; separate `status`, `review_status` and `remote_status`. A remote GitHub/GitLab PR/MR is created only if a token is configured and the push succeeds; otherwise the MR is explicitly a **local review record** (`REMOTE_UNAVAILABLE` / `REMOTE_FAILED` with the reason). Token is passed per invocation, never stored or logged. Idempotent.
- **Architect MR review**: approve / reject / request revision, persisted; rejection returns to implementation with the feedback.
- **DevOps deployment** (`deployment.py`): only from `MR_APPROVED` (or retry states), and only if the branch head equals the approved commit; `git archive` artifact with sha256; operator-configured `DEPLOY_COMMAND` (+ optional health check). Not configured → `DEPLOYMENT_UNAVAILABLE`, never "deployed".
- **RBAC (server-side)**: new `ARCHITECT` role and permissions. ADMIN & DEVELOPER create tasks/MRs but cannot approve/reject; ARCHITECT approves/rejects but cannot create tasks/MRs; VIEWER read-only. `/auth/me` and login return `permissions`; the UI uses them. ADMIN is no longer "all permissions".
- **Default-branch discovery fix**: `git ls-remote --symref` HEAD is used at repository creation; an explicit branch is verified on the remote; `default_branch_source` (`remote_head` / `user_specified` / `fallback`) is stored and shown. Onboarding records the actually checked-out branch. Creating a repository neither clones nor indexes it; indexing is a separate state.
- **Reports** (`/tasks/{id}/report`, `/reports`): built from stored evidence; a planning-only run is never reported as implemented; "complete" only when DEPLOYED. Recommendations are labelled model-authored; unverified items and unavailable capabilities are listed.
- **Migrations**: `c4d5e6f7a8b9` (new lifecycle tables/columns) and a fix to the existing `ab12cd34ef56` (it failed on a fresh DB with a duplicate-enum error).
- **Frontend**: task list, create page, and 8-stage detail page (lifecycle timeline, evidence-annotated plan, diff viewer, checks table, MR panel that states local-vs-remote plainly, deployment panel, report, history, polling while an agent runs). Action buttons are rendered **only** from the server's `allowed_actions`. Repository page shows branch source. Settings role selector includes ARCHITECT. There is deliberately no mock/fallback adapter for the lifecycle (`WORKFLOW_PORT`).
- `docs/WORKFLOW_API.md` documents the API contract; `backend/.env.example` (placeholders only) was added.

## B. Verified functionality (real outcomes)

| Check | Command / method | Result |
|---|---|---|
| Backend tests | `pytest tests` (Postgres 16) | **294 passed, 1 skipped** (skipped = real-Mistral smoke test, no API key) |
| of which new | `tests/test_lifecycle.py` (34), `tests/test_default_branch.py` (10) | all pass |
| Compile | `python -m compileall app tests alembic` | OK |
| Migrations | fresh DB `alembic upgrade head` → `alembic check` → `downgrade -1` → `upgrade head` | clean, "No new upgrade operations detected"; legacy rows preserved in an earlier upgrade test |
| Frontend tests | `ng test --watch=false` | **17 passed** (5 files) |
| Frontend build | `ng build` | succeeds |
| **Test A** RBAC | API tests per role + live browser per role | Server rejects forbidden actions (403); UI as DEVELOPER shows "+ New task"; as ARCHITECT/VIEWER no create button and "Not permitted" on `/app/tasks/new`; ARCHITECT `/auth/me` returned exactly the review + read permissions |
| **Test B** branches | local bare remotes with `main`, `master`, `trunk`; live `git ls-remote` on **torvalds/linux** | resolved `main` / `master` / `trunk`; **linux → `master`** (live, network call, nothing cloned). Live API creation of `octocat/Hello-World` recorded `default_branch=master`, source `remote_head`; creation left it `PENDING`/`NOT_INDEXED`; onboarding and indexing were separate calls and ended `READY` / `INDEXED` (0 chunks, README-only repo) |
| **Test C** planning | scripted `FakeLLMProvider` against a real fixture repo | plan references real files, quotes verified, hallucinated paths/quotes rejected, plan persisted |
| **Test D** | tests | implementation blocked before approval (409); reject / revision comment required and persisted |
| **Test E** | tests on a real git fixture | correct file modified, diff matches git, unrelated files untouched, out-of-scope/protected/traversal edits refused, no-change → failure |
| **Test F** | tests (local runner, real pytest in fixture) | passing run → PASSED; deliberately failing test → FAILED and cannot pass; Docker unavailable → BLOCKED |
| **Test G** | tests: real local commit/branch, local bare remote push, **fake local GitHub API** | MR carries actual diff + verdict; remote created / denied / no-token cases recorded precisely; token not leaked into responses/events |
| **Test H** | tests | only ARCHITECT approves/rejects MR; ADMIN/DEVELOPER/VIEWER get 403; decisions persisted |
| **Test I** | tests | deployment blocked before approval; unavailable without `DEPLOY_COMMAND`; success, command failure, health-check failure and tampered-branch cases recorded (local command + local health server) |
| **Test J** | live browser (Playwright/Chromium) against the real backend + built frontend; tests | After refresh the real stage showed (PLAN FAILED, with the true reason "MISTRAL_API_KEY is not configured"); implementation/deployment shown BLOCKED; planning-only report not shown as implemented; action API calls covered by adapter tests |
| **Test K** | all of the above | no regression; legacy suite adapted where it asserted removed behaviour (`modify_file` over HTTP now 409) |

Pre-existing issues found (not caused by this work): the original migration `ab12cd34ef56` failed on a fresh DB; ~59 legacy tests called `get_current_user` with a stale signature (fixed).

## C. Known limitations

1. **No real LLM run.** No `MISTRAL_API_KEY` was available. All plan/implementation behaviour was tested with a scripted fake provider; the real-model quality of plans and edits is **unverified**. The live UI run correctly showed the planning failure.
2. **Docker QA runner not exercised** (no Docker in the sandbox): only command construction and the BLOCKED path were tested. QA results in tests came from the `local` runner (`QA_RUNNER=local`), which runs repo commands on the API host and must not be used for untrusted repos.
3. **Real GitHub/GitLab MR creation not exercised.** Only a local fake provider API and a local bare git remote. Push over HTTPS with a real token is untested.
4. **Linux kernel was not cloned or indexed**; only default-branch discovery (`master`) and the separation of access vs. indexing were verified.
5. **Deployment**: no production infrastructure; only operator-supplied `DEPLOY_COMMAND` against a local test command. Production deployment was **not** tested.
6. LangGraph uses the in-process `MemorySaver`; background work uses FastAPI `BackgroundTasks` (stale-worker recovery exists, but there is no durable queue; a restart interrupts running agents).
7. Visibility is **team-wide** for repositories/tasks (needed so Architects can review others' work); per-repo access control is not implemented.
8. Python-language QA and the other languages in the check table are limited to fixed checks (compile/pytest/npm/maven/gradle/go/cargo); repos needing other toolchains get UNVERIFIED/DEPENDENCY_MISSING rather than a pass.
9. The ZIP contains no `node_modules`; Angular CLI 22 requires Node ≥ 22.22.3 (the sandbox default 22.22.0 was too old, a newer Node was used for build/tests).
10. The older "agent workspace" / analysis pages and legacy task endpoints (`/analyze`, `/run`) remain for compatibility; `/run` can no longer apply changes.

## D. How to run

```bash
# 1. config (no secrets are shipped)
cp backend/.env.example backend/.env      # set AUTH_JWT_SECRET, POSTGRES_PASSWORD, MISTRAL_API_KEY (+ optional GIT_PROVIDER_TOKEN, DEPLOY_COMMAND)

# 2. full stack (Docker Desktop must be running; it also provides the QA sandbox)
docker compose up --build                  # backend http://localhost:8000/docs (runs `alembic upgrade head`)

# 3. frontend (Node >= 22.22.3)
cd frontend && npm ci && npm start         # http://localhost:4200

# Backend without Docker (dev)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg2://USER:PASS@127.0.0.1:5432/ai_swe_agent
alembic upgrade head && uvicorn app.main:app --port 8000

# Tests / build
cd backend && python -m pytest -q          # needs the Postgres from DATABASE_URL; set QA_RUNNER=local only for dev
cd frontend && npm test -- --watch=false && npm run build
```
First registered user becomes ADMIN; an ADMIN assigns `ARCHITECT` in Settings.

## E. Workflow verification

- **Exercised end-to-end through the real API + real git + real DB (with scripted LLM)**: create task → plan → Architect approve → implement on isolated branch → QA → commit + MR → Architect approve → deploy (local command). Also the rejection loops, failure branches and all RBAC denials. Covered in `tests/test_lifecycle.py`.
- **Exercised end-to-end through the real UI + real backend**: login per role, repository with discovered `master` branch, task creation, lifecycle display, honest failure at planning (no LLM key), role-specific action visibility.
- **Verified only in isolation**: remote PR creation (fake provider), Docker QA runner (not run), deployment (local command), real LLM output.
- **Not verified**: any run with a real Mistral key, real GitHub/GitLab, Docker sandbox, real deployment target.

## F. Remaining work

1. Run the full flow once with a real `MISTRAL_API_KEY`, Docker, and a real GitHub token on a throwaway repo; tune prompts from real outputs.
2. Durable job queue (e.g. Celery/RQ) and a persistent LangGraph checkpointer.
3. Per-repository access control if team-wide visibility is not wanted.
4. Playwright/Cypress E2E suite committed to the repo (the browser check here was ad hoc and is not included).
5. Streaming progress (SSE/WebSocket) instead of 2 s polling; pagination for large task lists.
6. Real deployment targets / adapters beyond the generic `DEPLOY_COMMAND`.
7. Indexing a very large repository (Linux) needs sizing/limits and a background indexing job with progress.
