/**
 * Analytics API Client
 * 
 * Functions to fetch analytics data from the backend.
 */

import {
  SummaryResponse,
  TrendsResponse,
  ReposResponse,
  JudgesResponse,
  HealthResponse,
  PeriodOption,
  MetricOption,
  SortOption,
} from './analytics-types';

// Use the same proxy as main API
const API_BASE = '/api/cva';

/**
 * Fetch executive summary metrics.
 */
export async function fetchAnalyticsSummary(
  period: PeriodOption = '24h',
  repo?: string
): Promise<SummaryResponse> {
  const params = new URLSearchParams({ period });
  if (repo) params.set('repo', repo);
  
  const res = await fetch(`${API_BASE}/analytics/summary?${params}`);
  
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics summary: ${res.statusText}`);
  }
  
  return res.json();
}

/**
 * Fetch trend data for charts.
 */
export async function fetchAnalyticsTrends(
  days: number = 7,
  metric: MetricOption = 'pass_rate',
  repo?: string
): Promise<TrendsResponse> {
  const params = new URLSearchParams({
    days: String(days),
    metric,
  });
  if (repo) params.set('repo', repo);
  
  const res = await fetch(`${API_BASE}/analytics/trends?${params}`);
  
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics trends: ${res.statusText}`);
  }
  
  return res.json();
}

/**
 * Fetch repository leaderboard.
 */
export async function fetchAnalyticsRepos(
  sort: SortOption = 'pass_rate',
  order: 'asc' | 'desc' = 'desc',
  limit: number = 10
): Promise<ReposResponse> {
  const params = new URLSearchParams({
    sort,
    order,
    limit: String(limit),
  });
  
  const res = await fetch(`${API_BASE}/analytics/repos?${params}`);
  
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics repos: ${res.statusText}`);
  }
  
  return res.json();
}

/**
 * Fetch judge performance metrics.
 */
export async function fetchAnalyticsJudges(): Promise<JudgesResponse> {
  const res = await fetch(`${API_BASE}/analytics/judges`);
  
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics judges: ${res.statusText}`);
  }
  
  return res.json();
}

/**
 * Fetch system health status.
 */
export async function fetchAnalyticsHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/analytics/health`);
  
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics health: ${res.statusText}`);
  }
  
  return res.json();
}

/**
 * Trigger manual backfill of analytics.
 */
export async function triggerAnalyticsBackfill(
  limit?: number
): Promise<{ status: string; runs_processed: number }> {
  const params = limit ? new URLSearchParams({ limit: String(limit) }) : '';
  
  const res = await fetch(`${API_BASE}/analytics/backfill?${params}`, {
    method: 'POST',
  });
  
  if (!res.ok) {
    throw new Error(`Failed to trigger backfill: ${res.statusText}`);
  }
  
  return res.json();
}
