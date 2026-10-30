import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { APP_CONFIG } from '@core/config/app-config';
import { AuthSession, AuthUser, Permission, UserRole } from './auth.model';

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

const READ: Permission[] = ['repository:read', 'task:read', 'agent:read', 'tool:read'];
const FALLBACK_PERMISSIONS: Record<UserRole, Permission[]> = {
  ADMIN: [...READ, 'repository:write', 'task:write', 'task:create', 'agent:run', 'tool:invoke', 'user:read', 'user:manage', 'sandbox:execute', 'mr:create', 'deploy:execute'],
  DEVELOPER: [...READ, 'repository:write', 'task:write', 'task:create', 'agent:run', 'tool:invoke', 'sandbox:execute', 'mr:create', 'deploy:execute'],
  ARCHITECT: [...READ, 'mr:approve', 'mr:reject', 'plan:approve', 'plan:reject'],
  VIEWER: READ,
};

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly config = inject(APP_CONFIG);
  private readonly http = inject(HttpClient);
  private readonly _session = signal<AuthSession | null>(this.loadSession());

  readonly session = this._session.asReadonly();
  readonly isAuthenticated = computed(() => this._session() !== null);
  readonly username = computed(() => this._session()?.user.email ?? this._session()?.username ?? null);
  readonly user = computed(() => this._session()?.user ?? null);
  readonly role = computed<UserRole | null>(() => this._session()?.user.role ?? null);

  async login(email: string, password: string): Promise<boolean> {
    if (!email.trim() || !password.trim()) {
      return false;
    }

    if (this.config.auth.mockEnabled) {
      const fallbackUser: AuthUser = {
        id: 'dev-user',
        email: email.trim(),
        full_name: email.trim(),
        role: 'DEVELOPER',
        is_active: true,
      };
      const session: AuthSession = {
        token: `mock-token-${Date.now()}`,
        username: email.trim(),
        user: fallbackUser,
        expiresAt: Date.now() + 24 * 60 * 60 * 1000,
      };
      this.setSession(session);
      return true;
    }

    try {
      const response = await firstValueFrom(
        this.http.post<TokenResponse>(this.resolve('/auth/login'), {
          email: email.trim(),
          password,
        }),
      );

      this.setSession({
        token: response.access_token,
        username: response.user.email,
        user: response.user,
        expiresAt: Date.now() + response.expires_in * 1000,
      });
      return true;
    } catch {
      return false;
    }
  }

  async register(email: string, password: string, fullName: string): Promise<boolean> {
    if (!email.trim() || !password.trim() || !fullName.trim()) {
      return false;
    }

    if (this.config.auth.mockEnabled) {
      const fallbackUser: AuthUser = {
        id: 'dev-user',
        email: email.trim(),
        full_name: fullName.trim(),
        role: 'ADMIN',
        is_active: true,
      };
      const session: AuthSession = {
        token: `mock-token-${Date.now()}`,
        username: fallbackUser.email,
        user: fallbackUser,
        expiresAt: Date.now() + 24 * 60 * 60 * 1000,
      };
      this.setSession(session);
      return true;
    }

    try {
      const response = await firstValueFrom(
        this.http.post<TokenResponse>(this.resolve('/auth/register'), {
          email: email.trim(),
          password,
          full_name: fullName.trim(),
        }),
      );

      this.setSession({
        token: response.access_token,
        username: response.user.email,
        user: response.user,
        expiresAt: Date.now() + response.expires_in * 1000,
      });
      return true;
    } catch {
      return false;
    }
  }

  async refreshUser(): Promise<AuthUser | null> {
    const session = this._session();
    if (!session) return null;

    try {
      const user = await firstValueFrom(this.http.get<AuthUser>(this.resolve('/auth/me')));
      const refreshed = { ...session, user, username: user.email };
      this.setSession(refreshed);
      return user;
    } catch {
      this.logout();
      return null;
    }
  }

  logout(): void {
    sessionStorage.removeItem(this.config.auth.tokenKey);
    this._session.set(null);
  }

  getToken(): string | null {
    const session = this._session();
    if (!session) return null;
    if (session.expiresAt && Date.now() >= session.expiresAt) {
      this.logout();
      return null;
    }
    return session.token;
  }

  hasRole(...roles: UserRole[]): boolean {
    const role = this.role();
    return role !== null && roles.includes(role);
  }

  /**
   * Permissions come from the server (`/auth/me`, login response). The table below is only a
   * fallback for sessions created before `permissions` existed or in mock-auth dev mode; the
   * backend enforces RBAC regardless. Note ADMIN is NOT all-powerful: approvals are ARCHITECT-only.
   */
  hasPermission(permission: Permission): boolean {
    const user = this._session()?.user;
    if (!user) return false;
    if (Array.isArray(user.permissions)) return user.permissions.includes(permission);
    return FALLBACK_PERMISSIONS[user.role]?.includes(permission) ?? false;
  }

  private setSession(session: AuthSession): void {
    sessionStorage.setItem(this.config.auth.tokenKey, JSON.stringify(session));
    this._session.set(session);
  }

  private loadSession(): AuthSession | null {
    const raw = sessionStorage.getItem(this.config.auth.tokenKey);
    if (!raw) return null;

    try {
      const parsed = JSON.parse(raw) as AuthSession;
      if (
        typeof parsed.token === 'string' &&
        typeof parsed.username === 'string' &&
        parsed.user?.role &&
        parsed.expiresAt > Date.now()
      ) {
        return parsed;
      }
    } catch {
      // Clear malformed session below.
    }

    sessionStorage.removeItem(this.config.auth.tokenKey);
    return null;
  }

  private resolve(path: string): string {
    const base = this.config.apiBaseUrl.replace(/\/$/, '');
    return `${base}${path.startsWith('/') ? path : `/${path}`}`;
  }
}
