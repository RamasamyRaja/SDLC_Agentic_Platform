import { Routes } from '@angular/router';
import { guestGuard } from '@core/auth/guest.guard';

export const authRoutes: Routes = [
  {
    path: 'register',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./pages/register-page/register-page.component').then((m) => m.RegisterPageComponent),
  },
  {
    path: '',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./pages/login-page/login-page.component').then((m) => m.LoginPageComponent),
  },
];
