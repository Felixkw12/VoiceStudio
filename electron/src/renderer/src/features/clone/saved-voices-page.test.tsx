import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), save: vi.fn(), profiles: [] as object[] }));
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => mocks.navigate }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/hooks/use-profiles', () => ({ useProfiles: () => ({ data: mocks.profiles }) }));
vi.mock('@/lib/local-export', () => ({ saveLocalFile: mocks.save }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/store/workspace', () => ({
  setWorkspace: vi.fn(),
  useWorkspace: () => ({ editingProfileId: null }),
}));
vi.mock('./voices-sidebar', () => ({ SavedVoices: () => <div>voice library</div> }));
vi.mock('./edit-profile', () => ({ EditProfile: () => null }));
vi.mock('@/components/app-shell/workspace-header', () => ({
  WorkspaceHeader: ({ children }: { children: ReactNode }) => <header>{children}</header>,
}));

import { SavedVoicesPage } from './saved-voices-page';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.profiles = [];
});

it('saves all loaded voice prompts as a Markdown file and skips canceled saves', async () => {
  mocks.profiles = [
    {
      id: 'voice-1',
      name: 'Narrator',
      kind: 'design',
      language: 'English',
      instruct: '[warm]',
      ref_text: null,
      personality: null,
    },
  ];
  mocks.save.mockResolvedValue({ canceled: true });
  render(<SavedVoicesPage />);
  fireEvent.click(screen.getByRole('button', { name: 'clone.export_prompts' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledOnce());
  const [blob, name] = mocks.save.mock.calls[0];
  expect(name).toBe('voicestudio-voice-prompts.md');
  expect(await blob.text()).toContain('[warm]');
});

it('keeps saved profiles as the page content and exposes both creation paths', () => {
  render(<SavedVoicesPage />);
  expect(screen.getByText('voice library')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'clone.title' }));
  expect(mocks.navigate).toHaveBeenCalledWith({ to: '/clone' });

  fireEvent.click(screen.getByRole('button', { name: 'designWorkspace.title' }));
  expect(mocks.navigate).toHaveBeenCalledWith({ to: '/design' });
});
