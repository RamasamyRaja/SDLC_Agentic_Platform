# Task lifecycle API contract (backend is the source of truth)

All routes are under `/api` (Angular `ApiClient` already prefixes `/api`; paths below omit it). Bearer JWT auth.
Error bodies: `{ "detail": string }`. 403 = role lacks permission, 409 = action not allowed in the current stage, 400/422 = validation.

## Roles / permissions
`GET /auth/me` and the login/register `user` object now include `permissions: string[]` (server truth). Roles: `ADMIN | DEVELOPER | ARCHITECT | VIEWER`.
Matrix: create task / create MR = ADMIN, DEVELOPER. approve/reject plan and MR = ARCHITECT only. VIEWER read-only. The UI must use `permissions` (not a copied table) and must render only `task.allowed_actions`.
Permission strings: repository:read|write, task:read|write|create, agent:read|run, tool:read|invoke, user:read|manage, sandbox:execute, mr:create|approve|reject, plan:approve|reject, deploy:execute.

## Tasks
- `POST /tasks` {repository_id, request (requirement text), title?, expected_outcome?, context?, branch?} -> 201 {task_id, repository_id, status, workflow_stage, planning_started: bool, planning_blocker: string|null}. Needs `task:create`. Starts the Architecture Agent in the background when the repository is READY and INDEXED; otherwise `planning_blocker` explains why.
- `GET /tasks` -> TaskSummary[] (all tasks, team-wide). Query: repository_id, workflow_stage.
- `GET /tasks/{id}` -> TaskDetail = TaskSummary + {expected_outcome, context, user_id, repository:{id,name,url,default_branch,default_branch_source,status,indexing_status,commit_sha}, lifecycle: LifecycleStage[], allowed_actions: Action[]}

TaskSummary: {id, title, description, repository_id, repository_name, branch, status (legacy), workflow_stage, creator:{id,email,full_name}|null, plan_status, development_status, validation_verdict, mr_status, mr_review_status, deployment_status, created_at, updated_at, user_id?}
- workflow_stage: CREATED | PLANNING | PLAN_FAILED | PLAN_PENDING_APPROVAL | PLAN_APPROVED | PLAN_REJECTED | PLAN_REVISION_REQUIRED | IMPLEMENTING | IMPLEMENTATION_FAILED | VALIDATING | VALIDATION_FAILED | READY_FOR_MR | MR_CREATING | MR_CREATION_FAILED | MR_PENDING_REVIEW | MR_APPROVED | MR_REJECTED | MR_REVISION_REQUIRED | DEPLOYING | DEPLOYED | DEPLOYMENT_FAILED | DEPLOYMENT_UNAVAILABLE
- plan_status: NOT_STARTED | GENERATING | FAILED | PENDING_APPROVAL | APPROVED | REJECTED | REVISION_REQUIRED
- development_status: NOT_STARTED | RUNNING | FAILED | NO_CHANGES | CHANGES_APPLIED | COMMITTED
- validation_verdict: NOT_RUN | PASSED | PARTIAL | FAILED
- mr_status: NOT_CREATED | CREATING | OPEN | CREATION_FAILED ; mr_review_status: NOT_CREATED | MR_PENDING_REVIEW | MR_APPROVED | MR_REJECTED | MR_REVISION_REQUIRED
- deployment_status: BLOCKED_PENDING_APPROVAL | READY_FOR_DEPLOYMENT | DEPLOYING | DEPLOYED | DEPLOYMENT_FAILED | UNAVAILABLE

LifecycleStage (always 8, in order: requirement, architecture_plan, plan_approval, implementation, testing, merge_request, architect_review, deployment):
{key, label, owner (human role or agent), status: NOT_STARTED|IN_PROGRESS|COMPLETED|FAILED|BLOCKED|PENDING_HUMAN, started_at, finished_at, error, blockers: string[], summary, outputs: object}

Action: {key, label, method:"POST", endpoint: "/api/tasks/{id}/<path>" (absolute, includes /api — strip the leading /api when using ApiClient), decision?: "APPROVED"|"REJECTED"|"REVISION_REQUESTED", requires_comment?: bool, accepts_comment?: bool, requires_acknowledgement?: bool}
Keys: start_planning, approve_plan, reject_plan, request_plan_revision, start_implementation, run_validation, create_merge_request, approve_mr, reject_mr, request_mr_revision, deploy.
Request bodies: start_planning/start_implementation -> {feedback?}; plan/MR decision -> {decision, comment?, plan_id?|mr_id?}; create_merge_request -> {title?, description?, acknowledge_validation_risk: bool}; run_validation/deploy -> no body.
`requires_acknowledgement` => show a checkbox ("submit despite failing/unavailable validation") and send acknowledge_validation_risk=true.

