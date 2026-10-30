/** Types mirroring docs/WORKFLOW_API.md. The backend is the source of truth for every status. */

export type WorkflowStage =
  | 'CREATED' | 'PLANNING' | 'PLAN_FAILED' | 'PLAN_PENDING_APPROVAL' | 'PLAN_APPROVED' | 'PLAN_REJECTED'
  | 'PLAN_REVISION_REQUIRED' | 'IMPLEMENTING' | 'IMPLEMENTATION_FAILED' | 'VALIDATING' | 'VALIDATION_FAILED'
  | 'READY_FOR_MR' | 'MR_CREATING' | 'MR_CREATION_FAILED' | 'MR_PENDING_REVIEW' | 'MR_APPROVED' | 'MR_REJECTED'
  | 'MR_REVISION_REQUIRED' | 'DEPLOYING' | 'DEPLOYED' | 'DEPLOYMENT_FAILED' | 'DEPLOYMENT_UNAVAILABLE';

/** Stages during which a background agent is working and the UI should poll. */
export const BUSY_STAGES: readonly WorkflowStage[] = ['PLANNING', 'IMPLEMENTING', 'VALIDATING', 'DEPLOYING', 'MR_CREATING'];

export type AttentionLevel = 'human_action' | 'error' | 'blocked' | 'running' | null;
export interface Attention { level: AttentionLevel; reason: string | null }

export interface WorkflowSummary {
  total: number;
  validation: Record<string, number>;
  deployment: Record<string, number>;
  attention: Record<string, number>;
  completed: number;
  needs_attention: Array<{ id: string; title: string | null; repository_name: string | null; workflow_stage: string; level: AttentionLevel; reason: string; updated_at: string }>;
}

export interface Creator { id: string; email: string; full_name: string | null }

export interface TaskSummary {
  id: string;
  title: string | null;
  description: string;
  repository_id: string;
  repository_name: string | null;
  branch: string | null;
  status: string;
  workflow_stage: WorkflowStage;
  creator: Creator | null;
  plan_status: string;
  development_status: string;
  validation_verdict: string;
  validation_headline?: string | null;
  validation_counts?: Record<string, number> | null;
  attention?: Attention;
  mr_status: string;
  mr_review_status: string;
  deployment_status: string;
  created_at: string;
  updated_at: string;
}

export type LifecycleStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED' | 'BLOCKED' | 'PENDING_HUMAN' | 'PARTIAL';

export interface LifecycleStage {
  key: string;
  label: string;
  owner: string;
  status: LifecycleStatus;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  blockers: string[];
  summary: string | null;
  outputs: Record<string, unknown>;
}

export type ActionKey =
  | 'start_planning' | 'approve_plan' | 'reject_plan' | 'request_plan_revision' | 'start_implementation'
  | 'run_validation' | 'create_merge_request' | 'approve_mr' | 'reject_mr' | 'request_mr_revision' | 'deploy';

export interface TaskAction {
  key: ActionKey;
  label: string;
  method: 'POST';
  endpoint: string;
  decision?: 'APPROVED' | 'REJECTED' | 'REVISION_REQUESTED';
  requires_comment?: boolean;
  accepts_comment?: boolean;
  requires_acknowledgement?: boolean;
}

export interface TaskRepositoryInfo {
  id: string; name: string; url: string; default_branch: string;
  default_branch_source: string | null; status: string; indexing_status: string | null; commit_sha: string | null;
}

export interface TaskDetail extends TaskSummary {
  expected_outcome: string | null;
  context: string | null;
  user_id: string;
  repository: TaskRepositoryInfo | null;
  lifecycle: LifecycleStage[];
  allowed_actions: TaskAction[];
}

export interface TaskCreatePayload {
  repository_id: string;
  request: string;
  title?: string;
  expected_outcome?: string;
  context?: string;
  branch?: string;
}

export interface TaskCreateResult {
  task_id: string; repository_id: string; status: string; workflow_stage: WorkflowStage;
  planning_started: boolean; planning_blocker: string | null;
}

