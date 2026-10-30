export interface AppEnvironment {
  production: boolean;
  apiBaseUrl: string;
  apiProvider: 'fastapi' | 'mock' | 'spring';
  mockPorts: string[];
  auth: {
    mockEnabled: boolean;
    tokenKey: string;
  };
  polling: {
    executionIntervalMs: number;
  };
}
