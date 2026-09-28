import { expect, it } from 'vitest';
import type { Profile } from '@/lib/api/types';
import { profilePromptsMarkdown } from './profile-prompts';

const profile = (overrides: Partial<Profile>): Profile => ({
  id: 'voice-1',
  name: 'Warm narrator',
  kind: 'design',
  ref_audio_path: null,
  ref_text: null,
  instruct: '[warm] [calm]',
  language: 'English',
  seed: 42,
  personality: 'Thoughtful',
  vd_states: null,
  created_at: 0,
  is_locked: false,
  ...overrides,
});
const t = (key: string) => key;

it('exports every saved design and clone as a readable Markdown prompt catalog', () => {
  const md = profilePromptsMarkdown(
    [
      profile({}),
      profile({
        id: 'voice-2',
        name: 'Mara',
        kind: 'clone',
        ref_audio_path: 'ref.wav',
        ref_text: 'A sample transcript',
        instruct: null,
        personality: null,
      }),
    ],
    t,
  );
  expect(md).toContain('## Warm narrator');
  expect(md).toContain('[warm] [calm]');
  expect(md).toContain('Thoughtful');
  expect(md).toContain('## Mara');
  expect(md).toContain('A sample transcript');
  expect(md).toContain('voice-2');
  expect(md).toContain('clone.prompt_audio_note');
  expect(md).not.toContain('ref.wav');
});

it('keeps profile text from creating extra Markdown sections', () => {
  const md = profilePromptsMarkdown(
    [profile({ name: 'A\n## Forged', instruct: 'gentle\n## Forged' })],
    t,
  );
  expect(md.match(/^## /gm)).toHaveLength(1);
  expect(md).toContain('> ## Forged');
});
