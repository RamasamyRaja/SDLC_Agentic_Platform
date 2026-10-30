import { InjectionToken } from '@angular/core';
import { AppEnvironment } from './app-environment.model';

export const APP_CONFIG = new InjectionToken<AppEnvironment>('APP_CONFIG');
