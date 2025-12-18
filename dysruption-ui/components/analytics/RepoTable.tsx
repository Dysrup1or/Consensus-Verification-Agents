'use client';

import { clsx } from 'clsx';
import { GitBranch, Minus, TrendingDown, TrendingUp } from 'lucide-react';
import type { ReposResponse } from '@/lib/analytics-types';
import Sparkline from '@/components/analytics/Sparkline';

export type RepoTableProps = {
  repos: ReposResponse['repos'];
};

export default function RepoTable({ repos }: RepoTableProps) {
  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-800">
        <h3 className="text-sm font-medium text-zinc-400">Repository Performance</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="px-4 py-3 font-medium">Repository</th>
              <th className="px-4 py-3 font-medium text-right">Runs</th>
              <th className="px-4 py-3 font-medium text-right">Pass Rate</th>
              <th className="px-4 py-3 font-medium text-right">Avg Score</th>
              <th className="px-4 py-3 font-medium text-right">7d Trend</th>
              <th className="px-4 py-3 font-medium text-center">Activity</th>
            </tr>
          </thead>
          <tbody>
            {repos.map((repo) => (
              <tr
                key={repo.repo_full_name}
                className="border-b border-zinc-800/50 hover:bg-zinc-800/50 transition-colors"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-zinc-500" />
                    <span className="text-sm text-white font-medium">{repo.repo_full_name}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-sm text-zinc-300">{repo.total_runs}</td>
                <td className="px-4 py-3 text-right">
                  <span
                    className={clsx(
                      'text-sm font-medium',
                      repo.pass_rate >= 80
                        ? 'text-green-500'
                        : repo.pass_rate >= 50
                          ? 'text-yellow-500'
                          : 'text-red-500'
                    )}
                  >
                    {repo.pass_rate.toFixed(1)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-sm text-zinc-300">{repo.avg_score?.toFixed(1) ?? '-'}</td>
                <td className="px-4 py-3 text-right">
                  {repo.trend === 'up' && <TrendingUp className="w-4 h-4 text-green-500 inline" />}
                  {repo.trend === 'down' && <TrendingDown className="w-4 h-4 text-red-500 inline" />}
                  {repo.trend === 'stable' && <Minus className="w-4 h-4 text-zinc-500 inline" />}
                </td>
                <td className="px-4 py-3 flex justify-center">
                  <Sparkline
                    data={repo.sparkline}
                    color={repo.trend === 'up' ? '#22c55e' : repo.trend === 'down' ? '#ef4444' : '#71717a'}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
