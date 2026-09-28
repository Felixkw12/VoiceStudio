import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ api: vi.fn(), setTier: vi.fn(), success: vi.fn() }));
vi.mock('@/lib/api/client', () => ({ apiJson: mocks.api }));
vi.mock('@/hooks/use-backend-status', () => ({ useBackendStatus: () => ({ stage: 'ready' }) }));
vi.mock('@/hooks/use-performance-profile', () => ({
  usePerformanceProfile: () => ({
    data: { global: 'balanced' },
    isSaving: false,
    setTier: mocks.setTier,
  }),
}));
vi.mock('@/components/performance-profile', () => ({ PerformanceProfile: () => null }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('sonner', () => ({ toast: { success: mocks.success, error: vi.fn() } }));
import { PerformanceModelPacks } from './model-library';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function mount(installed: boolean, diskFree: number) {
  mocks.setTier.mockResolvedValue({});
  mocks.api.mockImplementation((path: string) =>
    Promise.resolve(
      path === '/models'
        ? {
            disk_free_gb: diskFree,
            models: [
              {
                repo_id: 'k2-fsa/OmniVoice',
                label: 'OmniVoice',
                role: 'TTS',
                installed,
                supported: true,
                size_gb: 2.4,
              },
            ],
          }
        : path === '/setup/recommendations'
          ? { device: { label: 'Apple Silicon' } }
          : { jobs: [] },
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PerformanceModelPacks />
    </QueryClientProvider>,
  );
  return client;
}

it.each([8.5, 0])(
  'activates an installed pack with %s GB free without downloading',
  async (free) => {
    mount(true, free);
    const button = await screen.findByRole('button', { name: 'models.pack_use' });
    expect(button).toBeEnabled();
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.click(button);
    await waitFor(() =>
      expect(mocks.setTier).toHaveBeenCalledWith({ tier: 'balanced', family: null }),
    );
    await waitFor(() => expect(mocks.success).toHaveBeenCalledWith('models.pack_ready'));
    expect(mocks.api.mock.calls.some(([path]) => path === '/models/install')).toBe(false);
  },
);

it('still blocks missing-model downloads without the safety reserve', async () => {
  mount(false, 8.5);
  expect(await screen.findByRole('button', { name: 'models.pack_install' })).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('models.reco_low_disk');
  expect(screen.getByRole('alert')).toHaveClass('text-destructive');
  expect(mocks.setTier).not.toHaveBeenCalled();
});

it('downloads missing models when there is enough space including the reserve', async () => {
  mount(false, 13);
  const button = await screen.findByRole('button', { name: 'models.pack_install' });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await waitFor(() =>
    expect(mocks.api).toHaveBeenCalledWith('/models/install', {
      method: 'POST',
      body: JSON.stringify({ repo_id: 'k2-fsa/OmniVoice', target: 'local' }),
    }),
  );
  expect(mocks.setTier).not.toHaveBeenCalled();
  expect(mocks.success).not.toHaveBeenCalledWith('models.pack_ready');
});

it('applies the pack only after all downloaded models become installed', async () => {
  const client = mount(false, 13);
  fireEvent.click(await screen.findByRole('button', { name: 'models.pack_install' }));
  await waitFor(() => expect(mocks.success).toHaveBeenCalledWith('models.started_downloading'));
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'models.pack_install' })).toBeEnabled(),
  );
  expect(mocks.setTier).not.toHaveBeenCalled();
  act(() =>
    client.setQueryData(['model-catalogue'], {
      disk_free_gb: 8.5,
      models: [
        {
          repo_id: 'k2-fsa/OmniVoice',
          label: 'OmniVoice',
          role: 'TTS',
          installed: true,
          supported: true,
          size_gb: 2.4,
        },
      ],
    }),
  );
  await waitFor(() =>
    expect(mocks.setTier).toHaveBeenCalledWith({ tier: 'balanced', family: null }),
  );
  await waitFor(() => expect(mocks.success).toHaveBeenCalledWith('models.pack_ready'));
  expect(mocks.setTier).toHaveBeenCalledTimes(1);
});
