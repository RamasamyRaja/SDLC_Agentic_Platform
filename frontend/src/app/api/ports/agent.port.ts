import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Artifact,
  ToolDefinition,
  ToolInvocationRequest,
  ToolInvocationResult,
} from '../models/agent.model';
import { Execution, RunAgentRequest, RunAgentResponse } from '../models/execution.model';

export interface AgentPort {
  run(taskId: string, req?: RunAgentRequest): Observable<RunAgentResponse>;
  getRunStatus(taskId: string, executionId: string): Observable<Execution>;
  listTools(taskId: string): Observable<ToolDefinition[]>;
  invokeTool(taskId: string, toolName: string, req?: ToolInvocationRequest): Observable<ToolInvocationResult>;
  listArtifacts(taskId: string): Observable<Artifact[]>;
  uploadArtifact(taskId: string, file: File): Observable<Artifact>;
}

export const AGENT_PORT = new InjectionToken<AgentPort>('AGENT_PORT');
