"""
Analytics API Router

Provides REST endpoints for the Trend Analytics Dashboard.
Exposes summary metrics, trend data, repository stats, judge performance, and system health.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from .analytics_models import (
    AnalyticsDailyRollup,
    AnalyticsHourlyRollup,
    AnalyticsJudgePerformance,
    AnalyticsRepoStats,
    AnalyticsRunMetrics,
    AnalyticsSystemHealth,
)


# =========================================================================
# CONFIGURATION
# =========================================================================

DATABASE_PATH = "db/invariant.db"

# Lazy session factory
_engine = None
_SessionFactory = None


def get_session() -> Session:
    """Get a database session."""
    global _engine, _SessionFactory
    
    if _engine is None:
        _engine = create_engine(f"sqlite:///{DATABASE_PATH}")
        _SessionFactory = sessionmaker(bind=_engine)
    
    return _SessionFactory()


# =========================================================================
# PYDANTIC RESPONSE MODELS
# =========================================================================

class VerdictBreakdown(BaseModel):
    """Verdict counts and percentages."""
    pass_count: int = 0
    fail_count: int = 0
    veto_count: int = 0
    partial_count: int = 0
    error_count: int = 0
    pass_rate: float = 0.0
    fail_rate: float = 0.0
    veto_rate: float = 0.0


class LatencyMetrics(BaseModel):
    """Latency statistics."""
    avg_seconds: Optional[float] = None
    p50_seconds: Optional[float] = None
    p95_seconds: Optional[float] = None
    p99_seconds: Optional[float] = None


class ScoreMetrics(BaseModel):
    """Score statistics."""
    avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class SummaryResponse(BaseModel):
    """Executive summary metrics."""
    period: str = "24h"
    total_runs: int = 0
    verdicts: VerdictBreakdown = Field(default_factory=VerdictBreakdown)
    scores: ScoreMetrics = Field(default_factory=ScoreMetrics)
    latency: LatencyMetrics = Field(default_factory=LatencyMetrics)
    total_tokens: int = 0
    unique_repos: int = 0
    unique_projects: int = 0
    generated_at: str = ""


class TrendPoint(BaseModel):
    """Single point in a trend series."""
    date: str
    value: float


class TrendSeries(BaseModel):
    """Named trend series."""
    name: str
    data: List[TrendPoint]


class TrendsResponse(BaseModel):
    """Trend data for charts."""
    period_start: str
    period_end: str
    granularity: str  # 'hourly' or 'daily'
    series: List[TrendSeries]


class RepoSummary(BaseModel):
    """Repository summary for leaderboard."""
    repo_full_name: str
    total_runs: int
    pass_rate: float
    avg_score: Optional[float]
    runs_7d: int
    trend: str  # 'up', 'down', 'stable'
    sparkline: List[int] = []


class ReposResponse(BaseModel):
    """Repository leaderboard response."""
    repos: List[RepoSummary]
    total_repos: int


class JudgeSummary(BaseModel):
    """Judge performance summary."""
    judge_id: str
    judge_name: str
    total_evaluations: int
    avg_score: float
    score_stddev: float
    veto_count: int
    veto_rate: float
    domain: Optional[str] = None


class JudgesResponse(BaseModel):
    """Judge performance response."""
    judges: List[JudgeSummary]


class ProviderHealth(BaseModel):
    """Provider health status."""
    name: str
    healthy: bool
    latency_ms: Optional[int] = None


class HealthResponse(BaseModel):
    """System health response."""
    healthy: bool
    runs_per_hour: int
    avg_latency_seconds: float
    error_rate: float
    providers: List[ProviderHealth]
    last_updated: str


# =========================================================================
# API ROUTER
# =========================================================================

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    period: str = Query("24h", regex="^(1h|6h|24h|7d|30d)$"),
    repo: Optional[str] = Query(None, description="Filter by repository"),
):
    """
    Get executive summary metrics for the specified period.
    
    Periods:
    - 1h: Last hour
    - 6h: Last 6 hours
    - 24h: Last 24 hours (default)
    - 7d: Last 7 days
    - 30d: Last 30 days
    """
    session = get_session()
    
    try:
        # Determine date range
        now = datetime.utcnow()
        period_map = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }
        delta = period_map.get(period, timedelta(hours=24))
        cutoff = (now - delta).isoformat()
        
        # Build query
        query = select(AnalyticsRunMetrics).where(
            AnalyticsRunMetrics.started_at >= cutoff
        )
        
        if repo:
            query = query.where(AnalyticsRunMetrics.repo_full_name == repo)
        
        runs = session.execute(query).scalars().all()
        
        if not runs:
            return SummaryResponse(
                period=period,
                generated_at=now.isoformat(),
            )
        
        # Aggregate metrics
        total = len(runs)
        pass_count = sum(1 for r in runs if r.verdict == "PASS")
        fail_count = sum(1 for r in runs if r.verdict == "FAIL")
        veto_count = sum(1 for r in runs if r.verdict == "VETO")
        partial_count = sum(1 for r in runs if r.verdict == "PARTIAL")
        error_count = sum(1 for r in runs if r.verdict == "ERROR")
        
        verdicts = VerdictBreakdown(
            pass_count=pass_count,
            fail_count=fail_count,
            veto_count=veto_count,
            partial_count=partial_count,
            error_count=error_count,
            pass_rate=round(pass_count / total * 100, 1) if total else 0,
            fail_rate=round(fail_count / total * 100, 1) if total else 0,
            veto_rate=round(veto_count / total * 100, 1) if total else 0,
        )
        
        # Scores
        all_scores = [r.overall_score for r in runs if r.overall_score is not None]
        scores = ScoreMetrics(
            avg=round(sum(all_scores) / len(all_scores), 2) if all_scores else None,
            min=min(all_scores) if all_scores else None,
            max=max(all_scores) if all_scores else None,
        )
        
        # Latency
        durations = sorted([r.duration_seconds for r in runs if r.duration_seconds])
        if durations:
            latency = LatencyMetrics(
                avg_seconds=round(sum(durations) / len(durations), 2),
                p50_seconds=durations[len(durations) // 2],
                p95_seconds=durations[int(len(durations) * 0.95)],
                p99_seconds=durations[int(len(durations) * 0.99)],
            )
        else:
            latency = LatencyMetrics()
        
        # Tokens
        total_tokens = sum(r.token_count or 0 for r in runs)
        
        # Unique counts
        unique_repos = len(set(r.repo_full_name for r in runs if r.repo_full_name))
        unique_projects = len(set(r.project_id for r in runs if r.project_id))
        
        return SummaryResponse(
            period=period,
            total_runs=total,
            verdicts=verdicts,
            scores=scores,
            latency=latency,
            total_tokens=total_tokens,
            unique_repos=unique_repos,
            unique_projects=unique_projects,
            generated_at=now.isoformat(),
        )
        
    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve summary")
    finally:
        session.close()


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    days: int = Query(7, ge=1, le=90),
    metric: str = Query("pass_rate", regex="^(pass_rate|avg_score|total_runs|avg_duration)$"),
    repo: Optional[str] = Query(None),
):
    """
    Get trend data for charting.
    
    Metrics:
    - pass_rate: Verification pass rate over time
    - avg_score: Average tribunal score over time
    - total_runs: Run volume over time
    - avg_duration: Average run duration over time
    """
    session = get_session()
    
    try:
        now = datetime.utcnow()
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        
        # Use daily rollups for longer periods, hourly for shorter
        granularity = "daily" if days > 2 else "hourly"
        
        if granularity == "daily":
            query = select(AnalyticsDailyRollup).where(
                AnalyticsDailyRollup.date_bucket >= start_date
            ).order_by(AnalyticsDailyRollup.date_bucket)
            
            if repo:
                query = query.where(AnalyticsDailyRollup.repo_full_name == repo)
            else:
                query = query.where(AnalyticsDailyRollup.repo_full_name.is_(None))
            
            rollups = session.execute(query).scalars().all()
            
            # Build series
            data = []
            for r in rollups:
                if metric == "pass_rate":
                    value = r.pass_rate or 0
                elif metric == "avg_score":
                    value = r.avg_score or 0
                elif metric == "total_runs":
                    value = r.total_runs or 0
                elif metric == "avg_duration":
                    value = r.avg_duration_seconds or 0
                else:
                    value = 0
                
                data.append(TrendPoint(date=r.date_bucket, value=value))
            
            series = [TrendSeries(name=metric, data=data)]
            
        else:
            # Hourly granularity
            query = select(AnalyticsHourlyRollup).where(
                AnalyticsHourlyRollup.date_bucket >= start_date
            ).order_by(AnalyticsHourlyRollup.date_bucket, AnalyticsHourlyRollup.hour_bucket)
            
            if repo:
                query = query.where(AnalyticsHourlyRollup.repo_full_name == repo)
            else:
                query = query.where(AnalyticsHourlyRollup.repo_full_name.is_(None))
            
            rollups = session.execute(query).scalars().all()
            
            data = []
            for r in rollups:
                date_hour = f"{r.date_bucket}T{r.hour_bucket:02d}:00:00"
                
                if metric == "pass_rate" and r.total_runs:
                    value = r.pass_count / r.total_runs * 100
                elif metric == "avg_score":
                    value = r.avg_score or 0
                elif metric == "total_runs":
                    value = r.total_runs or 0
                elif metric == "avg_duration":
                    value = r.avg_duration_seconds or 0
                else:
                    value = 0
                
                data.append(TrendPoint(date=date_hour, value=value))
            
            series = [TrendSeries(name=metric, data=data)]
        
        return TrendsResponse(
            period_start=start_date,
            period_end=end_date,
            granularity=granularity,
            series=series,
        )
        
    except Exception as e:
        logger.error(f"Failed to get trends: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trends")
    finally:
        session.close()


@router.get("/repos", response_model=ReposResponse)
async def get_repos(
    sort: str = Query("pass_rate", regex="^(pass_rate|total_runs|avg_score|last_run)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(10, ge=1, le=100),
):
    """
    Get repository leaderboard/ranking.
    """
    session = get_session()
    
    try:
        stats = session.execute(select(AnalyticsRepoStats)).scalars().all()
        
        if not stats:
            return ReposResponse(repos=[], total_repos=0)
        
        # Sort
        def get_sort_key(s: AnalyticsRepoStats):
            if sort == "pass_rate":
                return s.lifetime_pass_rate or 0
            elif sort == "total_runs":
                return s.total_runs or 0
            elif sort == "avg_score":
                return s.avg_score or 0
            elif sort == "last_run":
                return s.last_run_at or ""
            return 0
        
        sorted_stats = sorted(stats, key=get_sort_key, reverse=(order == "desc"))
        
        # Convert to response
        repos = []
        for s in sorted_stats[:limit]:
            # Determine trend
            if s.pass_rate_7d and s.pass_rate_30d:
                if s.pass_rate_7d > s.pass_rate_30d + 5:
                    trend = "up"
                elif s.pass_rate_7d < s.pass_rate_30d - 5:
                    trend = "down"
                else:
                    trend = "stable"
            else:
                trend = "stable"
            
            repos.append(RepoSummary(
                repo_full_name=s.repo_full_name,
                total_runs=s.total_runs or 0,
                pass_rate=s.lifetime_pass_rate or 0,
                avg_score=s.avg_score,
                runs_7d=s.runs_7d or 0,
                trend=trend,
                sparkline=s.get_sparkline_runs(),
            ))
        
        return ReposResponse(repos=repos, total_repos=len(stats))
        
    except Exception as e:
        logger.error(f"Failed to get repos: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve repositories")
    finally:
        session.close()


@router.get("/judges", response_model=JudgesResponse)
async def get_judges():
    """
    Get judge performance metrics.
    """
    session = get_session()
    
    try:
        perfs = session.execute(select(AnalyticsJudgePerformance)).scalars().all()
        
        judges = []
        for p in perfs:
            judges.append(JudgeSummary(
                judge_id=p.judge_id,
                judge_name=p.judge_name or p.judge_id,
                total_evaluations=p.total_evaluations or 0,
                avg_score=p.avg_score or 0,
                score_stddev=p.score_stddev or 0,
                veto_count=p.veto_count or 0,
                veto_rate=p.veto_rate or 0,
                domain=p.domain,
            ))
        
        return JudgesResponse(judges=judges)
        
    except Exception as e:
        logger.error(f"Failed to get judges: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve judges")
    finally:
        session.close()


@router.get("/health", response_model=HealthResponse)
async def get_health():
    """
    Get current system health status.
    """
    session = get_session()
    
    try:
        # Get latest health record
        latest = session.execute(
            select(AnalyticsSystemHealth)
            .order_by(AnalyticsSystemHealth.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if not latest:
            return HealthResponse(
                healthy=True,
                runs_per_hour=0,
                avg_latency_seconds=0,
                error_rate=0,
                providers=[],
                last_updated=datetime.utcnow().isoformat(),
            )
        
        # Parse provider status
        providers = []
        for name, status in latest.get_provider_status().items():
            providers.append(ProviderHealth(
                name=name,
                healthy=status.get("healthy", False),
                latency_ms=status.get("latency_ms"),
            ))
        
        return HealthResponse(
            healthy=bool(latest.healthy),
            runs_per_hour=latest.runs_per_hour or 0,
            avg_latency_seconds=latest.avg_latency_seconds or 0,
            error_rate=latest.error_rate or 0,
            providers=providers,
            last_updated=latest.timestamp or "",
        )
        
    except Exception as e:
        logger.error(f"Failed to get health: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve health")
    finally:
        session.close()


# =========================================================================
# HELPER ENDPOINTS
# =========================================================================

@router.get("/verdicts/{run_id}")
async def get_run_metrics(run_id: str):
    """
    Get detailed metrics for a specific run.
    """
    session = get_session()
    
    try:
        run = session.execute(
            select(AnalyticsRunMetrics).where(
                AnalyticsRunMetrics.run_id == run_id
            )
        ).scalar_one_or_none()
        
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        
        return run.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get run metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve run metrics")
    finally:
        session.close()


@router.post("/ingest/{run_id}")
async def ingest_run_metrics(
    run_id: str,
    repo: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
):
    """
    Manually trigger metrics extraction for a run.
    (Normally called automatically on run completion)
    """
    from pathlib import Path
    import json
    
    session = get_session()
    
    try:
        # Check if already exists
        existing = session.execute(
            select(AnalyticsRunMetrics).where(
                AnalyticsRunMetrics.run_id == run_id
            )
        ).scalar_one_or_none()
        
        if existing:
            return {"status": "already_exists", "run_id": run_id}
        
        # Load verdict from artifact
        artifact_path = Path("run_artifacts") / run_id / "tribunal_verdicts.json"
        
        if not artifact_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Verdict artifact not found: {artifact_path}",
            )
        
        with open(artifact_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        
        # Extract metrics
        from .analytics_extractor import AnalyticsExtractor
        extractor = AnalyticsExtractor(session)
        
        record = extractor.extract_run_metrics(
            run_id=run_id,
            verdict_payload=payload,
            repo_full_name=repo,
            branch=branch,
        )
        
        if record:
            return {"status": "ingested", "run_id": run_id, "verdict": record.verdict}
        else:
            raise HTTPException(status_code=500, detail="Failed to extract metrics")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to ingest run metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.post("/backfill")
async def backfill_analytics(
    limit: Optional[int] = Query(None, ge=1, le=1000),
):
    """
    Backfill analytics from existing verdict artifacts.
    """
    from pathlib import Path
    
    session = get_session()
    
    try:
        from .analytics_extractor import AnalyticsExtractor
        extractor = AnalyticsExtractor(session)
        
        count = extractor.backfill_from_artifacts(
            artifacts_root=Path("run_artifacts"),
            limit=limit,
        )
        
        return {"status": "completed", "runs_processed": count}
        
    except Exception as e:
        logger.error(f"Failed to backfill: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
