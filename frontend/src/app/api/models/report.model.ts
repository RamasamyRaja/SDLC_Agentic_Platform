export interface EngineeringReport {
  id: string;
  taskId: string;
  taskTitle: string;
  repositoryId: string;
  repositoryName: string;
  status: 'draft' | 'complete' | 'failed';
  generatedAt: string;
  updatedAt: string;
  taskSummary: string;
  repositoryContext: string;
  analysisSummary: string;
  agentSummary: string;
  retrievedContextSummary: string;
  toolsUsed: string[];
  executionResults: string;
  warnings: string[];
  errors: string[];
  finalOutcome: string;
}
