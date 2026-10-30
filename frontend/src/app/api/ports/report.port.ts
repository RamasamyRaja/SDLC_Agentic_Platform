import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import { EngineeringReport } from '../models/report.model';

export interface ReportPort {
  list(): Observable<EngineeringReport[]>;
  getById(id: string): Observable<EngineeringReport>;
}

export const REPORT_PORT = new InjectionToken<ReportPort>('REPORT_PORT');
