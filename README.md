# RAD AI Agent — Final Integrated Package

This is the consolidated RAD AI Agent package: M7 repository intelligence + RBAC + real Code Explorer + engineering agent loop + Docker sandbox + bounded QA/repair + execution/report telemetry.

## What is included

- FastAPI + PostgreSQL + Alembic
- JWT authentication and ADMIN / DEVELOPER / ARCHITECT / VIEWER RBAC
- GitHub repository onboarding
- Tree-sitter structural analysis
- Semantic chunking + Milvus Lite retrieval
- Mistral reasoning
- LangGraph orchestration
- Safe repository tools: read/search/structure/modify/diff
- Real repository file-content API for Code Explorer
- Docker sandbox with network isolation, resource limits and timeouts
- Bounded validation and repair loop
- Execution telemetry, validation results, changed files and final diff
- Real backend-backed execution history and engineering reports
- Angular frontend with real authentication, RBAC UI, real Code Explorer content and admin user management
- Registration page

## Task lifecycle (new)

Requirement → Architecture plan (grounded in real repo files) → **Architect approval** → Development Agent (isolated git branch, real diff) → QA (real checks, honest statuses) → Merge request → **Architect review** → DevOps deployment (only after MR approval). Roles: ADMIN/DEVELOPER create tasks and MRs; ARCHITECT approves/rejects plans and MRs; VIEWER is read-only. All of this is enforced server-side. See `docs/WORKFLOW_API.md` and `IMPLEMENTATION_STATUS.md`.

## First-time setup

1. Copy `backend/.env.example` to `backend/.env`.
2. Set a strong `AUTH_JWT_SECRET`.
3. Add `MISTRAL_API_KEY` if you want real reasoning/code-editing runs.
4. From this root folder run:

```powershell
docker compose up --build
```

PostgreSQL is intentionally **not published to a Windows host port**. The backend reaches it internally as `db:5432`, so an existing local PostgreSQL installation will not cause the old 5432 conflict.

5. In another terminal:

```powershell
cd frontend
npm ci
npm start
```

6. Open `http://localhost:4200`.

## First login

Use the registration page to create the first account. On a fresh database, the first registered user becomes `ADMIN`. Later registrations become `DEVELOPER`. An ADMIN assigns the `ARCHITECT` role in Settings → users.

## Backend

Swagger: `http://localhost:8000/docs`

Important functional endpoints include:

- `/api/auth/*`
- `/api/users/*`
- `/api/repositories/*`
- `/api/repositories/{id}/files/content`
- `/api/repositories/{id}/index`
- `/api/repositories/{id}/search`
- `/api/tasks/*`
- `/api/tasks/{id}/run`
- `/api/tasks/{id}/sandbox/validate`
- `/api/tasks/{id}/tools/*`
- `/api/executions`
- `/api/reports`

## Sandbox prerequisite

The compose stack gives the backend access to Docker's socket so it can launch short-lived validation containers. Docker Desktop must be running. Sandbox containers have no network, bounded memory/CPU/PIDs, a timeout, a read-only repository mount and bounded logs.

## Verification

See `IMPLEMENTATION_STATUS.md` for exactly what was run and what was not.
# SDLC_Agentic_Platform
