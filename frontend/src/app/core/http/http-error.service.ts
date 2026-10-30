import { Injectable, inject, signal } from '@angular/core';
import { ApiError } from './api-error.model';

@Injectable({ providedIn: 'root' })
export class HttpErrorService {
  private readonly _lastError = signal<ApiError | null>(null);

  readonly lastError = this._lastError.asReadonly();

  report(error: ApiError): void {
    this._lastError.set(error);
  }

  clear(): void {
    this._lastError.set(null);
  }
}
