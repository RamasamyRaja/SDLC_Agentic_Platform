import { inject } from '@angular/core';
import { catchError, forkJoin, map, Observable, of, switchMap } from 'rxjs';
import { ApiClient } from '@core/http/api-client.service';
import {
  AnalysisStatus,
  IndexStatus,
  Repository,
  RepositoryAnalysis,
  RepositoryCreateRequest,
  RepositoryDocument,
  RepositoryIndexResult,
  RepositoryIndexStatus,
  RepositoryOnboarding,
  SearchRequest,
  SearchResult,
} from '../../models/repository.model';
import { RepositoryPort } from '../../ports/repository.port';

interface RepositoryDto {
  id: string;
  user_id: string;
  name: string;
  url: string;
  default_branch: string;
  default_branch_source?: 'remote_head' | 'user_specified' | 'fallback';
  commit_sha?: string | null;
  onboarding_error?: string | null;
  workspace_path: string | null;
  status: 'PENDING' | 'CLONING' | 'ANALYZING' | 'READY' | 'ERROR';
  created_at: string;
  updated_at: string;
}

interface OnboardingDto {
  repository_id: string;
  status: RepositoryDto['status'];
  workspace_path: string;
  commit_sha: string | null;
  languages: string[];
  files_analyzed: number;
  files_skipped: number;
  parse_error_count: number;
  parse_errors: unknown[];
  symbols: unknown[];
  classes: unknown[];
  functions: unknown[];
  imports: unknown[];
  calls: unknown[];
  dependencies: unknown[];
  files: unknown[];
}

interface AnalysisDto {
  repository_id: string;
  status: RepositoryDto['status'];
  commit_sha: string | null;
  detected_languages: string[] | null;
  files_analyzed_count: number | null;
  files_skipped_count: number | null;
  parse_error_count: number | null;
  last_onboarded_at: string | null;
  onboarding_error: string | null;
  summary?: string | null;
}

interface DocumentDto {
  id: string;
  repository_id: string;
  file_path: string;
  language: string | null;
  file_size: number;
  content_hash: string;
  analysis_status: string;
  created_at: string;
}

interface IndexDto {
  repository_id: string;
  status: 'NOT_INDEXED' | 'INDEXING' | 'INDEXED' | 'FAILED';
  chunks_created: number;
  chunks_unchanged: number;
  chunks_removed: number;
  embeddings_generated: number;
  total_chunks: number;
}

interface IndexStatusDto {
  repository_id: string;
  indexing_status: IndexDto['status'];
  indexed_chunk_count: number | null;
  last_indexed_at: string | null;
  indexing_error: string | null;
}

interface ReadinessDto {
  status: string;
  error: string | null;
  commit_sha: string | null;
  onboarding: { phase: string | null; interrupted: boolean };
  indexing: {
    status: IndexDto['status']; phase: string | null; chunks_done: number | null; chunks_total: number | null;
    indexed_chunk_count: number | null; last_indexed_at: string | null; indexed_commit_sha: string | null;
    error: string | null; interrupted: boolean;
  };
  documents: { total: number; by_status: Record<string, number>; by_language: Record<string, number>; pending_index: number };
  stale: boolean;
  ready_for_retrieval: boolean;
  reasons: string[];
}

interface SearchDto {
  query: string;
  results: Array<{
    chunk_id: string;
    file_path: string;
    symbol_name: string | null;
    chunk_type: string;
    language: string | null;
    score: number;
    content: string;
  }>;
}

export class FastApiRepositoryAdapter implements RepositoryPort {
  private readonly api = inject(ApiClient);

  list(): Observable<Repository[]> {
    return this.api.get<RepositoryDto[]>('/repositories').pipe(
      switchMap((items) => items.length === 0
        ? of([] as Repository[])
        : forkJoin(items.map((item) => this.withIndexStatus(this.toRepository(item)))),
      ),
    );
  }

  getById(id: string): Observable<Repository> {
    return this.api.get<RepositoryDto>(`/repositories/${id}`).pipe(
      switchMap((item) => this.withIndexStatus(this.toRepository(item))),
    );
  }

  create(req: RepositoryCreateRequest): Observable<Repository> {
    return this.api.post<RepositoryDto>('/repositories', {
      url: req.url,
      branch: req.branch || undefined,
      name: req.name || undefined,
    }).pipe(map((item) => this.toRepository(item)));
  }

  onboard(id: string): Observable<RepositoryOnboarding> {
    return this.api.post<OnboardingDto>(`/repositories/${id}/onboard`, {}).pipe(map((item) => ({
      repository_id: item.repository_id,
      status: this.toAnalysisStatus(item.status),
      workspace_path: item.workspace_path,
      commit_sha: item.commit_sha ?? undefined,
      languages: item.languages,
      files_analyzed: item.files_analyzed,
      files_skipped: item.files_skipped,
      parse_error_count: item.parse_error_count,
      parse_errors: item.parse_errors,
      symbols: item.symbols,
      classes: item.classes,
      functions: item.functions,
      imports: item.imports,
      calls: item.calls,
      dependencies: item.dependencies,
      files: item.files,
    })));
  }

