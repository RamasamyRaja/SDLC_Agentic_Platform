import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { KeyValuePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { WORKFLOW_PORT } from '../../api/ports/workflow.port';
import {
  Deployment, DevelopmentRun, ExecutionReport, MergeRequest, TaskAction, TaskDetail, TaskPlan, WorkflowEvent,
} from '../../api/models/workflow.model';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { StatusBadgeComponent } from '@shared/components/status-badge/status-badge.component';
import { DiffViewerComponent } from '@shared/components/diff-viewer/diff-viewer.component';
import { ShellContextService } from '@core/layout/shell-context.service';
import { AuthService } from '@core/auth/auth.service';
import { formatDateTime } from '@shared/utils/format.utils';
import { actionBlockedReason, checksSummary, isBusy, mergeRequestHonesty } from './task-detail.helpers';

@Component({
  selector: 'app-task-detail-page',
  imports: [KeyValuePipe, RouterLink, PageHeaderComponent, StatusBadgeComponent, DiffViewerComponent],
  templateUrl: './task-detail-page.component.html',
  styleUrl: './task-detail-page.component.scss',
})
export class TaskDetailPageComponent implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly port = inject(WORKFLOW_PORT);
  private readonly shell = inject(ShellContextService);
  readonly auth = inject(AuthService);

  readonly task = signal<TaskDetail | null>(null);
  readonly plan = signal<TaskPlan | null>(null);
  readonly runs = signal<DevelopmentRun[]>([]);
  readonly run = signal<DevelopmentRun | null>(null);
  readonly mr = signal<MergeRequest | null>(null);
  readonly deployment = signal<Deployment | null>(null);
  readonly events = signal<WorkflowEvent[]>([]);
  readonly report = signal<ExecutionReport | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly comment = signal('');
  readonly ack = signal(false);
  readonly tab = signal<'plan' | 'implementation' | 'validation' | 'mr' | 'deployment' | 'report' | 'history'>('plan');

  readonly stage = computed(() => this.task()?.workflow_stage);
  readonly working = computed(() => isBusy(this.stage()));
  readonly actions = computed(() => this.task()?.allowed_actions ?? []);
  readonly needsComment = computed(() => this.actions().some((a) => a.requires_comment || a.accepts_comment));
  readonly needsAck = computed(() => this.actions().some((a) => a.requires_acknowledgement));
  readonly checks = computed(() => this.run()?.checks ?? []);
  readonly checkCounts = computed(() => checksSummary(this.checks()));
  readonly mrInfo = computed(() => { const m = this.mr(); return m ? mergeRequestHonesty(m) : null; });
  readonly viewOnly = computed(() => this.actions().length === 0 && !this.working());

  private timer: ReturnType<typeof setInterval> | null = null;
  private id = '';

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('taskId')!;
    this.shell.setPage('Task', 'Lifecycle, evidence and decisions for this task.');
    void this.refresh(true);
    this.timer = setInterval(() => { if (this.working()) void this.refresh(false); }, 2000);
  }

  ngOnDestroy(): void { if (this.timer) clearInterval(this.timer); }

  blocked(a: TaskAction): string | null { return actionBlockedReason(a, this.comment(), this.ack()); }
  time(v: string | null | undefined): string { return v ? formatDateTime(v) : '—'; }
  json(v: unknown): string { return JSON.stringify(v, null, 2); }
  entries(o: Record<string, unknown> | undefined): Array<[string, unknown]> { return Object.entries(o ?? {}); }
  setComment(e: Event): void { this.comment.set((e.target as HTMLTextAreaElement).value); }
  setAck(e: Event): void { this.ack.set((e.target as HTMLInputElement).checked); }

  async refresh(initial: boolean): Promise<void> {
    if (initial) this.loading.set(true);
    try {
      const task = await firstValueFrom(this.port.get(this.id));
      this.task.set(task);
      this.shell.setPage(task.title || 'Task', task.description);
      const [plan, runs, mr, dep, events] = await Promise.all([
        firstValueFrom(this.port.plan(this.id)), firstValueFrom(this.port.runs(this.id)),
        firstValueFrom(this.port.mergeRequest(this.id)), firstValueFrom(this.port.deployment(this.id)),
        firstValueFrom(this.port.events(this.id)),
      ]);
      this.plan.set(plan); this.runs.set(runs); this.mr.set(mr); this.deployment.set(dep); this.events.set(events);
      if (runs.length) this.run.set(await firstValueFrom(this.port.run(this.id, runs[0].id)));
      else this.run.set(null);
      this.error.set(null);
    } catch (e) {
      this.error.set((e as { message?: string })?.message ?? 'Task unavailable.');
    } finally { this.loading.set(false); }
  }

  async loadReport(): Promise<void> {
    try { this.report.set(await firstValueFrom(this.port.report(this.id))); }
    catch (e) { this.error.set((e as { message?: string })?.message ?? 'Report unavailable.'); }
  }

  selectTab(t: 'plan' | 'implementation' | 'validation' | 'mr' | 'deployment' | 'report' | 'history'): void {
    this.tab.set(t);
    if (t === 'report') void this.loadReport();
  }

  async act(a: TaskAction): Promise<void> {
    const reason = this.blocked(a);
    if (reason) { this.notice.set(reason); return; }
    if (a.key === 'deploy' && !window.confirm('Run the deployment for the approved commit?')) return;
    this.busy.set(true); this.notice.set(null);
    try {
      await firstValueFrom(this.port.perform(this.id, a, { comment: this.comment(), acknowledge_validation_risk: this.ack() }));
      this.comment.set(''); this.ack.set(false);
      this.notice.set(`${a.label}: accepted by the server.`);
      await this.refresh(false);
    } catch (e) {
      // Surface the server's exact reason (403 role, 409 wrong stage, 400 validation).
      this.notice.set((e as { message?: string })?.message ?? 'Action failed.');
      await this.refresh(false);
    } finally { this.busy.set(false); }
  }
}
