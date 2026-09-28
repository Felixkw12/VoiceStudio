import type { Profile } from '@/lib/api/types';

type Translate = (key: string) => string;

function heading(value: string): string {
  return value
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[^\p{L}\p{N} -]/gu, '\\$&');
}

function quoted(value: string): string {
  return value
    .replace(/\r\n?/g, '\n')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .split('\n')
    .map((line) => `> ${line}`)
    .join('\n');
}

/** Text-only catalog of saved metadata; acoustic identity stays in the local audio. */
export function profilePromptsMarkdown(profiles: Profile[], t: Translate): string {
  const lines = [
    `# ${t('clone.saved_profiles')}`,
    '',
    t('clone.prompt_intro'),
    '',
    t('clone.prompt_audio_note'),
  ];
  for (const profile of profiles) {
    lines.push('', `## ${heading(profile.name)}`, '');
    const fields: [string, string | null | undefined][] = [
      ['clone.prompt_profile_id', profile.id],
      [
        'clone.prompt_type',
        t(profile.kind === 'design' ? 'projects.designed_voice' : 'projects.cloned_voice'),
      ],
      ['clone.language', profile.language],
      ['clone.prompt_personality', profile.personality],
      ['clone.style', profile.instruct],
      ['clone.transcript', profile.ref_text],
    ];
    for (const [label, value] of fields) {
      if (!value?.trim()) continue;
      lines.push(`**${t(label)}**`, quoted(value), '');
    }
  }
  return lines.join('\n').trimEnd() + '\n';
}