  getAnalysis(id: string): Observable<RepositoryAnalysis> {
    return this.api.get<AnalysisDto>(`/repositories/${id}/analysis`).pipe(map((item) => ({
      repository_id: item.repository_id,
      status: this.toAnalysisStatus(item.status),
      commit_sha: item.commit_sha ?? undefined,
      detected_languages: item.detected_languages ?? undefined,
      files_analyzed: item.files_analyzed_count ?? undefined,
      files_skipped: item.files_skipped_count ?? undefined,
      parse_error_count: item.parse_error_count ?? undefined,
      last_analyzed_at: item.last_onboarded_at ?? undefined,
      summary: item.summary ?? item.onboarding_error ?? undefined,
      languages: item.detected_languages?.reduce<Record<string, number>>((acc, language) => {
        acc[language] = 1;
        return acc;
      }, {}),
    })));
  }

  getDocuments(id: string): Observable<RepositoryDocument[]> {
    return this.api.get<DocumentDto[]>(`/repositories/${id}/documents`).pipe(
      map((items) => items.map((item) => ({
        path: item.file_path,
        name: item.file_path.split('/').pop() ?? item.file_path,
        type: 'file' as const,
        language: item.language ?? undefined,
        size: item.file_size,
      }))),
    );
  }

  index(id: string): Observable<RepositoryIndexResult> {
    return this.api.post<IndexDto>(`/repositories/${id}/index`, {}).pipe(map((item) => ({
      repository_id: item.repository_id,
      status: this.toIndexStatus(item.status),
      chunks_created: item.chunks_created,
      chunks_unchanged: item.chunks_unchanged,
      chunks_removed: item.chunks_removed,
      embeddings_generated: item.embeddings_generated,
      total_chunks: item.total_chunks,
    })));
  }

  getIndexStatus(id: string): Observable<RepositoryIndexStatus> {
    return this.api.get<ReadinessDto>(`/repositories/${id}/status`).pipe(map((r) => ({
      status: this.toIndexStatus(r.indexing.status),
      indexed_chunks: r.indexing.indexed_chunk_count ?? undefined,
      last_indexed_at: r.indexing.last_indexed_at ?? undefined,
      indexing_error: r.indexing.error ?? undefined,
      phase: r.indexing.phase,
      chunks_done: r.indexing.chunks_done,
      chunks_total: r.indexing.chunks_total,
      indexed_commit_sha: r.indexing.indexed_commit_sha,
      commit_sha: r.commit_sha,
      onboarding_phase: r.onboarding.phase,
      onboarding_error: r.error,
      onboarding_interrupted: r.onboarding.interrupted,
      indexing_interrupted: r.indexing.interrupted,
      stale: r.stale,
      ready_for_retrieval: r.ready_for_retrieval,
      reasons: r.reasons,
      documents_total: r.documents.total,
      documents_by_status: r.documents.by_status,
      documents_by_language: r.documents.by_language,
      documents_pending_index: r.documents.pending_index,
    })));
  }

  search(id: string, req: SearchRequest): Observable<SearchResult[]> {
    return this.api.post<SearchDto>(`/repositories/${id}/search`, {
      query: req.query,
      top_k: req.top_k ?? req.limit ?? 5,
    }).pipe(map((response) => response.results.map((item) => ({
      path: item.file_path,
      content: item.content,
      score: item.score,
      language: item.language ?? undefined,
    }))));
  }

  private withIndexStatus(repository: Repository): Observable<Repository> {
    return this.api.get<IndexStatusDto>(`/repositories/${repository.id}/index/status`).pipe(
      map((item) => ({ ...repository, indexing_status: this.toIndexStatus(item.indexing_status) })),
      catchError(() => of(repository)),
    );
  }

  private toRepository(item: RepositoryDto): Repository {
    return {
      id: item.id,
      name: item.name,
      url: item.url,
      branch: item.default_branch,
      branch_source: item.default_branch_source,
      commit_sha: item.commit_sha ?? undefined,
      onboarding_error: item.onboarding_error ?? undefined,
      provider: this.providerFromUrl(item.url),
      analysis_status: this.toAnalysisStatus(item.status),
      indexing_status: undefined,
      created_at: item.created_at,
      updated_at: item.updated_at,
      description: item.workspace_path ? `Workspace: ${item.workspace_path}` : undefined,
    };
  }

  private toAnalysisStatus(status: RepositoryDto['status']): AnalysisStatus {
    if (status === 'CLONING' || status === 'ANALYZING') return 'analyzing';
    if (status === 'READY') return 'completed';
    if (status === 'ERROR') return 'failed';
    return 'not_started';
  }

  private toIndexStatus(status: IndexDto['status']): IndexStatus {
    if (status === 'INDEXING') return 'indexing';
    if (status === 'INDEXED') return 'indexed';
    if (status === 'FAILED') return 'failed';
    return 'not_started';
  }

  private providerFromUrl(url: string): string | undefined {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (host.includes('github')) return 'github';
      if (host.includes('gitlab')) return 'gitlab';
      if (host.includes('bitbucket')) return 'bitbucket';
      return host;
    } catch {
      return undefined;
    }
  }
}
