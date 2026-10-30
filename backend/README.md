# AI Software Engineering Agent — Backend

Backend for an independent AI Software Engineering Agent. Given a Git
repository URL and a natural-language change request, the agent is intended
to onboard the repo, understand its structure, retrieve relevant context,
plan and implement a change, validate it (build/test/QA), and prepare a
pull/merge request for human review.

**Decided technology stack** (not to be changed without an explicit
architecture discussion):

| Concern                  | Technology              |
|---------------------------|--------------------------|
| HTTP/API layer            | FastAPI                 |
| Agent orchestration       | LangGraph                |
| LLM reasoning/generation  | Mistral                  |
| Source parsing            | Tree-sitter               |
| Code structural analysis  | Custom Python layer on Tree-sitter |
| Vector search              | Milvus                   |
| Relational persistence    | PostgreSQL + SQLAlchemy + Alembic |
| Repository interaction    | Git / GitPython          |
| Isolated execution         | Docker                   |

This repo is built incrementally, milestone by milestone. **This README
reflects the actual current state of the code — not the target
architecture.** See "Roadmap" below for what's implemented vs. still TODO.

---

## Milestone 1 — Backend Foundation (COMPLETE)

Implemented in this milestone:

- FastAPI application (`app/main.py`) with a `/` root endpoint and a real
  `GET /health` endpoint that checks Postgres connectivity (`SELECT 1`) and
  reports `ok` / `degraded` accordingly — it does not just return a static
  200.
- Centralized configuration via `pydantic-settings`, loaded from environment
  variables / `.env` (`app/core/config.py`). See `.env.example`.
- Basic logging setup (`app/core/logging.py`).
- SQLAlchemy 2.0 engine/session management (`app/db/session.py`), declarative
  `Base` plus `UUIDPrimaryKeyMixin` / `TimestampMixin` (`app/db/base_class.py`).
- First real ORM model: `User` (`app/models/user.py`) — part of the "Core"
  schema area (Users / Repositories / Tasks / Task Artifacts). Repository,
  Task, and TaskArtifact models are scoped to Milestone 2, along with their
  services and API endpoints.
- Alembic configured against the app's own settings and model metadata
  (`alembic/env.py`), with an initial migration
  (`alembic/versions/75b6206438dc_create_users_table.py`) that creates the
  `users` table. Verified against a real PostgreSQL instance.
- Dockerfile (non-root user, healthcheck) and docker-compose.yml (Postgres +
  backend, backend runs `alembic upgrade head` then `uvicorn` on start).
- Tests (`tests/`): config loading, root endpoint, health endpoint (asserts
  real DB connectivity, not mocked), and a User model DB round-trip.
  **6/6 passing.**

Explicitly **placeholder / NOT IMPLEMENTED yet** (each has a docstring
saying so): `app/services`, `app/agent`, `app/analysis`, `app/retrieval`,
`app/llm`, `app/tools`, `app/sandbox`, `app/qa`. Nothing in these packages
should be assumed to work.

### Verified locally

```
GET /health
→ {"status":"ok","app_name":"AI SWE Agent Backend","environment":"local","database":"ok"}
```

```
$ pytest -v
6 passed
```

---

## Milestone 2 — Repository & Task Management (COMPLETE)

Builds the core ownership chain: **User → Repository → Task → TaskArtifact**.
Creating a task at this stage only persists it with `status=PENDING` — it
does **not** start LangGraph, call Mistral, clone anything, or run any agent
logic. Those remain future milestones.

### Models (`app/models/`)

- **`Repository`** (`repository.py`) — a registered Git repository (`url`,
  `default_branch`, `workspace_path` for later cloning, `status`:
  `PENDING` / `READY` / `ERROR`). Belongs to a `User`.
- **`Task`** (`task.py`) — a natural-language change request against a
  repository (`description`, optional `title`/`branch`, `status`:
  `PENDING` → `QUEUED` → `RUNNING` → `COMPLETED`/`FAILED`, or `CANCELLED`
  from any non-terminal state). Belongs to a `User` and a `Repository`.
  Status transitions are enforced server-side
  (`ALLOWED_TASK_STATUS_TRANSITIONS` in `task.py`) — invalid transitions are
  rejected with `400`.
- **`TaskArtifact`** (`task_artifact.py`) — a repository-relative file path
  associated with a task (`file_path`, `artifact_type`, optional `notes`).
  Deliberately does **not** reference a `RepositoryDocument` yet — that link
  arrives with repository indexing in Milestone 4. Belongs to a `Task`.

All foreign keys cascade on delete (`ondelete="CASCADE"`) — deleting a
repository deletes its tasks, deleting a task deletes its artifacts. No
orphaned rows are possible.

### Services (`app/services/`)

`repository_service.py`, `task_service.py`, `task_artifact_service.py` hold
all business logic — ownership checks, status-transition rules, and name
derivation from a Git URL. Route handlers are thin wrappers around these.

### API endpoints

| Method | Path                              | Purpose                                   |
|--------|------------------------------------|--------------------------------------------|
| POST   | `/api/repositories`                | Register a repository (no cloning)         |
| GET    | `/api/repositories`                | List the current user's repositories       |
| GET    | `/api/repositories/{id}`           | Get one repository                         |
| POST   | `/api/tasks`                       | Create a task (`status=PENDING`, no agent run) |
| GET    | `/api/tasks`                       | List tasks, optional `repository_id`/`status` filters |
| GET    | `/api/tasks/{id}`                  | Get one task                               |
| PATCH  | `/api/tasks/{id}/status`           | Controlled status transition (validated)   |
| POST   | `/api/tasks/{id}/artifacts`        | Attach an artifact (file path) to a task   |
| GET    | `/api/tasks/{id}/artifacts`        | List a task's artifacts                    |

### Error handling

Domain exceptions (`app/core/exceptions.py`) are translated to HTTP
responses by handlers registered in `app/api/errors.py` — route handlers
never leak raw SQLAlchemy exceptions:

- `NotFoundError` → `404`
- `OwnershipError` → `403`
- `InvalidStatusTransitionError` → `400`
- Pydantic input validation (bad URL, empty request, absolute file path) → `422`

### User context (temporary, not real auth)

Milestone 1 had no authentication, and this milestone does **not** add
SSO/OAuth/RBAC/multi-tenancy either. `app/api/deps.py::get_current_user` is
an explicitly-documented development stand-in: it resolves (creating on
first use) a single `dev@local.test` user so ownership checks have a real
`User` to work against. Every service function takes `user: User` as an
explicit argument, so swapping this dependency for real auth later will not
require touching the service layer.

### Database migration

`alembic/versions/e787b3a70435_add_repository_task_task_artifact_tables.py`
creates `repositories`, `tasks`, and `task_artifacts` (plus their enum types
and indexes). Verified three ways:
- Applied on top of the existing Milestone 1 database.
- A full `downgrade -1` → `upgrade head` cycle (the downgrade explicitly
  drops the Postgres ENUM types it created, so re-running upgrade doesn't
  hit a "type already exists" error).
- A completely fresh database (`alembic upgrade head` from empty, both
  Milestone 1 and Milestone 2 revisions apply cleanly in order).

### Tests

`tests/test_repositories.py`, `tests/test_tasks.py`,
`tests/test_task_artifacts.py` — repository CRUD, invalid URL validation,
task creation/listing/filtering, empty-request rejection, the full
`PENDING → QUEUED → RUNNING → COMPLETED` transition path, rejection of
invalid transitions, artifact creation/listing, path validation (rejects
blank and absolute paths), 404s for nonexistent repositories/tasks, and a
cascade-delete integrity check (deleting a task deletes its artifacts).

**Result: 29/29 tests passing** (6 from Milestone 1 + 23 new).

### Verified live (in addition to pytest)

Every endpoint above was also exercised against a running server and a real
Postgres instance in this milestone — repository creation (with URL→name
derivation), task creation, the full status-transition happy path, an
invalid-transition rejection (`400`), artifact creation/listing, and the
`404`/`422` error paths. Test data was cleaned up afterward.

Explicitly **placeholder / NOT IMPLEMENTED yet**: `app/agent`,
`app/analysis`, `app/retrieval`, `app/llm`, `app/tools`, `app/sandbox`,
`app/qa`. No LangGraph, no Mistral, no Tree-sitter, no Milvus, no Docker
sandbox execution, no PR creation. Nothing in this milestone pretends the
agent runs.

