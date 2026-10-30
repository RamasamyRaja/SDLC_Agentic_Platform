import { inject } from '@angular/core';
import { catchError } from 'rxjs';
import { TaskPort, TASK_PORT } from '../../ports/task.port';
import { TaskCreateRequest, TaskStatusPatch } from '../../models/task.model';
import { FastApiTaskAdapter } from '../fastapi/task.adapter';
import { MockTaskAdapter } from '../mock/task.adapter';

export class FallbackTaskAdapter implements TaskPort {
  private readonly fastApi = inject(FastApiTaskAdapter);
  private readonly mock = inject(MockTaskAdapter);

  list() {
    return this.fastApi.list().pipe(catchError(() => this.mock.list()));
  }

  getById(id: string) {
    return this.fastApi.getById(id).pipe(catchError(() => this.mock.getById(id)));
  }

  create(req: TaskCreateRequest) {
    return this.fastApi.create(req).pipe(catchError(() => this.mock.create(req)));
  }

  updateStatus(id: string, patch: TaskStatusPatch) {
    return this.fastApi.updateStatus(id, patch).pipe(catchError(() => this.mock.updateStatus(id, patch)));
  }

  analyze(id: string) {
    return this.fastApi.analyze(id).pipe(catchError(() => this.mock.analyze(id)));
  }
}

export function provideTaskPort() {
  return [
    FastApiTaskAdapter,
    MockTaskAdapter,
    { provide: TASK_PORT, useClass: FallbackTaskAdapter },
  ];
}
