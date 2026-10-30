import { Component, inject, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ShellContextService } from '@core/layout/shell-context.service';
import { KpiCardComponent } from '@shared/components/kpi-card/kpi-card.component';
import { StatusBadgeComponent } from '@shared/components/status-badge/status-badge.component';
import { LoadingSkeletonComponent } from '@shared/components/loading-skeleton/loading-skeleton.component';
import { ErrorStateComponent } from '@shared/components/error-state/error-state.component';
import { SectionHeaderComponent } from '@shared/components/section-header/section-header.component';
import { formatRelativeTime, formatDuration } from '@shared/utils/format.utils';
import { DashboardFacade } from '../../dashboard.facade';

@Component({
  selector: 'app-dashboard-page',
  imports: [
    RouterLink, KpiCardComponent, StatusBadgeComponent,
    LoadingSkeletonComponent, ErrorStateComponent, SectionHeaderComponent,
  ],
  templateUrl: './dashboard-page.component.html',
  styleUrl: './dashboard-page.component.scss',
})
export class DashboardPageComponent implements OnInit {
  protected readonly facade = inject(DashboardFacade);
  private readonly shell = inject(ShellContextService);
  protected readonly formatRelativeTime = formatRelativeTime;
  protected readonly formatDuration = formatDuration;

  protected activityTypeIcon(type: string): string {
    return ({ tool: '⌘', execution: '▶', analysis: '◈', index: '▦' } as Record<string, string>)[type] ?? '•';
  }

  protected categoryIcon(category: string): string {
    return ({ execution: '▶', repository: '◆', task: '✓', agent: '⌘' } as Record<string, string>)[category] ?? '•';
  }

  protected statusBars() {
    const summary = this.facade.data()?.taskStatusSummary;
    return [
      { key: 'completed', label: 'Completed', count: summary?.completed ?? 0, color: 'var(--status-success)' },
      { key: 'running', label: 'Running', count: summary?.running ?? 0, color: 'var(--status-info)' },
      { key: 'pending', label: 'Pending', count: summary?.pending ?? 0, color: 'var(--status-warning)' },
      { key: 'failed', label: 'Failed', count: summary?.failed ?? 0, color: 'var(--status-danger)' },
    ];
  }

  ngOnInit(): void {
    this.shell.setPage('Dashboard', 'Engineering overview across repositories, tasks, and agent activity');
    this.facade.load();
  }
}
