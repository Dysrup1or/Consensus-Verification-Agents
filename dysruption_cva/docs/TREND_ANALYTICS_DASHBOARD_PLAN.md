# Trend Analytics Dashboard - Implementation Plan

**Created:** December 17, 2025  
**Status:** 🔄 In Progress  
**Goal:** Management visibility into CVA verification trends, performance metrics, and system health  
**Effort:** 4-6 days

---

## Executive Summary

The **Trend Analytics Dashboard** provides management-level visibility into the CVA (Consensus Verifier Agent) system's performance, trends, and operational health. It aggregates historical run data, surfaces key metrics, and presents actionable insights through interactive visualizations.

### Key Stakeholders
- **Engineering Managers**: Track code quality trends across repositories
- **Security Teams**: Monitor security verdict patterns and compliance rates
- **DevOps**: Observe system performance, latency, and reliability
- **Executives**: High-level pass/fail trends and cost efficiency

---

## Research Summary: Dashboard Best Practices

Based on industry best practices (Grafana, Google SRE, dashboard design literature):

### Core Principles Applied

1. **Tell a Story**: Each dashboard section answers a specific management question
2. **Reduce Cognitive Load**: Use consistent layouts, color coding, and simple visualizations
3. **Four Golden Signals** (Google SRE):
   - **Latency**: Time to complete verifications
   - **Traffic**: Number of runs per time period
   - **Errors**: Failed runs, veto triggers, system errors
   - **Saturation**: Resource utilization, queue depth

4. **RED Method** (Rate, Errors, Duration):
   - Applied to verification "requests" as the unit of work

5. **Dashboard Maturity Model**:
   - Start with methodical dashboards (medium maturity)
   - Use template variables for filtering
   - Hierarchical drill-down capability

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TREND ANALYTICS DASHBOARD                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Overview Panel  │  │  Trends Charts   │  │  Health Status   │  │
│  │  - Total Runs    │  │  - Pass Rate     │  │  - API Health    │  │
│  │  - Pass Rate     │  │  - Latency       │  │  - Model Status  │  │
│  │  - Avg Duration  │  │  - Veto Rate     │  │  - Error Rate    │  │
│  │  - Error Count   │  │  - Volume        │  │  - Queue Depth   │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    TIME SERIES CHARTS                         │  │
│  │  - Runs over time (stacked: pass/fail/veto)                  │  │
│  │  - Latency percentiles (p50, p95, p99)                       │  │
│  │  - Token usage and cost estimation                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────┐  ┌─────────────────────────────────┐  │
│  │   Repository Breakdown  │  │    Judge Performance Matrix     │  │
│  │   - By repo/branch      │  │    - Architect judge scores     │  │
│  │   - Pass rate per repo  │  │    - Security judge vetoes      │  │
│  │   - Trend sparklines    │  │    - User proxy alignment       │  │
│  └─────────────────────────┘  └─────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    RECENT RUNS TABLE                          │  │
│  │  | Time | Repo | Branch | Verdict | Score | Duration | Veto | │  │
│  │  | ...  | ...  | ...    | ...     | ...   | ...      | ...  | │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ANALYTICS API (Backend)                        │
├─────────────────────────────────────────────────────────────────────┤
│  GET /api/analytics/summary       - Aggregate metrics              │
│  GET /api/analytics/trends        - Time series data               │
│  GET /api/analytics/repos         - Per-repository breakdown       │
│  GET /api/analytics/judges        - Judge performance metrics      │
│  GET /api/analytics/health        - System health indicators       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA AGGREGATION LAYER                           │
├─────────────────────────────────────────────────────────────────────┤
│  - RunTelemetry aggregation from verdict artifacts                 │
│  - Time-bucketed rollups (hourly, daily, weekly)                   │
│  - Repository-level metrics                                         │
│  - Judge-level performance tracking                                 │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PERSISTENCE (SQLite/Postgres)                    │
├─────────────────────────────────────────────────────────────────────┤
│  - analytics_runs: Denormalized run records for fast queries       │
│  - analytics_daily_rollups: Pre-aggregated daily metrics           │
│  - analytics_repo_stats: Per-repository statistics                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Metrics Specification

