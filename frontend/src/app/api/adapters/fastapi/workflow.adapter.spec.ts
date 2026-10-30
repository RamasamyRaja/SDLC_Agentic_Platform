import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { APP_CONFIG } from '@core/config/app-config';
import { FastApiWorkflowAdapter, actionPath } from './workflow.adapter';
import { TaskAction } from '../../models/workflow.model';

describe('FastApiWorkflowAdapter', () => {
  let adapter: FastApiWorkflowAdapter;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(), provideHttpClientTesting(), FastApiWorkflowAdapter,
        { provide: APP_CONFIG, useValue: { production: false, apiBaseUrl: '/api', apiProvider: 'fastapi', mockPorts: [], auth: { mockEnabled: false, tokenKey: 'k' }, polling: { executionIntervalMs: 1 } } },
      ],
    });
    adapter = TestBed.inject(FastApiWorkflowAdapter);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('strips the /api prefix from server-provided action endpoints', () => {
    expect(actionPath('/api/tasks/1/plan/decision')).toBe('/tasks/1/plan/decision');
  });

  it('sends the decision from the server action and a required comment', () => {
    const a: TaskAction = { key: 'reject_plan', label: 'Reject', method: 'POST', endpoint: '/api/tasks/{id}/plan/decision', decision: 'REJECTED', requires_comment: true };
    adapter.perform('abc', a, { comment: ' too risky ' }).subscribe();
    const req = http.expectOne('/api/tasks/abc/plan/decision');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ decision: 'REJECTED', comment: 'too risky' });
    req.flush({});
  });

  it('sends the acknowledgement flag only as an explicit boolean for MR creation', () => {
    const a: TaskAction = { key: 'create_merge_request', label: 'MR', method: 'POST', endpoint: '/api/tasks/1/merge-request', requires_acknowledgement: true };
    adapter.perform('1', a, { acknowledge_validation_risk: true }).subscribe();
    const req = http.expectOne('/api/tasks/1/merge-request');
    expect(req.request.body).toEqual({ acknowledge_validation_risk: true });
    req.flush({});
  });

  it('treats 404 of a stage resource as "not produced yet" but surfaces other errors', () => {
    let plan: unknown = 'unset';
    adapter.plan('1').subscribe((p) => (plan = p));
    http.expectOne('/api/tasks/1/plan').flush({ detail: 'none' }, { status: 404, statusText: 'Not Found' });
    expect(plan).toBeNull();
  });
});
