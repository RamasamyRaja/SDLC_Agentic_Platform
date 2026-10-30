export type ExecutionStatus = 'running' | 'success' | 'failed' | 'timeout' | 'pending';

export interface Execution {
  id: string;
  task_id: string;
  task_title?: string;
  repository_id?: string;
  repository_name?: string;
  status: ExecutionStatus;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  exit_code?: number;
  tools_used?: string[];
  command?: string;
  sandbox_status?: string;
  stdout?: string;
  stderr?: string;
  steps?: ExecutionStep[];
  is_local?: boolean;
}

export interface ExecutionStep {
  id: string;
  name: string;
  status: ExecutionStatus;
  timestamp: string;
  detail?: string;
}

export interface RunAgentRequest {
  prompt?: string;
}

export interface RunAgentResponse {
  execution_id: string;
  task_id?: string;
  status: ExecutionStatus;
  action?: string;
  model_name?: string;
  reasoning_result?: unknown;
  errors?: string[];
  validation?: Record<string, unknown>;
  changed_files?: string[];
  repair_attempts?: number;
  final_diff?: string;
}
