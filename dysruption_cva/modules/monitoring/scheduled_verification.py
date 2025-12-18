"""Scheduled Verification Runner.

Runs layered verification on a configurable schedule (default: every 15 minutes).
Designed for continuous monitoring without expensive API calls unless necessary.

Usage:
    python -m modules.monitoring.scheduled_verification --interval 15
    python -m modules.monitoring.scheduled_verification --repo /path/to/repo
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

# Suppress LiteLLM verbose logging before importing other modules
import logging
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from modules.monitoring.layered_verification import (
    EscalationDecision,
    GitDiffDetector,
    IssueRanker,
    QuickConstitutionalScanner,
    QuickScanResult,
    QuickViolation,
    VerificationCycleResult,
    LayeredVerificationDaemon,
)

from modules.monitoring.sarif_formatter import SarifFormatter, SarifLocation, SarifResult, SarifRule


class ScheduledVerificationRunner:
    """Runs verification on a schedule (e.g., every 15 minutes).
    
    Unlike the continuous daemon, this runs discrete checks at intervals,
    making it suitable for cron jobs or Task Scheduler.
    """
    
    def __init__(
        self,
        repo_path: str,
        constitution_path: Optional[str] = None,
        interval_minutes: int = 15,
        escalation_threshold: int = 20,
        enable_llm: bool = False,  # Default to NO LLM for scheduled runs
        report_path: Optional[str] = None,
        sarif_output: bool = False,  # Enable SARIF output
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.constitution_path = constitution_path
        self.interval_minutes = interval_minutes
        self.escalation_threshold = escalation_threshold
        self.enable_llm = enable_llm
        self.report_path = report_path or str(self.repo_path / "verification_report.json")
        self.sarif_output = sarif_output
        self.sarif_path = str(Path(self.report_path).with_suffix(".sarif"))
        
        # Initialize components
        self.git_detector = GitDiffDetector(str(self.repo_path))
        self.scanner = QuickConstitutionalScanner(constitution_path)
        self.ranker = IssueRanker(threshold=escalation_threshold)
        
        # State tracking
        self._run_count = 0
        self._total_violations = 0
        self._total_escalations = 0
        self._start_time = datetime.utcnow()
        self._history: List[Dict] = []
        
        # Supported file extensions
        self._code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs"}
    
    def _filter_code_files(self, files: List[str]) -> List[str]:
        """Filter to only code files we should scan."""
        return [
            f for f in files
            if Path(f).suffix.lower() in self._code_extensions
            and not any(ignore in f for ignore in ["node_modules", "__pycache__", ".git", "venv", ".venv"])
        ]
    
    async def run_single_check(self) -> Dict:
        """Run a single verification check."""
        self._run_count += 1
        run_start = datetime.utcnow()
        
        logger.info("=" * 60)
        logger.info(f"SCHEDULED VERIFICATION #{self._run_count}")
        logger.info(f"Time: {run_start.isoformat()}")
        logger.info("=" * 60)
        
        # Layer 0: Git diff detection
        git_diff = self.git_detector.detect_changes()
        
        result = {
            "run_number": self._run_count,
            "timestamp": run_start.isoformat(),
            "git_changes": {
                "has_changes": git_diff.has_changes,
                "files_changed": len(git_diff.changed_files),
                "current_commit": git_diff.current_commit[:12] if git_diff.current_commit else None,
            },
            "quick_scan": None,
            "escalation": None,
            "status": "no_changes",
        }
        
        if not git_diff.has_changes:
            logger.info("No changes detected since last run")
            result["status"] = "no_changes"
        else:
            code_files = self._filter_code_files(git_diff.changed_files)
            logger.info(f"Found {len(git_diff.changed_files)} changed files ({len(code_files)} code files)")
            
            if code_files:
                # Layer 1: Quick scan
                scan_result = self.scanner.scan_files(code_files, base_path=str(self.repo_path))
                
                result["quick_scan"] = {
                    "files_scanned": scan_result.files_scanned,
                    "violations_count": len(scan_result.violations),
                    "total_score": scan_result.total_score,
                    "scan_time_ms": scan_result.scan_time_ms,
                    "violations": [
                        {
                            "rule_id": v.rule_id,
                            "severity": v.severity,
                            "file": v.file,
                            "line": v.line_start,
                            "message": v.message,
                        }
                        for v in scan_result.violations
                    ],
                }
                
                self._total_violations += len(scan_result.violations)
                
                if scan_result.violations:
                    logger.warning(f"Found {len(scan_result.violations)} violations (score: {scan_result.total_score})")
                    for v in scan_result.violations:
                        logger.warning(f"  [{v.severity.upper()}] {v.rule_id}: {v.message}")
                        logger.warning(f"           in {v.file}:{v.line_start}")
                else:
                    logger.info("Quick scan: No violations found")
                
                # Layer 2: Evaluate threshold
                decision = self.ranker.evaluate(scan_result)
                
                result["escalation"] = {
                    "should_escalate": decision.should_escalate,
                    "reason": decision.reason,
                    "score": decision.score,
                    "threshold": decision.threshold,
                    "critical_count": decision.critical_count,
                    "high_count": decision.high_count,
                }
                
                if decision.should_escalate:
                    self._total_escalations += 1
                    logger.warning(f"ESCALATION RECOMMENDED: {decision.reason}")
                    result["status"] = "escalation_needed"
                    
                    if self.enable_llm:
                        logger.info("Running full LLM verification...")
                        # Layer 3 would run here
                        result["status"] = "llm_verification_run"
                    else:
                        logger.info("LLM disabled - manual review recommended")
                else:
                    result["status"] = "clean" if not scan_result.violations else "minor_issues"
            else:
                result["status"] = "no_code_changes"
            
            # Mark as verified
            self.git_detector.mark_verified()
        
        run_duration = (datetime.utcnow() - run_start).total_seconds()
        result["duration_seconds"] = run_duration
        
        logger.info(f"Check completed in {run_duration:.2f}s - Status: {result['status']}")
        
        # Save to history
        self._history.append(result)
        if len(self._history) > 100:
            self._history = self._history[-100:]
        
        # Save report
        self._save_report()
        
        return result
    
    def _save_report(self) -> None:
        """Save current verification report to file."""
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "runner_start": self._start_time.isoformat(),
            "interval_minutes": self.interval_minutes,
            "repo_path": str(self.repo_path),
            "summary": {
                "total_runs": self._run_count,
                "total_violations": self._total_violations,
                "total_escalations": self._total_escalations,
            },
            "recent_runs": self._history[-10:],  # Last 10 runs
        }
        
        try:
            Path(self.report_path).write_text(
                json.dumps(report, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save report: {e}")
        
        # Also save SARIF if enabled
        if self.sarif_output:
            self._save_sarif_report(report)
    
    def _save_sarif_report(self, report: Dict) -> None:
        """Save verification report in SARIF format."""
        try:
            formatter = SarifFormatter(base_path=str(self.repo_path))
            
            # Add all rules from scanner patterns
            formatter.add_rules_from_patterns(self.scanner.patterns)
            
            # Add violations from recent runs
            for run in report.get("recent_runs", []):
                quick_scan = run.get("quick_scan", {})
                violations = quick_scan.get("violations", [])
                formatter.add_results_from_violations(violations)
            
            formatter.set_invocation_complete(success=True)
            formatter.write_file(self.sarif_path)
            logger.debug(f"SARIF report saved to {self.sarif_path}")
        except Exception as e:
            logger.warning(f"Failed to save SARIF report: {e}")
    
    async def run_scheduled(self) -> None:
        """Run verification on schedule."""
        logger.info(f"Starting scheduled verification (every {self.interval_minutes} minutes)")
        logger.info(f"Repository: {self.repo_path}")
        logger.info(f"Report: {self.report_path}")
        logger.info(f"LLM enabled: {self.enable_llm}")
        
        # Initial run
        await self.run_single_check()
        
        while True:
            next_run = datetime.utcnow() + timedelta(minutes=self.interval_minutes)
            logger.info(f"Next check at: {next_run.strftime('%H:%M:%S')}")
            
            await asyncio.sleep(self.interval_minutes * 60)
            
            try:
                await self.run_single_check()
            except Exception as e:
                logger.error(f"Check failed: {e}")


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run scheduled verification checks"
    )
    parser.add_argument(
        "--repo", "-r",
        default=".",
        help="Path to git repository"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=15,
        help="Interval between checks in minutes (default: 15)"
    )
    parser.add_argument(
        "--constitution", "-c",
        help="Path to constitution file"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=int,
        default=20,
        help="Escalation threshold score"
    )
    parser.add_argument(
        "--enable-llm",
        action="store_true",
        help="Enable LLM verification when threshold exceeded"
    )
    parser.add_argument(
        "--report", "-o",
        help="Path to save verification report JSON"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run single check and exit"
    )
    parser.add_argument(
        "--sarif",
        action="store_true",
        help="Also output SARIF format (verification_report.sarif)"
    )
    
    args = parser.parse_args()
    
    runner = ScheduledVerificationRunner(
        repo_path=args.repo,
        constitution_path=args.constitution,
        interval_minutes=args.interval,
        escalation_threshold=args.threshold,
        enable_llm=args.enable_llm,
        report_path=args.report,
        sarif_output=args.sarif,
    )
    
    def signal_handler(sig, frame):
        logger.info("Shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if args.once:
        result = asyncio.run(runner.run_single_check())
        print(json.dumps(result, indent=2))
    else:
        asyncio.run(runner.run_scheduled())


if __name__ == "__main__":
    main()
