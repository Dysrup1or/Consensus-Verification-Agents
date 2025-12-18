'use client';

import { clsx } from 'clsx';
import { CheckCircle2, XCircle } from 'lucide-react';
import type { HealthResponse } from '@/lib/analytics-types';

export type HealthStatusProps = {
  health: HealthResponse | null;
};

export default function HealthStatus({ health }: HealthStatusProps) {
  if (!health) return null;

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-zinc-400">System Health</h3>
        <div
          className={clsx(
            'flex items-center gap-1 px-2 py-1 rounded text-xs font-medium',
            health.healthy ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'
          )}
        >
          {health.healthy ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
          {health.healthy ? 'Healthy' : 'Degraded'}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <p className="text-xs text-zinc-500">Runs/Hour</p>
          <p className="text-lg font-bold text-white">{health.runs_per_hour}</p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Avg Latency</p>
          <p className="text-lg font-bold text-white">{health.avg_latency_seconds.toFixed(1)}s</p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Error Rate</p>
          <p className={clsx('text-lg font-bold', health.error_rate < 5 ? 'text-green-500' : 'text-red-500')}>
            {health.error_rate.toFixed(1)}%
          </p>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-xs text-zinc-500 mb-1">Provider Status</p>
        {health.providers.map((provider) => (
          <div key={provider.name} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <div
                className={clsx('w-2 h-2 rounded-full', provider.healthy ? 'bg-green-500' : 'bg-red-500')}
              />
              <span className="text-zinc-300">{provider.name}</span>
            </div>
            <span className="text-zinc-500">{provider.latency_ms ? `${provider.latency_ms}ms` : '-'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
