import { inject } from '@angular/core';
import { map, Observable, switchMap } from 'rxjs';
import { ApiClient } from '@core/http/api-client.service';
import { Task, TaskAnalysis, TaskCreateRequest, TaskStatusPatch } from '../../models/task.model';
import { TaskPort } from '../../ports/task.port';

interface TaskDto {
  id: string;
  user_id: string;
  repository_id: string;
  title: string | null;
  description: string;
  branch: string | null;
  status: 'PENDING' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  created_at: string;
  updated_at: string;
}

interface TaskCreateDto {
  task_id: string;
  repository_id: string;
  status: TaskDto['status'];
}

interface TaskStatusDto {
  id: string;
  status: TaskDto['status'];
  updated_at: string;
}

export class FastApiTaskAdapter implements TaskPort {
  private readonly api = inject(ApiClient);

  list(): Observable<Task[]> {
    return this.api.get<TaskDto[]>('/tasks').pipe(map((items) => items.map((item) => this.toTask(item))));
  }

  getById(id: string): Observable<Task> {
    return this.api.get<TaskDto>(`/tasks/${id}`).pipe(map((item) => this.toTask(item)));
  }

  create(req: TaskCreateRequest): Observable<Task> {
    const description = (req.description ?? '').trim() || req.title.trim();
    return this.api.post<TaskCreateDto>('/tasks', {
      repository_id: req.repository_id,
      request: description,
      title: req.title.trim() || undefined,
      branch: req.branch?.trim() || undefined,
    }).pipe(
      map((created) => created.task_id),
      switchMap((taskId) => this.getById(taskId)),
    );
  }

  updateStatus(id: string, patch: TaskStatusPatch): Observable<Task> {
    return this.api.patch<TaskStatusDto>(`/tasks/${id}/status`, { status: patch.status.toUpperCase() }).pipe(
      switchMap(() => this.getById(id)),
    );
  }

  analyze(id: string): Observable<TaskAnalysis> {
    return this.api.post<TaskAnalysis>(`/tasks/${id}/analyze`, {});
  }

  private toTask(item: TaskDto): Task {
    return {
      id: item.id,
      title: item.title ?? 'Untitled task',
      description: item.description,
      repository_id: item.repository_id,
      branch: item.branch ?? undefined,
      status: item.status.toLowerCase() as Task['status'],
      created_at: item.created_at,
      updated_at: item.updated_at,
      agent_state: item.status === 'RUNNING' ? 'executing' : item.status === 'COMPLETED' ? 'completed' : item.status === 'FAILED' ? 'failed' : 'idle',
    };
  }
}
