import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { usePerformanceProfile } from './use-performance-profile';

const mocks = vi.hoisted(() => ({ dub: vi.fn(), clone: vi.fn(), api: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
vi.mock('@/lib/api/client', () => ({ apiJson: mocks.api }));
vi.mock('@/lib/store/clone-settings', () => ({ patchCloneSettings: mocks.clone }));
vi.mock('@/features/dub/dub-session', () => ({ setDubProduction: mocks.dub }));
vi.mock('./use-backend-status', () => ({ useBackendStatus: () => ({ stage: 'ready' }) }));
vi.mock('@/lib/i18n-text', () => ({ tr: (key: string) => key }));
const installedCatalogue = {
  models: [{ repo_id: 'k2-fsa/OmniVoice', supported: true, installed: true, size_gb: 2.4 }],
};
function respondWithState(state: unknown) {
  mocks.api.mockImplementation(async (path) => (path === '/models' ? installedCatalogue : state));
}

it('rejects a global Max change before saving when its models are missing', async () => {
  const state = {
    global: 'balanced',
    targets: { tts: {} },
    selections: { tts: { engine: 'other' } },
  };
  mocks.api.mockImplementation(async (path) =>
    path === '/models'
      ? {
          models: [
            { repo_id: 'k2-fsa/OmniVoice', supported: true, installed: false, size_gb: 2.4 },
          ],
        }
      : state,
  );
  const client = new QueryClient();
  client.setQueryData(['performance-profile'], state);
  const { result, unmount } = renderHook(() => usePerformanceProfile(), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  try {
    await expect(result.current.setTier({ tier: 'max', family: null })).rejects.toThrow();
    expect(mocks.api.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false);
    expect(client.getQueryData(['performance-profile'])).toEqual(state);
  } finally {
    unmount();
    client.clear();
  }
});

it('shares pack changes in both directions between settings and sidebar consumers', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const initial = {
    global: 'balanced',
    targets: { tts: {} },
    selections: { tts: { engine: 'other' } },
  };
  client.setQueryData(['performance-profile'], initial);
  mocks.api.mockImplementation(async (_path, init) =>
    _path === '/models'
      ? installedCatalogue
      : {
          ...initial,
          global: init?.body ? JSON.parse(init.body).tier : 'balanced',
        },
  );
  const { result, unmount } = renderHook(
    () => ({
      settings: usePerformanceProfile(),
      sidebar: usePerformanceProfile(),
    }),
    {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    },
  );
  await act(async () => {
    await result.current.settings.setTier({ tier: 'quality', family: null });
  });
  await waitFor(() => expect(result.current.sidebar.data?.global).toBe('quality'));
  await act(async () => {
    await result.current.sidebar.setTier({ tier: 'fast', family: null });
  });
  await waitFor(() => expect(result.current.settings.data?.global).toBe('fast'));
  unmount();
  client.clear();
});

it('changes the global preset without replacing Dubbing production overrides', async () => {
  const state = {
    targets: { tts: { steps: 32, postprocess: true } },
    selections: { tts: { engine: 'omnivoice' } },
  };
  respondWithState(state);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { result, unmount } = renderHook(() => usePerformanceProfile(), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  await act(async () => {
    await result.current.setTier({ tier: 'quality', family: null });
  });
  expect(mocks.clone).toHaveBeenCalledWith({ steps: 32, postprocess: true });
  expect(mocks.dub).not.toHaveBeenCalled();
  expect(mocks.api.mock.calls.filter(([, init]) => init?.method === 'PUT')).toEqual([
    [
      '/api/settings/performance-profile',
      {
        method: 'PUT',
        body: JSON.stringify({ tier: 'quality', family: null }),
      },
    ],
  ]);
  unmount();
  client.clear();
});

it('keeps an applied backend preset successful when the clone draft chunk cannot load', async () => {
  mocks.clone.mockImplementationOnce(() => {
    throw new Error('draft unavailable');
  });
  respondWithState({
    targets: { tts: { steps: 8, postprocess: false } },
    selections: { tts: { engine: 'omnivoice' } },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { result, unmount } = renderHook(() => usePerformanceProfile(), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });

  await expect(
    act(async () => result.current.setTier({ tier: 'fast', family: 'tts' })),
  ).resolves.toEqual(
    expect.objectContaining({ targets: { tts: { steps: 8, postprocess: false } } }),
  );
  expect(mocks.api).toHaveBeenCalledWith('/api/settings/performance-profile', {
    method: 'PUT',
    body: JSON.stringify({ tier: 'fast', family: 'tts' }),
  });
  unmount();
  client.clear();
});

it('finishes saving before dependent catalogue refreshes complete', async () => {
  respondWithState({
    targets: { tts: { steps: 16, postprocess: true } },
    selections: { tts: { engine: 'omnivoice' } },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, 'invalidateQueries').mockImplementation(() => new Promise(() => {}));
  const { result, unmount } = renderHook(() => usePerformanceProfile(), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });

  let saved = false;
  await act(async () => {
    void result.current.setTier({ tier: 'balanced', family: null }).then(() => {
      saved = true;
    });
    await vi.waitFor(() => expect(saved).toBe(true));
  });

  unmount();
  client.clear();
});
