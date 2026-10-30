import { Repository, RepositoryAnalysis, RepositoryDocument, RepositoryIndexStatus } from '../../models/repository.model';

export const MOCK_REPOSITORIES: Repository[] = [
  {
    id: 'repo-1',
    name: 'rad-ai-agent',
    url: 'https://github.com/org/rad-ai-agent',
    provider: 'github',
    branch: 'main',
    language: 'Python',
    analysis_status: 'completed',
    indexing_status: 'indexed',
    task_count: 4,
    last_analyzed_at: '2026-08-31T14:22:00Z',
    created_at: '2026-08-20T09:00:00Z',
    description: 'Core AI software engineering agent with LangGraph orchestration',
  },
  {
    id: 'repo-2',
    name: 'rad-ai-agent-frontend',
    url: 'https://github.com/org/rad-ai-agent-frontend',
    provider: 'github',
    branch: 'main',
    language: 'TypeScript',
    analysis_status: 'completed',
    indexing_status: 'indexed',
    task_count: 2,
    last_analyzed_at: '2026-09-01T08:15:00Z',
    created_at: '2026-08-28T11:30:00Z',
    description: 'Angular frontend for the RAD AI Agent platform',
  },
  {
    id: 'repo-3',
    name: 'payment-service',
    url: 'https://github.com/org/payment-service',
    provider: 'github',
    branch: 'develop',
    language: 'Java',
    analysis_status: 'analyzing',
    indexing_status: 'indexing',
    task_count: 1,
    last_analyzed_at: '2026-08-30T16:45:00Z',
    created_at: '2026-08-25T14:00:00Z',
    description: 'Spring Boot payment processing microservice',
  },
  {
    id: 'repo-4',
    name: 'infra-terraform',
    url: 'https://github.com/org/infra-terraform',
    provider: 'github',
    branch: 'main',
    language: 'HCL',
    analysis_status: 'not_started',
    indexing_status: 'not_started',
    task_count: 0,
    created_at: '2026-09-01T06:00:00Z',
    description: 'Infrastructure as code for deployment environments',
  },
];

export const MOCK_ANALYSIS: Record<string, RepositoryAnalysis> = {
  'repo-1': {
    repository_id: 'repo-1',
    status: 'completed',
    files_analyzed: 142,
    languages: { Python: 89, YAML: 12, Markdown: 8, Shell: 5 },
    functions_count: 387,
    classes_count: 64,
    chunks_count: 1240,
    indexed_documents: 1180,
    last_analyzed_at: '2026-08-31T14:22:00Z',
    summary: 'FastAPI backend with LangGraph agent, Tree-sitter analysis, Milvus retrieval, and Docker sandbox execution.',
  },
  'repo-2': {
    repository_id: 'repo-2',
    status: 'completed',
    files_analyzed: 86,
    languages: { TypeScript: 72, SCSS: 10, HTML: 4 },
    functions_count: 245,
    classes_count: 38,
    chunks_count: 680,
    indexed_documents: 650,
    last_analyzed_at: '2026-09-01T08:15:00Z',
    summary: 'Angular 22 standalone frontend with feature-based architecture and ports/adapters API layer.',
  },
};

export const MOCK_DOCUMENTS: Record<string, RepositoryDocument[]> = {
  'repo-1': [
    { path: 'src', name: 'src', type: 'directory', children: [
      { path: 'src/main.py', name: 'main.py', type: 'file', language: 'python', size: 4200 },
      { path: 'src/agent', name: 'agent', type: 'directory', children: [
        { path: 'src/agent/graph.py', name: 'graph.py', type: 'file', language: 'python', size: 8900 },
        { path: 'src/agent/tools.py', name: 'tools.py', type: 'file', language: 'python', size: 5600 },
      ]},
      { path: 'src/api', name: 'api', type: 'directory', children: [
        { path: 'src/api/routes.py', name: 'routes.py', type: 'file', language: 'python', size: 12400 },
      ]},
    ]},
    { path: 'tests', name: 'tests', type: 'directory', children: [
      { path: 'tests/test_agent.py', name: 'test_agent.py', type: 'file', language: 'python', size: 3200 },
    ]},
    { path: 'requirements.txt', name: 'requirements.txt', type: 'file', language: 'text', size: 890 },
  ],
  'repo-2': [
    { path: 'src/app', name: 'app', type: 'directory', children: [
      { path: 'src/app/features', name: 'features', type: 'directory', children: [
        { path: 'src/app/features/dashboard', name: 'dashboard', type: 'directory', children: [] },
      ]},
      { path: 'src/app/core', name: 'core', type: 'directory', children: [] },
    ]},
    { path: 'angular.json', name: 'angular.json', type: 'file', language: 'json', size: 2400 },
  ],
};

export const MOCK_INDEX_STATUS: Record<string, RepositoryIndexStatus> = {
  'repo-1': { status: 'indexed', indexed_chunks: 1180, documents_total: 1180, last_indexed_at: '2026-08-31T14:30:00Z' },
  'repo-2': { status: 'indexed', indexed_chunks: 650, documents_total: 650, last_indexed_at: '2026-09-01T08:20:00Z' },
  'repo-3': { status: 'indexing', indexed_chunks: 340, documents_total: 340, last_indexed_at: '2026-08-30T16:50:00Z' },
};
