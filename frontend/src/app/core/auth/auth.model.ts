export type UserRole = 'ADMIN' | 'DEVELOPER' | 'ARCHITECT' | 'VIEWER';

export type Permission =
  | 'repository:read'
  | 'repository:write'
  | 'task:read'
  | 'task:write'
  | 'task:create'
  | 'agent:read'
  | 'agent:run'
  | 'tool:read'
  | 'tool:invoke'
  | 'user:read'
  | 'user:manage'
  | 'sandbox:execute'
  | 'mr:create'
  | 'mr:approve'
  | 'mr:reject'
  | 'plan:approve'
  | 'plan:reject'
  | 'deploy:execute';

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  /** Server-computed permissions (source of truth). */
  permissions?: string[];
}

export interface AuthSession {
  token: string;
  username: string;
  user: AuthUser;
  expiresAt: number;
}
