import { describe, expect, it } from 'vitest';
import { statusVariant } from './format.utils';

describe('validation / attention status variants', () => {
  it('never renders PARTIAL, NO_TESTS or human_action as success', () => {
    for (const s of ['PARTIAL', 'NO_TESTS', 'human_action', 'DEPENDENCY_MISSING']) expect(statusVariant(s)).toBe('warning');
  });
  it('renders error attention and failures as error', () => {
    for (const s of ['error', 'FAILED', 'VALIDATION_FAILED']) expect(statusVariant(s)).toBe('error');
  });
  it('only PASSED is success for validation', () => {
    expect(statusVariant('PASSED')).toBe('success');
    expect(statusVariant('NOT_RUN')).toBe('neutral');
  });
});
