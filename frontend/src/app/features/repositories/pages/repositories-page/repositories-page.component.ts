import { Component, computed, inject, OnInit, signal, viewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AnalysisStatus, IndexStatus, Repository } from '../../../../api/models/repository.model';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { StatusBadgeComponent } from '@shared/components/status-badge/status-badge.component';
import { LoadingSkeletonComponent } from '@shared/components/loading-skeleton/loading-skeleton.component';
import { ErrorStateComponent } from '@shared/components/error-state/error-state.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { formatRelativeTime } from '@shared/utils/format.utils';
import { ShellContextService } from '@core/layout/shell-context.service';
import { RepositoryFacade } from '../../repository.facade';
import { CreateRepositoryDialogComponent } from '../../components/create-repository-dialog/create-repository-dialog.component';

type SortField = 'name' | 'created_at' | 'last_analyzed_at' | 'task_count';
type SortDirection = 'asc' | 'desc';
type StatusFilter = 'all' | AnalysisStatus | IndexStatus;

@Component({
  selector: 'app-repositories-page',
  imports: [
    RouterLink,
    PageHeaderComponent,
    StatusBadgeComponent,
    LoadingSkeletonComponent,
    ErrorStateComponent,
    EmptyStateComponent,
    CreateRepositoryDialogComponent,
  ],
  templateUrl: './repositories-page.component.html',
  styleUrl: './repositories-page.component.scss',
})
export class RepositoriesPageComponent implements OnInit {
  protected readonly facade = inject(RepositoryFacade);
  private readonly shell = inject(ShellContextService);
  private readonly router = inject(Router);

  protected readonly createDialog = viewChild.required(CreateRepositoryDialogComponent);

  protected readonly searchQuery = signal('');
  protected readonly statusFilter = signal<StatusFilter>('all');
  protected readonly languageFilter = signal('all');
  protected readonly sortField = signal<SortField>('name');
  protected readonly sortDirection = signal<SortDirection>('asc');

  protected readonly availableLanguages = computed(() => {
    const langs = new Set<string>();
    for (const repo of this.facade.repositories()) {
      if (repo.language) langs.add(repo.language);
    }
    return [...langs].sort();
  });

  protected readonly filteredRepositories = computed(() => {
    let items = [...this.facade.repositories()];
    const query = this.searchQuery().trim().toLowerCase();
    const status = this.statusFilter();
    const language = this.languageFilter();

    if (query) {
      items = items.filter(
        (r) =>
          r.name.toLowerCase().includes(query) ||
          r.url?.toLowerCase().includes(query) ||
          r.description?.toLowerCase().includes(query),
      );
    }

    if (status !== 'all') {
      items = items.filter(
        (r) => r.analysis_status === status || r.indexing_status === status,
      );
    }

    if (language !== 'all') {
      items = items.filter((r) => r.language === language);
    }

    const field = this.sortField();
    const dir = this.sortDirection() === 'asc' ? 1 : -1;

    items.sort((a, b) => {
      const av = this.sortValue(a, field);
      const bv = this.sortValue(b, field);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });

    return items;
  });

  protected readonly hasActiveFilters = computed(
    () =>
      this.searchQuery().trim() !== '' ||
      this.statusFilter() !== 'all' ||
      this.languageFilter() !== 'all',
  );

  ngOnInit(): void {
    this.shell.setPage('Repositories', 'Browse and manage onboarded codebases for agent analysis.');
    void this.facade.loadList();
  }

  protected formatTime(iso?: string): string {
    return iso ? formatRelativeTime(iso) : '—';
  }

  protected onSearchInput(event: Event): void {
    this.searchQuery.set((event.target as HTMLInputElement).value);
  }

  protected onStatusFilterChange(event: Event): void {
    this.statusFilter.set((event.target as HTMLSelectElement).value as StatusFilter);
  }

  protected onLanguageFilterChange(event: Event): void {
    this.languageFilter.set((event.target as HTMLSelectElement).value);
  }

  protected onSortFieldChange(event: Event): void {
    this.sortField.set((event.target as HTMLSelectElement).value as SortField);
  }

  protected toggleSortDirection(): void {
    this.sortDirection.update((d) => (d === 'asc' ? 'desc' : 'asc'));
  }

  protected openCreateDialog(): void {
    this.createDialog().open();
  }

  protected onRepositoryCreated(id: string): void {
    void this.router.navigate(['/app/repositories', id]);
  }

  protected clearFilters(): void {
    this.searchQuery.set('');
    this.statusFilter.set('all');
    this.languageFilter.set('all');
  }

  protected retryLoad(): void {
    void this.facade.loadList();
  }

  private sortValue(repo: Repository, field: SortField): string | number {
    switch (field) {
      case 'name':
        return repo.name.toLowerCase();
      case 'created_at':
        return repo.created_at ?? '';
      case 'last_analyzed_at':
        return repo.last_analyzed_at ?? '';
      case 'task_count':
        return repo.task_count ?? 0;
    }
  }
}
