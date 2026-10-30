import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import { DashboardData } from '../models/dashboard.model';

export interface DashboardPort {
  getDashboard(): Observable<DashboardData>;
}

export const DASHBOARD_PORT = new InjectionToken<DashboardPort>('DASHBOARD_PORT');
