import { Observable, of, delay, throwError } from 'rxjs';
import { Task, TaskAnalysis, TaskCreateRequest, TaskStatusPatch } from '../../models/task.model';
import { TaskPort } from '../../ports/task.port';
import { MOCK_TASKS } from './task.fixtures';

export class MockTaskAdapter implements TaskPort {
  private tasks = [...MOCK_TASKS];

  list(): Observable<Task[]> {
    return of([...this.tasks]).pipe(delay(300));
  }

  getById(id: string): Observable<Task> {
    const task = this.tasks.find((t) => t.id === id);
    return task ? of({ ...task }).pipe(delay(200)) : throwError(() => new Error('Task not found'));
  }

  create(req: TaskCreateRequest): Observable<Task> {
    const task: Task = {
      id: `task-${Date.now()}`,
      title: req.title,
      description: req.description,
      repository_id: req.repository_id,
      branch: req.branch ?? 'main',
      status: 'pending',
      priority: req.priority ?? 'medium',
      agent_state: 'idle',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    this.tasks.push(task);
    return of(task).pipe(delay(400));
  }

  updateStatus(id: string, patch: TaskStatusPatch): Observable<Task> {
    const task = this.tasks.find((t) => t.id === id);
    if (!task) return throwError(() => new Error('Task not found'));
    task.status = patch.status;
    task.updated_at = new Date().toISOString();
    return of({ ...task }).pipe(delay(300));
  }

  analyze(id: string): Observable<TaskAnalysis> {
    const task = this.tasks.find((t) => t.id === id);
    if (task) task.status = 'running';
    return of({
      task_id: id, model: 'mock', prompt_version: 'v1',
      result: { summary: 'Mock analysis result.', understanding: { goal: task?.description ?? 'Task analysis', affected_area: 'Repository' },
        relevant_files: [], affected_symbols: [], implementation_plan: [], dependencies: [], risks: [], uncertainties: [], confidence: 0.5 }
    }).pipe(delay(500));
  }
}
