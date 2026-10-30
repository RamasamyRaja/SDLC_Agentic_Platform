import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';
import { UserSettings } from '../models/settings.model';

export interface SettingsPort {
  get(): Observable<UserSettings>;
  save(settings: UserSettings): Observable<UserSettings>;
}

export const SETTINGS_PORT = new InjectionToken<SettingsPort>('SETTINGS_PORT');
