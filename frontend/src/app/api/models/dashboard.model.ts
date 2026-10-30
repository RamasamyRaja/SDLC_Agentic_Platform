import { ExecutionStatus } from './execution.model';
import { TaskStatus } from './task.model';
import { AnalysisStatus, IndexStatus } from './repository.model';

export interface DashboardKpis {
  repositories: number;
  activeTasks: number;
  runningExecutions: number;
  successfulExecutions: number;
  failedExecutions: number;
  repositoriesDelta?: string;
  activeTasksDelta?: string;
}

export interface RecentTaskItem {
  id: string;
  title: string;
  repository: string;
  status: TaskStatus;
  priority: string;
  updatedAt: string;
}

export interface RecentExecutionItem {
  id: string;
  taskTitle: string;
  status: ExecutionStatus;
  durationMs: number;
  timestamp: string;
}

export interface RepositoryHealthItem {
  id: string;
  name: string;
  analysisStatus: AnalysisStatus;
  indexingStatus: IndexStatus;
  lastActivity: string;
}

export interface AgentActivityItem {
  id: string;
  type: 'tool' | 'execution' | 'analysis' | 'index';
  message: string;
  timestamp: string;
  status: 'success' | 'failed' | 'running' | 'info';
}

export interface TaskStatusSummary {
  pending: number;
  running: number;
  completed: number;
  failed: number;
}

export interface ActivityTimelineItem {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  category: 'task' | 'execution' | 'repository' | 'agent';
}

export interface DashboardData {
  kpis: DashboardKpis;
  recentTasks: RecentTaskItem[];
  recentExecutions: RecentExecutionItem[];
  repositoryHealth: RepositoryHealthItem[];
  agentActivity: AgentActivityItem[];
  taskStatusSummary: TaskStatusSummary;
  recentActivity: ActivityTimelineItem[];
}
