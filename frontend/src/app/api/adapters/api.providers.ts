import { Provider } from '@angular/core';
import { environment } from '../../../environments/environment';
import { DASHBOARD_PORT } from '../ports/dashboard.port';
import { EXECUTION_HISTORY_PORT } from '../ports/execution-history.port';
import { REPORT_PORT } from '../ports/report.port';
import { SETTINGS_PORT } from '../ports/settings.port';
import { CODE_CONTENT_PORT } from '../ports/code-content.port';
import { REPOSITORY_PORT } from '../ports/repository.port';
import { TASK_PORT } from '../ports/task.port';
import { WORKFLOW_PORT } from '../ports/workflow.port';
import { AGENT_PORT } from '../ports/agent.port';
import { DerivedDashboardAdapter } from './mock/dashboard.adapter';
import { FastApiExecutionHistoryAdapter } from './fastapi/execution-history.adapter';
import { FastApiReportAdapter } from './fastapi/report.adapter';
import { LocalStorageSettingsAdapter } from './mock/settings.adapter';
import { provideRepositoryPort } from './fallback/repository.adapter';
import { provideTaskPort } from './fallback/task.adapter';
import { provideAgentPort } from './fallback/agent.adapter';
import { FastApiRepositoryAdapter } from './fastapi/repository.adapter';
import { FastApiTaskAdapter } from './fastapi/task.adapter';
import { FastApiWorkflowAdapter } from './fastapi/workflow.adapter';
import { FastApiAgentAdapter } from './fastapi/agent.adapter';
import { FastApiCodeContentAdapter } from './fastapi/code-content.adapter';

export function provideApiAdapters(): Provider[] {
  const backendProviders: Provider[] = environment.apiProvider === 'fastapi'
    ? [
        FastApiRepositoryAdapter,
        FastApiTaskAdapter,
        FastApiAgentAdapter,
        { provide: REPOSITORY_PORT, useClass: FastApiRepositoryAdapter },
        { provide: TASK_PORT, useClass: FastApiTaskAdapter },
        { provide: AGENT_PORT, useClass: FastApiAgentAdapter },
      ]
    : [
        ...provideRepositoryPort(),
        ...provideTaskPort(),
        ...provideAgentPort(),
      ];

  return [
    ...backendProviders,
    // The task lifecycle always talks to the real backend (no mock fallback by design).
    { provide: WORKFLOW_PORT, useClass: FastApiWorkflowAdapter },
    { provide: DASHBOARD_PORT, useClass: DerivedDashboardAdapter },
    { provide: EXECUTION_HISTORY_PORT, useClass: FastApiExecutionHistoryAdapter },
    { provide: REPORT_PORT, useClass: FastApiReportAdapter },
    { provide: SETTINGS_PORT, useClass: LocalStorageSettingsAdapter },
    { provide: CODE_CONTENT_PORT, useClass: FastApiCodeContentAdapter },
  ];
}