## Stage resources (all GET need task:read)
- `GET /tasks/{id}/plan` -> Plan {id, version, status, model_name, feedback, plan: ArchitecturePlan|null, evidence, error, repository_commit_sha, created_at, finished_at}; 404 if none. `GET /tasks/{id}/plans` -> Plan[] (newest first).
  ArchitecturePlan: {summary, requirement_understanding, current_implementation, findings:[{statement, evidence:[{file_path, quote, verified}]}], recommended_approach, rationale, alternatives_rejected[], files_to_change:[{file_path, action:"modify"|"create", change_description, symbols[], expected_behavior, exists}], implementation_steps:[{step, description, files[]}], risks[], dependencies[], acceptance_criteria[], test_strategy:{approach, test_cases:[{name, description, file_path}], validation_notes[]}, uncertainties[], confidence}
  evidence: {files_read:[{path, sha256, chars, lines}], retrieved_chunks:[{file_path, symbol_name, score}], rounds[], verification:{verified_quotes, total_quotes, files_to_change[]}}
- `GET /tasks/{id}/development-runs` -> Run[] (no diff); `GET /tasks/{id}/development-runs/{run_id}` -> Run
  Run: {id, attempt, status, model_name, feedback, branch_name, base_branch, base_commit_sha, files_read[], tool_calls[], edits:[{kind, file_path, status:"APPLIED"|"REJECTED", reason?, rationale?}], changed_files[] (from git), diff (unified text), diff_stat:{additions,deletions,files,repair_attempts}, summary, error, validation_verdict, commit_sha, commit_message, checks: Check[], created_at, finished_at}
  Check: {id, batch, name, command, status: PASSED|FAILED|TIMED_OUT|DEPENDENCY_MISSING|BLOCKED|SKIPPED|UNVERIFIED, exit_code, output, failure_details, runner, started_at, finished_at}
- `GET /tasks/{id}/merge-request` -> MR {id, status, review_status, title, description, source_branch, target_branch, commit_sha, validation_verdict, failed_validation_acknowledged, remote_status: NOT_ATTEMPTED|REMOTE_CREATED|REMOTE_FAILED|REMOTE_UNAVAILABLE, remote_provider, remote_url, remote_identifier, remote_error, pushed, error, run: Run|null}; 404 if none. A non-REMOTE_CREATED MR is a LOCAL review record: say so plainly with remote_error.
- `GET /tasks/{id}/deployment` -> {status, attempt, commit_sha, artifact_path, artifact_sha256, steps:[{name,status,detail,exit_code,output,at}], health_check, log, error, started_at, finished_at}
- `GET /tasks/{id}/events` -> [{id, event_type, from_stage, to_stage, actor, message, detail, created_at}]
- `GET /tasks/{id}/report` -> ExecutionReport {task_id, generated_at, workflow_stage, implementation_completed, requirement, repository, verified:{architecture_findings, plan_evidence, approved_plan, approved_plan_version, tool_calls, files_read, files_modified, edits, git_diff, commit, merge_request, tests_executed, validation_verdict, architect_decisions, deployments, agent_stages}, recommendations:{...model-authored, label as such}, unverified:{acceptance_criteria}, unavailable:string[], unresolved_issues:string[]}

Repositories: `GET /repositories` is team-wide. RepositoryResponse gained default_branch_source ("remote_head"|"user_specified"|"fallback"), commit_sha, indexing_status (NOT_INDEXED|INDEXING|INDEXED|FAILED), indexed_chunk_count, last_indexed_at, onboarding_error, indexing_error. `POST /repositories/{id}/onboard`, `POST /repositories/{id}/index`, `GET /repositories/{id}/index/status` already exist.
Long operations (plan, implementation, validation, deployment) return 202 and run in the background: poll `GET /tasks/{id}` every ~2s while workflow_stage is PLANNING/IMPLEMENTING/VALIDATING/DEPLOYING/MR_CREATING.
