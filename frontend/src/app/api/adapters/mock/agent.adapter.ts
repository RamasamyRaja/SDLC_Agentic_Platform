import { Observable, of, delay } from 'rxjs';
import {
  Artifact,
  ToolDefinition,
  ToolInvocationRequest,
  ToolInvocationResult,
} from '../../models/agent.model';
import { Execution, RunAgentRequest, RunAgentResponse } from '../../models/execution.model';
import { AgentPort } from '../../ports/agent.port';
import { MOCK_EXECUTIONS } from './execution.fixtures';

const MOCK_TOOLS: ToolDefinition[] = [
  { name: 'read_file', description: 'Read file contents from the repository sandbox' },
  { name: 'write_file', description: 'Write or modify a file in the sandbox' },
  { name: 'search_code', description: 'Search indexed code chunks via vector retrieval' },
  { name: 'run_command', description: 'Execute a shell command in the Docker sandbox' },
  { name: 'list_directory', description: 'List directory contents in the sandbox' },
];

export class MockAgentAdapter implements AgentPort {
  run(taskId: string, _req?: RunAgentRequest): Observable<RunAgentResponse> {
    const executionId = `exec-${Date.now()}`;
    return of({ execution_id: executionId, status: 'running' as const }).pipe(delay(400));
  }

  getRunStatus(taskId: string, executionId: string): Observable<Execution> {
    const exec = MOCK_EXECUTIONS.find((e) => e.id === executionId) ?? {
      id: executionId,
      task_id: taskId,
      status: 'running' as const,
      started_at: new Date().toISOString(),
      tools_used: ['read_file'],
      sandbox_status: 'active',
      stdout: 'Agent execution in progress...',
      is_local: true,
    };
    return of({ ...exec }).pipe(delay(200));
  }

  listTools(_taskId: string): Observable<ToolDefinition[]> {
    return of([...MOCK_TOOLS]).pipe(delay(150));
  }

  invokeTool(_taskId: string, toolName: string, _req?: ToolInvocationRequest): Observable<ToolInvocationResult> {
    return of({
      tool_name: toolName,
      status: 'success' as const,
      output: `Tool ${toolName} executed successfully in sandbox.`,
    }).pipe(delay(500));
  }

  listArtifacts(taskId: string): Observable<Artifact[]> {
    return of([
      { id: 'art-1', name: 'analysis-report.md', type: 'markdown', size: 4200, created_at: '2026-09-01T07:00:00Z' },
      { id: 'art-2', name: 'diff.patch', type: 'patch', size: 1800, created_at: '2026-09-01T07:15:00Z' },
    ]).pipe(delay(200));
  }

  uploadArtifact(_taskId: string, file: File): Observable<Artifact> {
    return of({
      id: `art-${Date.now()}`,
      name: file.name,
      type: file.type || 'file',
      size: file.size,
      created_at: new Date().toISOString(),
    }).pipe(delay(400));
  }
}