### 1. Summary Metrics (KPIs)

| Metric | Description | Calculation | Display |
|--------|-------------|-------------|---------|
| **Total Runs** | Count of all verification runs | `COUNT(*)` | Number with trend arrow |
| **Pass Rate** | Percentage of successful runs | `COUNT(PASS) / COUNT(*) * 100` | Percentage with gauge |
| **Fail Rate** | Percentage of failed runs | `COUNT(FAIL) / COUNT(*) * 100` | Percentage |
| **Veto Rate** | Percentage triggering security veto | `COUNT(VETO) / COUNT(*) * 100` | Percentage with alert color |
| **Avg Duration** | Mean execution time | `AVG(execution_time_seconds)` | Duration in seconds |
| **P95 Latency** | 95th percentile latency | `PERCENTILE(execution_time, 0.95)` | Duration |
| **Error Rate** | System/infrastructure errors | `COUNT(ERROR) / COUNT(*) * 100` | Percentage with threshold |
| **Active Repos** | Unique repositories with runs | `COUNT(DISTINCT repo_id)` | Number |

### 2. Time Series Metrics

| Chart | Data Points | Time Buckets |
|-------|-------------|--------------|
| **Run Volume** | pass, fail, veto, error counts | Hourly/Daily |
| **Latency Distribution** | p50, p75, p95, p99 | Hourly/Daily |
| **Token Usage** | input tokens, output tokens | Daily |
| **Score Trend** | average score, min, max | Daily |

### 3. Breakdown Dimensions

| Dimension | Metrics |
|-----------|---------|
| **Repository** | runs, pass_rate, avg_score, avg_duration |
| **Branch** | runs, pass_rate (vs main) |
| **Judge** | avg_score, veto_count, avg_confidence |
| **Model** | usage_count, latency, token_count |

---

## Database Schema

### New Tables

```sql
-- Pre-aggregated analytics for fast dashboard queries
CREATE TABLE analytics_run_metrics (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT,
    repo_full_name TEXT,
    branch TEXT,
    
    -- Verdict data
    verdict TEXT NOT NULL,  -- PASS, FAIL, VETO, ERROR
    overall_score REAL,
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    duration_seconds REAL,
    llm_latency_ms INTEGER,
    
    -- Token metrics
    token_count INTEGER,
    llm_input_tokens INTEGER,
    
    -- Judge breakdown
    architect_score REAL,
    security_score REAL,
    user_proxy_score REAL,
    veto_triggered BOOLEAN DEFAULT FALSE,
    veto_judge TEXT,
    
    -- Static analysis
    static_issues_count INTEGER,
    critical_issues_count INTEGER,
    
    -- Coverage
    files_covered INTEGER,
    files_total INTEGER,
    
    -- Indexing
    date_bucket DATE GENERATED ALWAYS AS (DATE(started_at)) STORED,
    hour_bucket INTEGER GENERATED ALWAYS AS (EXTRACT(HOUR FROM started_at)) STORED,
    
    UNIQUE(run_id)
);

CREATE INDEX idx_analytics_date ON analytics_run_metrics(date_bucket);
CREATE INDEX idx_analytics_repo ON analytics_run_metrics(repo_full_name);
CREATE INDEX idx_analytics_verdict ON analytics_run_metrics(verdict);

-- Daily rollups for fast trend queries
CREATE TABLE analytics_daily_rollups (
    id TEXT PRIMARY KEY,
    date_bucket DATE NOT NULL,
    repo_full_name TEXT,  -- NULL for global rollup
    
    -- Counts
    total_runs INTEGER DEFAULT 0,
    pass_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    veto_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    
    -- Averages
    avg_score REAL,
    avg_duration_seconds REAL,
    avg_token_count REAL,
    
    -- Percentiles (stored as JSON array)
    duration_percentiles TEXT,  -- {"p50": x, "p75": y, "p95": z, "p99": w}
    
    -- Judge metrics
    avg_architect_score REAL,
    avg_security_score REAL,
    avg_user_proxy_score REAL,
    
    -- Computed at rollup time
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(date_bucket, repo_full_name)
);

CREATE INDEX idx_rollups_date ON analytics_daily_rollups(date_bucket);
```

