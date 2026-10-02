import i18next from 'i18next';
import { afterEach, expect, it, vi } from 'vitest';
import { publicFailureFromEvent } from './failure';

afterEach(() => vi.restoreAllMocks());

it('localizes a segment identity conflict delivered after generation starts', () => {
  const translate = vi.spyOn(i18next, 't').mockReturnValue('Localized identity conflict');
  const failure = publicFailureFromEvent({
    type: 'error',
    error_code: 'dub_segment_identity_conflict',
    error: 'Server fallback',
  }, 'Task failed');
  expect(failure.reason).toBe('Localized identity conflict');
  expect(translate).toHaveBeenCalledWith('dub.qc_identity_missing');
});
