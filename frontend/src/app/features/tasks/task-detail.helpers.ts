import { ActionKey, MergeRequest, TaskAction, WorkflowStage, BUSY_STAGES } from '../../api/models/workflow.model';

export interface DiffLine { kind: 'add' | 'del' | 'hunk' | 'file' | 'ctx'; text: string }

/** Classifies unified-diff lines for display. Pure; never executes or interprets the content. */
export function parseDiff(diff: string | null | undefined): DiffLine[] {
  if (!diff) return [];
  return diff.split('\n').map((text): DiffLine => {
    if (text.startsWith('+++') || text.startsWith('---') || text.startsWith('diff --git') || text.startsWith('index ')) return { kind: 'file', text };
    if (text.startsWith('@@')) return { kind: 'hunk', text };
    if (text.startsWith('+')) return { kind: 'add', text };
    if (text.startsWith('-')) return { kind: 'del', text };
    return { kind: 'ctx', text };
  });
}

export function isBusy(stage: WorkflowStage | undefined | null): boolean {
  return !!stage && BUSY_STAGES.includes(stage);
}

/** Returns why an action cannot be submitted yet (null when it can). The server re-validates everything. */
export function actionBlockedReason(action: TaskAction, comment: string, acknowledged: boolean): string | null {
  if (action.requires_comment && !comment.trim()) return 'A comment is required for this action.';
  if (action.requires_acknowledgement && !acknowledged) return 'You must acknowledge the validation risk to continue.';
  return null;
}

export const DESTRUCTIVE_OR_FINAL: ActionKey[] = ['deploy', 'approve_mr', 'approve_plan'];

/** Plain-language description of what the merge request really is. Never claims a remote MR that does not exist. */
export function mergeRequestHonesty(mr: MergeRequest): { kind: 'remote' | 'local'; text: string } {
  if (mr.remote_status === 'REMOTE_CREATED') {
    return { kind: 'remote', text: `Remote ${mr.remote_provider ?? ''} merge request #${mr.remote_identifier ?? '?'} was created.`.replace('  ', ' ') };
  }
  const why = mr.remote_error ? ` Reason: ${mr.remote_error}` : '';
  const state = mr.remote_status === 'REMOTE_FAILED' ? 'Creating it on the remote failed.'
    : mr.remote_status === 'REMOTE_UNAVAILABLE' ? 'Remote creation is unavailable in this environment.'
    : 'No remote merge request was attempted.';
  return { kind: 'local', text: `This is a LOCAL review record only — no merge request exists on the remote. ${state}${why}` };
}

export function checksSummary(checks: Array<{ status: string }>): Record<string, number> {
  return checks.reduce<Record<string, number>>((acc, c) => { acc[c.status] = (acc[c.status] ?? 0) + 1; return acc; }, {});
}
