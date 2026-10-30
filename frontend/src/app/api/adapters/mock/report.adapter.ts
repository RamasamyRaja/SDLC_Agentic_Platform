import { Observable, of, delay } from 'rxjs';
import { ReportPort } from '../../ports/report.port';
import { EngineeringReport } from '../../models/report.model';

const MOCK_REPORTS: EngineeringReport[] = [
  {
    id: 'report-1',
    taskId: 'task-2',
    taskTitle: 'Implement repository onboarding UI',
    repositoryId: 'repo-2',
    repositoryName: 'rad-ai-agent-frontend',
    status: 'complete',
    generatedAt: '2026-08-31T18:00:00Z',
    updatedAt: '2026-08-31T18:00:00Z',
    taskSummary: 'Build frontend for repository registration and onboarding workflow with ports/adapters architecture.',
    repositoryContext: 'Angular 22 standalone application with feature-based lazy routing and SCSS design system.',
    analysisSummary: '86 files analyzed. Primary language TypeScript (72 files). 680 code chunks indexed.',
    agentSummary: 'Agent designed feature routes, shared components, and API abstraction layer. 3 tool invocations, all successful.',
    retrievedContextSummary: 'Retrieved 8 relevant code chunks from features/ and core/ directories.',
    toolsUsed: ['read_file', 'write_file', 'search_code'],
    executionResults: 'Build passed. 12 new files created. All routes functional.',
    warnings: ['Component style budget approaching limit for agent-workspace'],
    errors: [],
    finalOutcome: 'Task completed successfully. Repository onboarding UI ready for integration testing.',
  },
  {
    id: 'report-2',
    taskId: 'task-4',
    taskTitle: 'Add Milvus index optimization',
    repositoryId: 'repo-1',
    repositoryName: 'rad-ai-agent',
    status: 'failed',
    generatedAt: '2026-08-29T11:00:00Z',
    updatedAt: '2026-08-29T11:00:00Z',
    taskSummary: 'Optimize vector index configuration for improved code chunk retrieval performance.',
    repositoryContext: 'Python FastAPI backend with Milvus vector store and Mistral embeddings.',
    analysisSummary: '142 files analyzed. Embedding pipeline uses 768-dimension Mistral vectors.',
    agentSummary: 'Agent attempted index reconfiguration but encountered dimension mismatch.',
    retrievedContextSummary: 'Retrieved Milvus configuration and embedding service code.',
    toolsUsed: ['read_file', 'run_command'],
    executionResults: 'Execution failed with exit code 1.',
    warnings: ['Index dimension mismatch detected before write operation'],
    errors: ['embedding dimension 768 does not match index configuration 1024'],
    finalOutcome: 'Task failed. Manual intervention required to align embedding dimensions with index schema.',
  },
];

export class MockReportAdapter implements ReportPort {
  list(): Observable<EngineeringReport[]> {
    return of([...MOCK_REPORTS]).pipe(delay(250));
  }

  getById(id: string): Observable<EngineeringReport> {
    const report = MOCK_REPORTS.find((r) => r.id === id);
    if (!report) throw new Error('Report not found');
    return of({ ...report }).pipe(delay(200));
  }
}
