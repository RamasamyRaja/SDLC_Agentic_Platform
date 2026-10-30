import { Injectable, computed, inject, signal } from '@angular/core';
import { DASHBOARD_PORT } from '@app/api/ports/dashboard.port';
import { DashboardData } from '@app/api/models/dashboard.model';
import { initialRequestState, RequestState } from '@app/api/models/common.model';

@Injectable({ providedIn: 'root' })
export class DashboardFacade {
  private readonly port = inject(DASHBOARD_PORT);
  readonly state = signal<RequestState<DashboardData>>(initialRequestState());
  readonly loading = computed(() => this.state().status === 'loading');
  readonly error = computed(() => this.state().error);
  readonly data = computed(() => this.state().data);

  load(): void {
    this.state.update((s) => ({ ...s, status: 'loading', error: null }));
    this.port.getDashboard().subscribe({
      next: (data) => this.state.set({ status: 'success', data, error: null }),
      error: (err: Error) => this.state.set({ status: 'error', data: null, error: err.message }),
    });
  }
}
