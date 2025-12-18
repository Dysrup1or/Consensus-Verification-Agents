"""
Analytics Rollup Job

Background job that computes analytics rollups on a schedule.
Can be run as a standalone script or integrated into the main application.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

# Configure logging
logger.add(
    "logs/analytics_rollup.log",
    rotation="10 MB",
    retention="7 days",
    level="INFO",
)


class AnalyticsRollupJob:
    """
    Background job for computing analytics rollups.
    
    Handles:
    - Hourly rollup computation (retains 48 hours)
    - Daily rollup computation (retains indefinitely)
    - Repo stats updates
    - Judge performance updates
    - System health snapshots
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        artifacts_root: Optional[Path] = None,
    ):
        """
        Initialize rollup job.
        
        Args:
            db_path: Path to SQLite database (uses default if None)
            artifacts_root: Path to run_artifacts directory
        """
        self.db_path = db_path or "db/invariant.db"
        self.artifacts_root = artifacts_root or Path("run_artifacts")
        self._running = False
        self._session = None
        self._extractor = None
    
    def _get_session(self):
        """Get database session lazily."""
        if self._session is None:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            
            engine = create_engine(f"sqlite:///{self.db_path}")
            Session = sessionmaker(bind=engine)
            self._session = Session()
        return self._session
    
    def _get_extractor(self):
        """Get analytics extractor lazily."""
        if self._extractor is None:
            from .analytics_extractor import AnalyticsExtractor
            self._extractor = AnalyticsExtractor(self._get_session())
        return self._extractor
    
    # =========================================================================
    # HOURLY ROLLUPS
    # =========================================================================
    
    def compute_hourly_rollups(self) -> int:
        """
        Compute hourly rollups for the current hour.
        
        Returns:
            Number of rollups computed
        """
        from sqlalchemy import select
        from .analytics_models import AnalyticsHourlyRollup, AnalyticsRunMetrics
        
        session = self._get_session()
        now = datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")
        hour = now.hour
        
        computed = 0
        
        try:
            # Get runs for this hour
            runs = session.execute(
                select(AnalyticsRunMetrics).where(
                    AnalyticsRunMetrics.date_bucket == date_str,
                    AnalyticsRunMetrics.hour_bucket == hour,
                )
            ).scalars().all()
            
            if not runs:
                logger.debug(f"No runs for {date_str} hour {hour}")
                return 0
            
            # Global rollup
            existing = session.execute(
                select(AnalyticsHourlyRollup).where(
                    AnalyticsHourlyRollup.date_bucket == date_str,
                    AnalyticsHourlyRollup.hour_bucket == hour,
                    AnalyticsHourlyRollup.repo_full_name.is_(None),
                )
            ).scalar_one_or_none()
            
            if existing:
                rollup = existing
            else:
                rollup = AnalyticsHourlyRollup(
                    date_bucket=date_str,
                    hour_bucket=hour,
                    repo_full_name=None,
                )
                session.add(rollup)
            
            total = len(runs)
            rollup.total_runs = total
            rollup.pass_count = sum(1 for r in runs if r.verdict == "PASS")
            rollup.fail_count = sum(1 for r in runs if r.verdict == "FAIL")
            rollup.veto_count = sum(1 for r in runs if r.verdict == "VETO")
            
            durations = [r.duration_seconds for r in runs if r.duration_seconds]
            rollup.avg_duration_seconds = sum(durations) / len(durations) if durations else None
            
            scores = [r.overall_score for r in runs if r.overall_score]
            rollup.avg_score = sum(scores) / len(scores) if scores else None
            
            tokens = [r.token_count for r in runs if r.token_count]
            rollup.total_tokens = sum(tokens)
            
            rollup.computed_at = now.isoformat()
            computed += 1
            
            session.commit()
            logger.info(f"Computed hourly rollup for {date_str} hour {hour}: {total} runs")
            
        except Exception as e:
            logger.error(f"Failed to compute hourly rollups: {e}")
            session.rollback()
        
        return computed
    
    def cleanup_old_hourly_rollups(self, retain_hours: int = 48) -> int:
        """
        Delete hourly rollups older than retain_hours.
        
        Returns:
            Number of rollups deleted
        """
        from sqlalchemy import delete
        from .analytics_models import AnalyticsHourlyRollup
        
        session = self._get_session()
        cutoff = datetime.utcnow() - timedelta(hours=retain_hours)
        cutoff_date = cutoff.strftime("%Y-%m-%d")
        cutoff_hour = cutoff.hour
        
        try:
            # Delete rollups from dates before cutoff
            result = session.execute(
                delete(AnalyticsHourlyRollup).where(
                    AnalyticsHourlyRollup.date_bucket < cutoff_date
                )
            )
            deleted = result.rowcount
            
            # For cutoff date, delete hours before cutoff hour
            result = session.execute(
                delete(AnalyticsHourlyRollup).where(
                    AnalyticsHourlyRollup.date_bucket == cutoff_date,
                    AnalyticsHourlyRollup.hour_bucket < cutoff_hour
                )
            )
            deleted += result.rowcount
            
            session.commit()
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old hourly rollups")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to cleanup hourly rollups: {e}")
            session.rollback()
            return 0
    
    # =========================================================================
    # DAILY ROLLUPS
    # =========================================================================
    
    def compute_daily_rollups_for_yesterday(self) -> int:
        """
        Compute daily rollups for yesterday (should run at midnight).
        
        Returns:
            Number of rollups computed
        """
        extractor = self._get_extractor()
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        computed = 0
        
        # Global rollup
        if extractor.compute_daily_rollups(yesterday, repo_full_name=None):
            computed += 1
        
        # Per-repo rollups
        from sqlalchemy import select
        from .analytics_models import AnalyticsRunMetrics
        
        session = self._get_session()
        repos = session.execute(
            select(AnalyticsRunMetrics.repo_full_name).where(
                AnalyticsRunMetrics.date_bucket == yesterday,
                AnalyticsRunMetrics.repo_full_name.isnot(None),
            ).distinct()
        ).scalars().all()
        
        for repo in repos:
            if repo and extractor.compute_daily_rollups(yesterday, repo_full_name=repo):
                computed += 1
        
        logger.info(f"Computed {computed} daily rollups for {yesterday}")
        return computed
    
    # =========================================================================
    # REPO STATS
    # =========================================================================
    
    def update_all_repo_stats(self) -> int:
        """
        Update stats for all repositories with recent activity.
        
        Returns:
            Number of repos updated
        """
        from sqlalchemy import select
        from .analytics_models import AnalyticsRunMetrics
        
        session = self._get_session()
        extractor = self._get_extractor()
        
        # Get repos with runs in last 7 days
        cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        repos = session.execute(
            select(AnalyticsRunMetrics.repo_full_name).where(
                AnalyticsRunMetrics.date_bucket >= cutoff,
                AnalyticsRunMetrics.repo_full_name.isnot(None),
            ).distinct()
        ).scalars().all()
        
        updated = 0
        for repo in repos:
            if repo and extractor.update_repo_stats(repo):
                updated += 1
        
        logger.info(f"Updated stats for {updated} repositories")
        return updated
    
    # =========================================================================
    # JUDGE PERFORMANCE
    # =========================================================================
    
    def update_judge_performance(self) -> int:
        """
        Update performance metrics for all judges.
        
        Returns:
            Number of judges updated
        """
        from sqlalchemy import select
        from .analytics_models import AnalyticsJudgePerformance, AnalyticsRunMetrics
        
        session = self._get_session()
        now = datetime.utcnow()
        
        # Get judge scores from recent runs
        cutoff_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        
        runs = session.execute(
            select(AnalyticsRunMetrics).where(
                AnalyticsRunMetrics.date_bucket >= cutoff_30d
            )
        ).scalars().all()
        
        if not runs:
            return 0
        
        # Aggregate by judge role
        judges = {
            "architect": {"scores": [], "vetos": 0},
            "security": {"scores": [], "vetos": 0},
            "user_proxy": {"scores": [], "vetos": 0},
        }
        
        for run in runs:
            if run.architect_score is not None:
                judges["architect"]["scores"].append(run.architect_score)
            if run.security_score is not None:
                judges["security"]["scores"].append(run.security_score)
            if run.user_proxy_score is not None:
                judges["user_proxy"]["scores"].append(run.user_proxy_score)
            
            if run.veto_triggered and run.veto_judge:
                judge_key = run.veto_judge.lower()
                if judge_key in judges:
                    judges[judge_key]["vetos"] += 1
        
        updated = 0
        for judge_id, data in judges.items():
            if not data["scores"]:
                continue
            
            # Upsert performance record
            existing = session.execute(
                select(AnalyticsJudgePerformance).where(
                    AnalyticsJudgePerformance.judge_id == judge_id
                )
            ).scalar_one_or_none()
            
            if existing:
                perf = existing
            else:
                perf = AnalyticsJudgePerformance(judge_id=judge_id, judge_name=judge_id.title())
                session.add(perf)
            
            import statistics
            
            perf.total_evaluations = len(data["scores"])
            perf.avg_score = round(statistics.mean(data["scores"]), 2)
            perf.score_stddev = round(statistics.stdev(data["scores"]), 2) if len(data["scores"]) > 1 else 0
            perf.min_score = min(data["scores"])
            perf.max_score = max(data["scores"])
            perf.veto_count = data["vetos"]
            perf.veto_rate = round(data["vetos"] / len(data["scores"]) * 100, 2) if data["scores"] else 0
            perf.updated_at = now.isoformat()
            
            updated += 1
        
        try:
            session.commit()
            logger.info(f"Updated performance for {updated} judges")
        except Exception as e:
            logger.error(f"Failed to update judge performance: {e}")
            session.rollback()
            return 0
        
        return updated
    
    # =========================================================================
    # SYSTEM HEALTH
    # =========================================================================
    
    def record_system_health(self) -> Optional[str]:
        """
        Record current system health snapshot.
        
        Returns:
            Health record ID or None on failure
        """
        from sqlalchemy import select
        from .analytics_models import AnalyticsSystemHealth, AnalyticsRunMetrics
        
        session = self._get_session()
        now = datetime.utcnow()
        
        # Get runs from last hour
        cutoff = (now - timedelta(hours=1)).isoformat()
        
        runs = session.execute(
            select(AnalyticsRunMetrics).where(
                AnalyticsRunMetrics.started_at >= cutoff
            )
        ).scalars().all()
        
        # Calculate rates
        runs_per_hour = len(runs)
        
        if runs:
            error_count = sum(1 for r in runs if r.verdict == "ERROR")
            error_rate = error_count / len(runs) * 100
            
            durations = [r.duration_seconds for r in runs if r.duration_seconds]
            avg_latency = sum(durations) / len(durations) if durations else 0
        else:
            error_rate = 0
            avg_latency = 0
        
        # Provider status (placeholder - would integrate with actual monitoring)
        import json
        provider_status = json.dumps({
            "openai": {"healthy": True, "latency_ms": 850},
            "anthropic": {"healthy": True, "latency_ms": 720},
        })
        
        # Create health record
        import uuid
        health = AnalyticsSystemHealth(
            id=str(uuid.uuid4()),
            timestamp=now.isoformat(),
            runs_per_hour=runs_per_hour,
            avg_latency_seconds=avg_latency,
            error_rate=error_rate,
            queue_depth=0,  # Would integrate with actual queue
            active_connections=1,  # Would integrate with connection pool
            provider_status=provider_status,
            healthy=1 if error_rate < 10 else 0,
        )
        
        try:
            session.add(health)
            session.commit()
            logger.debug(f"Recorded system health: {runs_per_hour} runs/hr, {error_rate:.1f}% errors")
            return health.id
        except Exception as e:
            logger.error(f"Failed to record system health: {e}")
            session.rollback()
            return None
    
    def cleanup_old_health_records(self, retain_hours: int = 168) -> int:
        """
        Delete health records older than retain_hours (default 7 days).
        
        Returns:
            Number of records deleted
        """
        from sqlalchemy import delete
        from .analytics_models import AnalyticsSystemHealth
        
        session = self._get_session()
        cutoff = (datetime.utcnow() - timedelta(hours=retain_hours)).isoformat()
        
        try:
            result = session.execute(
                delete(AnalyticsSystemHealth).where(
                    AnalyticsSystemHealth.timestamp < cutoff
                )
            )
            deleted = result.rowcount
            session.commit()
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old health records")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to cleanup health records: {e}")
            session.rollback()
            return 0
    
    # =========================================================================
    # SCHEDULER
    # =========================================================================
    
    async def run_continuous(self):
        """
        Run continuous rollup job with scheduled tasks.
        
        Tasks:
        - Every minute: Record system health
        - Every hour: Compute hourly rollups, cleanup old hourly data
        - Every day at midnight: Compute daily rollups, update repo stats
        """
        self._running = True
        logger.info("Analytics rollup job started")
        
        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_shutdown)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass
        
        last_hourly = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        last_daily = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        while self._running:
            now = datetime.utcnow()
            
            try:
                # Every minute: health snapshot
                self.record_system_health()
                
                # Check if new hour
                current_hour = now.replace(minute=0, second=0, microsecond=0)
                if current_hour > last_hourly:
                    logger.info("Running hourly tasks...")
                    self.compute_hourly_rollups()
                    self.cleanup_old_hourly_rollups()
                    last_hourly = current_hour
                
                # Check if new day (midnight UTC)
                current_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if current_day > last_daily:
                    logger.info("Running daily tasks...")
                    self.compute_daily_rollups_for_yesterday()
                    self.update_all_repo_stats()
                    self.update_judge_performance()
                    self.cleanup_old_health_records()
                    last_daily = current_day
                
            except Exception as e:
                logger.error(f"Error in rollup job: {e}")
            
            # Sleep for 60 seconds
            await asyncio.sleep(60)
        
        logger.info("Analytics rollup job stopped")
    
    def _handle_shutdown(self):
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._running = False
    
    def run_once(self):
        """
        Run all rollup tasks once (for manual invocation or cron).
        """
        logger.info("Running analytics rollup tasks...")
        
        # Compute yesterday's daily rollups
        self.compute_daily_rollups_for_yesterday()
        
        # Update current hour
        self.compute_hourly_rollups()
        
        # Update repo stats
        self.update_all_repo_stats()
        
        # Update judge performance
        self.update_judge_performance()
        
        # Record health
        self.record_system_health()
        
        # Cleanup
        self.cleanup_old_hourly_rollups()
        self.cleanup_old_health_records()
        
        logger.info("Analytics rollup tasks completed")


# =========================================================================
# CLI ENTRY POINT
# =========================================================================

def main():
    """CLI entry point for rollup job."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Analytics Rollup Job")
    parser.add_argument(
        "--mode",
        choices=["once", "continuous"],
        default="once",
        help="Run mode: once (single execution) or continuous (scheduled)",
    )
    parser.add_argument(
        "--db",
        default="db/invariant.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill from existing artifacts before running",
    )
    parser.add_argument(
        "--backfill-limit",
        type=int,
        default=None,
        help="Limit number of artifacts to backfill",
    )
    
    args = parser.parse_args()
    
    job = AnalyticsRollupJob(db_path=args.db)
    
    if args.backfill:
        logger.info("Backfilling from artifacts...")
        extractor = job._get_extractor()
        count = extractor.backfill_from_artifacts(
            Path("run_artifacts"),
            limit=args.backfill_limit,
        )
        logger.info(f"Backfilled {count} runs")
    
    if args.mode == "once":
        job.run_once()
    else:
        asyncio.run(job.run_continuous())


if __name__ == "__main__":
    main()
