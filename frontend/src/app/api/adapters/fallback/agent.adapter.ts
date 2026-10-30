import { inject } from '@angular/core';
import { catchError } from 'rxjs';
import { AgentPort, AGENT_PORT } from '../../ports/agent.port';
import { RunAgentRequest } from '../../models/execution.model';
import { ToolInvocationRequest } from '../../models/agent.model';
import { FastApiAgentAdapter } from '../fastapi/agent.adapter';
import { MockAgentAdapter } from '../mock/agent.adapter';

export class FallbackAgentAdapter implements AgentPort {
  private readonly fastApi = inject(FastApiAgentAdapter);
  private readonly mock = inject(MockAgentAdapter);

  run(taskId: string, req?: RunAgentRequest) {
    return this.fastApi.run(taskId, req).pipe(catchError(() => this.mock.run(taskId, req)));
  }

  getRunStatus(taskId: string, executionId: string) {
    return this.fastApi.getRunStatus(taskId, executionId).pipe(
      catchError(() => this.mock.getRunStatus(taskId, executionId)),
    );
  }

  listTools(taskId: string) {
    return this.fastApi.listTools(taskId).pipe(catchError(() => this.mock.listTools(taskId)));
  }

  invokeTool(taskId: string, toolName: string, req?: ToolInvocationRequest) {
    return this.fastApi.invokeTool(taskId, toolName, req).pipe(
      catchError(() => this.mock.invokeTool(taskId, toolName, req)),
    );
  }

  listArtifacts(taskId: string) {
    return this.fastApi.listArtifacts(taskId).pipe(catchError(() => this.mock.listArtifacts(taskId)));
  }

  uploadArtifact(taskId: string, file: File) {
    return this.fastApi.uploadArtifact(taskId, file).pipe(
      catchError(() => this.mock.uploadArtifact(taskId, file)),
    );
  }
}

export function provideAgentPort() {
  return [
    FastApiAgentAdapter,
    MockAgentAdapter,
    { provide: AGENT_PORT, useClass: FallbackAgentAdapter },
  ];
}
