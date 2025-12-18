-- Migration: 003_analytics_tables.sql
-- Description: Add tables for Trend Analytics Dashboard
-- Created: 2025-12-17

-- ============================================================================
-- ANALYTICS RUN METRICS
-- Denormalized run records optimized for fast analytics queries
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_run_metrics (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    project_id TEXT,
    repo_full_name TEXT,
    branch TEXT,
    
    -- Verdict data
    verdict TEXT NOT NULL CHECK (verdict IN ('PASS', 'FAIL', 'VETO', 'PARTIAL', 'ERROR')),
    overall_score REAL,
    
    -- Timing
    started_at TEXT,  -- ISO timestamp
    finished_at TEXT, -- ISO timestamp
    duration_seconds REAL,
    llm_latency_ms INTEGER,
    
    -- Token metrics
    token_count INTEGER,
    llm_input_tokens INTEGER,
    
    -- Judge breakdown (scores 1-10)
    architect_score REAL,
    security_score REAL,
    user_proxy_score REAL,
    
    -- Veto tracking
    veto_triggered INTEGER DEFAULT 0,  -- SQLite boolean
    veto_judge TEXT,
    veto_confidence REAL,
    
    -- Static analysis
    static_issues_count INTEGER DEFAULT 0,
    critical_issues_count INTEGER DEFAULT 0,
    
    -- Coverage metrics
    files_covered INTEGER DEFAULT 0,
    files_total INTEGER DEFAULT 0,
    
    -- Criteria tracking
    criteria_passed INTEGER DEFAULT 0,
    criteria_total INTEGER DEFAULT 0,
    
    -- Mode and event info
    mode TEXT,  -- 'diff', 'full', etc.
    event_type TEXT,  -- 'push', 'pr', 'manual', etc.
    
    -- Indexable date fields (stored as TEXT for SQLite)
    date_bucket TEXT,  -- YYYY-MM-DD
    hour_bucket INTEGER,  -- 0-23
    
    -- Metadata
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_analytics_run_date ON analytics_run_metrics(date_bucket);
CREATE INDEX IF NOT EXISTS idx_analytics_run_repo ON analytics_run_metrics(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_analytics_run_verdict ON analytics_run_metrics(verdict);
CREATE INDEX IF NOT EXISTS idx_analytics_run_project ON analytics_run_metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_analytics_run_created ON analytics_run_metrics(created_at);

-- ============================================================================
-- ANALYTICS DAILY ROLLUPS
-- Pre-aggregated daily metrics for fast trend queries
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_daily_rollups (
    id TEXT PRIMARY KEY,
    date_bucket TEXT NOT NULL,  -- YYYY-MM-DD
    repo_full_name TEXT,        -- NULL for global rollup
    
    -- Run counts
    total_runs INTEGER DEFAULT 0,
    pass_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    veto_count INTEGER DEFAULT 0,
    partial_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    
    -- Computed rates (stored for efficiency)
    pass_rate REAL,
    fail_rate REAL,
    veto_rate REAL,
    
    -- Score aggregates
    avg_score REAL,
    min_score REAL,
    max_score REAL,
    
    -- Duration aggregates
    avg_duration_seconds REAL,
    min_duration_seconds REAL,
    max_duration_seconds REAL,
    p50_duration_seconds REAL,
    p75_duration_seconds REAL,
    p95_duration_seconds REAL,
    p99_duration_seconds REAL,
    
    -- Token aggregates
    total_tokens INTEGER DEFAULT 0,
    avg_tokens REAL,
    
    -- Judge score averages
    avg_architect_score REAL,
    avg_security_score REAL,
    avg_user_proxy_score REAL,
    
    -- Static analysis totals
    total_static_issues INTEGER DEFAULT 0,
    total_critical_issues INTEGER DEFAULT 0,
    
    -- Unique counts
    unique_repos INTEGER DEFAULT 0,
    unique_projects INTEGER DEFAULT 0,
    
    -- Rollup metadata
    computed_at TEXT DEFAULT (datetime('now')),
    
    -- Ensure one rollup per date per repo (or global)
    UNIQUE(date_bucket, repo_full_name)
);

-- Indexes for trend queries
CREATE INDEX IF NOT EXISTS idx_rollups_date ON analytics_daily_rollups(date_bucket);
CREATE INDEX IF NOT EXISTS idx_rollups_repo ON analytics_daily_rollups(repo_full_name);

-- ============================================================================
-- ANALYTICS HOURLY ROLLUPS
-- For more granular recent data (last 48 hours)
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_hourly_rollups (
    id TEXT PRIMARY KEY,
    datetime_bucket TEXT NOT NULL,  -- YYYY-MM-DD HH:00
    repo_full_name TEXT,            -- NULL for global
    
    -- Run counts
    total_runs INTEGER DEFAULT 0,
    pass_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    veto_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    
    -- Averages
    avg_score REAL,
    avg_duration_seconds REAL,
    
    -- Token usage
    total_tokens INTEGER DEFAULT 0,
    
    -- Metadata
    computed_at TEXT DEFAULT (datetime('now')),
    
    UNIQUE(datetime_bucket, repo_full_name)
);

CREATE INDEX IF NOT EXISTS idx_hourly_datetime ON analytics_hourly_rollups(datetime_bucket);

-- ============================================================================
-- ANALYTICS REPOSITORY STATS
-- Aggregated per-repository statistics
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_repo_stats (
    id TEXT PRIMARY KEY,
    repo_full_name TEXT NOT NULL UNIQUE,
    
    -- Lifetime totals
    total_runs INTEGER DEFAULT 0,
    total_pass INTEGER DEFAULT 0,
    total_fail INTEGER DEFAULT 0,
    total_veto INTEGER DEFAULT 0,
    
    -- Computed rates
    lifetime_pass_rate REAL,
    
    -- Running averages
    avg_score REAL,
    avg_duration_seconds REAL,
    
    -- Last 7 days metrics
    runs_7d INTEGER DEFAULT 0,
    pass_rate_7d REAL,
    
    -- Last 30 days metrics
    runs_30d INTEGER DEFAULT 0,
    pass_rate_30d REAL,
    
    -- Trend data (JSON array of last 14 daily values)
    sparkline_runs TEXT,      -- e.g., "[5,6,4,7,8,6,5,7,8,9,7,6,8,7]"
    sparkline_pass_rate TEXT, -- e.g., "[80,85,82,88,90,85,87,...]"
    
    -- Timestamps
    first_run_at TEXT,
    last_run_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_repo_stats_name ON analytics_repo_stats(repo_full_name);

-- ============================================================================
-- ANALYTICS JUDGE PERFORMANCE
-- Track individual judge performance over time
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_judge_performance (
    id TEXT PRIMARY KEY,
    date_bucket TEXT NOT NULL,  -- YYYY-MM-DD
    judge_name TEXT NOT NULL,   -- 'architect', 'security', 'user_proxy'
    
    -- Score distribution
    evaluations_count INTEGER DEFAULT 0,
    avg_score REAL,
    min_score REAL,
    max_score REAL,
    
    -- Confidence tracking
    avg_confidence REAL,
    
    -- Veto tracking (primarily for security judge)
    veto_count INTEGER DEFAULT 0,
    veto_rate REAL,
    
    -- Model usage breakdown (JSON)
    models_used TEXT,  -- e.g., {"claude-sonnet-4": 45, "deepseek-chat": 30}
    
    -- Timing
    avg_latency_ms REAL,
    
    computed_at TEXT DEFAULT (datetime('now')),
    
    UNIQUE(date_bucket, judge_name)
);

CREATE INDEX IF NOT EXISTS idx_judge_perf_date ON analytics_judge_performance(date_bucket);
CREATE INDEX IF NOT EXISTS idx_judge_perf_name ON analytics_judge_performance(judge_name);

-- ============================================================================
-- ANALYTICS SYSTEM HEALTH
-- Track system health metrics over time
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_system_health (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,  -- ISO timestamp
    
    -- API health
    api_status TEXT DEFAULT 'ok',
    api_latency_ms REAL,
    
    -- Database health
    db_status TEXT DEFAULT 'ok',
    db_connections INTEGER,
    
    -- LLM provider health (JSON)
    provider_status TEXT,  -- {"anthropic": "ok", "deepseek": "ok", ...}
    
    -- Queue metrics
    queue_pending INTEGER DEFAULT 0,
    queue_processing INTEGER DEFAULT 0,
    queue_failed INTEGER DEFAULT 0,
    
    -- Error tracking
    errors_1h INTEGER DEFAULT 0,
    errors_24h INTEGER DEFAULT 0,
    
    -- Resource usage
    memory_mb REAL,
    cpu_percent REAL
);

CREATE INDEX IF NOT EXISTS idx_health_timestamp ON analytics_system_health(timestamp);