---

## Milestone 3 — Repository Onboarding + Tree-sitter + Structural Analysis (COMPLETE)

Given a registered repository, the system can now clone it into an isolated
workspace and build a **deterministic structural representation** of its
source code — no LLM involved anywhere in this pipeline:

```
Repository URL → clone (GitPython) → workspace → file discovery
    → language detection → Tree-sitter parse → per-language AST extraction
    → aggregation → RepositoryAnalysis (+ a persisted summary)
```

### Repository onboarding (`app/services/onboarding_service.py`)

`onboard_repository()` orchestrates the whole pipeline for a repository the
user owns: clone → checkout branch → record commit SHA → run structural
analysis → persist a `RepositoryDocument` row per discovered file → update
the `Repository` row's onboarding summary. It does **not** run automatically
when a task or repository is created — it's an explicit operation
(`POST /api/repositories/{id}/onboard`). It does not execute any
repository-provided command, script, or hook.

### Git handling (`app/services/git_service.py`)

Thin wrapper around GitPython: shallow clone (`depth=1` — only the current
tree + latest commit is needed), branch checkout, commit SHA lookup.
`GIT_TERMINAL_PROMPT=0` so a clone requiring interactive credentials fails
fast instead of hanging. Distinguishes a missing branch
(`BranchNotFoundError` → `404`) from any other clone failure
(`RepositoryCloneError` → `422`).

### Workspace management (`app/services/workspace_service.py`)

Every repository gets `WORKSPACE_ROOT/<repository-id>/` — never a
developer's local path. `get_workspace_path()` resolves and verifies the
result is actually under `WORKSPACE_ROOT` before returning it, and is the
only function that constructs these paths. `WORKSPACE_ROOT` is fully
configurable via env var (defaults to `/tmp/ai-swe-agent/workspaces`
locally; `/workspaces`, backed by a named Docker volume, in
docker-compose).

### Language detection & Tree-sitter (`app/analysis/tree_sitter/`)

`registry.py` implements the registry/factory pattern called for in the
spec: `SupportedLanguage` enum → grammar-loading factory function → cached
compiled `Language` → fresh `Parser` per call. Adding a language means
adding one grammar-loading function and one registry entry — nothing else
in the codebase needs to change.

**Currently supported: Python, JavaScript, TypeScript, Java** (via
`tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`,
`tree-sitter-java`). `.tsx` files are parsed with the plain TypeScript
grammar (not a dedicated TSX grammar) — this is a documented approximation,
not a claim of full TSX support. Anything else is recorded as
`SKIPPED_UNSUPPORTED`, never silently ignored or force-parsed.

`parser.py` wraps parsing so a malformed file is reported via
`ParsedFile.has_error` — it never raises, and never aborts analysis of the
rest of the repository.

### Structural analysis layer (`app/analysis/`)

