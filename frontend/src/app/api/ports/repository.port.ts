import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Repository,
  RepositoryAnalysis,
  RepositoryCreateRequest,
  RepositoryDocument,
  RepositoryIndexStatus,
  RepositoryOnboarding,
  RepositoryIndexResult,
  SearchRequest,
  SearchResult,
} from '../models/repository.model';

export interface RepositoryPort {
  list(): Observable<Repository[]>;
  getById(id: string): Observable<Repository>;
  create(req: RepositoryCreateRequest): Observable<Repository>;
  onboard(id: string): Observable<RepositoryOnboarding>;
  getAnalysis(id: string): Observable<RepositoryAnalysis>;
  getDocuments(id: string): Observable<RepositoryDocument[]>;
  index(id: string): Observable<RepositoryIndexResult>;
  getIndexStatus(id: string): Observable<RepositoryIndexStatus>;
  search(id: string, req: SearchRequest): Observable<SearchResult[]>;
}

export const REPOSITORY_PORT = new InjectionToken<RepositoryPort>('REPOSITORY_PORT');