---

## API Specification

### Endpoints

#### `GET /api/analytics/summary`
Returns aggregate KPI metrics for the dashboard header.

**Query Parameters:**
- `start_date` (optional): ISO date, default 30 days ago
- `end_date` (optional): ISO date, default today
- `repo` (optional): Filter by repository

**Response:**
```json
{
  "period": {"start": "2025-12-01", "end": "2025-12-17"},
  "totals": {
    "runs": 1234,
    "pass": 987,
    "fail": 180,
    "veto": 45,
    "error": 22
  },
  "rates": {
    "pass_rate": 80.0,
    "fail_rate": 14.6,
    "veto_rate": 3.6,
    "error_rate": 1.8
  },
  "latency": {
    "avg_seconds": 12.5,
    "p50_seconds": 8.2,
    "p95_seconds": 32.1,
    "p99_seconds": 58.4
  },
  "scores": {
    "avg": 7.8,
    "min": 2.1,
    "max": 10.0
  },
  "trends": {
    "runs_change_pct": 15.2,
    "pass_rate_change_pct": 2.1
  }
}
```

#### `GET /api/analytics/trends`
Returns time series data for charts.

**Query Parameters:**
- `start_date`, `end_date`: Date range
- `bucket`: `hourly` | `daily` | `weekly`
- `metrics`: Comma-separated list of metrics
- `repo` (optional): Filter by repository

**Response:**
```json
{
  "bucket": "daily",
  "data": [
    {
      "date": "2025-12-15",
      "runs": 45,
      "pass": 38,
      "fail": 5,
      "veto": 2,
      "avg_score": 7.9,
      "avg_duration": 11.2,
      "p95_duration": 28.5
    }
  ]
}
```

#### `GET /api/analytics/repos`
Returns per-repository breakdown.

**Response:**
```json
{
  "repos": [
    {
      "repo_full_name": "org/project",
      "runs": 456,
      "pass_rate": 82.5,
      "avg_score": 7.6,
      "avg_duration": 14.2,
      "veto_count": 8,
      "last_run": "2025-12-17T10:30:00Z",
      "sparkline": [38, 42, 40, 45, 41, 44, 43]
    }
  ]
}
```

#### `GET /api/analytics/judges`
Returns judge-level performance metrics.

**Response:**
```json
{
  "judges": {
    "architect": {
      "avg_score": 7.8,
      "veto_count": 0,
      "avg_confidence": 0.82
    },
    "security": {
      "avg_score": 7.2,
      "veto_count": 45,
      "avg_confidence": 0.88
    },
    "user_proxy": {
      "avg_score": 8.1,
      "veto_count": 0,
      "avg_confidence": 0.75
    }
  }
}
```

#### `GET /api/analytics/health`
Returns system health indicators.

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "api": {"status": "ok", "latency_ms": 12},
    "database": {"status": "ok", "connections": 5},
    "llm_providers": {
      "anthropic": {"status": "ok", "avg_latency_ms": 2100},
      "deepseek": {"status": "ok", "avg_latency_ms": 1800},
      "gemini": {"status": "ok", "avg_latency_ms": 950}
    }
  },
  "queue": {
    "pending": 3,
    "processing": 1
  },
  "last_run": "2025-12-17T14:22:00Z"
}
```

---

## UI Components

### Dashboard Layout (Next.js + Tailwind)

```
/app/analytics/
└── page.tsx                 # Analytics dashboard page

