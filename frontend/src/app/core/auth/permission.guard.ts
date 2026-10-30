import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';
import { Permission } from './auth.model';

export const permissionGuard = (permission: Permission): CanActivateFn => () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.hasPermission(permission) ? true : router.createUrlTree(['/app/dashboard']);
};

export const roleGuard = (...roles: Array<'ADMIN' | 'DEVELOPER' | 'ARCHITECT' | 'VIEWER'>): CanActivateFn => () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.hasRole(...roles) ? true : router.createUrlTree(['/app/dashboard']);
};
