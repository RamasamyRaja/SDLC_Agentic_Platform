import { TestBed } from '@angular/core/testing';
import { APP_CONFIG } from '@core/config/app-config';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        AuthService,
        {
          provide: APP_CONFIG,
          useValue: {
            production: false,
            apiBaseUrl: '/api',
            apiProvider: 'fastapi',
            mockPorts: [],
            auth: { mockEnabled: true, tokenKey: 'rad-auth-token' },
            polling: { executionIntervalMs: 2000 },
          },
        },
      ],
    });
    service = TestBed.inject(AuthService);
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('should not be authenticated initially', () => {
    expect(service.isAuthenticated()).toBe(false);
  });

  it('should authenticate with valid credentials', async () => {
    expect(await service.login('developer@example.com', 'password123')).toBe(true);
    expect(service.isAuthenticated()).toBe(true);
    expect(service.username()).toBe('developer@example.com');
  });

  it('should reject login with empty email', async () => {
    expect(await service.login('', '')).toBe(false);
    expect(service.isAuthenticated()).toBe(false);
  });

  it('should clear session on logout', async () => {
    await service.login('developer@example.com', 'password123');
    service.logout();
    expect(service.isAuthenticated()).toBe(false);
  });
});
