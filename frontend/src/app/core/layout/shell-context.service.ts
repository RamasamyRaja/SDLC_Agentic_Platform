import { Injectable, signal } from '@angular/core';

export interface Breadcrumb {
  label: string;
  route?: string;
}

@Injectable({ providedIn: 'root' })
export class ShellContextService {
  private readonly _title = signal('Dashboard');
  private readonly _description = signal('');
  private readonly _breadcrumbs = signal<Breadcrumb[]>([]);

  readonly title = this._title.asReadonly();
  readonly description = this._description.asReadonly();
  readonly breadcrumbs = this._breadcrumbs.asReadonly();

  setPage(title: string, description = '', breadcrumbs: Breadcrumb[] = []): void {
    this._title.set(title);
    this._description.set(description);
    this._breadcrumbs.set(breadcrumbs);
  }
}
