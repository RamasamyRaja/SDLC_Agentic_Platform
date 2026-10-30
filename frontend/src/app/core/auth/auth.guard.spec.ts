import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { APP_CONFIG } from '@core/config/app-config';
import { AuthService } from './auth.service';
import { authGuard } from './auth.guard';

describe('authGuard', () => {
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        AuthService,
        provideRouter([]),
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
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('should allow access when authenticated', async () => {
    const authService = TestBed.inject(AuthService);
    await authService.login('developer@example.com', 'password123');

    const result = TestBed.runInInjectionContext(() => authGuard({} as never, {} as never));
    expect(result).toBe(true);
  });

  it('should redirect to login when unauthenticated', () => {
    const router = TestBed.inject(Router);
    const result = TestBed.runInInjectionContext(() => authGuard({} as never, {} as never));

    expect(result).toEqual(router.createUrlTree(['/login']));
  });
});