export interface PlanEvidenceQuote { file_path: string; quote: string; verified: boolean }
export interface PlanFinding { statement: string; evidence: PlanEvidenceQuote[] }
export interface PlanFile { file_path: string; action: 'modify' | 'create'; change_description: string; symbols: string[]; expected_behavior: string; exists: boolean }
export interface PlanStep { step: number; description: string; files: string[] }
export interface ArchitecturePlan {
  summary: string; requirement_understanding: string; current_implementation: string;
  findings: PlanFinding[]; recommended_approach: string; rationale: string; alternatives_rejected: string[];
  files_to_change: PlanFile[]; implementation_steps: PlanStep[]; risks: string[]; dependencies: string[];
  acceptance_criteria: string[];
  test_strategy: { approach: string; test_cases: Array<{ name: string; description: string; file_path?: string }>; validation_notes: string[] };
  uncertainties: string[]; confidence: number;
}
export interface PlanEvidence {
  files_read: Array<{ path: string; sha256: string; chars: number; lines: number }>;
  retrieved_chunks: Array<{ file_path: string; symbol_name: string | null; score: number }>;
  rounds: unknown[];
  verification: { verified_quotes: number; total_quotes: number; files_to_change: unknown[] };
}
export interface TaskPlan {
  id: string; version: number; status: string; model_name: string | null; feedback: string | null;
  plan: ArchitecturePlan | null; evidence: PlanEvidence | null; error: string | null;
  repository_commit_sha: string | null; created_at: string; finished_at: string | null;
}

export type CheckStatus = 'PASSED' | 'FAILED' | 'TIMED_OUT' | 'DEPENDENCY_MISSING' | 'BLOCKED' | 'SKIPPED' | 'UNVERIFIED' | 'NO_TESTS';
export interface ValidationCheck {
  id: string; batch: number; name: string; command: string | null; status: CheckStatus; exit_code: number | null;
  output: string | null; failure_details: string | null; runner: string | null; started_at: string | null; finished_at: string | null;
  required?: boolean | null; kind?: string | null; metrics?: Record<string, unknown> | null;
}

/** Persisted explanation of a validation verdict (null on runs validated before explanations existed: those are explained from their stored checks). */
export interface ValidationSummary {
  verdict: string; headline: string; reasons: string[]; counts?: Record<string, number>;
  required?: string[]; executed?: string[]; passed?: string[];
  failed?: unknown[]; unresolved?: unknown[]; advisory?: unknown[];
  acceptance?: unknown; environment?: unknown; legacy?: boolean; evaluated_at?: string;
}
export interface DevelopmentRun {
  id: string; attempt: number; status: string; model_name: string | null; feedback: string | null;
  branch_name: string | null; base_branch: string | null; base_commit_sha: string | null;
  files_read: string[]; tool_calls: unknown[];
  edits: Array<{ kind: string; file_path: string; status: 'APPLIED' | 'REJECTED'; reason?: string; rationale?: string }>;
  changed_files: string[]; diff?: string | null;
  diff_stat: { additions: number; deletions: number; files: number; repair_attempts?: number } | null;
  summary: string | null; error: string | null; validation_verdict: string;
  validation_summary?: ValidationSummary | null; validated_at?: string | null;
  commit_sha: string | null; commit_message: string | null; checks: ValidationCheck[];
  created_at: string; finished_at: string | null;
}

export interface MergeRequest {
  id: string; status: string; review_status: string; title: string; description: string;
  source_branch: string; target_branch: string; commit_sha: string | null; validation_verdict: string;
  failed_validation_acknowledged: boolean;
  remote_status: 'NOT_ATTEMPTED' | 'REMOTE_CREATED' | 'REMOTE_FAILED' | 'REMOTE_UNAVAILABLE';
  remote_provider: string | null; remote_url: string | null; remote_identifier: string | null; remote_error: string | null;
  pushed: boolean; error: string | null; run: DevelopmentRun | null;
}

export interface DeploymentStep { name: string; status: string; detail: string | null; exit_code: number | null; output: string | null; at: string | null }
export interface Deployment {
  status: string; attempt: number; commit_sha: string | null; artifact_path: string | null; artifact_sha256: string | null;
  steps: DeploymentStep[]; health_check: unknown; log: string | null; error: string | null;
  started_at: string | null; finished_at: string | null;
  evidence?: Record<string, unknown> | null;
  verification_level?: 'FULLY_VERIFIED' | 'VERSION_VERIFIED' | 'SMOKE_VERIFIED' | 'HEALTH_ONLY' | 'COMMAND_ONLY' | 'NONE' | null;
}

export interface WorkflowEvent {
  id: string; event_type: string; from_stage: string | null; to_stage: string | null; actor: string | null;
  message: string | null; detail: unknown; created_at: string;
}

export interface ExecutionReport {
  task_id: string; generated_at: string; workflow_stage: WorkflowStage; implementation_completed: boolean;
  requirement: unknown; repository: unknown;
  verified: Record<string, unknown>;
  recommendations: Record<string, unknown>;
  unverified: Record<string, unknown>;
  unavailable: string[]; unresolved_issues: string[];
}

export interface ActionRequest {
  decision?: string;
  comment?: string;
  feedback?: string;
  title?: string;
  description?: string;
  acknowledge_validation_risk?: boolean;
  plan_id?: string;
  mr_id?: string;
}
