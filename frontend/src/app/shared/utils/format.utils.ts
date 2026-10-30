export function formatRelativeTime(iso: string): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatDuration(ms: number): string {
  if (!ms) return '—';
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  if (mins < 60) return `${mins}m ${remSecs}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

export function formatDateTime(iso: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

export type StatusKind =
  | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'analyzing'
  | 'success' | 'timeout' | 'indexed' | 'indexing' | 'not_started' | 'idle'
  | 'critical' | 'high' | 'medium' | 'low' | string;

const SUCCESS = new Set(['completed', 'success', 'indexed', 'passed', 'approved', 'deployed', 'remote_created', 'plan_approved',
  'mr_approved', 'applied', 'committed', 'changes_applied', 'open', 'ready_for_mr']);
const RUNNING = new Set(['running', 'analyzing', 'indexing', 'executing', 'planning', 'implementing', 'validating', 'deploying',
  'in_progress', 'generating', 'mr_creating', 'creating']);
const ERROR = new Set(['error', 'failed', 'cancelled', 'timeout', 'critical', 'timed_out', 'plan_failed', 'implementation_failed',
  'validation_failed', 'mr_creation_failed', 'deployment_failed', 'rejected', 'plan_rejected', 'mr_rejected', 'remote_failed',
  'creation_failed', 'no_changes']);
const WARNING = new Set(['high', 'medium', 'partial', 'blocked', 'unavailable', 'pending_human', 'pending_approval',
  'plan_pending_approval', 'mr_pending_review', 'revision_required', 'plan_revision_required', 'mr_revision_required',
  'dependency_missing', 'unverified', 'no_tests', 'human_action', 'deployment_unavailable', 'remote_unavailable', 'blocked_pending_approval']);
const NEUTRAL = new Set(['pending', 'not_started', 'idle', 'low', 'created', 'skipped', 'not_run', 'not_attempted', 'not_created']);

export function statusVariant(status: StatusKind): 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'running' {
  const s = status.toLowerCase();
  if (SUCCESS.has(s)) return 'success';
  if (RUNNING.has(s)) return 'running';
  if (ERROR.has(s)) return 'error';
  if (WARNING.has(s)) return 'warning';
  if (NEUTRAL.has(s)) return 'neutral';
  return 'info';
}

export function statusLabel(status: StatusKind): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
