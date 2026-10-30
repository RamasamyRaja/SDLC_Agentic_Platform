import { inject } from '@angular/core';
import { catchError, Observable } from 'rxjs';
import { RepositoryPort, REPOSITORY_PORT } from '../../ports/repository.port';
import { RepositoryCreateRequest, SearchRequest } from '../../models/repository.model';
import { FastApiRepositoryAdapter } from '../fastapi/repository.adapter';
import { MockRepositoryAdapter } from '../mock/repository.adapter';

export class FallbackRepositoryAdapter implements RepositoryPort {
  private readonly fastApi = inject(FastApiRepositoryAdapter);
  private readonly mock = inject(MockRepositoryAdapter);

  list() {
    return this.fastApi.list().pipe(catchError(() => this.mock.list()));
  }

  getById(id: string) {
    return this.fastApi.getById(id).pipe(catchError(() => this.mock.getById(id)));
  }

  create(req: RepositoryCreateRequest) {
    return this.fastApi.create(req).pipe(catchError(() => this.mock.create(req)));
  }

  onboard(id: string) {
    return this.fastApi.onboard(id).pipe(catchError(() => this.mock.onboard(id)));
  }

  getAnalysis(id: string) {
    return this.fastApi.getAnalysis(id).pipe(catchError(() => this.mock.getAnalysis(id)));
  }

  getDocuments(id: string) {
    return this.fastApi.getDocuments(id).pipe(catchError(() => this.mock.getDocuments(id)));
  }

  index(id: string) {
    return this.fastApi.index(id).pipe(catchError(() => this.mock.index(id)));
  }

  getIndexStatus(id: string) {
    return this.fastApi.getIndexStatus(id).pipe(catchError(() => this.mock.getIndexStatus(id)));
  }

  search(id: string, req: SearchRequest) {
    return this.fastApi.search(id, req).pipe(catchError(() => this.mock.search(id, req)));
  }
}

// Needed for inject() in class - register as providers
export function provideRepositoryPort() {
  return [
    FastApiRepositoryAdapter,
    MockRepositoryAdapter,
    { provide: REPOSITORY_PORT, useClass: FallbackRepositoryAdapter },
  ];
}
