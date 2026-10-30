import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { WORKFLOW_PORT } from '../../api/ports/workflow.port';
import { TaskSummary, WorkflowSummary } from '../../api/models/workflow.model';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { StatusBadgeComponent } from '@shared/components/status-badge/status-badge.component';
import { LoadingSkeletonComponent } from '@shared/components/loading-skeleton/loading-skeleton.component';
import { ShellContextService } from '@core/layout/shell-context.service';
import { AuthService } from '@core/auth/auth.service';
import { formatRelativeTime } from '@shared/utils/format.utils';
import { isBusy } from './task-detail.helpers';

@Component({
  selector: 'app-tasks-page',
  imports: [RouterLink, PageHeaderComponent, StatusBadgeComponent, LoadingSkeletonComponent],
  templateUrl: './tasks-page.component.html',
  styleUrl: './tasks-page.component.scss',
})
export class TasksPageComponent implements OnInit, OnDestroy {
  private readonly port = inject(WORKFLOW_PORT);
  private readonly shell = inject(ShellContextService);
  readonly auth = inject(AuthService);

  readonly tasks = signal<TaskSummary[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly query = signal('');
  readonly stage = signal('all');
  readonly onlyAttention = signal(false);
  readonly summary = signal<WorkflowSummary | null>(null);
  readonly summaryError = signal(false);
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly stages = computed(() => [...new Set(this.tasks().map((t) => t.workflow_stage))].sort());
  readonly filtered = computed(() => {
    const q = this.query().toLowerCase().trim();
    return this.tasks().filter((t) =>
      (this.stage() === 'all' || t.workflow_stage === this.stage()) &&
      (!this.onlyAttention() || ['human_action', 'error', 'blocked'].includes(t.attention?.level ?? '')) &&
      (!q || (t.title ?? '').toLowerCase().includes(q) || t.description.toLowerCase().includes(q) ||
        (t.repository_name ?? '').toLowerCase().includes(q) || (t.creator?.email ?? '').toLowerCase().includes(q)));
  });
  /** Tasks awaiting a human decision — the Architect's work queue. */
  readonly awaitingReview = computed(() => this.tasks().filter((t) => t.workflow_stage === 'PLAN_PENDING_APPROVAL' || t.workflow_stage === 'MR_PENDING_REVIEW').length);

  ngOnInit(): void {
    this.shell.setPage('Tasks', 'Requirement-to-deployment lifecycle for every task in the team.');
    void this.load(true);
    this.timer = setInterval(() => { if (this.tasks().some((t) => isBusy(t.workflow_stage))) void this.load(false); }, 4000);
  }

  ngOnDestroy(): void { if (this.timer) clearInterval(this.timer); }

  async load(initial: boolean): Promise<void> {
    if (initial) this.loading.set(true);
    this.error.set(null);
    try { this.tasks.set(await firstValueFrom(this.port.list())); void this.loadSummary(); }
    catch (e) { if (initial) this.error.set((e as { message?: string })?.message ?? 'Unable to load tasks.'); }
    finally { this.loading.set(false); }
  }

  async loadSummary(): Promise<void> {
    try { this.summary.set(await firstValueFrom(this.port.summary())); this.summaryError.set(false); }
    catch { this.summary.set(null); this.summaryError.set(true); }
  }
  toggleAttention(e: Event): void { this.onlyAttention.set((e.target as HTMLInputElement).checked); }
  time(v?: string): string { return v ? formatRelativeTime(v) : '—'; }
  setQuery(e: Event): void { this.query.set((e.target as HTMLInputElement).value); }
  setStage(e: Event): void { this.stage.set((e.target as HTMLSelectElement).value); }
}
