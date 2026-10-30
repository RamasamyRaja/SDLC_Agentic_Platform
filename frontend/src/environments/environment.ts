import { AppEnvironment } from '../app/core/config/app-environment.model';

export const environment: AppEnvironment = {
  production: true,
  apiBaseUrl: '/api',
  apiProvider: 'fastapi',
  mockPorts: [],
  auth: {
    mockEnabled: false,
    tokenKey: 'rad-auth-token',
  },
  polling: {
    executionIntervalMs: 2000,
  },
};
