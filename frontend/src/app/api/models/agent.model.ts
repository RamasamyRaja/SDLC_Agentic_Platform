export interface ToolDefinition {
  name: string;
  description: string;
  parameters?: Record<string, unknown>;
}

export interface ToolInvocationRequest {
  parameters?: Record<string, unknown>;
}

export interface ToolInvocationResult {
  tool_name: string;
  status: 'success' | 'failed';
  output?: string;
  error?: string;
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'agent' | 'system';
  content: string;
  timestamp: string;
  type?: 'request' | 'summary' | 'context' | 'tool' | 'result';
}

export interface Artifact {
  id: string;
  name: string;
  type: string;
  size?: number;
  created_at: string;
  content_preview?: string;
}
