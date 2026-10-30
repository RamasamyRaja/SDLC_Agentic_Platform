"""
Centralized application configuration.

All configuration is loaded from environment variables (see .env.example).
Nothing in this module hardcodes secrets or environment-specific values.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    APP_NAME: str = "AI SWE Agent Backend"
    ENVIRONMENT: Literal["local", "test", "staging", "production"] = "local"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # --- Authentication / RBAC ---
    AUTH_JWT_SECRET: str = "change-me-in-production"
    AUTH_ACCESS_TOKEN_EXPIRE_SECONDS: int = 3600
    AUTH_ALLOW_DEV_USER_FALLBACK: bool = True
    AUTH_DEV_USER_EMAIL: str = "dev@local.test"

    # --- PostgreSQL ---
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "agent_user"
    POSTGRES_PASSWORD: str = "agent_password"
    POSTGRES_DB: str = "ai_swe_agent"

    # Optional full override. If not set, it is built from the fields above.
    DATABASE_URL: str | None = None

    # --- Milvus (placeholder for Milestone 4) ---
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530

    # --- Mistral / LLM reasoning (Milestone 5) ---
    MISTRAL_API_KEY: str | None = None
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_BASE_URL: str | None = None  # only needed for a non-default endpoint (e.g. Azure/GCP)

    LLM_TEMPERATURE: float = 0.2  # low but nonzero: favors consistent, less creative reasoning
    LLM_MAX_OUTPUT_TOKENS: int = 2000
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 2  # bounded retries on invalid/malformed structured output — never unlimited

    # Context-building limits (Milestone 5) — keep what's sent to the model
    # deliberately bounded, never "the whole repository".
    LLM_MAX_RETRIEVED_CHUNKS: int = 8
    LLM_MAX_STRUCTURAL_SYMBOLS: int = 30
    LLM_MAX_CHARS_PER_CHUNK: int = 1500
    LLM_MAX_TOTAL_CONTEXT_CHARS: int = 20000

    # --- Agent orchestration (Milestone 6) ---
    # Below this reasoning confidence (or if any relevant_files/affected_symbols
    # entry fails grounding), the agent proposes REQUEST_APPROVAL instead of
    # PROPOSE_CHANGE — see app/agent/nodes.py::decide_action_node.
    AGENT_MIN_CONFIDENCE_FOR_AUTO_PROPOSE: float = 0.6

    # --- Code Agent tools (Milestone 7) ---
    # Shared with structural analysis (ANALYSIS_MAX_FILE_SIZE_BYTES) would
    # couple two independent concerns, so tools get their own explicit limit.
    TOOL_MAX_FILE_SIZE_BYTES: int = 1_000_000  # 1 MB — read_file/modify_file/search_code
    TOOL_MAX_SEARCH_RESULTS: int = 50
    TOOL_MAX_SEARCH_QUERY_LENGTH: int = 500
    TOOL_MAX_TREE_DEPTH: int = 8
    TOOL_MAX_TREE_ENTRIES: int = 500
    TOOL_MAX_DIFF_CHARS: int = 20_000
    # Bounds the automated TOOL_EXECUTION graph node's single read-only pass
    # (see app/agent/nodes.py::tool_execution_node) — never unlimited.
    AGENT_MAX_TOOL_CALLS: int = 10

    # --- Docker sandbox / QA (Milestones 8-10) ---
    SANDBOX_ENABLED: bool = True
    SANDBOX_DOCKER_SOCKET: str = "unix:///var/run/docker.sock"
    SANDBOX_WORKSPACE_VOLUME: str = "rad_ai_agent_workspaces"
    SANDBOX_MEMORY: str = "1g"
    SANDBOX_CPUS: float = 2.0
    SANDBOX_PIDS_LIMIT: int = 128
    SANDBOX_TIMEOUT_SECONDS: int = 120
    SANDBOX_MAX_OUTPUT_CHARS: int = 20_000
    AGENT_MAX_REPAIR_ATTEMPTS: int = 2
    AGENT_MAX_EDIT_FILES: int = 8
    AGENT_MAX_EDIT_CHARS: int = 30_000
    AGENT_MAX_FILE_CONTEXT_CHARS: int = 8_000

    # --- RAD lifecycle: planning / development / QA / MR / deployment ---
    # Architecture Agent
    PLAN_MAX_FILES_INSPECTED: int = 8
    PLAN_MAX_FILE_CHARS: int = 12_000
    PLAN_MAX_OUTPUT_TOKENS: int = 4000
    PLAN_STALE_AFTER_SECONDS: int = 900     # a PLANNING task older than this may be re-planned (crashed worker)
    # Development Agent
    DEV_MAX_OUTPUT_TOKENS: int = 6000
    DEV_STALE_AFTER_SECONDS: int = 3600
    DEV_BRANCH_PREFIX: str = "rad/task-"
    DEV_GIT_AUTHOR_NAME: str = "RAD AI Agent"
    DEV_GIT_AUTHOR_EMAIL: str = "rad-ai-agent@users.noreply.local"
    # QA runner: "docker" (default, hardened container) or "local" (an explicit,
    # opt-in subprocess runner for development/tests only - it executes repository
    # code on the host, so it must never be enabled for untrusted repositories).
    QA_RUNNER: str = "docker"
    QA_CHECK_TIMEOUT_SECONDS: int = 300
    QA_MAX_OUTPUT_CHARS: int = 20_000
    # The local runner executes repository code on the API host. Refuse it when ENVIRONMENT=production unless an
    # operator explicitly accepts that risk.
    QA_ALLOW_LOCAL_RUNNER_IN_PRODUCTION: bool = False
    # Dependency preparation for the docker runner. The check containers have NO network, so without this step
    # `pytest` and the repository's own requirements are simply absent and every Python test check ends as
    # DEPENDENCY_MISSING (=> PARTIAL). When enabled, a separate, secret-free container with network access installs
    # WHEEL-ONLY packages (no setup.py / build scripts are executed) into a per-run volume that the network-less test
    # container then mounts read-only. Set to false to forbid any network access during QA.
    QA_DEPENDENCY_INSTALL: bool = True
    QA_INSTALL_TIMEOUT_SECONDS: int = 300
    QA_PIP_EXTRA_ARGS: str = ""          # e.g. "--index-url https://pypi.internal/simple" (shell-split, operator-supplied)
    # Checks that are advisory: a failure is reported but does not fail the verdict, and an unavailable one never
    # blocks PASSED. Everything else is REQUIRED. Comma separated check names.
    QA_OPTIONAL_CHECKS: str = "npm-lint,npm-typecheck"
    # false: PASSED means every required AUTOMATED check passed (acceptance criteria are listed as pending the
    # Architect's confirmation). true: criteria that no automated check verifies keep the verdict at PARTIAL.
    QA_ACCEPTANCE_REQUIRED_FOR_PASS: bool = False
    SANDBOX_USER: str = "65534:65534"    # unprivileged user inside the check containers
    # Per-stage "worker lost" thresholds (a restart kills in-process background tasks).
    VALIDATE_STALE_AFTER_SECONDS: int = 3600
    MR_STALE_AFTER_SECONDS: int = 900
    DEPLOY_STALE_AFTER_SECONDS: int = 1800
    STARTUP_RECOVERY_ENABLED: bool = True
    GIT_API_RETRIES: int = 3
    GIT_API_RETRY_BACKOFF_SECONDS: float = 1.0
    # Merge request provider (credentials come from the environment, never from the repo).
    GIT_PROVIDER_TOKEN: str | None = None
    GIT_PROVIDER_KIND: str = "auto"   # auto | github | gitlab (set explicitly for GitHub Enterprise / self-hosted GitLab)
    GITHUB_API_URL: str = "https://api.github.com"
    GITLAB_API_URL: str = "https://gitlab.com/api/v4"
    GIT_PUSH_TIMEOUT_SECONDS: int = 120
    # Deployment (DevOps agent). Nothing is deployed unless an operator configures a
    # target. DEPLOY_COMMAND is operator-supplied server configuration (never model
    # output); it runs with the approved commit exported to DEPLOY_ARTIFACT_DIR.
    DEPLOY_COMMAND: str | None = None
    DEPLOY_HEALTHCHECK_URL: str | None = None
    DEPLOY_TIMEOUT_SECONDS: int = 600
    DEPLOY_HEALTHCHECK_RETRIES: int = 5
    DEPLOY_HEALTHCHECK_INTERVAL_SECONDS: float = 2.0
    # Deployment verification. A command that exited 0 and a 200 from "some" URL do not prove the TARGET
    # application runs the approved commit, so those are recorded as separate pieces of evidence:
    #   DEPLOY_HEALTHCHECK_URL  target application health (may contain {commit_sha})
    #   DEPLOY_VERSION_URL      endpoint of the TARGET app that reports its deployed version/commit; the response must
    #                           contain the approved commit (full SHA or the first 7+ characters). If the body is JSON
    #                           and DEPLOY_VERSION_JSON_KEY is set, only that (dotted) key is compared.
    #   DEPLOY_SMOKE_COMMAND    operator command run after the deploy (RAD_COMMIT_SHA / RAD_RELEASE_DIR are exported);
    #                           exit 0 = smoke tests passed.
    DEPLOY_VERSION_URL: str | None = None
    DEPLOY_VERSION_JSON_KEY: str | None = None
    DEPLOY_SMOKE_COMMAND: str | None = None
    DEPLOY_SMOKE_TIMEOUT_SECONDS: int = 300
    # true: DEPLOYED requires the deployed version to be verified (DEPLOY_VERSION_URL) or a passing smoke command;
    # health alone then yields DEPLOYMENT_UNAVAILABLE ("not verified"). false keeps the previous behaviour
    # (health check required) but the verification level is still recorded and shown.
    DEPLOY_REQUIRE_VERSION_VERIFICATION: bool = False

    # --- Repository onboarding / workspace (Milestone 3) ---
    # Root directory under which every repository gets its own isolated
    # clone directory: WORKSPACE_ROOT/<repository-id>/. Never hardcode a
    # developer's local path — always go through this setting.
    WORKSPACE_ROOT: str = "/tmp/ai-swe-agent/workspaces"

    # Files larger than this are skipped (recorded, not parsed) during
    # structural analysis to avoid loading huge blobs into memory.
    ANALYSIS_MAX_FILE_SIZE_BYTES: int = 1_000_000  # 1 MB

    # Directory names ignored anywhere in the repository tree during file
    # discovery. Comma-separated so it can be overridden via env var.
    ANALYSIS_IGNORED_DIR_NAMES: str = (
        ".git,node_modules,.venv,venv,target,build,dist,__pycache__,"
        ".mypy_cache,.pytest_cache,.idea,.vscode,coverage,.next,.tox,egg-info"
    )

    # File-name patterns (fnmatch, matched against the base name) of generated / minified / bundled files. They are
    # discovered but not parsed or embedded: they add size and noise, not understanding.
    ANALYSIS_IGNORED_FILE_PATTERNS: str = "*.min.js,*.min.css,*.bundle.js,*.chunk.js,*.map,*_pb2.py,*_pb2_grpc.py"

    # Repository onboarding / indexing reliability.
    REPO_STALE_AFTER_SECONDS: int = 1800      # CLONING/ANALYZING/INDEXING with no progress for this long = interrupted
    INDEX_EMBED_BATCH_SIZE: int = 64          # chunks embedded + stored per batch (bounded memory, resumable progress)
    INDEX_MAX_CHUNKS: int = 200_000           # refuse (with a clear error) instead of silently truncating

    # Git clone timeout, to avoid hanging forever on an unreachable host.
    GIT_CLONE_TIMEOUT_SECONDS: int = 120
    GIT_DISCOVERY_TIMEOUT_SECONDS: int = 25   # `git ls-remote` for default-branch discovery

    # --- Semantic retrieval: embeddings + Milvus (Milestone 4) ---
    # Milvus deployment mode. "lite" uses the embedded, file-backed Milvus
    # Lite database (MILVUS_LITE_PATH) — real Milvus, just running in-process
    # with no separate server, which is what this development environment
    # uses (see README "Milestone 4" for why: this sandbox's network
    # allowlist has no route to a Milvus server, and Lite is Milvus's own
    # documented answer for exactly that case). "server" connects to a real
    # standalone/cluster Milvus at MILVUS_HOST:MILVUS_PORT — supported by
    # the same client code, for use wherever a real server is reachable
    # (e.g. via docker-compose in an unrestricted environment).
    MILVUS_MODE: str = "lite"
    MILVUS_LITE_PATH: str = "/tmp/ai-swe-agent/milvus/milvus_lite.db"
    MILVUS_COLLECTION: str = "code_chunks"

    # Embedding provider. "spacy" is the only provider implemented — see
    # README "Milestone 4" for why it was selected over an OpenAI-based or
    # HuggingFace-hub-hosted model. The abstraction (EmbeddingProvider) is
    # designed so a different provider can be plugged in later purely via
    # this setting, without touching chunking or retrieval code.
    EMBEDDING_PROVIDER: str = "spacy"
    EMBEDDING_MODEL_NAME: str = "en_core_web_md"
    EMBEDDING_DIMENSION: int = 300

    # Chunking / indexing limits.
    CHUNK_MAX_CHARS: int = 4000  # a single chunk's stored content is capped at this length
    SEARCH_MAX_TOP_K: int = 20
    # Retrieval ranking: over-fetch from the vector index, drop dangling/duplicate hits, blend in a lexical score
    # (query terms found in the symbol name / path / content) and cap how many chunks one file may contribute.
    SEARCH_RERANK_ENABLED: bool = True
    SEARCH_OVERFETCH_FACTOR: int = 3
    SEARCH_LEXICAL_WEIGHT: float = 0.3
    SEARCH_MAX_CHUNKS_PER_FILE: int = 3

    @property
    def analysis_ignored_dir_names(self) -> set[str]:
        return {name.strip() for name in self.ANALYSIS_IGNORED_DIR_NAMES.split(",") if name.strip()}

    @property
    def analysis_ignored_file_patterns(self) -> list[str]:
        return [p.strip() for p in self.ANALYSIS_IGNORED_FILE_PATTERNS.split(",") if p.strip()]

    @property
    def qa_optional_checks(self) -> set[str]:
        return {p.strip() for p in self.QA_OPTIONAL_CHECKS.split(",") if p.strip()}

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so we only parse the environment once."""
    return Settings()
