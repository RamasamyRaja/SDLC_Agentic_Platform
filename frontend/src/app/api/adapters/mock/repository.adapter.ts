import { Observable, of, delay, throwError } from 'rxjs';
import {
  Repository,
  RepositoryAnalysis,
  RepositoryCreateRequest,
  RepositoryDocument,
  RepositoryIndexStatus,
  RepositoryIndexResult,
  RepositoryOnboarding,
  SearchRequest,
  SearchResult,
} from '../../models/repository.model';
import { RepositoryPort } from '../../ports/repository.port';
import {
  MOCK_REPOSITORIES,
  MOCK_ANALYSIS,
  MOCK_DOCUMENTS,
  MOCK_INDEX_STATUS,
} from './repository.fixtures';

export class MockRepositoryAdapter implements RepositoryPort {
  private repos = [...MOCK_REPOSITORIES];

  list(): Observable<Repository[]> {
    return of([...this.repos]).pipe(delay(300));
  }

  getById(id: string): Observable<Repository> {
    const repo = this.repos.find((r) => r.id === id);
    return repo ? of({ ...repo }).pipe(delay(200)) : throwError(() => new Error('Repository not found'));
  }

  create(req: RepositoryCreateRequest): Observable<Repository> {
    const repo: Repository = {
      id: `repo-${Date.now()}`,
      name: req.name,
      url: req.url,
      branch: req.branch ?? 'main',
      provider: req.provider ?? 'github',
      analysis_status: 'not_started',
      indexing_status: 'not_started',
      task_count: 0,
      created_at: new Date().toISOString(),
    };
    this.repos.push(repo);
    return of(repo).pipe(delay(400));
  }

  onboard(id: string): Observable<RepositoryOnboarding> {
    const repo = this.repos.find((r) => r.id === id);
    if (repo) {
      repo.analysis_status = 'analyzing';
      repo.indexing_status = 'pending';
    }
    return of({
      repository_id: id, status: 'completed' as const, workspace_path: '/workspace/mock', languages: ['TypeScript', 'Python'],
      files_analyzed: 42, files_skipped: 0, parse_error_count: 0, parse_errors: [], symbols: [], classes: [],
      functions: [], imports: [], calls: [], dependencies: [], files: [],
    }).pipe(delay(500));
  }

  getAnalysis(id: string): Observable<RepositoryAnalysis> {
    const analysis = MOCK_ANALYSIS[id] ?? {
      repository_id: id,
      status: 'not_started' as const,
      files_analyzed: 0,
      languages: {},
      functions_count: 0,
      classes_count: 0,
      chunks_count: 0,
    };
    return of({ ...analysis }).pipe(delay(250));
  }

  getDocuments(id: string): Observable<RepositoryDocument[]> {
    return of(MOCK_DOCUMENTS[id] ?? []).pipe(delay(200));
  }

  index(id: string): Observable<RepositoryIndexResult> {
    const repo = this.repos.find((r) => r.id === id);
    if (repo) repo.indexing_status = 'indexing';
    return of({ repository_id: id, status: 'indexed' as const, chunks_created: 120, chunks_unchanged: 0, chunks_removed: 0, embeddings_generated: 120, total_chunks: 120 }).pipe(delay(400));
  }

  getIndexStatus(id: string): Observable<RepositoryIndexStatus> {
    return of(MOCK_INDEX_STATUS[id] ?? { status: 'not_started' }).pipe(delay(200));
  }

  search(id: string, req: SearchRequest): Observable<SearchResult[]> {
    return of([
      { path: 'src/agent/tools.py', content: 'def invoke_tool(name, params)...', score: 0.92, language: 'python' },
      { path: 'src/agent/graph.py', content: 'def build_agent_graph(tools, llm)...', score: 0.87, language: 'python' },
    ]).pipe(delay(300));
  }
}
