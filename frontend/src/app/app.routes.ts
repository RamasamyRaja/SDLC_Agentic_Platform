import { Routes } from '@angular/router';
import { authGuard } from '@core/auth/auth.guard';
import { createPlaceholderRoute } from '@shared/routing/placeholder-route';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'app/dashboard',
    pathMatch: 'full',
  },
  {
    path: 'login',
    loadChildren: () => import('./features/auth/auth.routes').then((m) => m.authRoutes),
  },
  {
    path: 'app',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./core/layout/app-shell/app-shell.component').then((m) => m.AppShellComponent),
    children: [
      {
        path: '',
        redirectTo: 'dashboard',
        pathMatch: 'full',
      },
      {
        path: 'dashboard',
        loadChildren: () =>
          import('./features/dashboard/dashboard.routes').then((m) => m.dashboardRoutes),
      },
      {
        path: 'repositories',
        loadChildren: () =>
          import('./features/repositories/repositories.routes').then((m) => m.repositoriesRoutes),
      },
      {
        path: 'tasks',
        loadChildren: () => import('./features/tasks/tasks.routes').then((m) => m.tasksRoutes),
      },
      {
        path: 'executions',
        loadChildren: () =>
          import('./features/executions/executions.routes').then((m) => m.executionsRoutes),
      },
      {
        path: 'reports',
        loadChildren: () => import('./features/reports/reports.routes').then((m) => m.reportsRoutes),
      },
      {
        path: 'settings',
        loadChildren: () =>
          import('./features/settings/settings.routes').then((m) => m.settingsRoutes),
      },
    ],
  },
  createPlaceholderRoute('**', {
    title: 'Page Not Found',
    description: 'The requested route does not exist.',
  }),
];
