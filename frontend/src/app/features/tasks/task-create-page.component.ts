import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { WORKFLOW_PORT } from '../../api/ports/workflow.port';
import { REPOSITORY_PORT } from '../../api/ports/repository.port';
import { Repository } from '../../api/models/repository.model';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { ShellContextService } from '@core/layout/shell-context.service';
import { AuthService } from '@core/auth/auth.service';

@Component({
  selector: 'app-task-create-page',
  imports: [RouterLink, PageHeaderComponent],
  templateUrl: './task-create-page.component.html',
  styleUrl: './task-create-page.component.scss',
})
export class TaskCreatePageComponent implements OnInit {
  private readonly port = inject(WORKFLOW_PORT);
  private readonly repoPort = inject(REPOSITORY_PORT);
  private readonly router = inject(Router);
  private readonly shell = inject(ShellContextService);
  readonly auth = inject(AuthService);

  readonly repos = signal<Repository[]>([]);
  readonly selectedId = signal('');
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly selected = computed(() => this.repos().find((r) => r.id === this.selectedId()) ?? null);
  /** Honest pre-flight hint; the server makes the real decision and reports `planning_blocker`. */
  readonly repoHint = computed(() => {
    const r = this.selected();
    if (!r) return null;
    if (r.analysis_status !== 'completed') return 'This repository has not been onboarded yet. The task will be created, but planning stays blocked until it is onboarded and indexed.';
    if (r.indexing_status !== 'indexed') return 'This repository is not indexed yet. The task will be created, but planning stays blocked until indexing finishes.';
    return null;
  });

  ngOnInit(): void {
    this.shell.setPage('New task', 'Describe the requirement. The Architecture Agent will draft a plan for Architect approval.');
    firstValueFrom(this.repoPort.list()).then((x) => this.repos.set(x)).catch(() => this.error.set('Unable to load repositories.'));
  }

  onRepo(e: Event): void { this.selectedId.set((e.target as HTMLSelectElement).value); }

  async submit(e: Event): Promise<void> {
    e.preventDefault();
    const fd = new FormData(e.target as HTMLFormElement);
    const text = (k: string) => String(fd.get(k) ?? '').trim();
    const request = text('request');
    if (!this.selectedId() || request.length < 10) {
      this.error.set('Choose a repository and describe the requirement (at least 10 characters).');
      return;
    }
    this.saving.set(true);
    this.error.set(null);
    try {
      const r = await firstValueFrom(this.port.create({
        repository_id: this.selectedId(), request,
        title: text('title') || undefined, expected_outcome: text('expected_outcome') || undefined,
        context: text('context') || undefined, branch: text('branch') || undefined,
      }));
      await this.router.navigate(['/app/tasks', r.task_id]);
    } catch (err) {
      this.error.set((err as { message?: string })?.message ?? 'Unable to create task.');
    } finally { this.saving.set(false); }
  }
}
