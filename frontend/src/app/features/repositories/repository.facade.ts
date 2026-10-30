import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { REPOSITORY_PORT } from '../../api/ports/repository.port';
import {
  Repository,
  RepositoryAnalysis,
  RepositoryCreateRequest,
  RepositoryIndexStatus,
  SearchRequest,
  SearchResult,
} from '../../api/models/repository.model';
import { TASK_PORT } from '../../api/ports/task.port';
import { Task } from '../../api/models/task.model';

export type RepositoryAction = 'create' | 'onboard' | 'index' | 'search';

@Injectable({ providedIn: 'root' })
export class RepositoryFacade {
  private readonly repositoryPort = inject(REPOSITORY_PORT);
  private readonly taskPort = inject(TASK_PORT);

  readonly repositories = signal<Repository[]>([]);
  readonly listLoading = signal(false);
  readonly listError = signal<string | null>(null);

  readonly selectedRepository = signal<Repository | null>(null);
  readonly detailLoading = signal(false);
  readonly detailError = signal<string | null>(null);

  readonly analysis = signal<RepositoryAnalysis | null>(null);
  readonly analysisLoading = signal(false);
  readonly analysisError = signal<string | null>(null);

  readonly indexStatus = signal<RepositoryIndexStatus | null>(null);
  readonly indexStatusLoading = signal(false);
  readonly indexStatusError = signal<string | null>(null);

  readonly searchResults = signal<SearchResult[]>([]);
  readonly searchLoading = signal(false);
  readonly searchError = signal<string | null>(null);

  readonly activeAction = signal<RepositoryAction | null>(null);
  readonly actionError = signal<string | null>(null);

  readonly recentTasks = signal<Task[]>([]);

  async loadList(): Promise<void> {
    this.listLoading.set(true);
    this.listError.set(null);
    try {
      const repos = await firstValueFrom(this.repositoryPort.list());
      this.repositories.set(repos);
    } catch {
      this.listError.set('Failed to load repositories.');
    } finally {
      this.listLoading.set(false);
    }
  }

  async loadById(id: string): Promise<void> {
    this.detailLoading.set(true);
    this.detailError.set(null);
    this.selectedRepository.set(null);
    try {
      const repo = await firstValueFrom(this.repositoryPort.getById(id));
      this.selectedRepository.set(repo);
      try {
        const tasks = await firstValueFrom(this.taskPort.list());
        this.recentTasks.set(tasks.filter((task) => task.repository_id === id).slice(0, 5));
      } catch {
        this.recentTasks.set([]);
      }
    } catch {
      this.detailError.set('Repository not found or unavailable.');
    } finally {
      this.detailLoading.set(false);
    }
  }

  async getDocuments(id: string): Promise<import('../../api/models/repository.model').RepositoryDocument[]> {
    return firstValueFrom(this.repositoryPort.getDocuments(id));
  }

  async loadAnalysis(id: string): Promise<void> {
    this.analysisLoading.set(true);
    this.analysisError.set(null);
    try {
      const data = await firstValueFrom(this.repositoryPort.getAnalysis(id));
      this.analysis.set(data);
    } catch {
      this.analysisError.set('Failed to load analysis.');
      this.analysis.set(null);
    } finally {
      this.analysisLoading.set(false);
    }
  }

  async loadIndexStatus(id: string): Promise<void> {
    this.indexStatusLoading.set(true);
    this.indexStatusError.set(null);
    try {
      const data = await firstValueFrom(this.repositoryPort.getIndexStatus(id));
      this.indexStatus.set(data);
    } catch {
      this.indexStatusError.set('Failed to load index status.');
      this.indexStatus.set(null);
    } finally {
      this.indexStatusLoading.set(false);
    }
  }

  async create(req: RepositoryCreateRequest): Promise<Repository | null> {
    this.activeAction.set('create');
    this.actionError.set(null);
    try {
      const repo = await firstValueFrom(this.repositoryPort.create(req));
      this.repositories.update((list) => [...list, repo]);
      return repo;
    } catch {
      this.actionError.set('Failed to create repository.');
      return null;
    } finally {
      this.activeAction.set(null);
    }
  }

  async onboard(id: string): Promise<boolean> {
    this.activeAction.set('onboard');
    this.actionError.set(null);
    try {
      await firstValueFrom(this.repositoryPort.onboard(id));
      await this.loadAnalysis(id);
      await this.refreshRepository(id);
      return true;
    } catch {
      this.actionError.set('Failed to start analysis.');
      return false;
    } finally {
      this.activeAction.set(null);
    }
  }

  async index(id: string): Promise<boolean> {
    this.activeAction.set('index');
    this.actionError.set(null);
    try {
      await firstValueFrom(this.repositoryPort.index(id));
      await this.loadIndexStatus(id);
      await this.refreshRepository(id);
      return true;
    } catch {
      this.actionError.set('Failed to start indexing.');
      return false;
    } finally {
      this.activeAction.set(null);
    }
  }

  async search(id: string, req: SearchRequest): Promise<SearchResult[]> {
    this.activeAction.set('search');
    this.searchLoading.set(true);
    this.searchError.set(null);
    this.searchResults.set([]);
    try {
      const results = await firstValueFrom(this.repositoryPort.search(id, req));
      this.searchResults.set(results);
      return results;
    } catch {
      this.searchError.set('Search failed.');
      return [];
    } finally {
      this.searchLoading.set(false);
      this.activeAction.set(null);
    }
  }

  clearSearch(): void {
    this.searchResults.set([]);
    this.searchError.set(null);
  }

  resetDetail(): void {
    this.selectedRepository.set(null);
    this.analysis.set(null);
    this.indexStatus.set(null);
    this.detailError.set(null);
    this.analysisError.set(null);
    this.indexStatusError.set(null);
    this.clearSearch();
  }

  private async refreshRepository(id: string): Promise<void> {
    try {
      const repo = await firstValueFrom(this.repositoryPort.getById(id));
      this.selectedRepository.set(repo);
      this.repositories.update((list) => list.map((r) => (r.id === id ? repo : r)));
    } catch {
      // keep existing state on refresh failure
    }
  }
}
