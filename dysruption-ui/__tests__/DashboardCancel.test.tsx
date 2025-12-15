import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('next-auth/react', () => {
  return {
    useSession: () => ({
      data: {
        user: { name: 'Test User' },
        githubAccessToken: 'gho_testtoken',
      },
      status: 'authenticated',
    }),
    signIn: jest.fn(async () => undefined),
  };
});

jest.mock('@/lib/ws', () => {
  class CVAWebSocket {
    onMessage() {}
    onStatusChange() {}
    start() {}
    stop() {}
  }
  return { CVAWebSocket };
});

jest.mock('@/components/ConstitutionInput', () => {
  return function ConstitutionInputMock() {
    return <div>ConstitutionInput</div>;
  };
});

jest.mock('@/components/Verdict', () => () => <div />);
jest.mock('@/components/PatchDiff', () => () => <div />);
jest.mock('@/components/PromptRecommendation', () => () => <div />);

jest.mock('@/components/Toast', () => {
  return function ToastMock({ message }: any) {
    if (!message) return null;
    return <div role="status">{message}</div>;
  };
});

jest.mock('@/lib/api', () => {
  return {
    startRun: jest.fn(async () => ({ run_id: 'run123', status: 'scanning', message: 'started' })),
    fetchVerdict: jest.fn(async () => ({ ready: false })),
    fetchRuns: jest.fn(async () => ({ runs: [], total: 0 })),
    fetchStatus: jest.fn(async () => ({ run_id: 'run123', state: { status: 'scanning', current_phase: 'scanning', progress_percent: 0, message: '...', started_at: null, completed_at: null } })),
    fetchPrompt: jest.fn(async () => ({ ready: false, prompt: null })),
    fetchVerdictsPayload: jest.fn(async () => ({})),
    cancelRun: jest.fn(async () => ({ cancelled: true, message: 'cancelled' })),
  };
});

import Dashboard from '@/app/page';
import { cancelRun } from '@/lib/api';

describe('Dashboard cancel', () => {
  beforeEach(() => {
    (global as any).fetch = jest.fn(async (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : String(input?.url || input);

      if (url.startsWith('/api/github/repos')) {
        return {
          ok: true,
          json: async () => ({
            repos: [
              { id: 1, full_name: 'acme/repo', private: false, default_branch: 'main' },
            ],
          }),
        } as any;
      }

      if (url.startsWith('/api/github/branches')) {
        return {
          ok: true,
          json: async () => ({
            branches: [{ name: 'main', protected: false }],
          }),
        } as any;
      }

      if (url.startsWith('/api/github/import') && (init?.method || 'GET') === 'POST') {
        return {
          ok: true,
          json: async () => ({
            targetPath: '/tmp/upload_123',
            fileCount: 3,
            repo: 'acme/repo',
            ref: 'main',
          }),
        } as any;
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('shows Cancel while running and calls cancelRun', async () => {
    render(<Dashboard />);

    const repoSelect = await screen.findByLabelText('Repository');
    fireEvent.change(repoSelect, { target: { value: 'acme/repo' } });

    const verify = screen.getByRole('button', { name: /Verify Invariant/i });
    await waitFor(() => expect(verify).not.toBeDisabled());
    fireEvent.click(verify);

    const cancel = await screen.findByRole('button', { name: 'Cancel' });
    fireEvent.click(cancel);

    expect(cancelRun).toHaveBeenCalledWith('run123');
    expect(await screen.findByText(/Cancelled run/i)).toBeInTheDocument();
  });

  it('shows error toast if cancel fails', async () => {
    (cancelRun as jest.Mock).mockRejectedValueOnce(new Error('nope'));

    render(<Dashboard />);

    const repoSelect = await screen.findByLabelText('Repository');
    fireEvent.change(repoSelect, { target: { value: 'acme/repo' } });

    const verify = screen.getByRole('button', { name: /Verify Invariant/i });
    await waitFor(() => expect(verify).not.toBeDisabled());
    fireEvent.click(verify);

    const cancel = await screen.findByRole('button', { name: 'Cancel' });
    fireEvent.click(cancel);

    expect(await screen.findByText(/Failed to cancel: nope/i)).toBeInTheDocument();
  });
});
