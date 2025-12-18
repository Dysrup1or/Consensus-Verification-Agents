"""
Analytics Models - SQLAlchemy ORM models for the Trend Analytics Dashboard.

These models map to the analytics tables created by migration 003_analytics_tables.sql.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base


def _uuid_str() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


def _now_iso() -> str:
    """Current time as ISO string."""
    return datetime.utcnow().isoformat()


class AnalyticsRunMetrics(Base):
    """
    Denormalized run records optimized for fast analytics queries.
    
    Each record represents a single verification run with all metrics
    needed for dashboard displays pre-computed.
    """
    __tablename__ = "analytics_run_metrics"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    run_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    project_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repo_full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Verdict data
    verdict: Mapped[str] = mapped_column(Text, nullable=False)  # PASS, FAIL, VETO, PARTIAL, ERROR
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Timing
    started_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    finished_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    llm_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Token metrics
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Judge breakdown
    architect_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    security_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    user_proxy_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Veto tracking
    veto_triggered: Mapped[int] = mapped_column(Integer, default=0)  # SQLite boolean
    veto_judge: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    veto_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Static analysis
    static_issues_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_issues_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Coverage
    files_covered: Mapped[int] = mapped_column(Integer, default=0)
    files_total: Mapped[int] = mapped_column(Integer, default=0)
    
    # Criteria tracking
    criteria_passed: Mapped[int] = mapped_column(Integer, default=0)
    criteria_total: Mapped[int] = mapped_column(Integer, default=0)
    
    # Mode and event
    mode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Indexable date fields
    date_bucket: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # YYYY-MM-DD
    hour_bucket: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-23
    
    # Metadata
    created_at: Mapped[str] = mapped_column(Text, default=_now_iso)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "repo_full_name": self.repo_full_name,
            "branch": self.branch,
            "verdict": self.verdict,
            "overall_score": self.overall_score,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "llm_latency_ms": self.llm_latency_ms,
            "token_count": self.token_count,
            "architect_score": self.architect_score,
            "security_score": self.security_score,
            "user_proxy_score": self.user_proxy_score,
            "veto_triggered": bool(self.veto_triggered),
            "veto_judge": self.veto_judge,
            "static_issues_count": self.static_issues_count,
            "critical_issues_count": self.critical_issues_count,
            "criteria_passed": self.criteria_passed,
            "criteria_total": self.criteria_total,
            "mode": self.mode,
            "event_type": self.event_type,
            "date_bucket": self.date_bucket,
        }


class AnalyticsDailyRollup(Base):
    """
    Pre-aggregated daily metrics for fast trend queries.
    
    One record per date per repository (NULL repo for global aggregates).
    """
    __tablename__ = "analytics_daily_rollups"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    date_bucket: Mapped[str] = mapped_column(Text, nullable=False)  # YYYY-MM-DD
    repo_full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Run counts
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    veto_count: Mapped[int] = mapped_column(Integer, default=0)
    partial_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Computed rates
    pass_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fail_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    veto_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Score aggregates
    avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Duration aggregates
    avg_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p50_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p75_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p95_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p99_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Token aggregates
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    avg_tokens: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Judge score averages
    avg_architect_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_security_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_user_proxy_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Static analysis totals
    total_static_issues: Mapped[int] = mapped_column(Integer, default=0)
    total_critical_issues: Mapped[int] = mapped_column(Integer, default=0)
    
    # Unique counts
    unique_repos: Mapped[int] = mapped_column(Integer, default=0)
    unique_projects: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    computed_at: Mapped[str] = mapped_column(Text, default=_now_iso)
    
    __table_args__ = (
        UniqueConstraint("date_bucket", "repo_full_name", name="uq_rollup_date_repo"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "date": self.date_bucket,
            "repo": self.repo_full_name,
            "runs": self.total_runs,
            "pass": self.pass_count,
            "fail": self.fail_count,
            "veto": self.veto_count,
            "error": self.error_count,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "avg_duration": self.avg_duration_seconds,
            "p95_duration": self.p95_duration_seconds,
            "avg_tokens": self.avg_tokens,
        }


class AnalyticsHourlyRollup(Base):
    """Hourly rollups for granular recent data."""
    __tablename__ = "analytics_hourly_rollups"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    datetime_bucket: Mapped[str] = mapped_column(Text, nullable=False)  # YYYY-MM-DD HH:00
    repo_full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    veto_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    computed_at: Mapped[str] = mapped_column(Text, default=_now_iso)
    
    __table_args__ = (
        UniqueConstraint("datetime_bucket", "repo_full_name", name="uq_hourly_datetime_repo"),
    )


class AnalyticsRepoStats(Base):
    """Aggregated per-repository statistics."""
    __tablename__ = "analytics_repo_stats"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    repo_full_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    
    # Lifetime totals
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_pass: Mapped[int] = mapped_column(Integer, default=0)
    total_fail: Mapped[int] = mapped_column(Integer, default=0)
    total_veto: Mapped[int] = mapped_column(Integer, default=0)
    
    lifetime_pass_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Rolling metrics
    runs_7d: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate_7d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    runs_30d: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate_30d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Trend sparklines (JSON arrays)
    sparkline_runs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sparkline_pass_rate: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    first_run_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(Text, default=_now_iso)
    
    def get_sparkline_runs(self) -> List[int]:
        """Parse sparkline runs JSON."""
        if not self.sparkline_runs:
            return []
        try:
            return json.loads(self.sparkline_runs)
        except json.JSONDecodeError:
            return []
    
    def get_sparkline_pass_rate(self) -> List[float]:
        """Parse sparkline pass rate JSON."""
        if not self.sparkline_pass_rate:
            return []
        try:
            return json.loads(self.sparkline_pass_rate)
        except json.JSONDecodeError:
            return []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "repo_full_name": self.repo_full_name,
            "runs": self.total_runs,
            "pass_rate": self.lifetime_pass_rate,
            "avg_score": self.avg_score,
            "avg_duration": self.avg_duration_seconds,
            "veto_count": self.total_veto,
            "runs_7d": self.runs_7d,
            "pass_rate_7d": self.pass_rate_7d,
            "runs_30d": self.runs_30d,
            "pass_rate_30d": self.pass_rate_30d,
            "sparkline": self.get_sparkline_runs(),
            "last_run": self.last_run_at,
        }


class AnalyticsJudgePerformance(Base):
    """Track individual judge performance over time."""
    __tablename__ = "analytics_judge_performance"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    date_bucket: Mapped[str] = mapped_column(Text, nullable=False)
    judge_name: Mapped[str] = mapped_column(Text, nullable=False)
    
    evaluations_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    veto_count: Mapped[int] = mapped_column(Integer, default=0)
    veto_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    models_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    avg_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    computed_at: Mapped[str] = mapped_column(Text, default=_now_iso)
    
    __table_args__ = (
        UniqueConstraint("date_bucket", "judge_name", name="uq_judge_date_name"),
    )
    
    def get_models_used(self) -> Dict[str, int]:
        """Parse models used JSON."""
        if not self.models_used:
            return {}
        try:
            return json.loads(self.models_used)
        except json.JSONDecodeError:
            return {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "date": self.date_bucket,
            "judge": self.judge_name,
            "evaluations": self.evaluations_count,
            "avg_score": self.avg_score,
            "avg_confidence": self.avg_confidence,
            "veto_count": self.veto_count,
            "veto_rate": self.veto_rate,
            "avg_latency_ms": self.avg_latency_ms,
        }


class AnalyticsSystemHealth(Base):
    """Track system health metrics over time."""
    __tablename__ = "analytics_system_health"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    
    api_status: Mapped[str] = mapped_column(Text, default="ok")
    api_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    db_status: Mapped[str] = mapped_column(Text, default="ok")
    db_connections: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    provider_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    
    queue_pending: Mapped[int] = mapped_column(Integer, default=0)
    queue_processing: Mapped[int] = mapped_column(Integer, default=0)
    queue_failed: Mapped[int] = mapped_column(Integer, default=0)
    
    errors_1h: Mapped[int] = mapped_column(Integer, default=0)
    errors_24h: Mapped[int] = mapped_column(Integer, default=0)
    
    memory_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpu_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    def get_provider_status(self) -> Dict[str, str]:
        """Parse provider status JSON."""
        if not self.provider_status:
            return {}
        try:
            return json.loads(self.provider_status)
        except json.JSONDecodeError:
            return {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "api": {"status": self.api_status, "latency_ms": self.api_latency_ms},
            "database": {"status": self.db_status, "connections": self.db_connections},
            "providers": self.get_provider_status(),
            "queue": {
                "pending": self.queue_pending,
                "processing": self.queue_processing,
                "failed": self.queue_failed,
            },
            "errors": {"1h": self.errors_1h, "24h": self.errors_24h},
            "resources": {"memory_mb": self.memory_mb, "cpu_percent": self.cpu_percent},
        }
