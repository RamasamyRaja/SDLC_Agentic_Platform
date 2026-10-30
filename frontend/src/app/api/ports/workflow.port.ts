import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import {
  ActionRequest, Deployment, DevelopmentRun, ExecutionReport, MergeRequest, TaskAction, TaskCreatePayload,
  TaskCreateResult, TaskDetail, TaskPlan, TaskSummary, WorkflowEvent, WorkflowSummary,
} from '../models/workflow.model';

/**
 * Task lifecycle port. There is intentionally NO mock/fallback implementation: the lifecycle is
 * server-enforced, so a simulated backend would misrepresent real state.
 */
export interface WorkflowPort {
  list(filters?: { repository_id?: string; workflow_stage?: string }): Observable<TaskSummary[]>;
  summary(): Observable<WorkflowSummary>;
  get(id: string): Observable<TaskDetail>;
  create(payload: TaskCreatePayload): Observable<TaskCreateResult>;
  perform(taskId: string, action: TaskAction, body: ActionRequest): Observable<unknown>;
  plan(taskId: string): Observable<TaskPlan | null>;
  plans(taskId: string): Observable<TaskPlan[]>;
  runs(taskId: string): Observable<DevelopmentRun[]>;
  run(taskId: string, runId: string): Observable<DevelopmentRun>;
  mergeRequest(taskId: string): Observable<MergeRequest | null>;
  deployment(taskId: string): Observable<Deployment | null>;
  events(taskId: string): Observable<WorkflowEvent[]>;
  report(taskId: string): Observable<ExecutionReport>;
}

export const WORKFLOW_PORT = new InjectionToken<WorkflowPort>('WORKFLOW_PORT');
