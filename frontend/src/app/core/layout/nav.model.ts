export interface NavItem {
  label: string;
  route: string;
  icon?: string;
  description?: string;
}

export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', route: '/app/dashboard', icon: 'dashboard', description: 'Overview and activity' },
  { label: 'Repositories', route: '/app/repositories', icon: 'repo', description: 'Manage codebases' },
  { label: 'Tasks', route: '/app/tasks', icon: 'task', description: 'Agent work items' },
  { label: 'Executions', route: '/app/executions', icon: 'execution', description: 'Run history' },
  { label: 'Reports', route: '/app/reports', icon: 'report', description: 'Analysis output' },
  { label: 'Settings', route: '/app/settings', icon: 'settings', description: 'Preferences' },
];
