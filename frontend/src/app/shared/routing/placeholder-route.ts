import { Route } from '@angular/router';

export interface PlaceholderRouteData {
  title: string;
  description: string;
}

export function createPlaceholderRoute(
  path: string,
  data: PlaceholderRouteData,
): Route {
  return {
    path,
    loadComponent: () =>
      import('@shared/components/placeholder-page/placeholder-page.component').then(
        (m) => m.PlaceholderPageComponent,
      ),
    data,
  };
}
