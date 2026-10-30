import { inject } from '@angular/core';
import { Observable, of, delay } from 'rxjs';
import { SettingsPort } from '../../ports/settings.port';
import { DEFAULT_SETTINGS, UserSettings } from '../../models/settings.model';
import { AuthService } from '@core/auth/auth.service';

const STORAGE_KEY = 'rad-user-settings';

export class LocalStorageSettingsAdapter implements SettingsPort {
  private readonly auth = inject(AuthService);

  get(): Observable<UserSettings> {
    const settings = this.load();
    const username = this.auth.username() ?? settings.profile.username;
    return of({
      ...settings,
      profile: { ...settings.profile, username, displayName: settings.profile.displayName || username },
    }).pipe(delay(100));
  }

  save(settings: UserSettings): Observable<UserSettings> {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    return of(settings).pipe(delay(200));
  }

  private load(): UserSettings {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as UserSettings) };
    } catch { /* use defaults */ }
    return { ...DEFAULT_SETTINGS };
  }
}