Per-language AST extractors (`tree_sitter/languages/{python,javascript,
typescript,java}.py`) each walk their own grammar's node types directly
(documented at the top of each file) and return a shared
`LanguageExtractionResult` (classes, functions, imports, calls) — this
confines grammar-specific knowledge to one file per language.
`analyzers/*.py` aggregates these across files and derives two convenience
views: a unified `Symbol` index (from classes+functions) and raw
`DependencyEdge`s (from imports — the *raw* imported name, e.g. `"./api"`
or `"java.util.List"`, **not** resolved to an actual repository file; see
`DependencyEdge`'s docstring). `service.py::analyze_repository()` is the
single entry point tying discovery → parsing → extraction → aggregation
together, and is what `onboarding_service` calls.

What's extracted, where the grammar supports it: file-level language;
classes (name, file, line, method names); functions/methods (name, file,
line, enclosing class if any, parameter names); imports (raw imported
name); calls (callee name, and caller function/method name if known — the
call target is **not** resolved to a definition, since that would require
real semantic analysis this milestone does not attempt). Anything not
reliably resolvable is left out rather than guessed.

### File discovery (`app/analysis/file_discovery.py`)

Recursively walks a workspace, pruning ignored directory names
(`.git`, `node_modules`, `.venv`, `venv`, `target`, `build`, `dist`,
`__pycache__`, and more — configurable via `ANALYSIS_IGNORED_DIR_NAMES`)
directly during the walk (`os.walk`'s `dirnames[:]` filtering), so ignored
trees are never even listed, not just filtered afterward. Never follows
symlinks, and verifies every resolved path is still under the workspace
root before including it. Reports file size without reading file content —
files over `ANALYSIS_MAX_FILE_SIZE_BYTES` (default 1 MB) are recorded as
`SKIPPED_TOO_LARGE` and never read.

### Database changes

- **`Repository`** gained onboarding-summary columns: `commit_sha`,
  `detected_languages`, `files_analyzed_count`, `files_skipped_count`,
  `parse_error_count`, `last_onboarded_at`, `onboarding_error`. Its
  `status` enum (`RepositoryStatus`) gained `CLONING` and `ANALYZING`
  alongside the existing `PENDING`/`READY`/`ERROR` — this describes
  repository *preparation*, kept deliberately separate from `TaskStatus`.
- **`RepositoryDocument`** (new table) — one row per discovered file:
  `file_path`, `language`, `file_size`, `content_hash` (sha256), and
  `analysis_status`. This is the **only** per-file persistence this
  milestone introduces.

**Deliberately NOT persisted**: the detailed symbol/class/function/import/
call/dependency breakdown. It's computed fresh by `analyze_repository()`
and returned in full by the `POST /onboard` response, but not written to
PostgreSQL — building a large in-database code graph this early (before
Milestone 4 actually needs to query it) would be overbuilding, per the
spec. `GET /analysis` returns the persisted *summary* only (counts,
languages, commit SHA) — re-run `POST /onboard` to get the full detail
again. This is a deliberate trade-off, not an oversight, and is easy to
revisit once Milestone 4 (embeddings/retrieval) defines what it actually
needs to query.

### API endpoints

| Method | Path                                          | Purpose                                             |
|--------|-------------------------------------------------|-------------------------------------------------------|
| POST   | `/api/repositories/{id}/onboard`                | Clone + analyze (synchronous); returns full analysis   |
| GET    | `/api/repositories/{id}/analysis`               | Persisted onboarding summary (404 if never onboarded) |
| GET    | `/api/repositories/{id}/documents`              | Per-file metadata from the last onboarding run         |

Onboarding is **synchronous** in this milestone — there's no LangGraph or
background task infrastructure yet (that's Milestone 6), so the request
blocks until clone + analysis finish and returns the complete result
directly.

### Security boundaries

This milestone is **static analysis only** — no repository-provided code
ever executes:
- Repository URL validated at creation (Milestone 2); clone failures
  surface as clean `422`/`404` errors, never a raw exception.
- Every workspace path is verified to resolve under `WORKSPACE_ROOT`
  before use.
- Symlinks are never followed during file discovery.
- File-size limits prevent large blobs from being read into memory.
- No `npm`/`Maven`/`Gradle`/shell/build/test command of any kind is ever
  invoked. That's explicitly out of scope until the Milestone 8 Docker
  sandbox, which will run under much stricter isolation than a plain clone.

### Tests

68 tests total (6 Milestone 1 + 23 Milestone 2 + **39 new**), organized as:
- **Unit**: language registry/detection (`test_analysis_registry.py`),
  per-language extraction against fixtures
  (`test_analysis_extractors.py`), file discovery/ignore-rules
  (`test_file_discovery.py`), workspace path safety
  (`test_workspace_service.py`), git clone/branch-not-found
  (`test_git_service.py`).
- **Integration**: full analysis-service pipeline against a mixed-language
  temp repo (`test_analysis_service.py`), and full onboarding —
  register → clone (a real local git repo, no network needed) → analyze →
  persist → retrieve via the actual API (`test_onboarding.py`).
- **Security**: path-traversal protection, oversized-file skip-without-read,
  ignored-directory pruning, symlink-escape protection
  (`test_security.py`).

Fixture source files live under `tests/fixtures/{java,python,typescript,
javascript}_sample/` — tiny, deterministic, and used both directly (unit
tests) and copied into a real git repo created at test time (integration
tests) so nothing depends on network access or a public repository.

**Result: 68/68 tests passing.**

### Known limitations

- No cross-file/cross-repository import resolution — `DependencyEdge`
  target is the raw imported name, not a resolved file reference.
- No call-target resolution — `CallInfo.callee` is the name as written,
  not a link to the function/method it actually calls.
- `.tsx` uses the plain TypeScript grammar (documented approximation).
- No framework-specific semantic understanding (e.g. Spring annotations,
  React hooks) — only what the raw grammar exposes.
- Onboarding is synchronous and re-clones from scratch each time (no
  incremental re-indexing yet, though content hashing is in place to
  support it later).
- Milvus/embeddings, Mistral, LangGraph, and Docker sandbox execution are
  **not implemented** — onboarding is clone + static analysis only.

---

## Milestone 4 — Semantic Repository Intelligence: Embeddings + Milvus + Retrieval (COMPLETE)

Adds a **second, complementary** source of repository understanding —
semantic similarity search — alongside (not replacing) Milestone 3's
deterministic structural analysis:

```
RepositoryDocument (Milestone 3) → chunking (structural boundaries) →
embedding model → Milvus (vector storage/search) → semantic search results
```

**The hybrid architecture, explicitly:**
- **Structural analysis (Milestone 3)**: exact — Tree-sitter parses real
  syntax; classes/functions/imports/calls are extracted deterministically.
  Wrong or missing only if the grammar can't parse the file.
- **Semantic retrieval (Milestone 4)**: approximate — embeddings capture
  *similarity*, not exact relationships. A high-scoring search result is
  semantically related, not necessarily an exact match, and embeddings make
  no claim about call graphs, type relationships, or control flow — that's
  what Milestone 3 is for. Neither replaces the other.

### Embedding model: spaCy `en_core_web_md`

**What it is**: 300-dimensional pretrained static word vectors
(GloVe-derived), averaged per document. No OpenAI, runs fully offline once
installed.

**Why this model, specifically**: the natural first choice — a
transformer-based sentence/code embedding model via `sentence-transformers`
or `fastembed` (e.g. a `BAAI/bge-*` model) — turned out to be
un-downloadable in this build/test sandbox: those libraries fetch model
weights from `huggingface.co`, which is not in this environment's network
allowlist. spaCy's models, by contrast, are published as plain pip wheels
on **GitHub Releases**, which *is* allowlisted
(`github.com` / `release-assets.githubusercontent.com`), making
`en_core_web_md` the strongest genuinely-pretrained, non-OpenAI embedding
option that actually installs here. This is a documented environment
constraint, not a preference — see `app/retrieval/embeddings.py`'s
docstring for the full reasoning.

**Honest limitation**: static word-vector averaging is real but
meaningfully weaker than a modern transformer embedding — no word order, no
context. `split_identifier_words()` (in `embeddings.py`) partially
compensates by turning `deleteInvestigation` into "delete investigation"
before embedding, so identifiers contribute real English words the model
has vectors for. Verified empirically (`tests/test_embeddings.py`,
`tests/test_retrieval_integration.py`): a query like "delete investigation"
does correctly score a `deleteInvestigation`-related chunk above an
unrelated one, in both unit tests and a live run.

**The `EmbeddingProvider` abstraction** (`app/retrieval/embeddings.py`)
exists specifically so a stronger model can replace this one later — purely
via `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL_NAME` config — once network access
to a model hub is available; chunking and retrieval code never need to
change.

### Milvus: real embedded Milvus (Lite), not a mock

`MILVUS_MODE=lite` (the default) connects to **Milvus Lite** — Milvus's own
official embedded, file-backed deployment mode, run in-process via the same
`pymilvus` client used for a full server. This is genuine Milvus, not a
fake/stub adapter: schema creation, indexing (`AUTOINDEX` on the vector
field, an `INVERTED` index on `repository_id` for fast repository-scoped
filtering), upsert, and COSINE-similarity search all go through real
Milvus code paths. This sandbox's network allowlist has no route to pull a
Milvus server container and no `docker compose` execution is available
either, so Lite is the practical way to exercise real Milvus here.
`MILVUS_MODE=server` (pointing `MILVUS_HOST`/`MILVUS_PORT` at a real
standalone/cluster deployment) uses the exact identical `MilvusVectorStore`
code — see `app/retrieval/milvus_client.py`.

One real bug found and fixed during this milestone: a Milvus Lite
collection persisted from a prior process reconnects in a "released" state
and needs an explicit `load_collection()` call before it can be searched —
without it, search intermittently fails after a process restart. Fixed in
`MilvusVectorStore._ensure_collection()` and verified stable across
repeated full test-suite runs.

### Chunking (`app/retrieval/chunking.py`)

**Reuses Milestone 3's analysis** rather than re-parsing anything: for each
repository document, it re-runs `analyze_repository()` (the same function
Milestone 3's onboarding uses) against the still-on-disk workspace, then
turns each extracted `ClassInfo`/`FunctionInfo` into a chunk using their
exact `line`/`end_line` boundaries (a small additive field added to those
Milestone 3 models specifically to support this — see the "Milestone 3
integration" note below). A file with no extracted symbols (unsupported
language, parse error, or genuinely no top-level classes/functions) falls
back to one whole-file chunk, so every readable file still contributes at
least one chunk. Chunk content is capped at `CHUNK_MAX_CHARS` (default
4000).

### Database changes

- **`CodeChunk`** (new) — one row per chunk: `repository_document_id`,
  `chunk_index`, `chunk_type` (`CLASS`/`FUNCTION`/`METHOD`/`FILE`),
  `symbol_name`, `content_hash`, `start_line`/`end_line`, `language`, and
  `content` (the actual chunk text — justified here, unlike Milestone 3's
  full analysis result, because a chunk's content *is* the retrieval unit
  search needs to return, and it's bounded by `CHUNK_MAX_CHARS`).
- **`EmbeddingMetadata`** (new) — one row per embedded chunk: `provider`,
  `model_name`, `dimension`, `milvus_collection`, `milvus_id`. **The vector
  itself is never stored in PostgreSQL** — only in Milvus. This is the
  PostgreSQL/Milvus separation the spec calls for: PostgreSQL is the
  relational source of truth, Milvus is the vector-search engine.
- **`Repository`** gained an `IndexingStatus` enum
  (`NOT_INDEXED`/`INDEXING`/`INDEXED`/`FAILED`) and summary columns
  (`indexed_chunk_count`, `last_indexed_at`, `indexing_error`) —
  deliberately a **separate** status from `RepositoryStatus` (onboarding)
  and `TaskStatus` (the requested change). A repository can be `READY`
  (onboarded) but still `NOT_INDEXED`.

Migration verified three ways, same as prior milestones: applied to the
existing database, a full downgrade→upgrade cycle, and a fresh database.

### Indexing workflow & idempotency

`POST /api/repositories/{id}/index` requires the repository to have been
onboarded first (`workspace_path` must be set — a clear `400` otherwise,
not a confusing failure). Each run:
1. Re-analyzes the workspace (Milestone 3, reused).
2. Chunks the result.
3. Diffs against existing `CodeChunk` rows by
   `(repository_document_id, content_hash)`: **unchanged** chunks keep their
   existing row and embedding untouched; **new/changed** content gets a
   fresh `CodeChunk` row and a fresh embedding; chunks that no longer exist
   are deleted (from both PostgreSQL and Milvus).
4. Embeds only the new/changed chunks (batched in one call).

This is a **repository-level re-index with per-chunk idempotency** — not
fully incremental file-level indexing. Re-running indexing with no source
changes reports every chunk as `chunks_unchanged` and creates nothing new
(verified in `test_reindexing_is_idempotent_for_unchanged_content`). Making
this incremental at the file-discovery level (skip unchanged files
entirely, using `RepositoryDocument.content_hash` from Milestone 3) is a
natural next step, not yet implemented — the content-hash groundwork for it
is already in place.

### API endpoints

| Method | Path                                       | Purpose                                          |
|--------|-----------------------------------------------|-----------------------------------------------------|
| POST   | `/api/repositories/{id}/index`                | (Re-)index a repository (requires prior onboarding)  |
| GET    | `/api/repositories/{id}/index/status`         | Indexing status + summary                            |
| POST   | `/api/repositories/{id}/search`               | Semantic search (`query`, `top_k` ≤ `SEARCH_MAX_TOP_K`) |

Indexing is **synchronous**, same as onboarding — no LangGraph/background
task infrastructure yet.

### Repository isolation

Every vector carries a `repository_id`, and search always filters on it at
the Milvus level (an `INVERTED` index keeps this efficient) — repository A
never leaks into repository B's search results. Verified at two levels:
`test_milvus_client.py::test_repository_isolation_in_search` (direct
Milvus-layer check) and
`test_retrieval_integration.py::test_repository_isolation_end_to_end` (full
API-level check across two independently onboarded+indexed repositories).
Ownership is also checked at the service layer (same `get_repository()`
ownership check used everywhere else), so a user can't even name another
user's `repository_id` to search it.

### Security

Same static/retrieval-only boundary as Milestone 3 — no repository code is
ever executed. `top_k` is capped server-side at `SEARCH_MAX_TOP_K` (default
20, requests above that get a clean `422`) so a single search request can't
trigger unbounded vector retrieval.

### Tests

**29 new tests** (97 total: 68 from Milestones 1–3 + 29 here):
- **Embeddings** (`test_embeddings.py`): provider initialization, correct
  documented dimension, deterministic output, empty-input handling,
  identifier-splitting, and a semantic-relevance check (not exact ranking —
  a reasonable "more relevant scores higher" assertion, per the spec).
- **Chunking** (`test_chunking.py`): class/method chunk extraction with
  correct boundaries and content, whole-file fallback, content hashing,
  max-length truncation, full repository-level chunking.
- **Milvus** (`test_milvus_client.py`): collection creation, upsert+search,
  `top_k` limiting, **repository isolation**, repository-scoped deletion,
  counting. All against a real (Lite) Milvus instance, isolated per test via
  a throwaway file path — not a mock.
- **Integration** (`test_retrieval_integration.py`): full
  onboard→index→search through the real API against a real local git repo;
  index-before-onboard and search-before-index error paths; **re-indexing
  idempotency**; **end-to-end repository isolation**.

**Result: 97/97 tests passing**, confirmed stable across repeated runs
(the Milvus reload fix above was found and fixed via exactly this repeated-run
verification).

### Known limitations

- Re-indexing is repository-level with per-chunk idempotency, not
  file-level-incremental (see "Indexing workflow" above).
- No cross-repository or cross-chunk relationship reasoning — search
  returns individually-relevant chunks, not a reasoned answer (that's
  Milestone 5/Mistral's job, not implemented here).
- spaCy static vectors are a real but comparatively weak embedding
  compared to a transformer model — see "Embedding model" above for why,
  and how to upgrade it later via the `EmbeddingProvider` abstraction.
- Milvus Lite is a real but single-process, file-backed deployment — not
  representative of a production Milvus cluster's operational
  characteristics (though the same client code path works against one).
- Mistral, LangGraph, the Code Agent, and Docker sandbox execution are
  **not implemented** — this milestone is chunking + embeddings + vector
  search only.

---

## Milestone 5 — Mistral Reasoning Layer (COMPLETE)

Adds an LLM reasoning component that consumes Milestone 3's structural
knowledge and Milestone 4's semantic retrieval to produce a **strictly
structured, validated** analysis of a requested change — nothing more.
Mistral does not write to the database, clone repositories, run
Tree-sitter, query Milvus, execute code, or modify files; it reasons over
context assembled by the application and returns a plan.

```
Task + M3 structural context + M4 retrieved context
    → context builder (bounded)
    → Mistral (system + user prompt, JSON mode)
    → JSON extraction + Pydantic validation (bounded retry on failure)
    → grounding against supplied context
    → ReasoningResult (persisted + returned)
```

### Model & provider: Mistral via the official SDK

**Provider abstraction** (`app/llm/provider.py`): `LLMProvider` is the only
interface `app/llm/service.py` depends on. `MistralProvider`
(`mistral_provider.py`) is the real implementation; `FakeLLMProvider`
(`fake_provider.py`) is a deterministic offline implementation used
throughout the test suite — injected via a constructor parameter on
`analyze_task()`, never a real network call in normal tests.

**Capability check performed before implementation** (not assumed): the
installed `mistralai` SDK (`mistralai.client.Mistral`) was inspected
directly — `chat.complete(...)` accepts `response_format`, `temperature`,
`max_tokens`, and `timeout_ms`, all used here. `response_format={"type":
"json_object"}` (Mistral's JSON mode) is requested: this **guarantees
parseable JSON**, but — per Mistral's own documented behavior — does
**not** guarantee the JSON matches any particular schema. (A stricter
`"json_schema"` mode exists on some models; not used here, to keep this
provider working uniformly across whatever `MISTRAL_MODEL` is configured
rather than depending on per-model schema-mode support.) Because JSON mode
alone doesn't guarantee schema conformance, full Pydantic validation
(`ReasoningResult.model_validate`) runs on every response regardless —
this is the actual enforcement layer, with JSON mode as a floor, not a
substitute. `app/llm/parsing.py` additionally handles the case where a
response still isn't clean JSON (markdown fences, stray prose) before
validation — the "robust JSON extraction" half of the spec's fallback
strategy.

**Verified against real network behavior, not just code review**: this
sandbox's network allowlist has no route to `api.mistral.ai`. A real call
with a dummy key was exercised during development and confirmed to fail
cleanly as `LLMProviderError` rather than crash — see
`tests/test_llm_provider.py::test_mistral_provider_wraps_transport_failure_as_provider_error`,
which runs this exact path (a genuine SDK/transport call, not a mock) as
part of the normal test suite.

### Context builder: consumes M3 + M4, never re-derives structure

`app/llm/context_builder.py` builds the bounded `ReasoningInput` sent to
the model:
- **Structural context**: read from the Milestone 4 `CodeChunk` table
  (`symbol_name`, `chunk_type`, `file_path`, `language`) — which was itself
  derived from Milestone 3's Tree-sitter analysis at indexing time. M3's
  full per-symbol analysis isn't persisted (documented in Milestone 3/4),
  so this is the practical, already-persisted way to consume M3's *output*
  without re-parsing anything.
- **Semantic context**: calls `app.retrieval.retrieval_service.search()`
  directly (never Milvus directly from this layer) — the task's own
  description is used as the search query. If the repository hasn't been
  indexed yet, retrieved context is simply empty; reasoning still proceeds
  on structural context alone rather than refusing outright, and the model
  is instructed to note uncertainty where context is thin.

**Bounding** (all configurable, see `.env.example`):
`LLM_MAX_STRUCTURAL_SYMBOLS` (default 30), `LLM_MAX_RETRIEVED_CHUNKS`
(default 8), `LLM_MAX_CHARS_PER_CHUNK` (default 1500, applied per chunk
before it's even added to the context), and a final
`LLM_MAX_TOTAL_CONTEXT_CHARS` (default 20000) safety net that trims the
lowest-scoring retrieved chunks if the bounded context is still too large.
The whole repository is never sent — only what these limits allow through.

### Prompt design & security boundary

`app/llm/prompts.py` builds two clearly separated pieces: a system prompt
(role, rules, the exact required output shape — see
`_OUTPUT_SCHEMA_DESCRIPTION`) and a user prompt (the task request plus a
clearly delimited, JSON-serialized `REPOSITORY CONTEXT` block). The system
prompt explicitly instructs the model to treat everything under
`REPOSITORY CONTEXT` as **data to analyze, not instructions** — so a source
file containing text like "ignore previous instructions and..." remains
repository content to describe, never becomes a command the model follows.

**What this construction defends against**: naive injection where
repository text is mistaken for a system-level directive, because
repository content never appears near the system role and is explicitly
labeled untrusted. **What it does NOT guarantee**: that a sufficiently
adversarial payload can never influence a model that chooses not to follow
its system prompt — no prompt-formatting technique fully prevents that.
The real backstop is `app/llm/grounding.py`'s post-hoc validation (below),
which checks the model's *claims* against supplied context after the fact,
rather than trusting the prompt boundary alone to prevent the model from
*acting* on fabricated content.

### Structured output contract & validation

`app/llm/schemas.py::ReasoningResult` — `summary`, `understanding`
(`goal`/`affected_area`), `relevant_files` (`file_path`/`reason`/
`confidence`/`grounded`), `affected_symbols` (`file_path`/`symbol_name`/
`reason`/`grounded`), `implementation_plan` (numbered steps with
`target_files`), `dependencies`, `risks`, `uncertainties`, and an overall
`confidence`. Every response goes through: JSON extraction
(`parsing.py`) → Pydantic validation → **bounded retry** (`LLM_MAX_RETRIES`,
default 2) with a corrective follow-up prompt that includes the exact
validation error, so the model gets one concrete chance to fix a specific
mistake rather than guessing again blind. Exhausting the retry budget
raises `LLMOutputValidationError` (→ `502`) — the application never
silently accepts or fabricates a result.

### Grounding: model-reported confidence is never trusted blindly

`app/llm/grounding.py` checks every `relevant_files[].file_path` and
`affected_symbols[].(file_path, symbol_name)` the model named against what
was actually supplied in `ReasoningInput` (both structural and retrieved
context). A match sets `grounded=True`; no match sets `grounded=False` —
flagged entries are **kept, not deleted**, so the caller can see exactly
what the model claimed and whether it checks out, rather than the
application silently hiding a hallucination. This is explicitly a
practical, deterministic membership check, not a general hallucination
detector or a verifier of the model's *reasoning* — see the module
docstring for the exact scope. A `confidence: 0.99` from the model is
never treated as proof of correctness; `grounded` is the application-level
check that actually matters.

### Database: `TaskAnalysis`

One new table — `task_analyses`: `task_id`, `model_name`, `prompt_version`
(`PROMPT_VERSION = "v1"`, versioned so a future prompt change is
traceable against past results), `status` (`COMPLETED`/`FAILED`), the
validated result as JSONB, and a clean error message on failure. Deliberately
**one-to-many** with `Task` — re-running analysis (e.g. after
re-indexing) creates a new row rather than overwriting history. The
bounded context sent to the model is NOT duplicated into this table, only
the result — proportional storage, not a second copy of everything sent.
Migration verified the same three ways as every prior milestone.

### API

`POST /api/tasks/{task_id}/analyze` — validates task/repository ownership,
builds context, calls Mistral, validates, grounds, persists a
`TaskAnalysis` row (`COMPLETED` or `FAILED`), and returns:

```json
{
  "task_id": "...",
  "model": "mistral-large-latest",
  "prompt_version": "v1",
  "result": { "summary": "...", "relevant_files": [...], "confidence": 0.82, ... }
}
```

Never exposes the raw Mistral response, the prompt, or any credential.
`LLMUnavailableError` (missing/invalid key, timeout, rate limit, transport
failure) and `LLMOutputValidationError` (retries exhausted) both map to a
clean `502` — the failure is clearly upstream, and the application never
fabricates a fallback answer.

### Failure handling

| Situation | Behavior |
|---|---|
| Missing/invalid `MISTRAL_API_KEY` | Clean `502` before any request is sent |
| Timeout / rate limit / transport error | Caught in `mistral_provider.py`, wrapped as `LLMProviderError` → `502`, no retry burned (a retry can't fix a transport problem) |
| Malformed / schema-invalid JSON response | Bounded retry (`LLM_MAX_RETRIES`) with a corrective prompt, then `502` if still invalid |
| Task/repository not found or not owned | `404` / `403`, same as every other endpoint |

### Testing strategy

**43 new tests** (140 total: 97 from Milestones 1–4 + 43 here — one of the
43, the real-Mistral smoke test, is skipped rather than run whenever
`MISTRAL_API_KEY` is unset): provider tests (missing key, a *real*
dummy-key call against the actual SDK/transport path confirming clean
error handling, `FakeLLMProvider` behavior), schema/parsing tests
(valid/invalid payloads, JSON extraction edge cases), context-builder
tests (combines M3+M4, enforces every configured limit, preserves
file-path/symbol metadata, handles an unindexed repository gracefully),
grounding tests (valid and hallucinated file/symbol references,
structural-only matches, entries never silently dropped), service tests
(success, retry-recovery, retry-exhaustion, provider-error fails fast
without burning retries), and full API integration tests (end-to-end with
`FakeLLMProvider` injected via monkeypatch, persistence, grounding flows
through to the API response, clean `502` paths).

**The real Mistral API is never called by the normal suite** —
`test_mistral_real_smoke.py` is `pytest.mark.skipif`'d cleanly whenever
`MISTRAL_API_KEY` is unset (which it is in this environment, and this
environment's network allowlist has no route to `api.mistral.ai` regardless),
so the suite passes fully without credentials while still providing a real
integration path for an environment where they're available.

### Known limitations

- No LangGraph — `reasoning_service.analyze_task()` is a plain function
  call today; it's structured so a future LangGraph node can call it
  directly without modification (per spec), but no graph/orchestration
  exists yet.
- The context builder's "structural context" comes from M4's CodeChunk
  index (classes/functions extracted by M3), not the full M3
  imports/calls/dependencies graph — reasonable given M3 doesn't persist
  that, but a real limitation if the model would benefit from seeing
  call-graph relationships explicitly.
- Grounding checks file/symbol *existence* in supplied context only — it
  does not and cannot verify that the model's proposed plan is actually
  correct or complete.
- No LangGraph, Code Agent, code modification, Docker sandbox execution,
  QA, or PR creation — this milestone is reasoning/planning output only.

---

## Milestone 6 — Agent Orchestration / LangGraph Workflow (COMPLETE)

Introduces the actual stateful agent workflow that coordinates the
capabilities already implemented in M1–M5, using LangGraph. This is an
**orchestration** layer, not an execution one: the graph produces a
structured, declarative proposed action — it never runs shell commands,
executes model-generated code, modifies repository files, commits to Git,
or creates a pull request.

```
Task
  → LOAD_TASK (validate ownership)
  → BUILD_CONTEXT (verify repository readiness)
  → REASON (the full M5 reasoning pipeline, reused wholesale)
  → VALIDATE_REASONING (defensive re-check)
  → DECIDE_ACTION (deterministic rule, not another LLM call)
  → FINALIZE (persist AgentExecution)
```

Any node failure short-circuits straight to FINALIZE (via a shared
conditional edge, `route_after_node`), so the workflow always terminates
cleanly and always produces a terminal, persisted record — never an
unhandled exception mid-graph, and never a fabricated success.

### Reused from M1–M5 (nothing duplicated)

- **`task_service.get_task` / `repository_service.get_repository`** — the
  exact same ownership-checked lookups every other endpoint uses (`LOAD_TASK`,
  `BUILD_CONTEXT`).
- **`llm.service.analyze_task()`** — called wholesale from the `REASON`
  node. This is the single biggest reuse decision in this milestone: rather
  than re-implementing (or splitting apart) Milestone 5's context-building
  → prompt → Mistral call-with-retry → grounding pipeline across graph
  nodes, `REASON` calls the existing public function directly. `BUILD_CONTEXT`
  is therefore a readiness check (is the repository onboarded/indexed?),
  not a context-construction step — the actual M3 structural context + M4
  semantic retrieval assembly still happens exactly once, inside
  `context_builder.py`, exactly as it did before this milestone.
- **`reasoning_service.persist_task_analysis()`** — extracted (in this
  milestone) from what was previously inline logic in the M5 API router,
  specifically so both the M5 `/analyze` endpoint and this milestone's
  `REASON` node persist `TaskAnalysis` rows through the identical code
  path. The M5 endpoint's behavior is unchanged — this was a pure
  extraction, verified by re-running all existing M5 tests unmodified
  before adding any M6 code.
- **`FakeLLMProvider`** — the entire M6 test suite (and the API's optional
  `provider` injection point) reuses this Milestone 5 test double; no new
  fake/mock LLM layer was introduced.
- **All M1–M5 domain exceptions** (`NotFoundError`, `OwnershipError`,
  `LLMUnavailableError`, `LLMOutputValidationError`, ...) — nodes catch
  these exact types and record them in state; `run_agent_workflow()`
  re-raises the *original* exception class afterward (via a small
  string→class registry keyed on the exception's class name), so the
  API layer's existing exception handlers (`app/api/errors.py`) map a
  workflow failure to the identical HTTP status the same failure produces
  everywhere else in the API — no parallel error-handling path was created.

### Agent state (`app/agent/state.py`)

A thin, JSON-serializable `TypedDict` — `task_id`, `repository_id`,
`task_description`, `indexing_status`, `reasoning_result` (bounded by M5's
own context limits, not arbitrary repository text), `model_name`, `action`,
`stage`, `status`, `errors`, `error_type`. Deliberately holds **no**
database session, ORM object, or secret — those are runtime dependencies
injected via LangGraph's `config["configurable"]` (the DB session, current
user, and an optional injected LLM provider), which is never part of the
checkpointed state.

### Declarative actions (`app/agent/models.py::AgentAction`)

`ANALYZE`, `RETRIEVE`, `PROPOSE_CHANGE`, `REQUEST_APPROVAL`, `COMPLETE` — a
closed enum. `DECIDE_ACTION` applies one deterministic, explicit rule (not
an LLM call):

1. Any `relevant_files`/`affected_symbols` entry failed grounding
   (Milestone 5's `grounded=False`) → **`REQUEST_APPROVAL`** — never
   auto-propose against a claim that didn't check out against the
   supplied repository context.
2. `confidence` below `AGENT_MIN_CONFIDENCE_FOR_AUTO_PROPOSE` (default
   `0.6`) → **`REQUEST_APPROVAL`**.
3. A non-empty `implementation_plan` and neither of the above triggered
   → **`PROPOSE_CHANGE`**.
4. Otherwise → **`COMPLETE`** (nothing concrete enough to propose).

### Checkpointing decision (documented, per the milestone spec)

Uses LangGraph's in-memory `MemorySaver`, **not**
`langgraph-checkpoint-postgres` (installed and available, but not wired
in as the default). Full reasoning in
`app/agent/checkpointer.py`'s docstring; summary: `PostgresSaver` manages
its own tables via a `.setup()` call that runs its own bundled SQL,
entirely outside Alembic — which conflicts with this project's
established, verified-every-milestone principle that "the database must
remain migration-driven, never require manual table creation." Since this
milestone's workflow executes synchronously within a single request
(same pattern as onboarding/indexing/analyze), `MemorySaver` covers what
checkpointing actually buys here (mid-run state inspection, used by
`test_agent_graph.py` and directly exercised via
`compiled.get_state_history()` during development). The durable,
cross-request record of a run is `AgentExecution` — a normal,
Alembic-migrated table. `get_checkpointer()` is the one place this
decision lives; swapping to `PostgresSaver` later touches only that
function.

### Database: `AgentExecution`

One new table, deliberately minimal per the spec's "do not prematurely
implement the complete execution subsystem": `task_id`, `status`
(`COMPLETED`/`FAILED`), `action`, `model_name`, `result` (JSONB — the
validated `ReasoningResult`), `error`. No `execution_steps`,
`step_logs`, or `tool_calls` tables — those are explicitly future-milestone
scope, introduced only once the capabilities they'd track actually exist.
Migration verified the same three ways as every prior milestone (existing
DB, downgrade/upgrade cycle, fresh DB).

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/tasks/{task_id}/run` | Runs the LangGraph workflow synchronously, returns the structured result |
| GET | `/api/tasks/{task_id}/run/{execution_id}` | Retrieves a persisted past run |

Both endpoints never expose a raw exception, stack trace, or credential —
only the structured `AgentExecutionResult`/`AgentExecution` record, and
the same `404`/`403`/`502`/etc. status codes every other endpoint uses for
the equivalent underlying failure.

### Failure handling

Every failure mode listed in the spec is covered by the existing M1–M5
exception types, reused rather than reinvented: task/repository not found
→ `NotFoundError`; not owned → `OwnershipError`; LLM unavailable/timeout/
rate-limited → `LLMUnavailableError`; malformed/schema-invalid LLM output
after M5's bounded retry budget → `LLMOutputValidationError`. A node
failure never silently produces a fabricated "success" result — `FINALIZE`
only reports `COMPLETED` when no node set `status="FAILED"` along the way.

### Logging

Each node logs its stage transition (workflow started, context verified,
reasoning completed, action selected, workflow completed/failed) via the
existing `app.core.logging` setup — never logs API keys, full prompts, or
full repository content (only file paths, symbol names, and short status
strings).

### Testing

**40 new tests** (180 total: 140 from Milestones 1–5 + 40 here): state
construction, graph compilation/structure (expected nodes/edges present,
compilation is cached), edge routing, **every node tested independently**
(including failure propagation for `LOAD_TASK`/`REASON`), full
`run_agent_workflow()` integration tests covering all three
`AgentAction` outcomes plus every failure path (task not found, LLM
unavailable, output validation exhausted, and that a failed run still
persists a terminal `AgentExecution` row), and full API tests for both
endpoints (structured response shape, no raw exception leakage, `404`s,
grounding flows through to the API response). All LLM-layer tests use
`FakeLLMProvider` — **no real Mistral API key or network access required**
for the standard suite, and no external Milvus server (same Milvus Lite
strategy as Milestone 4).

**Live smoke test performed** (not just unit tests): a real repository was
onboarded, indexed, and run through `POST /run` against a live server —
confirmed the graph correctly reaches `REASON`, fails there with a clean
`502` (no real Mistral key in this environment), and persists the failed
`AgentExecution` correctly; `GET /run/{execution_id}` was then confirmed to
retrieve that exact record.

### Known limitations / future work

- **`BUILD_CONTEXT` is a readiness check, not a distinct context-assembly
  step** — see "Reused from M1–M5" above for why; the actual context
  construction stays inside M5's `context_builder.py`, called once via
  `analyze_task()`.
- **`MemorySaver`, not `PostgresSaver`** — mid-run state history isn't
  queryable across process restarts; see "Checkpointing decision" above.
- **No async execution / job queue** — `POST /run` blocks until the
  workflow completes, same pattern as onboarding/indexing/analyze in
  earlier milestones. A future milestone could move this to a background
  task without changing `run_agent_workflow()`'s signature.
- **No `execution_steps`/`step_logs`/`tool_calls` tables** — deliberately
  not built ahead of the capabilities that would populate them.
- **`PROPOSE_CHANGE` is still just a label** — no future Code Agent exists
  yet to act on it; that's explicitly out of scope here.
- LangGraph, Mistral reasoning, and the declarative action model exist now;
  actual code generation/modification, Docker sandbox execution, QA, and
  PR creation remain **not implemented**.

---

## Milestone 7 — Code Agent Tools: Safe Repository Interaction (COMPLETE)

Gives the agent controlled, workspace-bounded capabilities to interact with
a repository's cloned workspace: read a file, search source code, inspect
repository structure, apply a single unambiguous file modification, and
inspect a local Git diff. **This is not code execution** — nothing in this
milestone runs a shell command, a subprocess, model-generated code, or any
build/test/lint tool. That remains explicitly out of scope for a future
sandbox/execution milestone.

### The five tools

| Tool | What it does | Key safety property |
|---|---|---|
| `read_file` | Reads a file, optionally a line range | Path validated, size-capped, truncates rather than OOMs |
| `search_code` | Text search across the workspace | Reuses M3's `discover_files` — ignored dirs, no symlinks, bounded results |
| `repository_structure` | Bounded, deterministic file/dir tree | Depth- and entry-capped, ignored dirs excluded |
| `modify_file` | Single unambiguous text replacement | Refuses on missing/ambiguous match; atomic write (`os.replace`) |
| `git_diff` | Inspects local uncommitted changes | Read-only — never commits, pushes, or touches the remote |

### Security: the workspace boundary

**Every** tool-supplied path goes through one function:
`app/tools/path_safety.py::resolve_safe_relative_path()`. Rejected, always:
empty/whitespace paths, absolute paths (POSIX `/...` and Windows
`C:\...`/`\\...`), any path containing a `..` segment, and — the
authoritative check — a **resolved** (symlinks followed) target outside the
workspace root. `search_code` and `repository_structure` don't need this
function directly: they reuse Milestone 3's `discover_files()`, which never
follows symlinks and never leaves the workspace root during the walk itself.

Verified with real attack payloads, not just code review:
`../../secret`, `../../../etc/passwd`, `/etc/passwd`, `C:\Windows\System32`,
`\\server\share`, and an actual symlink pointing outside the workspace —
every one rejected, confirmed in `tests/test_tools_path_safety.py` and via
a manual smoke test against a real filesystem during development.

### `modify_file`: the most security-sensitive operation

Per the spec, this is the one tool that writes. Its guarantees:
1. The target must exist and be a regular file (not a directory).
2. `old_content` must occur **exactly once** — zero occurrences raises
   `ModificationNotFoundError`, more than one raises
   `AmbiguousModificationError`. **It never guesses.**
3. The write is atomic: content is written to a temp file in the same
   directory, then `os.replace()` (atomic on POSIX) swaps it into place —
   a crash mid-write can never leave the target file half-written.
4. A rejected (ambiguous/missing) modification leaves the file byte-for-byte
   unchanged — verified explicitly in
   `test_modify_file_leaves_file_intact_after_rejected_ambiguous_modification`.

### Tool registry

`app/tools/registry.py` is the single name→tool lookup — an unknown tool
name is rejected in exactly one place, both for the automated graph node
and the API endpoint. `run_tool()` validates raw input against the specific
tool's own Pydantic model before anything executes; there is no code path
that runs an unvalidated dict. Adding a future tool (formatter, linter, a
bounded test runner once a real sandbox exists) means adding one registry
entry — nothing else changes.

### LangGraph integration: a bounded, single-pass extension

M6's graph gained one node — `TOOL_EXECUTION` — reached only when
`DECIDE_ACTION` selects `PROPOSE_CHANGE`:

```
... DECIDE_ACTION → [PROPOSE_CHANGE] → TOOL_EXECUTION → FINALIZE
                  → [else]           ────────────────→ FINALIZE
```

**Why not a full multi-round tool-calling loop** (the spec's suggested
`REASON ↔ TOOL_EXECUTION` cycle): Milestone 5's `ReasoningResult` schema
doesn't include literal new file content for the model to write — there is
no code-generation step yet. Auto-invoking `modify_file` with no real
content to write would mean fabricating a modification, which this project
does not do anywhere. So `TOOL_EXECUTION` does exactly one **bounded,
read-only** pass: it calls `read_file` (via the registry — never a raw
filesystem call) on each `target_files` entry from the plan, capped by
`AGENT_MAX_TOOL_CALLS` (default 10), and records what it found. A missing
target file is recorded as a failed observation but does **not** fail the
overall workflow. `modify_file`, `search_code`, `repository_structure`, and
`git_diff` remain fully available — reachable right now via the explicit
`POST /api/tasks/{task_id}/tools/{tool_name}` endpoint — for real use once
a future milestone adds genuine LLM-driven tool selection with real content
to act on.

`AgentState` (Milestone 6) gained three fields for this:
`tool_call_count`, `tool_results` (small summaries only — a file path and
line count, never full file content), `tool_limit_reached`.

### API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tasks/{task_id}/tools` | List available tools and descriptions |
| POST | `/api/tasks/{task_id}/tools/{tool_name}` | Invoke one tool, validated against its own schema |

**Deliberately not** a generic `POST /execute` — `tool_name` is checked
against the closed registry, and the request body is validated against
that specific tool's Pydantic model. The `repository_id` in the tool
input (if supplied) must match the task's own repository — a user can't
use one task's endpoint to reach a different, even if also-owned,
repository. Every invocation (success or failure) is recorded via
`ToolInvocation`.

### Database: `ToolInvocation`

One new table — deliberately distinct from Milestone 6's `AgentExecution`
(one row per *graph run*, not per tool call): `task_id`, `tool_name`,
`status`, `input_summary`/`result_summary` (small, non-sensitive metadata
only — a file path, never file content), `error`. Populated by both the
explicit API endpoint and the automated `TOOL_EXECUTION` node through the
same `record_tool_invocation()` helper — one recording path, not two.
`AgentExecution` also gained `tool_call_count`/`tool_results` columns (a
per-run summary, not a duplicate of the per-call `ToolInvocation` rows).
Migrations verified the same three ways as every prior milestone (existing
DB, downgrade/upgrade cycle, fresh DB) — 8 migrations total in the chain.

### Testing

**68 new tests**: path safety (traversal, absolute paths, symlink escape —
both directions: escaping vs. staying inside), tool registry (unknown
tool, malformed/wrong-type input), full functional coverage per tool
(including a real bug found and fixed during this milestone —
`repository_structure`'s `max_depth` was incorrectly hiding a shallow
directory whose only child happened to be deeper than the limit; fixed and
covered by `test_repository_structure_respects_max_depth`), **repository
isolation** (two separately onboarded repositories with identically-named
files — read/search/tree/modify on one never touches the other, verified
by content, not just by path), modification safety (missing/ambiguous
content, nonexistent target, directory-instead-of-file, and that a
*rejected* modification leaves the file untouched), Git diff correctness,
LangGraph integration (`TOOL_EXECUTION` runs only for `PROPOSE_CHANGE`,
respects `AGENT_MAX_TOOL_CALLS`, a missing file fails the observation but
not the workflow), and full API tests (all five tools, `404`/`422`/`400`
error paths, cross-task repository mismatch rejection, invocation
recording for both success and failure).

**Result: 247/247 tests passing, 1 skipped** (the real-Mistral smoke test,
unchanged from Milestone 5) — confirmed stable across repeated runs, zero
regressions across Milestones 1–6.

### Live smoke test (not just unit tests)

A real repository was onboarded and, through the actual running HTTP API:
listed tools, read a file, searched for a symbol, inspected the tree,
applied a real modification, confirmed a path-traversal attempt was
rejected with `400`, confirmed `git_diff` correctly reflected the applied
modification afterward, and confirmed an unknown tool name returned `404`.

### Known limitations

- `TOOL_EXECUTION` is read-only and single-pass — no automated
  multi-round tool-calling loop yet (see "LangGraph integration" above for
  why, and what unlocks it).
- `modify_file` operates on exact text matches only — no line-based
  patching, no fuzzy matching, no multi-file atomic transactions.
- `search_code` is a plain Python substring scan (case-insensitive), not a
  regex or AST-aware search — deliberately simple and dependency-free,
  consistent with "no unrestricted `grep`".
- No shell, subprocess, build, test, lint, or arbitrary-code execution of
  any kind — that remains a distinct, later, more heavily sandboxed
  milestone.
- No automatic Git commit, push, or PR creation — `git_diff` is
  inspection-only.

---

## Project structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app entrypoint
│   ├── api/                 # HTTP routers: health, repositories, onboarding, tasks, task_artifacts, deps, errors
│   ├── core/                # config, logging, domain exceptions
│   ├── db/                  # SQLAlchemy base/session
│   ├── models/               # ORM models: User, Repository, RepositoryDocument, Task, TaskArtifact
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/             # repository/task/task_artifact/git/workspace/onboarding services
│   ├── analysis/              # Tree-sitter + deterministic structural analysis (Milestone 3)
│   │   ├── tree_sitter/
│   │   │   ├── registry.py    # language -> grammar registry/factory
│   │   │   ├── parser.py      # safe parse wrapper
│   │   │   └── languages/     # per-language AST extractors (python/js/ts/java) + dispatch
│   │   ├── analyzers/         # classes/functions/imports/calls/symbols/dependencies aggregation
│   │   ├── file_discovery.py  # safe recursive file scanner
│   │   ├── models.py          # RepositoryAnalysis and friends (typed output)
│   │   └── service.py         # analyze_repository() — the pipeline entry point
│   ├── retrieval/              # Chunking + embeddings + Milvus + semantic search (Milestone 4)
│   │   ├── chunking.py          # builds chunks from M3 structural analysis
│   │   ├── embeddings.py        # EmbeddingProvider abstraction + spaCy implementation
│   │   ├── milvus_client.py     # MilvusVectorStore (real Milvus Lite / server)
│   │   ├── retrieval_service.py # index_repository() / search() — the pipeline entry point
│   │   └── models.py            # ChunkCandidate, SearchResponse, IndexingSummary
│   ├── llm/                     # Mistral reasoning layer (Milestone 5)
│   │   ├── provider.py           # LLMProvider abstraction
│   │   ├── mistral_provider.py   # real Mistral SDK implementation
│   │   ├── fake_provider.py      # deterministic offline provider (tests)
│   │   ├── prompts.py            # system/user/retry prompt construction
│   │   ├── schemas.py            # ReasoningInput / ReasoningResult (input+output contracts)
│   │   ├── parsing.py            # robust JSON extraction
│   │   ├── context_builder.py    # combines M3 (via M4 CodeChunk) + M4 retrieval, bounded
│   │   ├── grounding.py          # validates claims against supplied context
│   │   └── service.py            # analyze_task() — the pipeline entry point
│   ├── agent/                 # LangGraph orchestration (Milestone 6)
│   │   ├── state.py            # AgentState (thin, JSON-serializable TypedDict)
│   │   ├── models.py           # AgentAction / AgentExecutionStatus / AgentExecutionResult
│   │   ├── nodes.py             # LOAD_TASK/BUILD_CONTEXT/REASON/VALIDATE_REASONING/DECIDE_ACTION/FINALIZE
│   │   ├── edges.py             # conditional routing (fail-fast to FINALIZE)
│   │   ├── graph.py             # StateGraph wiring, compiled + cached
│   │   ├── checkpointer.py      # MemorySaver factory (documented decision)
│   │   ├── exceptions.py        # agent-layer-specific exceptions
│   │   └── service.py           # run_agent_workflow() — the pipeline entry point
│   ├── tools/                    # Code Agent tools (Milestone 7)
│   │   ├── path_safety.py         # resolve_safe_relative_path() — the workspace boundary
│   │   ├── base.py                # get_onboarded_workspace(), record_tool_invocation()
│   │   ├── models.py              # per-tool typed input/output models
│   │   ├── exceptions.py          # ToolError and subclasses
│   │   ├── filesystem.py          # read_file, modify_file
│   │   ├── search.py              # search_code (reuses M3 discover_files)
│   │   ├── tree.py                # repository_structure (reuses M3 discover_files)
│   │   ├── git.py                 # git_diff (local, uncommitted changes only)
│   │   └── registry.py            # name -> ToolSpec lookup, run_tool()
│   ├── sandbox/                   # TODO — Docker execution (Milestone 8)
│   └── qa/                         # TODO — QA / architecture gates (Milestone 9)
├── tests/                    # pytest test suite
│   └── fixtures/              # tiny deterministic source fixtures (java/python/typescript/javascript)
├── alembic/                   # DB migrations
├── Dockerfile
├── docker-compose.yml
├── requirements.txt / requirements-dev.txt / pyproject.toml
├── .env.example
└── README.md
```

---

## Running locally (without Docker)

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
# edit .env if your local Postgres credentials differ

# requires a running PostgreSQL matching the POSTGRES_* values in .env
alembic upgrade head

uvicorn app.main:app --reload
```

Then visit `http://localhost:8000/health` and `http://localhost:8000/docs`.

## Running with Docker Compose

```bash
cd backend
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, waits for it to be healthy, runs
`alembic upgrade head`, then starts the API on `http://localhost:8000`.

## Running tests

```
$ pytest -v
247 passed, 1 skipped
```

Tests assume a reachable PostgreSQL instance using the same `POSTGRES_*`
environment variables as the app (start one via
`docker compose up -d db`, or run Postgres locally). Onboarding/analysis
tests also require the `git` binary on PATH (used to build local, temporary
fixture repositories at test time — no network access required). Retrieval
tests use a real embedded Milvus Lite instance (file-backed, isolated per
test) and the spaCy `en_core_web_md` embedding model — both installed via
`requirements-dev.txt`, no external services or network access required at
test time. LLM-layer tests use `FakeLLMProvider` (deterministic, offline) —
the one exception, `test_mistral_real_smoke.py`, skips cleanly unless
`MISTRAL_API_KEY` is set in the environment.

---

## Roadmap (see full plan for details)

- [x] **Milestone 1** — Backend foundation
- [x] **Milestone 2** — Repository & task management (models, services, API)
- [x] **Milestone 3** — Repository onboarding, Tree-sitter, structural analysis
- [x] **Milestone 4** — Repository intelligence: chunking, embeddings, Milvus, semantic search
- [x] **Milestone 5** — Mistral reasoning layer: context building, structured output, validation, grounding
- [x] **Milestone 6** — Agent orchestration: LangGraph typed state, graph, declarative actions, checkpoints
- [x] **Milestone 7** — Code Agent tools: read/search/modify file, tree, git diff, safe workspace boundary (this milestone)
- [ ] Milestone 8 — Docker sandbox execution (build/test, isolation, limits)
- [ ] Milestone 9 — QA + architecture gates (#1 and #2), retry/rejection routing
- [ ] Milestone 10 — MR/PR preparation, final task lifecycle, end-to-end test

## Design notes / constraints carried forward

- FastAPI is the HTTP layer only — it is not where reasoning happens.
- LangGraph will own orchestration; it will not itself parse code, run
  Docker, or write files directly.
- Mistral is the only LLM provider used (no OpenAI). Structured outputs are
  required wherever the LLM's response feeds into deterministic logic.
- Tree-sitter + a custom Python analysis layer handle source parsing —
  the LLM is not responsible for basic code structure extraction.
- Milvus is the only vector store (no pgvector); PostgreSQL is the only
  relational store. Milvus stores vectors, PostgreSQL stores metadata that
  references them — vectors are never duplicated into Postgres.
- Repository code is treated as untrusted and will only ever be executed
  inside Docker (Milestone 8), never directly on the host.
- No Kubernetes, no additional agent frameworks, no additional vector or
  relational databases.

## RBAC / Authentication Addendum

The post-M7 RBAC layer adds:
- Roles: `ADMIN`, `DEVELOPER`, `VIEWER`
- Explicit permission policy in `app/rbac.py`
- PBKDF2-SHA256 password hashing and compact HS256 JWT authentication
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- Admin user management: `GET /api/users`, `PATCH /api/users/{user_id}/role`, `PATCH /api/users/{user_id}/active`
- Permission enforcement across repository, onboarding, retrieval, task, artifact, analysis, Agent, and tool APIs
- Alembic migration `9b6e2c1f4a10_add_auth_and_rbac.py`

For non-local deployments, set a strong `AUTH_JWT_SECRET` and disable `AUTH_ALLOW_DEV_USER_FALLBACK`.

---

# Final Engineering Completion Layer — M7 + RBAC + M8/M9/M10

The final integrated package extends the verified M7 core without replacing the existing repository-analysis/retrieval stack.

## Real repository inspection

- `GET /api/repositories/{id}/files/content` returns the actual onboarded workspace file content with repository ownership and path-safety checks.
- `GET /api/repositories/{id}/analysis` now includes a persisted-metrics summary suitable for the Angular analysis screen.

## RBAC

Roles are `ADMIN`, `DEVELOPER`, and `VIEWER`. Backend permission guards remain authoritative; the Angular UI only mirrors those permissions for usability.

## M8 — Secure Docker sandbox

`POST /api/tasks/{task_id}/sandbox/validate` executes a bounded validation command inside an isolated Docker container with:

- network disabled
- read-only repository workspace mount
- memory/CPU/PID limits
- timeout enforcement
- bounded stdout/stderr capture
- no arbitrary shell command accepted by the API
- persisted sandbox-run telemetry

The compose stack mounts the Docker socket because the backend is the sandbox orchestrator. The application drops back to `appuser` when the socket group can be resolved.

## M9 — QA + bounded repair

Agent execution can now:

1. analyze the task with grounded repository context
2. derive a bounded edit plan
3. read only grounded target files
4. apply exact, unambiguous edits through the existing safe `modify_file` tool
5. run sandbox validation
6. inspect validation output
7. request a bounded repair edit from the LLM
8. repeat only up to the configured repair limit
9. persist changed files, validation runs, repair count and final Git diff

## M10 — Engineering workflow telemetry

`AgentExecution` now records validation, changed files, repair attempts and final diff. The frontend execution history and reports screens use real backend data rather than mock execution/report fixtures.

## Frontend integration

The Angular frontend now uses FastAPI for:

- authentication and RBAC
- repository operations
- real repository file content
- task/agent execution history
- engineering reports
- user administration in Settings for users with the appropriate permissions

The registration page is included, and the Code Explorer no longer uses the mock file-content adapter in the FastAPI environment.

## Important runtime prerequisites

- A valid `MISTRAL_API_KEY` is required for actual reasoning/code-editing runs.
- Docker Desktop must be running for sandbox validation.
- The compose backend needs access to `/var/run/docker.sock` for M8/M9 execution.
- The database and workspace volumes are managed by Compose; PostgreSQL is intentionally not published to a host port.
