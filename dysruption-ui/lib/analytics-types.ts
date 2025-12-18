/**
 * Analytics API Types
 * 
 * Type definitions for the Trend Analytics Dashboard API responses.
 */

// =========================================================================
// SUMMARY TYPES
// =========================================================================

export interface VerdictBreakdown {
  pass_count: number;
  fail_count: number;
  veto_count: number;
  partial_count: number;
  error_count: number;
  pass_rate: number;
  fail_rate: number;
  veto_rate: number;
}

export interface LatencyMetrics {
  avg_seconds: number | null;
  p50_seconds: number | null;
  p95_seconds: number | null;
  p99_seconds: number | null;
}

export interface ScoreMetrics {
  avg: number | null;
  min: number | null;
  max: number | null;
}

export interface SummaryResponse {
  period: string;
  total_runs: number;
  verdicts: VerdictBreakdown;
  scores: ScoreMetrics;
  latency: LatencyMetrics;
  total_tokens: number;
  unique_repos: number;
  unique_projects: number;
  generated_at: string;
}

// =========================================================================
// TRENDS TYPES
// =========================================================================

export interface TrendPoint {
  date: string;
  value: number;
}

export interface TrendSeries {
  name: string;
  data: TrendPoint[];
}

export interface TrendsResponse {
  period_start: string;
  period_end: string;
  granularity: 'hourly' | 'daily';
  series: TrendSeries[];
}

// =========================================================================
// REPOS TYPES
// =========================================================================

export interface RepoSummary {
  repo_full_name: string;
  total_runs: number;
  pass_rate: number;
  avg_score: number | null;
  runs_7d: number;
  trend: 'up' | 'down' | 'stable';
  sparkline: number[];
}

export interface ReposResponse {
  repos: RepoSummary[];
  total_repos: number;
}

// =========================================================================
// JUDGES TYPES
// =========================================================================

export interface JudgeSummary {
  judge_id: string;
  judge_name: string;
  total_evaluations: number;
  avg_score: number;
  score_stddev: number;
  veto_count: number;
  veto_rate: number;
  domain: string | null;
}

export interface JudgesResponse {
  judges: JudgeSummary[];
}

// =========================================================================
// HEALTH TYPES
// =========================================================================

export interface ProviderHealth {
  name: string;
  healthy: boolean;
  latency_ms: number | null;
}

export interface HealthResponse {
  healthy: boolean;
  runs_per_hour: number;
  avg_latency_seconds: number;
  error_rate: number;
  providers: ProviderHealth[];
  last_updated: string;
}

// =========================================================================
// PERIOD OPTIONS
// =========================================================================

export type PeriodOption = '1h' | '6h' | '24h' | '7d' | '30d';
export type MetricOption = 'pass_rate' | 'avg_score' | 'total_runs' | 'avg_duration';
export type SortOption = 'pass_rate' | 'total_runs' | 'avg_score' | 'last_run';
