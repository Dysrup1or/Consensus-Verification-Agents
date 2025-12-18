'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock,
  RefreshCw,
  Zap,
} from 'lucide-react';
import { clsx } from 'clsx';

import {
  fetchAnalyticsSummary,
  fetchAnalyticsTrends,
  fetchAnalyticsRepos,
  fetchAnalyticsJudges,
  fetchAnalyticsHealth,
} from '@/lib/analytics-api';
import type {
  HealthResponse,
  JudgesResponse,
  MetricOption,
  PeriodOption,
  ReposResponse,
  SummaryResponse,
  TrendsResponse,
} from '@/lib/analytics-types';

import KPICard from '@/components/analytics/KPICard';
import DonutChart from '@/components/analytics/DonutChart';
import TrendChart from '@/components/analytics/TrendChart';
import RepoTable from '@/components/analytics/RepoTable';
import JudgePerformance from '@/components/analytics/JudgePerformance';
import HealthStatus from '@/components/analytics/HealthStatus';

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<PeriodOption>('24h');
  const [metric, setMetric] = useState<MetricOption>('pass_rate');

  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [trends, setTrends] = useState<TrendsResponse | null>(null);
  const [repos, setRepos] = useState<ReposResponse | null>(null);
  const [judges, setJudges] = useState<JudgesResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const days =
        period === '1h'
          ? 1
          : period === '6h'
          ? 1
          : period === '24h'
          ? 1
          : period === '7d'
          ? 7
          : 30;

      const [summaryData, trendsData, reposData, judgesData, healthData] =
        await Promise.all([
          fetchAnalyticsSummary(period),
          fetchAnalyticsTrends(days, metric),
          fetchAnalyticsRepos('pass_rate', 'desc', 10),
          fetchAnalyticsJudges(),
          fetchAnalyticsHealth(),
        ]);

      setSummary(summaryData);
      setTrends(trendsData);
      setRepos(reposData);
      setJudges(judgesData);
      setHealth(healthData);
    } catch (err: any) {
      console.error('Failed to fetch analytics:', err);
      setError(err?.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [metric, period]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-6 h-6 text-blue-500" />
            <h1 className="text-xl font-bold">Analytics Dashboard</h1>
          </div>
          <div className="flex items-center gap-4">
            {/* Period selector */}
            <div className="flex bg-zinc-800 rounded-lg p-1">
              {(['1h', '6h', '24h', '7d', '30d'] as PeriodOption[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={clsx(
                    'px-3 py-1 text-sm rounded transition-colors',
                    period === p
                      ? 'bg-blue-500 text-white'
                      : 'text-zinc-400 hover:text-white'
                  )}
                >
                  {p}
                </button>
              ))}
            </div>
            {/* Refresh button */}
            <button
              onClick={fetchData}
              disabled={loading}
              className="p-2 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <RefreshCw
                className={clsx('w-5 h-5', loading && 'animate-spin')}
              />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Error state */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-500">
            <AlertTriangle className="w-5 h-5 inline mr-2" />
            {error}
          </div>
        )}

        {/* KPI Cards */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KPICard
            title="Total Runs"
            value={summary?.total_runs ?? '-'}
            subtitle={`${period} period`}
            icon={<Activity className="w-5 h-5" />}
            color="blue"
          />
          <KPICard
            title="Pass Rate"
            value={
              summary?.verdicts.pass_rate
                ? `${summary.verdicts.pass_rate.toFixed(1)}%`
                : '-'
            }
            subtitle={`${summary?.verdicts.pass_count ?? 0} passed`}
            icon={<CheckCircle2 className="w-5 h-5" />}
            color="green"
          />
          <KPICard
            title="Avg Score"
            value={summary?.scores.avg?.toFixed(1) ?? '-'}
            subtitle={`Min: ${summary?.scores.min?.toFixed(1) ?? '-'} / Max: ${summary?.scores.max?.toFixed(1) ?? '-'}`}
            icon={<Zap className="w-5 h-5" />}
            color="purple"
          />
          <KPICard
            title="Avg Latency"
            value={
              summary?.latency.avg_seconds
                ? `${summary.latency.avg_seconds.toFixed(1)}s`
                : '-'
            }
            subtitle={`P95: ${summary?.latency.p95_seconds?.toFixed(1) ?? '-'}s`}
            icon={<Clock className="w-5 h-5" />}
            color="yellow"
          />
        </section>

        {/* Verdicts breakdown + Health */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          {/* Verdict Donut */}
          <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4">
            <h3 className="text-sm font-medium text-zinc-400 mb-4">
              Verdict Distribution
            </h3>
            <div className="flex items-center justify-center">
              <DonutChart
                data={[
                  {
                    label: 'Pass',
                    value: summary?.verdicts.pass_count ?? 0,
                    color: '#22c55e',
                  },
                  {
                    label: 'Fail',
                    value: summary?.verdicts.fail_count ?? 0,
                    color: '#ef4444',
                  },
                  {
                    label: 'Veto',
                    value: summary?.verdicts.veto_count ?? 0,
                    color: '#f59e0b',
                  },
                  {
                    label: 'Partial',
                    value: summary?.verdicts.partial_count ?? 0,
                    color: '#3b82f6',
                  },
                  {
                    label: 'Error',
                    value: summary?.verdicts.error_count ?? 0,
                    color: '#71717a',
                  },
                ]}
                size={160}
                strokeWidth={24}
                centerValue={`${summary?.verdicts.pass_rate?.toFixed(0) ?? 0}%`}
                centerLabel="Pass Rate"
              />
            </div>
            <div className="grid grid-cols-3 gap-2 mt-4 text-center text-xs">
              <div>
                <div className="w-2 h-2 rounded-full bg-green-500 mx-auto mb-1" />
                <span className="text-zinc-400">Pass</span>
                <p className="font-medium text-white">
                  {summary?.verdicts.pass_count ?? 0}
                </p>
              </div>
              <div>
                <div className="w-2 h-2 rounded-full bg-red-500 mx-auto mb-1" />
                <span className="text-zinc-400">Fail</span>
                <p className="font-medium text-white">
                  {summary?.verdicts.fail_count ?? 0}
                </p>
              </div>
              <div>
                <div className="w-2 h-2 rounded-full bg-yellow-500 mx-auto mb-1" />
                <span className="text-zinc-400">Veto</span>
                <p className="font-medium text-white">
                  {summary?.verdicts.veto_count ?? 0}
                </p>
              </div>
            </div>
          </div>

          {/* Trend Chart */}
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 mb-2">
              <label className="text-xs text-zinc-500">Metric:</label>
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value as MetricOption)}
                className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm text-white"
              >
                <option value="pass_rate">Pass Rate</option>
                <option value="avg_score">Avg Score</option>
                <option value="total_runs">Run Volume</option>
                <option value="avg_duration">Avg Duration</option>
              </select>
            </div>
            <TrendChart
              data={trends?.series[0]?.data ?? []}
              title={`${metric.replace('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase())} Over Time`}
              color={
                metric === 'pass_rate'
                  ? '#22c55e'
                  : metric === 'avg_score'
                  ? '#a855f7'
                  : metric === 'total_runs'
                  ? '#3b82f6'
                  : '#f59e0b'
              }
              valueFormatter={(v) =>
                metric === 'pass_rate'
                  ? `${v.toFixed(1)}%`
                  : metric === 'avg_duration'
                  ? `${v.toFixed(1)}s`
                  : v.toFixed(1)
              }
            />
          </div>
        </section>

        {/* Repos + Judges + Health */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <RepoTable repos={repos?.repos ?? []} />
          </div>
          <div className="space-y-6">
            <HealthStatus health={health} />
            <JudgePerformance judges={judges?.judges ?? []} />
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-800 mt-12">
        <div className="max-w-7xl mx-auto px-4 py-4 text-center text-xs text-zinc-500">
          Last updated: {summary?.generated_at ? new Date(summary.generated_at).toLocaleString() : '-'}
        </div>
      </footer>
    </div>
  );
}
