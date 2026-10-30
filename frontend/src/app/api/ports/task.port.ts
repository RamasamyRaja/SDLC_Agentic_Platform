import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import { Task, TaskAnalysis, TaskCreateRequest, TaskStatusPatch } from '../models/task.model';

export interface TaskPort {
  list(): Observable<Task[]>;
  getById(id: string): Observable<Task>;
  create(req: TaskCreateRequest): Observable<Task>;
  updateStatus(id: string, patch: TaskStatusPatch): Observable<Task>;
  analyze(id: string): Observable<TaskAnalysis>;
}

export const TASK_PORT = new InjectionToken<TaskPort>('TASK_PORT');