/components/analytics/
├── KPICard.tsx              # KPI card (uses Sparkline)
├── Sparkline.tsx            # Inline micro-trend
├── TrendChart.tsx           # Time series chart
├── DonutChart.tsx           # Distribution chart
├── RepoTable.tsx            # Repository breakdown table
├── JudgePerformance.tsx     # Judge performance panel
└── HealthStatus.tsx         # System health panel
```

### Component Specifications

#### KPICard
- KPI cards in a responsive grid
- Each card: metric value, label, optional sparkline

#### TrendChart
- Recharts or Chart.js line/area chart
- Toggle between metrics (runs, latency, score)
- Hover tooltips with exact values
- Responsive sizing

#### DonutChart
- Donut chart showing verdict distribution
- Legend with percentages

#### RepoTable
- Sortable table with repository metrics
- Inline sparklines for trend visualization
- Click to filter dashboard by repo

#### JudgeMatrix
- Heatmap showing judge scores across time/repos
- Color scale from red (low) to green (high)

---

## Implementation Tasks

### Phase 1: Backend Data Layer (Day 1-2)

| Task | Description | Verification |
|------|-------------|--------------|
| **1.1** Create analytics schema | Add migration for analytics tables | Migration runs without errors |
| **1.2** Implement metrics extractor | Parse verdict JSON to analytics_run_metrics | Unit test with sample verdict |
| **1.3** Add rollup job | Background task for daily aggregations | Rollup table populated correctly |
| **1.4** Backfill historical data | Process existing run artifacts | All historical runs have metrics |

### Phase 2: Analytics API (Day 2-3)

| Task | Description | Verification |
|------|-------------|--------------|
| **2.1** Summary endpoint | `/api/analytics/summary` | Returns valid JSON with all KPIs |
| **2.2** Trends endpoint | `/api/analytics/trends` | Time series data matches filters |
| **2.3** Repos endpoint | `/api/analytics/repos` | Per-repo breakdown is accurate |
| **2.4** Judges endpoint | `/api/analytics/judges` | Judge metrics calculated correctly |
| **2.5** Health endpoint | `/api/analytics/health` | Component statuses accurate |
| **2.6** Add API tests | Pytest tests for all endpoints | 100% endpoint coverage |

### Phase 3: Frontend Dashboard (Day 3-5)

| Task | Description | Verification |
|------|-------------|--------------|
| **3.1** Dashboard page layout | Create `/analytics` route | Page renders with placeholder data |
| **3.2** SummaryCards component | KPI cards with metrics | Cards show correct values |
| **3.3** TrendChart component | Time series visualization | Chart renders trends correctly |
| **3.4** VerdictDonut component | Verdict distribution pie/donut | Distribution matches data |
| **3.5** RepoTable component | Repository breakdown table | Table sortable and accurate |
| **3.6** JudgeMatrix component | Judge performance display | Matrix shows all judges |
| **3.7** DateRangePicker | Date filtering | Filters update all components |
| **3.8** RepoFilter | Repository filtering | Filters update all components |
| **3.9** Responsive layout | Mobile/tablet support | Layout adapts to screen size |

### Phase 4: Integration & Polish (Day 5-6)

| Task | Description | Verification |
|------|-------------|--------------|
| **4.1** Real-time updates | WebSocket for live data | Dashboard updates on new runs |
| **4.2** Loading states | Skeleton loaders | Smooth loading experience |
| **4.3** Error handling | Error boundaries | Graceful error display |
| **4.4** Navigation | Add to main nav | Dashboard accessible from nav |
| **4.5** Performance optimization | Memoization, lazy loading | Page loads in < 2s |
| **4.6** Documentation | Usage guide | README updated |

---

## Dependencies

### Backend
- **SQLAlchemy**: ORM for analytics tables (existing)
- **FastAPI**: API framework (existing)
- **APScheduler** or **Celery**: For rollup background jobs (new)

### Frontend
- **Recharts** or **Chart.js**: Charting library (new)
- **date-fns**: Date manipulation (may exist)
- **react-query** or **SWR**: Data fetching with caching (existing via tanstack)

---

## Potential Pitfalls

1. **Data Volume**: Large number of runs could slow queries
   - Mitigation: Pre-aggregated rollup tables, pagination

2. **Missing Historical Data**: Older runs may lack telemetry
   - Mitigation: Graceful handling of missing fields, backfill where possible

3. **LLM Provider Variability**: Provider latency varies significantly
   - Mitigation: Track per-provider metrics, show provider in breakdown

4. **Time Zone Handling**: Date buckets must be consistent
   - Mitigation: Store all times in UTC, convert for display

5. **Chart Performance**: Large datasets can slow rendering
   - Mitigation: Server-side aggregation, progressive loading

---

## Success Criteria

1. **Dashboard loads within 2 seconds** on typical connection
2. **All KPI metrics are accurate** within 1% of raw data
3. **Trend charts update daily** with new data
4. **Repository filtering works** across all components
5. **Mobile-responsive layout** works on tablets
6. **Zero console errors** in production build
7. **API endpoints handle 1000+ runs** without timeout

---

## Appendix: Sample Dashboard Mockup

```
┌────────────────────────────────────────────────────────────────────────┐
│ 📊 CVA Analytics Dashboard          [Dec 1-17, 2025 ▼] [All Repos ▼]  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │   1,234  │  │   80.0%  │  │   3.6%   │  │   12.5s  │  │   7.8    │ │
│  │  Runs    │  │Pass Rate │  │Veto Rate │  │Avg Time  │  │Avg Score │ │
│  │  ↑ 15%   │  │  ↑ 2.1%  │  │  ↓ 0.8%  │  │  ↓ 2.1s  │  │  ↑ 0.3   │ │
│  │  ▁▂▃▄▅▆▇ │  │  ▅▆▇▆▇▇█ │  │  ▃▂▂▁▁▁▁ │  │  ▆▅▄▄▃▃▂ │  │  ▅▆▆▇▇▇█ │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    Runs Over Time                                │  │
│  │  50│     ╭──╮                                                    │  │
│  │    │   ╭─╯  ╰─╮  ╭──╮                                           │  │
│  │  25│  ╭╯      ╰──╯  ╰─╮     ╭────╮                              │  │
│  │    │ ╭╯                ╰─────╯    ╰╮                            │  │
│  │   0│─╯                             ╰──                          │  │
│  │    └──────────────────────────────────────────────────────────  │  │
│  │        Dec 1   5    10    15    17                              │  │
│  │    ■ Pass  ■ Fail  ■ Veto                                       │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌───────────────────────┐  ┌────────────────────────────────────┐   │
│  │  Verdict Distribution │  │     Repository Breakdown           │   │
│  │       ╭─────╮         │  │ Repo         Runs  Pass%  Score    │   │
│  │    ╭──╯ 80% ╰──╮      │  │ ────────────────────────────────── │   │
│  │   ╱    PASS     ╲     │  │ org/project  456   82.5%  7.6 ▅▆▇ │   │
│  │  │    1,234      │    │  │ org/api      321   78.2%  7.4 ▄▅▆ │   │
│  │   ╲   total     ╱     │  │ org/web      234   85.1%  8.0 ▆▇█ │   │
│  │    ╰──╮  15% ╭──╯     │  │ org/lib      156   71.2%  6.8 ▃▄▄ │   │
│  │       ╰─FAIL─╯        │  │ org/cli       67   89.5%  8.5 ▇▇█ │   │
│  │         4% VETO       │  └────────────────────────────────────┘   │
│  └───────────────────────┘                                            │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. ✅ Create this plan document
2. 🔄 **Begin Phase 1**: Create database schema and migration
3. Implement metrics extractor
4. Build API endpoints
5. Create UI components
6. Integration testing
7. Documentation and deployment
