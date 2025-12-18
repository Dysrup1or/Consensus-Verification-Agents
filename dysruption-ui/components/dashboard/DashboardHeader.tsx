"use client";

import { clsx } from 'clsx';
import { Clock, Shield } from 'lucide-react';
import type { PipelineStatus } from '@/lib/types';

type Props = {
  status: PipelineStatus;
  isRunning: boolean;
  hasSession: boolean;
  showHistory: boolean;
  onSignOut: () => void;
  onToggleHistory: () => void;
};

export default function DashboardHeader({
  status,
  isRunning,
  hasSession,
  showHistory,
  onSignOut,
  onToggleHistory,
}: Props) {
  return (
    <header className="border-b border-border bg-surface/50 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <Shield className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Invariant</h1>
              <p className="text-xs text-textMuted">Invariant • Verification Coach</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface border border-border text-sm">
              <div
                className={clsx(
                  'w-2 h-2 rounded-full',
                  status === 'complete'
                    ? 'bg-success'
                    : status === 'error'
                      ? 'bg-danger'
                      : isRunning
                        ? 'bg-warning animate-pulse'
                        : 'bg-success'
                )}
              />
              <span className="text-textSecondary">
                {status === 'idle'
                  ? '🟢 Ready'
                  : status === 'complete'
                    ? '✅ Complete'
                    : status === 'error'
                      ? '❌ Error'
                      : '⏳ Analyzing...'}
              </span>
            </div>

            {hasSession ? (
              <button
                onClick={onSignOut}
                className="px-3 py-1.5 rounded-lg border border-border bg-surface text-sm hover:border-primary/50 transition-colors"
              >
                Sign out
              </button>
            ) : null}

            <button
              onClick={onToggleHistory}
              className={clsx(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-colors',
                showHistory
                  ? 'bg-primary text-white border-primary'
                  : 'bg-surface border-border hover:border-primary/50'
              )}
            >
              <Clock size={14} />
              History
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
