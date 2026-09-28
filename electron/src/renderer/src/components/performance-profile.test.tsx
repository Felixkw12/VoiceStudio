import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/api/client', () => ({
  apiJson: mocks.api,
  describeError: (error: Error) => error.message,
}));
vi.mock('sonner', () => ({ toast: { success: mocks.success, error: mocks.error } }));
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/lib/i18n-text', () => ({ tr: (key: string) => key }));
vi.mock('@/hooks/use-backend-status', () => ({ useBackendStatus: () => ({ stage: 'ready' }) }));
vi.mock('@/hooks/use-engines', () => ({
  useEngines: () => ({ data: {} }),
  engineFamilyState: () => null,
}));
vi.mock('@/hooks/use-dictation-selection', () => ({ useDictationSelection: () => ({}) }));
vi.mock('@/lib/app-activity', () => ({ useAppActivities: () => ({}) }));
import { PerformanceProfile } from './performance-profile';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function mount(variant: 'compact' | 'settings', installed: boolean, global = 'balanced') {
  let state = {
    global,
    implemented_families: ['tts'],
    targets: { tts: {} },
    selections: { tts: { engine: 'other' } },
  };
  mocks.api.mockImplementation(async (path, init) => {
    if (path === '/models')
      return {
        models: [{ repo_id: 'k2-fsa/OmniVoice', supported: true, installed, size_gb: 2.4 }],
      };
    if (path === '/batch/jobs?status=active&limit=100') return [];
    if (init?.method === 'PUT') state = { ...state, global: JSON.parse(init.body).tier };
    return state;
  });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <PerformanceProfile variant={variant} />
    </QueryClientProvider>,
  );
}

async function chooseMax(variant: 'compact' | 'settings') {
  if (variant === 'settings') {
    const button = await screen.findByRole('radio', { name: 'performanceProfile.max' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
  } else {
    const slider = await screen.findByRole('slider');
    await waitFor(() => expect(slider).not.toHaveAttribute('aria-disabled', 'true'));
    slider.focus();
    fireEvent.keyDown(slider, { key: 'End' });
    fireEvent.keyUp(slider, { key: 'End' });
  }
}

it.each(['compact', 'settings'] as const)(
  '%s rejects missing Max models without a success toast or PUT',
  async (variant) => {
    mount(variant, false);
    await chooseMax(variant);
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('performanceProfile.max'),
    );
    if (variant === 'compact')
      expect(screen.getByRole('link', { name: 'modelSettings.models' })).toHaveAttribute(
        'href',
        '/settings/models',
      );
    expect(mocks.error).not.toHaveBeenCalled();
    expect(screen.queryByText('common.retry')).not.toBeInTheDocument();
    expect(mocks.success).not.toHaveBeenCalled();
    expect(mocks.api.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false);
  },
);

it.each(['compact', 'settings'] as const)('%s applies installed Max models', async (variant) => {
  mount(variant, true);
  await chooseMax(variant);
  await waitFor(() => expect(mocks.success).toHaveBeenCalledWith('performanceProfile.applied'));
  expect(mocks.api).toHaveBeenCalledWith('/api/settings/performance-profile', {
    method: 'PUT',
    body: JSON.stringify({ tier: 'max', family: null }),
  });
});

it('marks an old persisted Max selection as incomplete instead of presenting it as ready', async () => {
  mount('compact', false, 'max');
  expect(await screen.findByRole('status')).toHaveTextContent('models.pack_needs_models');
});
