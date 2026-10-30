import { inject } from '@angular/core';
import { catchError, Observable, of, throwError } from 'rxjs';
import { ApiClient } from '@core/http/api-client.service';
import { isApiError } from '@core/http/api-error.model';
import {
  ActionRequest, Deployment, DevelopmentRun, ExecutionReport, MergeRequest, TaskAction, TaskCreatePayload,
  TaskCreateResult, TaskDetail, TaskPlan, TaskSummary, WorkflowSummary, WorkflowEvent,
} from '../../models/workflow.model';
import { WorkflowPort } from '../../ports/workflow.port';

/** The server action endpoint is absolute (`/api/tasks/...`); ApiClient already prefixes `/api`. */
export function actionPath(endpoint: string): string {
  return endpoint.replace(/^\/api(?=\/)/, '');
}

export class FastApiWorkflowAdapter implements WorkflowPort {
  private readonly api = inject(ApiClient);

  list(filters: { repository_id?: string; workflow_stage?: string } = {}): Observable<TaskSummary[]> {
    return this.api.get<TaskSummary[]>('/tasks', filters);
  }
  summary(): Observable<WorkflowSummary> { return this.api.get<WorkflowSummary>('/tasks/summary'); }
  get(id: string): Observable<TaskDetail> { return this.api.get<TaskDetail>(`/tasks/${id}`); }
  create(payload: TaskCreatePayload): Observable<TaskCreateResult> { return this.api.post<TaskCreateResult>('/tasks', payload); }

  perform(taskId: string, action: TaskAction, body: ActionRequest): Observable<unknown> {
    const payload: ActionRequest = {};
    if (action.decision) payload.decision = action.decision;
    if (body.comment?.trim()) payload.comment = body.comment.trim();
    if (action.key === 'start_planning' || action.key === 'start_implementation') {
      if (body.comment?.trim()) payload.feedback = body.comment.trim();
      delete payload.comment;
    }
    if (action.key === 'create_merge_request') {
      payload.acknowledge_validation_risk = !!body.acknowledge_validation_risk;
      if (body.title?.trim()) payload.title = body.title.trim();
      if (body.description?.trim()) payload.description = body.description.trim();
    }
    const noBody = action.key === 'run_validation' || action.key === 'deploy';
    return this.api.post<unknown>(actionPath(action.endpoint.replace('{id}', taskId)), noBody ? undefined : payload);
  }

  plan(taskId: string): Observable<TaskPlan | null> { return this.orNull(this.api.get<TaskPlan>(`/tasks/${taskId}/plan`)); }
  plans(taskId: string): Observable<TaskPlan[]> { return this.api.get<TaskPlan[]>(`/tasks/${taskId}/plans`); }
  runs(taskId: string): Observable<DevelopmentRun[]> { return this.api.get<DevelopmentRun[]>(`/tasks/${taskId}/development-runs`); }
  run(taskId: string, runId: string): Observable<DevelopmentRun> { return this.api.get<DevelopmentRun>(`/tasks/${taskId}/development-runs/${runId}`); }
  mergeRequest(taskId: string): Observable<MergeRequest | null> { return this.orNull(this.api.get<MergeRequest>(`/tasks/${taskId}/merge-request`)); }
  deployment(taskId: string): Observable<Deployment | null> { return this.orNull(this.api.get<Deployment>(`/tasks/${taskId}/deployment`)); }
  events(taskId: string): Observable<WorkflowEvent[]> { return this.api.get<WorkflowEvent[]>(`/tasks/${taskId}/events`); }
  report(taskId: string): Observable<ExecutionReport> { return this.api.get<ExecutionReport>(`/tasks/${taskId}/report`); }

  /** 404 means "this stage has not produced a resource yet"; anything else is a real error. */
  private orNull<T>(source: Observable<T>): Observable<T | null> {
    return source.pipe(catchError((err: unknown) =>
      isApiError(err) && err.status === 404 ? of(null) : throwError(() => err)));
  }
}
