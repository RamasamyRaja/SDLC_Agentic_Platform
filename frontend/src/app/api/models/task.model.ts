export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'analyzing';
export type TaskPriority = 'low' | 'medium' | 'high' | 'critical';
export type AgentState = 'idle' | 'planning' | 'executing' | 'waiting' | 'completed' | 'failed';

export interface Task {
  id: string;
  title: string;
  description?: string;
  repository_id: string;
  repository_name?: string;
  branch?: string;
  status: TaskStatus;
  priority?: TaskPriority;
  agent_state?: AgentState;
  created_at?: string;
  updated_at?: string;
  reasoning_summary?: string;
  result_summary?: string;
  relevant_files?: string[];
  retrieved_context?: RetrievedContext[];
  tool_invocations?: ToolInvocation[];
}

export interface TaskCreateRequest {
  title: string;
  description?: string;
  repository_id: string;
  branch?: string;
  priority?: TaskPriority;
}

export interface TaskAnalysis {
  task_id: string;
  model: string;
  prompt_version: string;
  result: {
    summary: string;
    understanding: { goal: string; affected_area: string };
    relevant_files: Array<{ file_path: string; reason: string; confidence: number; grounded?: boolean }>;
    affected_symbols: Array<{ file_path: string; symbol_name: string; reason: string; grounded?: boolean }>;
    implementation_plan: Array<{ step: number; description: string; target_files: string[] }>;
    dependencies: string[];
    risks: string[];
    uncertainties: string[];
    confidence: number;
  };
}

export interface TaskStatusPatch {
  status: TaskStatus;
}

export interface RetrievedContext {
  path: string;
  snippet: string;
  relevance?: number;
}

export interface ToolInvocation {
  id: string;
  tool_name: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  started_at?: string;
  completed_at?: string;
  input_summary?: string;
  output_summary?: string;
}
