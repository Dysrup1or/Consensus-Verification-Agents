import { clsx } from 'clsx';

export type LiveActivityEvent = {
  id: string;
  ts: number;
  kind: 'progress' | 'status' | 'verdict' | 'error' | 'system';
  message: string;
};

function formatTime(ts: number) {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

export default function LiveActivity({ events }: { events: LiveActivityEvent[] }) {
  if (!events || events.length === 0) {
    return (
      <div className="mt-6 p-4 rounded-xl bg-bg border border-border">
        <p className="text-xs text-textMuted uppercase tracking-wider">Live Activity</p>
        <p className="mt-2 text-sm text-textSecondary">No activity yet.</p>
      </div>
    );
  }

  return (
    <div className="mt-6 p-4 rounded-xl bg-bg border border-border">
      <div className="flex items-center justify-between">
        <p className="text-xs text-textMuted uppercase tracking-wider">Live Activity</p>
        <p className="text-xs text-textMuted">Latest first</p>
      </div>

      <div className="mt-3 space-y-2 max-h-[320px] overflow-auto">
        {events.map((e) => (
          <div key={e.id} className="flex gap-3 text-sm">
            <span className="text-xs text-textMuted font-mono shrink-0">{formatTime(e.ts)}</span>
            <span
              className={clsx(
                'shrink-0 text-[10px] px-2 py-0.5 rounded-full border',
                e.kind === 'error'
                  ? 'border-danger/30 text-danger bg-danger/10'
                  : e.kind === 'verdict'
                    ? 'border-success/30 text-success bg-success/10'
                    : e.kind === 'system'
                      ? 'border-border text-textMuted bg-surface'
                      : 'border-border text-textSecondary bg-surface'
              )}
            >
              {e.kind}
            </span>
            <span className="text-textSecondary break-words">{e.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
