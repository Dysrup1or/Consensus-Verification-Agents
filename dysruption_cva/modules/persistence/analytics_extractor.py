"""
Analytics Metrics Extractor

Extracts metrics from tribunal verdict artifacts and populates analytics tables.
Handles both real-time ingestion (on run completion) and batch backfill.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .analytics_models import (
    AnalyticsDailyRollup,
    AnalyticsHourlyRollup,
    AnalyticsJudgePerformance,
    AnalyticsRepoStats,
    AnalyticsRunMetrics,
    AnalyticsSystemHealth,
)


class AnalyticsExtractor:
    """
    Extracts metrics from verdict payloads and updates analytics tables.
    
    Usage:
        extractor = AnalyticsExtractor(session)
        
        # Extract from a verdict payload
        extractor.extract_run_metrics(run_id, verdict_payload)
        
        # Compute daily rollups
        extractor.compute_daily_rollups("2025-12-17")
        
        # Update repo stats
        extractor.update_repo_stats("org/repo")
    """
    
    def __init__(self, session: Session):
        """Initialize with database session."""
        self.session = session
    
    # =========================================================================
    # RUN METRICS EXTRACTION
    # =========================================================================
    
    def extract_run_metrics(
        self,
        run_id: str,
        verdict_payload: Dict[str, Any],
        repo_full_name: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Optional[AnalyticsRunMetrics]:
        """
        Extract metrics from a verdict payload and store in analytics table.
        
        Args:
            run_id: Unique run identifier
            verdict_payload: The tribunal verdict JSON payload
            repo_full_name: Optional repository name (org/repo)
            branch: Optional branch name
            
        Returns:
            The created AnalyticsRunMetrics record or None if extraction failed
        """
        try:
            # Check if already exists
            existing = self.session.execute(
                select(AnalyticsRunMetrics).where(AnalyticsRunMetrics.run_id == run_id)
            ).scalar_one_or_none()
            
            if existing:
                logger.debug(f"Analytics for run {run_id} already exists, skipping")
                return existing
            
            # Extract core fields
            telemetry = verdict_payload.get("telemetry", {})
            metrics = verdict_payload.get("metrics", {})
            
            # Determine verdict
            verdicts = verdict_payload.get("verdicts", [])
            verdict = self._determine_verdict(verdict_payload, verdicts)
            
            # Calculate score
            overall_score = self._calculate_overall_score(verdicts)
            
            # Extract judge scores
            architect_score, security_score, user_proxy_score = self._extract_judge_scores(verdicts)
            
            # Determine timing
            started_at = telemetry.get("run_started_at") or verdict_payload.get("created_at")
            finished_at = telemetry.get("run_final_at") or verdict_payload.get("created_at")
            
            duration_seconds = None
            if started_at and finished_at:
                try:
                    start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                    duration_seconds = (end_dt - start_dt).total_seconds()
                except (ValueError, TypeError):
                    pass
            
            # Get latency from telemetry
            latency = telemetry.get("latency", {})
            llm_latency_ms = latency.get("llm_latency_ms") or metrics.get("llm_latency_ms")
            
            # Token counts
            token_count = metrics.get("token_count", 0)
            cost = telemetry.get("cost", {})
            llm_input_tokens = cost.get("lane2_llm_input_tokens_est", 0)
            
            # Veto information
            veto_info = verdict_payload.get("veto_protocol", {})
            veto_triggered = 1 if veto_info.get("triggered") else 0
            veto_judge = veto_info.get("judge")
            
            # Static analysis
            coverage = telemetry.get("coverage", {})
            files_covered = coverage.get("included_files_count", 0)
            files_total = coverage.get("included_files_count", 0) + len(coverage.get("unknown_files", []))
            
            # Static issues (if available in legacy format)
            static_issues_count = metrics.get("violations_count", 0)
            
            # Extract project_id and mode
            project_id = telemetry.get("project_id") or verdict_payload.get("project_id")
            mode = telemetry.get("mode", "unknown")
            
            # Compute date buckets
            date_bucket = None
            hour_bucket = None
            if started_at:
                try:
                    dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    date_bucket = dt.strftime("%Y-%m-%d")
                    hour_bucket = dt.hour
                except (ValueError, TypeError):
                    pass
            
            # Create record
            record = AnalyticsRunMetrics(
                run_id=run_id,
                project_id=project_id,
                repo_full_name=repo_full_name,
                branch=branch,
                verdict=verdict,
                overall_score=overall_score,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                llm_latency_ms=llm_latency_ms,
                token_count=token_count,
                llm_input_tokens=llm_input_tokens,
                architect_score=architect_score,
                security_score=security_score,
                user_proxy_score=user_proxy_score,
                veto_triggered=veto_triggered,
                veto_judge=veto_judge,
                static_issues_count=static_issues_count,
                files_covered=files_covered,
                files_total=files_total,
                mode=mode,
                date_bucket=date_bucket,
                hour_bucket=hour_bucket,
            )
            
            self.session.add(record)
            self.session.commit()
            
            logger.info(f"Extracted analytics for run {run_id}: {verdict}, score={overall_score}")
            return record
            
        except Exception as e:
            logger.error(f"Failed to extract analytics for run {run_id}: {e}")
            self.session.rollback()
            return None
    
    def _determine_verdict(
        self,
        payload: Dict[str, Any],
        verdicts: List[Dict],
    ) -> str:
        """Determine overall verdict from payload."""
        # Check for explicit verdict
        if "overall_verdict" in payload:
            return payload["overall_verdict"]
        
        # Check veto
        veto = payload.get("veto_protocol", {})
        if veto.get("triggered"):
            return "VETO"
        
        # Check fail-fast abort
        fail_fast = payload.get("fail_fast", {})
        if fail_fast.get("aborted"):
            return "ERROR"
        
        # Analyze individual verdicts
        if not verdicts:
            return "ERROR"
        
        # Count by status
        statuses = [v.get("verdict", "").upper() for v in verdicts]
        
        if all(s == "PASS" for s in statuses):
            return "PASS"
        elif any(s == "FAIL" for s in statuses):
            return "FAIL"
        elif any(s == "PARTIAL" for s in statuses):
            return "PARTIAL"
        else:
            return "PASS"
    
    def _calculate_overall_score(self, verdicts: List[Dict]) -> Optional[float]:
        """Calculate overall score from verdicts."""
        scores = []
        for v in verdicts:
            score = v.get("score")
            if score is not None:
                try:
                    scores.append(float(score))
                except (ValueError, TypeError):
                    pass
        
        if not scores:
            return None
        
        return round(sum(scores) / len(scores), 2)
    
    def _extract_judge_scores(
        self,
        verdicts: List[Dict],
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Extract scores by judge role from verdicts."""
        architect_scores = []
        security_scores = []
        user_proxy_scores = []
        
        for v in verdicts:
            role = v.get("judge_role", "").lower()
            score = v.get("score")
            
            if score is None:
                continue
            
            try:
                score_val = float(score)
            except (ValueError, TypeError):
                continue
            
            if "architect" in role:
                architect_scores.append(score_val)
            elif "security" in role:
                security_scores.append(score_val)
            elif "user" in role or "proxy" in role:
                user_proxy_scores.append(score_val)
        
        def avg_or_none(scores: List[float]) -> Optional[float]:
            return round(sum(scores) / len(scores), 2) if scores else None
        
        return (
            avg_or_none(architect_scores),
            avg_or_none(security_scores),
            avg_or_none(user_proxy_scores),
        )
    
    # =========================================================================
    # DAILY ROLLUPS
    # =========================================================================
    
    def compute_daily_rollups(
        self,
        date_str: str,
        repo_full_name: Optional[str] = None,
    ) -> Optional[AnalyticsDailyRollup]:
        """
        Compute and store daily rollup for a specific date.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            repo_full_name: Optional repo filter (None for global)
            
        Returns:
            The created/updated rollup record
        """
        try:
            # Build query
            query = select(AnalyticsRunMetrics).where(
                AnalyticsRunMetrics.date_bucket == date_str
            )
            
            if repo_full_name:
                query = query.where(AnalyticsRunMetrics.repo_full_name == repo_full_name)
            
            runs = self.session.execute(query).scalars().all()
            
            if not runs:
                logger.debug(f"No runs found for {date_str}, repo={repo_full_name}")
                return None
            
            # Aggregate metrics
            total_runs = len(runs)
            pass_count = sum(1 for r in runs if r.verdict == "PASS")
            fail_count = sum(1 for r in runs if r.verdict == "FAIL")
            veto_count = sum(1 for r in runs if r.verdict == "VETO")
            partial_count = sum(1 for r in runs if r.verdict == "PARTIAL")
            error_count = sum(1 for r in runs if r.verdict == "ERROR")
            
            pass_rate = (pass_count / total_runs * 100) if total_runs > 0 else None
            fail_rate = (fail_count / total_runs * 100) if total_runs > 0 else None
            veto_rate = (veto_count / total_runs * 100) if total_runs > 0 else None
            
            # Score aggregates
            scores = [r.overall_score for r in runs if r.overall_score is not None]
            avg_score = statistics.mean(scores) if scores else None
            min_score = min(scores) if scores else None
            max_score = max(scores) if scores else None
            
            # Duration aggregates with percentiles
            durations = [r.duration_seconds for r in runs if r.duration_seconds is not None]
            avg_duration = statistics.mean(durations) if durations else None
            min_duration = min(durations) if durations else None
            max_duration = max(durations) if durations else None
            
            p50, p75, p95, p99 = self._compute_percentiles(durations)
            
            # Token aggregates
            tokens = [r.token_count for r in runs if r.token_count is not None]
            total_tokens = sum(tokens)
            avg_tokens = statistics.mean(tokens) if tokens else None
            
            # Judge score averages
            arch_scores = [r.architect_score for r in runs if r.architect_score is not None]
            sec_scores = [r.security_score for r in runs if r.security_score is not None]
            user_scores = [r.user_proxy_score for r in runs if r.user_proxy_score is not None]
            
            avg_architect = statistics.mean(arch_scores) if arch_scores else None
            avg_security = statistics.mean(sec_scores) if sec_scores else None
            avg_user_proxy = statistics.mean(user_scores) if user_scores else None
            
            # Static analysis
            total_static = sum(r.static_issues_count for r in runs)
            total_critical = sum(r.critical_issues_count for r in runs)
            
            # Unique counts
            unique_repos = len(set(r.repo_full_name for r in runs if r.repo_full_name))
            unique_projects = len(set(r.project_id for r in runs if r.project_id))
            
            # Upsert rollup
            existing = self.session.execute(
                select(AnalyticsDailyRollup).where(
                    AnalyticsDailyRollup.date_bucket == date_str,
                    AnalyticsDailyRollup.repo_full_name == repo_full_name,
                )
            ).scalar_one_or_none()
            
            if existing:
                rollup = existing
            else:
                rollup = AnalyticsDailyRollup(
                    date_bucket=date_str,
                    repo_full_name=repo_full_name,
                )
                self.session.add(rollup)
            
            # Update fields
            rollup.total_runs = total_runs
            rollup.pass_count = pass_count
            rollup.fail_count = fail_count
            rollup.veto_count = veto_count
            rollup.partial_count = partial_count
            rollup.error_count = error_count
            rollup.pass_rate = pass_rate
            rollup.fail_rate = fail_rate
            rollup.veto_rate = veto_rate
            rollup.avg_score = avg_score
            rollup.min_score = min_score
            rollup.max_score = max_score
            rollup.avg_duration_seconds = avg_duration
            rollup.min_duration_seconds = min_duration
            rollup.max_duration_seconds = max_duration
            rollup.p50_duration_seconds = p50
            rollup.p75_duration_seconds = p75
            rollup.p95_duration_seconds = p95
            rollup.p99_duration_seconds = p99
            rollup.total_tokens = total_tokens
            rollup.avg_tokens = avg_tokens
            rollup.avg_architect_score = avg_architect
            rollup.avg_security_score = avg_security
            rollup.avg_user_proxy_score = avg_user_proxy
            rollup.total_static_issues = total_static
            rollup.total_critical_issues = total_critical
            rollup.unique_repos = unique_repos
            rollup.unique_projects = unique_projects
            rollup.computed_at = datetime.utcnow().isoformat()
            
            self.session.commit()
            logger.info(f"Computed daily rollup for {date_str}: {total_runs} runs")
            return rollup
            
        except Exception as e:
            logger.error(f"Failed to compute daily rollup for {date_str}: {e}")
            self.session.rollback()
            return None
    
    def _compute_percentiles(
        self,
        values: List[float],
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Compute p50, p75, p95, p99 percentiles."""
        if not values:
            return None, None, None, None
        
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        
        def percentile(p: float) -> float:
            idx = int(n * p)
            idx = min(idx, n - 1)
            return round(sorted_vals[idx], 2)
        
        return percentile(0.50), percentile(0.75), percentile(0.95), percentile(0.99)
    
    # =========================================================================
    # REPOSITORY STATS
    # =========================================================================
    
    def update_repo_stats(self, repo_full_name: str) -> Optional[AnalyticsRepoStats]:
        """
        Update aggregated statistics for a repository.
        
        Args:
            repo_full_name: Repository name (org/repo)
            
        Returns:
            The updated stats record
        """
        try:
            # Get all runs for this repo
            runs = self.session.execute(
                select(AnalyticsRunMetrics).where(
                    AnalyticsRunMetrics.repo_full_name == repo_full_name
                )
            ).scalars().all()
            
            if not runs:
                return None
            
            # Lifetime totals
            total_runs = len(runs)
            total_pass = sum(1 for r in runs if r.verdict == "PASS")
            total_fail = sum(1 for r in runs if r.verdict == "FAIL")
            total_veto = sum(1 for r in runs if r.verdict == "VETO")
            
            lifetime_pass_rate = (total_pass / total_runs * 100) if total_runs > 0 else None
            
            scores = [r.overall_score for r in runs if r.overall_score is not None]
            avg_score = statistics.mean(scores) if scores else None
            
            durations = [r.duration_seconds for r in runs if r.duration_seconds is not None]
            avg_duration = statistics.mean(durations) if durations else None
            
            # Time-based filtering
            now = datetime.utcnow()
            
            def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
                if not ts:
                    return None
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                except (ValueError, TypeError):
                    return None
            
            runs_7d = [r for r in runs if parse_timestamp(r.started_at) and (now - parse_timestamp(r.started_at)).days <= 7]
            runs_30d = [r for r in runs if parse_timestamp(r.started_at) and (now - parse_timestamp(r.started_at)).days <= 30]
            
            runs_7d_count = len(runs_7d)
            pass_rate_7d = (sum(1 for r in runs_7d if r.verdict == "PASS") / runs_7d_count * 100) if runs_7d_count > 0 else None
            
            runs_30d_count = len(runs_30d)
            pass_rate_30d = (sum(1 for r in runs_30d if r.verdict == "PASS") / runs_30d_count * 100) if runs_30d_count > 0 else None
            
            # Sparklines (last 14 days)
            sparkline_runs = []
            sparkline_pass_rate = []
            
            for days_ago in range(13, -1, -1):
                target_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
                day_runs = [r for r in runs if r.date_bucket == target_date]
                sparkline_runs.append(len(day_runs))
                
                if day_runs:
                    day_pass = sum(1 for r in day_runs if r.verdict == "PASS")
                    sparkline_pass_rate.append(round(day_pass / len(day_runs) * 100, 1))
                else:
                    sparkline_pass_rate.append(0)
            
            # First and last run timestamps
            timestamps = [parse_timestamp(r.started_at) for r in runs if parse_timestamp(r.started_at)]
            first_run = min(timestamps).isoformat() if timestamps else None
            last_run = max(timestamps).isoformat() if timestamps else None
            
            # Upsert stats
            existing = self.session.execute(
                select(AnalyticsRepoStats).where(
                    AnalyticsRepoStats.repo_full_name == repo_full_name
                )
            ).scalar_one_or_none()
            
            if existing:
                stats = existing
            else:
                stats = AnalyticsRepoStats(repo_full_name=repo_full_name)
                self.session.add(stats)
            
            stats.total_runs = total_runs
            stats.total_pass = total_pass
            stats.total_fail = total_fail
            stats.total_veto = total_veto
            stats.lifetime_pass_rate = lifetime_pass_rate
            stats.avg_score = avg_score
            stats.avg_duration_seconds = avg_duration
            stats.runs_7d = runs_7d_count
            stats.pass_rate_7d = pass_rate_7d
            stats.runs_30d = runs_30d_count
            stats.pass_rate_30d = pass_rate_30d
            stats.sparkline_runs = json.dumps(sparkline_runs)
            stats.sparkline_pass_rate = json.dumps(sparkline_pass_rate)
            stats.first_run_at = first_run
            stats.last_run_at = last_run
            stats.updated_at = datetime.utcnow().isoformat()
            
            self.session.commit()
            logger.info(f"Updated repo stats for {repo_full_name}: {total_runs} runs")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to update repo stats for {repo_full_name}: {e}")
            self.session.rollback()
            return None
    
    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================
    
    def backfill_from_artifacts(
        self,
        artifacts_root: Path,
        limit: Optional[int] = None,
    ) -> int:
        """
        Backfill analytics from existing verdict artifact files.
        
        Args:
            artifacts_root: Path to run_artifacts directory
            limit: Maximum number of runs to process (None for all)
            
        Returns:
            Number of runs processed
        """
        processed = 0
        
        if not artifacts_root.exists():
            logger.warning(f"Artifacts root not found: {artifacts_root}")
            return 0
        
        for run_dir in artifacts_root.iterdir():
            if limit and processed >= limit:
                break
            
            if not run_dir.is_dir():
                continue
            
            verdict_file = run_dir / "tribunal_verdicts.json"
            if not verdict_file.exists():
                continue
            
            try:
                with open(verdict_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                
                run_id = run_dir.name
                self.extract_run_metrics(run_id, payload)
                processed += 1
                
            except Exception as e:
                logger.warning(f"Failed to backfill {run_dir.name}: {e}")
        
        logger.info(f"Backfilled {processed} runs from artifacts")
        return processed
    
    def recompute_all_rollups(
        self,
        start_date: str,
        end_date: str,
    ) -> int:
        """
        Recompute daily rollups for a date range.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            Number of rollups computed
        """
        computed = 0
        
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            return 0
        
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            
            # Compute global rollup
            if self.compute_daily_rollups(date_str, repo_full_name=None):
                computed += 1
            
            # Compute per-repo rollups
            repos = self.session.execute(
                select(AnalyticsRunMetrics.repo_full_name).where(
                    AnalyticsRunMetrics.date_bucket == date_str,
                    AnalyticsRunMetrics.repo_full_name.isnot(None),
                ).distinct()
            ).scalars().all()
            
            for repo in repos:
                if repo:
                    self.compute_daily_rollups(date_str, repo_full_name=repo)
            
            current += timedelta(days=1)
        
        logger.info(f"Recomputed {computed} daily rollups from {start_date} to {end_date}")
        return computed
