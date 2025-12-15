import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';

jest.mock('@/lib/ws', () => {
  class CVAWebSocket {
    onMessage() {}
    onStatusChange() {}
    start() {}
    stop() {}
  }
  return { CVAWebSocket };
});

jest.mock('@/components/FileDropZone', () => {
  return function FileDropZoneMock(props: any) {
    return (
      <button onClick={() => props.onFilesSelected(null, 'C:\\Temp\\myproj')}>
        SelectPath
      </button>
    );
  };
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
  it('shows Cancel while running and calls cancelRun', async () => {
    render(<Dashboard />);

    fireEvent.click(screen.getByText('SelectPath'));
    fireEvent.click(screen.getByRole('button', { name: /Verify Invariant/i }));

    const cancel = await screen.findByRole('button', { name: 'Cancel' });
    fireEvent.click(cancel);

    expect(cancelRun).toHaveBeenCalledWith('run123');
    expect(await screen.findByText(/Cancelled run/i)).toBeInTheDocument();
  });

  it('shows error toast if cancel fails', async () => {
    (cancelRun as jest.Mock).mockRejectedValueOnce(new Error('nope'));

    render(<Dashboard />);

    fireEvent.click(screen.getByText('SelectPath'));
    fireEvent.click(screen.getByRole('button', { name: /Verify Invariant/i }));

    const cancel = await screen.findByRole('button', { name: 'Cancel' });
    fireEvent.click(cancel);

    expect(await screen.findByText(/Failed to cancel: nope/i)).toBeInTheDocument();
  });
});
