import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import { Execution } from '../models/execution.model';

export interface ExecutionHistoryPort {
  list(): Observable<Execution[]>;
  getById(taskId: string, executionId: string): Observable<Execution | null>;
  register(execution: Execution): void;
}

export const EXECUTION_HISTORY_PORT = new InjectionToken<ExecutionHistoryPort>('EXECUTION_HISTORY_PORT');
