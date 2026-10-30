import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideApiAdapters } from './api/adapters/api.providers';
import { APP_CONFIG } from '@core/config/app-config';
import { authInterceptor } from '@core/http/auth.interceptor';
import { errorInterceptor } from '@core/http/error.interceptor';
import { environment } from '../environments/environment';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
    { provide: APP_CONFIG, useValue: environment },
    ...provideApiAdapters(),
  ],
};
