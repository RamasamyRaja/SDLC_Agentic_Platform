import { inject } from '@angular/core';
import { forkJoin, map, Observable } from 'rxjs';
import { DashboardPort } from '../../ports/dashboard.port';
import { DashboardData } from '../../models/dashboard.model';
import { REPOSITORY_PORT } from '../../ports/repository.port';
import { TASK_PORT } from '../../ports/task.port';
import { EXECUTION_HISTORY_PORT } from '../../ports/execution-history.port';

export class DerivedDashboardAdapter implements DashboardPort {
  private readonly repoPort = inject(REPOSITORY_PORT);
  private readonly taskPort = inject(TASK_PORT);
  private readonly execPort = inject(EXECUTION_HISTORY_PORT);

  getDashboard(): Observable<DashboardData> {
    return forkJoin({
      repos: this.repoPort.list(),
      tasks: this.taskPort.list(),
      executions: this.execPort.list(),
    }).pipe(
      map(({ repos, tasks, executions }) => {
        const sortedTasks = [...tasks].sort((a, b) => new Date(b.updated_at ?? b.created_at ?? 0).getTime() - new Date(a.updated_at ?? a.created_at ?? 0).getTime());
        const sortedExecutions = [...executions].sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
        const running = sortedExecutions.filter((e) => e.status === 'running').length;
        const success = sortedExecutions.filter((e) => e.status === 'success').length;
        const failed = sortedExecutions.filter((e) => e.status === 'failed').length;
        const activeTasks = tasks.filter((t) => t.status === 'running' || t.status === 'analyzing').length;

        const agentActivity = sortedExecutions.slice(0, 5).map((execution) => ({
          id: execution.id,
          type: 'execution' as const,
          message: `Agent execution ${execution.status} for ${execution.task_title ?? execution.task_id}`,
          timestamp: execution.started_at,
          status: execution.status === 'success' ? 'success' as const : execution.status === 'failed' ? 'failed' as const : execution.status === 'running' ? 'running' as const : 'info' as const,
        }));

        const recentActivity = sortedTasks.slice(0, 5).map((task) => ({
          id: `task-${task.id}`,
          title: `Task ${task.status}`,
          description: task.title,
          timestamp: task.updated_at ?? task.created_at ?? '',
          category: 'task' as const,
        }));

        return {
          kpis: {
            repositories: repos.length,
            activeTasks,
            runningExecutions: running,
            successfulExecutions: success,
            failedExecutions: failed,
            repositoriesDelta: `+${repos.filter((r) => r.created_at && new Date(r.created_at) > new Date(Date.now() - 7 * 86400000)).length} this week`,
            activeTasksDelta: `${activeTasks} in progress`,
          },
          recentTasks: sortedTasks.slice(0, 5).map((t) => ({
            id: t.id,
            title: t.title,
            repository: t.repository_name ?? t.repository_id,
            status: t.status,
            priority: t.priority ?? 'medium',
            updatedAt: t.updated_at ?? t.created_at ?? '',
          })),
          recentExecutions: sortedExecutions.slice(0, 5).map((e) => ({
            id: e.id,
            taskTitle: e.task_title ?? e.task_id,
            status: e.status,
            durationMs: e.duration_ms ?? 0,
            timestamp: e.started_at,
          })),
          repositoryHealth: repos.slice(0, 5).map((r) => ({
            id: r.id,
            name: r.name,
            analysisStatus: r.analysis_status ?? 'not_started',
            indexingStatus: r.indexing_status ?? 'not_started',
            lastActivity: r.last_analyzed_at ?? r.updated_at ?? r.created_at ?? '',
          })),
          agentActivity,
          taskStatusSummary: {
            pending: tasks.filter((t) => t.status === 'pending').length,
            running: tasks.filter((t) => t.status === 'running' || t.status === 'analyzing').length,
            completed: tasks.filter((t) => t.status === 'completed').length,
            failed: tasks.filter((t) => t.status === 'failed').length,
          },
          recentActivity,
        };
      }),
    );
  }
}
