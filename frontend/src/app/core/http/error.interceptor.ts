import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { AuthService } from '@core/auth/auth.service';
import { createApiError } from './api-error.model';
import { HttpErrorService } from './http-error.service';

function extractErrorMessage(error: HttpErrorResponse): string {
  if (typeof error.error === 'string') return error.error;
  if (typeof error.error === 'object' && error.error !== null && 'detail' in error.error) {
    const detail = (error.error as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (typeof d === 'object' && d !== null && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d))).join(', ');
    }
  }
  if (error.status === 0) return 'Unable to reach the server. Check your connection and try again.';
  return error.message || 'An unexpected error occurred.';
}

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const httpErrorService = inject(HttpErrorService);
  const auth = inject(AuthService);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse) {
        if (error.status === 401 && !req.url.includes('/auth/login')) {
          auth.logout();
        }
        const apiError = createApiError(error.status, extractErrorMessage(error), { url: error.url ?? req.url });
        httpErrorService.report(apiError);
        return throwError(() => apiError);
      }
      const fallback = createApiError(0, 'An unexpected error occurred.', { url: req.url });
      httpErrorService.report(fallback);
      return throwError(() => fallback);
    }),
  );
};
