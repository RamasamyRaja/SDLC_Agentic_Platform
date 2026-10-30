import { inject } from '@angular/core';
import { map, Observable } from 'rxjs';
import { ApiClient } from '@core/http/api-client.service';
import { Artifact, ToolDefinition, ToolInvocationRequest, ToolInvocationResult } from '../../models/agent.model';
import { Execution, RunAgentRequest, RunAgentResponse } from '../../models/execution.model';
import { AgentPort } from '../../ports/agent.port';

interface AgentRunDto {
  execution_id: string;
  task_id: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED';
  action: string | null;
  model_name: string | null;
  reasoning_result: unknown | null;
  errors: string[];
  validation?: Record<string, unknown> | null;
  changed_files?: string[];
  repair_attempts?: number;
  final_diff?: string | null;
}

interface ExecutionDto {
  id: string;
  task_id: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED';
  action: string | null;
  model_name: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

interface ToolListDto { tools: ToolDefinition[] }
interface ToolInvokeDto { tool_name: string; output: Record<string, unknown> }
interface ArtifactDto { id: string; task_id: string; file_path: string; artifact_type: string; notes: string | null; created_at: string }

export class FastApiAgentAdapter implements AgentPort {
  private readonly api = inject(ApiClient);

  run(taskId: string, _req?: RunAgentRequest): Observable<RunAgentResponse> {
    return this.api.post<AgentRunDto>(`/tasks/${taskId}/run`, { execute_changes: true, run_validation: true }).pipe(map((item) => ({
      execution_id: item.execution_id,
      task_id: item.task_id,
      status: item.status.toLowerCase() as RunAgentResponse['status'],
      action: item.action ?? undefined,
      model_name: item.model_name ?? undefined,
      reasoning_result: item.reasoning_result ?? undefined,
      errors: item.errors,
    })));
  }

  getRunStatus(taskId: string, executionId: string): Observable<Execution> {
    return this.api.get<ExecutionDto>(`/tasks/${taskId}/run/${executionId}`).pipe(map((item) => ({
      id: item.id,
      task_id: item.task_id,
      status: this.toExecutionStatus(item.status),
      started_at: item.created_at,
      completed_at: item.status === 'RUNNING' ? undefined : item.updated_at,
      stdout: item.result ? JSON.stringify(item.result, null, 2) : undefined,
      stderr: item.error ?? undefined,
      command: item.action ?? undefined,
      sandbox_status: 'not_available_in_m7',
    })));
  }

  listTools(_taskId: string): Observable<ToolDefinition[]> {
    return this.api.get<ToolListDto>('/tasks/' + _taskId + '/tools').pipe(map((item) => item.tools));
  }

  invokeTool(taskId: string, toolName: string, req?: ToolInvocationRequest): Observable<ToolInvocationResult> {
    return this.api.post<ToolInvokeDto>(`/tasks/${taskId}/tools/${toolName}`, { input: req?.parameters ?? {} }).pipe(map((item) => ({
      tool_name: item.tool_name,
      status: 'success',
      output: JSON.stringify(item.output, null, 2),
    })));
  }

  listArtifacts(taskId: string): Observable<Artifact[]> {
    return this.api.get<ArtifactDto[]>(`/tasks/${taskId}/artifacts`).pipe(map((items) => items.map((item) => ({
      id: item.id, name: item.file_path.split('/').pop() ?? item.file_path, type: item.artifact_type,
      created_at: item.created_at, content_preview: item.notes ?? undefined,
    }))));
  }

  uploadArtifact(taskId: string, file: File): Observable<Artifact> {
    return this.api.post<ArtifactDto>(`/tasks/${taskId}/artifacts`, {
      file_path: file.name,
      artifact_type: 'OTHER',
      notes: `Registered from frontend file selector (${file.size} bytes).`,
    }).pipe(map((item) => ({
      id: item.id, name: item.file_path.split('/').pop() ?? item.file_path, type: item.artifact_type,
      created_at: item.created_at, content_preview: item.notes ?? undefined,
    })));
  }

  private toExecutionStatus(status: ExecutionDto['status']): Execution['status'] {
    if (status === 'COMPLETED') return 'success';
    if (status === 'FAILED') return 'failed';
    return 'running';
  }
}
