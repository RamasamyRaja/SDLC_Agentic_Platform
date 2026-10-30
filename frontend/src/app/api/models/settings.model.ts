export interface UserSettings {
  profile: ProfileSettings;
  appearance: AppearanceSettings;
  agent: AgentPreferences;
  execution: ExecutionPreferences;
  notifications: NotificationPreferences;
}

export interface ProfileSettings {
  username: string;
  displayName: string;
  email: string;
}

export interface AppearanceSettings {
  theme: 'dark' | 'light' | 'system';
  density: 'compact' | 'comfortable';
}

export interface AgentPreferences {
  confirmBeforeRun: boolean;
  showRetrievedContext: boolean;
  maxContextItems: number;
}

export interface ExecutionPreferences {
  showSandboxStatus: boolean;
  autoExpandLogs: boolean;
  logLineLimit: number;
}

export interface NotificationPreferences {
  taskCompletion: boolean;
  executionFailures: boolean;
  agentEvents: boolean;
}

export const DEFAULT_SETTINGS: UserSettings = {
  profile: { username: '', displayName: '', email: '' },
  appearance: { theme: 'dark', density: 'compact' },
  agent: { confirmBeforeRun: true, showRetrievedContext: true, maxContextItems: 10 },
  execution: { showSandboxStatus: true, autoExpandLogs: false, logLineLimit: 500 },
  notifications: { taskCompletion: true, executionFailures: true, agentEvents: true },
};
