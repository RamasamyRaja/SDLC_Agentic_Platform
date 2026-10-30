export type AnalysisStatus = 'pending' | 'analyzing' | 'completed' | 'failed' | 'not_started';
export type IndexStatus = 'pending' | 'indexing' | 'indexed' | 'failed' | 'not_started';

export interface Repository {
  id: string;
  name: string;
  url?: string;
  provider?: string;
  branch?: string;
  /** How the default branch was determined: remote_head (discovered), user_specified (verified) or fallback (could not be discovered). */
  branch_source?: 'remote_head' | 'user_specified' | 'fallback';
  commit_sha?: string;
  onboarding_error?: string;
  language?: string;
  analysis_status?: AnalysisStatus;
  indexing_status?: IndexStatus;
  task_count?: number;
  last_analyzed_at?: string;
  created_at?: string;
  updated_at?: string;
  description?: string;
}

export interface RepositoryCreateRequest {
  name: string;
  url: string;
  branch?: string;
  provider?: string;
}

export interface RepositoryAnalysis {
  repository_id: string;
  status: AnalysisStatus;
  commit_sha?: string;
  detected_languages?: string[];
  files_analyzed?: number;
  files_skipped?: number;
  parse_error_count?: number;
  languages?: Record<string, number>;
  functions_count?: number;
  classes_count?: number;
  chunks_count?: number;
  indexed_documents?: number;
  last_analyzed_at?: string;
  summary?: string;
}

export interface RepositoryDocument {
  path: string;
  name: string;
  type: 'file' | 'directory';
  language?: string;
  size?: number;
  children?: RepositoryDocument[];
}

/** Real readiness state from GET /repositories/{id}/status. Nothing here is estimated by the UI. */
export interface RepositoryIndexStatus {
  status: IndexStatus;
  indexed_chunks?: number;
  last_indexed_at?: string;
  indexing_error?: string;
  /** current / last embedding run counters (only the chunks that needed embedding) */
  phase?: string | null;
  chunks_done?: number | null;
  chunks_total?: number | null;
  indexed_commit_sha?: string | null;
  commit_sha?: string | null;
  onboarding_phase?: string | null;
  onboarding_error?: string | null;
  onboarding_interrupted?: boolean;
  indexing_interrupted?: boolean;
  stale?: boolean;
  ready_for_retrieval?: boolean;
  reasons?: string[];
  documents_total?: number;
  documents_by_status?: Record<string, number>;
  documents_by_language?: Record<string, number>;
  documents_pending_index?: number;
}

export interface RepositoryIndexResult {
  repository_id: string;
  status: IndexStatus;
  chunks_created: number;
  chunks_unchanged: number;
  chunks_removed: number;
  embeddings_generated: number;
  total_chunks: number;
}

export interface RepositoryOnboarding {
  repository_id: string;
  status: AnalysisStatus;
  workspace_path: string;
  commit_sha?: string;
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

export interface SearchRequest {
  query: string;
  limit?: number;
  top_k?: number;
}

export interface SearchResult {
  path: string;
  content: string;
  score: number;
  language?: string;
}
