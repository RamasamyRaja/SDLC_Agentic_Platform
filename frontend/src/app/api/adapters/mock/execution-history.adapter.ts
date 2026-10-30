import { Observable, of, delay } from 'rxjs';
import { ExecutionHistoryPort } from '../../ports/execution-history.port';
import { Execution } from '../../models/execution.model';
import { MOCK_EXECUTIONS } from './execution.fixtures';
import { environment } from '../../../../environments/environment';

const STORAGE_KEY = 'rad-execution-history';

export class LocalExecutionHistoryAdapter implements ExecutionHistoryPort {
  list(): Observable<Execution[]> {
    const stored = this.loadStored();
    const base = environment.apiProvider === 'fastapi' ? [] : MOCK_EXECUTIONS;
    const merged = this.mergeExecutions(base, stored);
    return of(merged).pipe(delay(200));
  }

  getById(taskId: string, executionId: string): Observable<Execution | null> {
    const base = environment.apiProvider === 'fastapi' ? [] : MOCK_EXECUTIONS;
    const all = this.mergeExecutions(base, this.loadStored());
    const exec = all.find((e) => e.id === executionId && e.task_id === taskId) ?? null;
    return of(exec ? { ...exec } : null).pipe(delay(150));
  }

  register(execution: Execution): void {
    const stored = this.loadStored();
    const idx = stored.findIndex((e) => e.id === execution.id);
    if (idx >= 0) stored[idx] = execution;
    else stored.unshift({ ...execution, is_local: true });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored.slice(0, 50)));
  }

  private loadStored(): Execution[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as Execution[]) : [];
    } catch {
      return [];
    }
  }

  private mergeExecutions(base: Execution[], stored: Execution[]): Execution[] {
    const map = new Map<string, Execution>();
    for (const e of base) map.set(e.id, e);
    for (const e of stored) map.set(e.id, { ...e, is_local: true });
    return Array.from(map.values()).sort(
      (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
    );
  }
}
