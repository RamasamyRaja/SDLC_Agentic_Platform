import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { HttpParams } from '@angular/common/http';
import { APP_CONFIG } from '@core/config/app-config';

@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);
  private readonly config = inject(APP_CONFIG);

  get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Observable<T> {
    let httpParams = new HttpParams();
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) httpParams = httpParams.set(key, String(value));
      }
    }
    return this.http.get<T>(this.resolve(path), { params: httpParams });
  }

  post<T>(path: string, body?: unknown): Observable<T> {
    return this.http.post<T>(this.resolve(path), body ?? null);
  }

  patch<T>(path: string, body?: unknown): Observable<T> {
    return this.http.patch<T>(this.resolve(path), body ?? null);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(this.resolve(path));
  }

  private resolve(path: string): string {
    const base = this.config.apiBaseUrl.replace(/\/$/, '');
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${base}${normalizedPath}`;
  }
}
