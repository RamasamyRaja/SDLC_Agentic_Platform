import { actionBlockedReason, checksSummary, isBusy, mergeRequestHonesty, parseDiff } from './task-detail.helpers';
import { MergeRequest, TaskAction } from '../../api/models/workflow.model';

const act = (o: Partial<TaskAction>): TaskAction => ({ key: 'reject_plan', label: 'x', method: 'POST', endpoint: '/api/tasks/1/plan/decision', ...o });
const mr = (o: Partial<MergeRequest>): MergeRequest => ({
  id: '1', status: 'OPEN', review_status: 'MR_PENDING_REVIEW', title: 't', description: '', source_branch: 'a', target_branch: 'master',
  commit_sha: null, validation_verdict: 'PASSED', failed_validation_acknowledged: false, remote_status: 'NOT_ATTEMPTED',
  remote_provider: null, remote_url: null, remote_identifier: null, remote_error: null, pushed: false, error: null, run: null, ...o,
});

describe('task detail helpers', () => {
  it('classifies diff lines', () => {
    const k = parseDiff('diff --git a b\n--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n ctx').map((l) => l.kind);
    expect(k).toEqual(['file', 'file', 'file', 'hunk', 'del', 'add', 'ctx']);
    expect(parseDiff(null)).toEqual([]);
  });
  it('detects busy stages', () => {
    expect(isBusy('PLANNING')).toBe(true);
    expect(isBusy('PLAN_PENDING_APPROVAL')).toBe(false);
    expect(isBusy(undefined)).toBe(false);
  });
  it('requires comment and acknowledgement when the server says so', () => {
    expect(actionBlockedReason(act({ requires_comment: true }), '  ', false)).toContain('comment');
    expect(actionBlockedReason(act({ requires_comment: true }), 'why', false)).toBeNull();
    expect(actionBlockedReason(act({ requires_acknowledgement: true }), '', false)).toContain('acknowledge');
    expect(actionBlockedReason(act({ requires_acknowledgement: true }), '', true)).toBeNull();
  });
  it('never presents a local MR as a remote one', () => {
    const local = mergeRequestHonesty(mr({ remote_status: 'REMOTE_UNAVAILABLE', remote_error: 'GIT_PROVIDER_TOKEN not set' }));
    expect(local.kind).toBe('local');
    expect(local.text).toContain('LOCAL review record only');
    expect(local.text).toContain('GIT_PROVIDER_TOKEN');
    expect(mergeRequestHonesty(mr({ remote_status: 'REMOTE_FAILED' })).kind).toBe('local');
    expect(mergeRequestHonesty(mr({ remote_status: 'REMOTE_CREATED', remote_provider: 'github', remote_identifier: '7' })).kind).toBe('remote');
  });
  it('summarises checks', () => {
    expect(checksSummary([{ status: 'PASSED' }, { status: 'PASSED' }, { status: 'BLOCKED' }])).toEqual({ PASSED: 2, BLOCKED: 1 });
  });
});
