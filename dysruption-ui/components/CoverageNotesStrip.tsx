'use client';

import React, { useMemo } from 'react';
import { Info } from 'lucide-react';
import { clsx } from 'clsx';
import type { TelemetryCoverage } from '@/lib/types';

export interface CoverageNotesStripProps {
  coverage: TelemetryCoverage;
}

function groupReasons(skipReasons: Record<string, string>): Array<{ reason: string; count: number; files: string[] }> {
  const groups = new Map<string, string[]>();
  for (const [file, reason] of Object.entries(skipReasons || {})) {
    const key = reason || 'unknown';
    const list = groups.get(key) ?? [];
    list.push(file);
    groups.set(key, list);
  }

  return [...groups.entries()]
    .map(([reason, files]) => ({ reason, count: files.length, files }))
    .sort((a, b) => b.count - a.count);
}

export default function CoverageNotesStrip({ coverage }: CoverageNotesStripProps) {
  const skipReasons = coverage?.skip_reasons ?? {};

  const shouldShow =
    (Number.isFinite(coverage?.fully_covered_percent_of_changed) && coverage.fully_covered_percent_of_changed < 100) ||
    Object.keys(skipReasons).length > 0;

  const grouped = useMemo(() => groupReasons(skipReasons), [skipReasons]);

  if (!shouldShow) return null;

  const totalSkipped = Object.keys(skipReasons).length;
  const showFileList = totalSkipped > 0 && totalSkipped <= 5;

  return (
    <div className={clsx('p-4 rounded-xl border', 'bg-panel/30 border-border')}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          <Info className="w-4 h-4 text-textMuted" />
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-sm font-semibold">Coverage Notes</h4>
            <div className="text-xs text-textMuted font-mono">
              Fully covered: {Math.round(coverage.fully_covered_percent_of_changed)}%
            </div>
          </div>

          {grouped.length > 0 ? (
            <div className="mt-2 text-sm">
              <div className="flex flex-wrap gap-2">
                {grouped.map((g) => (
                  <span
                    key={g.reason}
                    className="text-[10px] px-2 py-0.5 rounded uppercase tracking-wider border bg-bg border-border text-textMuted"
                    title={g.reason}
                  >
                    {g.reason}: {g.count}
                  </span>
                ))}
              </div>

              {showFileList && (
                <div className="mt-2 text-xs text-textMuted">
                  <div className="mb-1">Skipped files:</div>
                  <ul className="list-disc pl-5 space-y-0.5">
                    {Object.entries(skipReasons).map(([file, reason]) => (
                      <li key={file} className="font-mono">
                        {file} ({reason})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-2 text-sm text-textMuted">Coverage was not complete for this run.</p>
          )}
        </div>
      </div>
    </div>
  );
}
