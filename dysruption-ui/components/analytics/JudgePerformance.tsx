'use client';

import { Shield } from 'lucide-react';
import type { JudgesResponse } from '@/lib/analytics-types';

export type JudgePerformanceProps = {
  judges: JudgesResponse['judges'];
};

export default function JudgePerformance({ judges }: JudgePerformanceProps) {
  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4">
      <h3 className="text-sm font-medium text-zinc-400 mb-4">Judge Performance</h3>
      <div className="space-y-3">
        {judges.map((judge) => (
          <div
            key={judge.judge_id}
            className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg"
          >
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-blue-500" />
              <div>
                <p className="text-sm font-medium text-white">{judge.judge_name}</p>
                <p className="text-xs text-zinc-500">{judge.total_evaluations} evaluations</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm font-medium text-white">{judge.avg_score.toFixed(1)}</p>
              <p className="text-xs text-zinc-500">
                {judge.veto_count} vetos ({judge.veto_rate.toFixed(1)}%)
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
