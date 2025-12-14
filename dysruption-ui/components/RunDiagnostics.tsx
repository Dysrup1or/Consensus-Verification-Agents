'use client';

import React, { useMemo } from 'react';
import { clsx } from 'clsx';
import { Activity, GitBranch, DatabaseZap, Layers } from 'lucide-react';
import type { RunTelemetry } from '@/lib/types';

export interface RunDiagnosticsProps {
  telemetry: RunTelemetry | null;
}

function formatMaybe(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'string' && value.trim().length > 0) return value;
  return '—';
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  }
  return sorted[mid];
}

export default function RunDiagnostics({ telemetry }: RunDiagnosticsProps) {
  const batchStats = useMemo(() => {
    const latencies = telemetry?.latency?.lane2_llm_per_item_latency_ms ?? null;
    if (!latencies || !Array.isArray(latencies) || latencies.length === 0) return null;
    const filtered = latencies.filter((n) => typeof n === 'number' && Number.isFinite(n) && n >= 0);
    if (filtered.length === 0) return null;
    const min = Math.min(...filtered);
    const med = median(filtered);
    const max = Math.max(...filtered);
    return { min, median: med, max, count: filtered.length };
  }, [telemetry]);

  if (!telemetry) {
    return (
      <div className="p-4 rounded-xl bg-surface border border-border">
        <div className="flex items-center gap-2 mb-1">
          <Activity className="w-4 h-4 text-textMuted" />
          <h3 className="text-sm font-semibold">Run Diagnostics</h3>
        </div>
        <p className="text-sm text-textMuted">Diagnostics unavailable for this run.</p>
      </div>
    );
  }

  const coverage = telemetry.coverage;
  const router = telemetry.router;
  const cache = telemetry.cache;
  const latency = telemetry.latency;

  const coveredPct = Number.isFinite(coverage?.fully_covered_percent_of_changed)
    ? Math.round(coverage.fully_covered_percent_of_changed)
    : null;

  const hasFallback = Boolean(router?.fallback_chain && router.fallback_chain.length > 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Activity className="w-5 h-5 text-primary" />
        <h3 className="text-lg font-semibold">Run Diagnostics</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Coverage */}
        <div className="p-4 rounded-xl bg-surface border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Layers className="w-4 h-4 text-primary" />
            <p className="text-xs text-textMuted uppercase tracking-wider">Coverage</p>
          </div>
          <div className="flex items-end justify-between">
            <div>
              <p className="text-2xl font-bold">
                {coveredPct === null ? '—' : `${coveredPct}%`}
              </p>
              <p className="text-xs text-textMuted">
                {formatMaybe(coverage.changed_files_fully_covered_count)}/{formatMaybe(coverage.changed_files_total)} changed files fully covered
              </p>
            </div>
            <div className="text-right text-xs text-textMuted">
              <div>Headers covered: {formatMaybe(coverage.header_covered_count)}</div>
              <div>Forced files: {formatMaybe(coverage.forced_files_count)}</div>
            </div>
          </div>
        </div>

        {/* Routing */}
        <div className="p-4 rounded-xl bg-surface border border-border">
          <div className="flex items-center gap-2 mb-2">
            <GitBranch className="w-4 h-4 text-primary" />
            <p className="text-xs text-textMuted uppercase tracking-wider">Routing</p>
          </div>

          {router ? (
            <div className="space-y-1 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-textMuted">Lane</span>
                <span className="font-mono">{formatMaybe(router.lane_used)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-textMuted">Provider</span>
                <span className="font-mono">{formatMaybe(router.provider)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-textMuted">Model</span>
                <span className="font-mono">{formatMaybe(router.model)}</span>
              </div>

              <div className="pt-2">
                <span
                  className={clsx(
                    'text-[10px] px-2 py-0.5 rounded uppercase tracking-wider border',
                    hasFallback
                      ? 'bg-warning/10 text-warning border-warning/30'
                      : 'bg-success/10 text-success border-success/30'
                  )}
                >
                  {hasFallback ? 'Fallback used' : 'No fallback'}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-textMuted">Router unavailable.</p>
          )}
        </div>

        {/* Cache */}
        <div className="p-4 rounded-xl bg-surface border border-border">
          <div className="flex items-center gap-2 mb-2">
            <DatabaseZap className="w-4 h-4 text-primary" />
            <p className="text-xs text-textMuted uppercase tracking-wider">Cache</p>
          </div>

          <div className="space-y-1 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-textMuted">Status</span>
              <span
                className={clsx(
                  'text-[10px] px-2 py-0.5 rounded uppercase tracking-wider border',
                  cache.cached_vs_uncached === 'cached'
                    ? 'bg-success/10 text-success border-success/30'
                    : cache.cached_vs_uncached === 'uncached'
                      ? 'bg-warning/10 text-warning border-warning/30'
                      : 'bg-panel text-textMuted border-border'
                )}
              >
                {formatMaybe(cache.cached_vs_uncached)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-textMuted">Intent</span>
              <span className="font-mono text-xs">{formatMaybe(cache.intent)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-textMuted">Provider signal</span>
              <span className="font-mono text-xs">{formatMaybe(cache.provider_cache_signal)}</span>
            </div>
          </div>
        </div>

        {/* Batch */}
        <div className="p-4 rounded-xl bg-surface border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Layers className="w-4 h-4 text-primary" />
            <p className="text-xs text-textMuted uppercase tracking-wider">Batch</p>
          </div>

          <div className="space-y-1 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-textMuted">Size</span>
              <span className="font-mono">{formatMaybe(latency.lane2_llm_batch_size)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-textMuted">Mode</span>
              <span className="font-mono">{formatMaybe(latency.lane2_llm_batch_mode)}</span>
            </div>
            {batchStats ? (
              <div className="pt-2 text-xs text-textMuted">
                Per-item latency (ms): min {Math.round(batchStats.min)}, median {Math.round(batchStats.median)}, max {Math.round(batchStats.max)}
              </div>
            ) : (
              <div className="pt-2 text-xs text-textMuted">Per-item latency unavailable.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
