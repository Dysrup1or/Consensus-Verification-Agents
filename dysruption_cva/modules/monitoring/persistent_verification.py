"""Persistent Verification Integration.

This module integrates the layered verification system with:
- watcher_v2 (file system events)
- monitoring/worker (GitHub webhooks)
- Existing CVA infrastructure

Usage:
    # As a daemon:
    python -m modules.monitoring.persistent_verification --repo /path/to/repo

    # Programmatic:
    from modules.monitoring.persistent_verification import start_persistent_verification
    await start_persistent_verification(repo_path="/path/to/repo")
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from modules.monitoring.layered_verification import (
    EscalationDecision,
    GitDiffDetector,
    IssueRanker,
    LayeredVerificationDaemon,
    QuickConstitutionalScanner,
    QuickScanResult,
    VerificationCycleResult,
)


class PersistentVerificationService:
    """Service that runs persistent layered verification.
    
    Features:
    - Combines file watcher + git diff detection
    - Configurable from environment variables
    - Integrates with existing CVA infrastructure
    - Provides REST API status endpoint
    """
    
    def __init__(
        self,
        repo_path: str,
        constitution_path: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.constitution_path = constitution_path
        self.config = config or {}
        
        # Load config from environment
        self.poll_interval = float(os.getenv("CVA_POLL_INTERVAL", "5.0"))
        self.escalation_threshold = int(os.getenv("CVA_ESCALATION_THRESHOLD", "20"))
        self.enable_llm_escalation = os.getenv("CVA_ENABLE_LLM_ESCALATION", "true").lower() == "true"
        
        # Initialize daemon
        self.daemon = LayeredVerificationDaemon(
            repo_path=str(self.repo_path),
            constitution_path=constitution_path,
            poll_interval_seconds=self.poll_interval,
            escalation_threshold=self.escalation_threshold,
            on_violation_callback=self._on_violation,
            on_escalation_callback=self._on_escalation,
        )
        
        # Metrics
        self._violations_total = 0
        self._escalations_total = 0
        self._cycles_total = 0
        self._start_time: Optional[datetime] = None
    
    def _on_violation(self, scan_result: QuickScanResult) -> None:
        """Called when violations are found in quick scan."""
        self._violations_total += len(scan_result.violations)
        
        # Log violations
        for v in scan_result.violations:
            logger.warning(
                f"Quick scan violation: [{v.severity}] {v.rule_id} - {v.message} "
                f"in {v.file}:{v.line_start}"
            )
        
        # Could trigger notifications here (Slack, email, etc.)
    
    def _on_escalation(self, decision: EscalationDecision) -> None:
        """Called when threshold is exceeded and LLM verification triggered."""
        self._escalations_total += 1
        
        logger.warning(
            f"Escalation triggered: {decision.reason} "
            f"(score={decision.score}, threshold={decision.threshold})"
        )
        
        if not self.enable_llm_escalation:
            logger.info("LLM escalation disabled by configuration")
    
    async def start(self) -> None:
        """Start the persistent verification service."""
        self._start_time = datetime.utcnow()
        
        logger.info("=" * 60)
        logger.info("PERSISTENT VERIFICATION SERVICE STARTING")
        logger.info("=" * 60)
        logger.info(f"Repository: {self.repo_path}")
        logger.info(f"Constitution: {self.constitution_path or 'default'}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Escalation threshold: {self.escalation_threshold}")
        logger.info(f"LLM escalation enabled: {self.enable_llm_escalation}")
        logger.info("=" * 60)
        
        await self.daemon.start()
    
    def stop(self) -> None:
        """Stop the service."""
        self.daemon.stop()
        logger.info("Persistent verification service stopped")
    
    def get_status(self) -> dict:
        """Get current service status."""
        uptime = None
        if self._start_time:
            uptime = (datetime.utcnow() - self._start_time).total_seconds()
        
        last_result = self.daemon.last_result
        
        return {
            "status": "running" if self.daemon._running else "stopped",
            "uptime_seconds": uptime,
            "repo_path": str(self.repo_path),
            "poll_interval": self.poll_interval,
            "escalation_threshold": self.escalation_threshold,
            "metrics": {
                "violations_total": self._violations_total,
                "escalations_total": self._escalations_total,
                "cycles_total": len(self.daemon.history),
            },
            "last_cycle": {
                "timestamp": last_result.timestamp.isoformat() if last_result else None,
                "files_changed": len(last_result.git_diff.changed_files) if last_result else 0,
                "violations_found": len(last_result.quick_scan.violations) if last_result and last_result.quick_scan else 0,
                "escalated": last_result.escalation.should_escalate if last_result and last_result.escalation else False,
                "time_ms": last_result.total_time_ms if last_result else 0,
            } if last_result else None,
        }


async def start_persistent_verification(
    repo_path: str,
    constitution_path: Optional[str] = None,
) -> PersistentVerificationService:
    """Start persistent verification for a repository.
    
    Args:
        repo_path: Path to the git repository
        constitution_path: Optional path to constitution file
    
    Returns:
        Running PersistentVerificationService instance
    """
    service = PersistentVerificationService(
        repo_path=repo_path,
        constitution_path=constitution_path,
    )
    
    # Start in background task
    asyncio.create_task(service.start())
    
    return service


def run_daemon(repo_path: str, constitution_path: Optional[str] = None) -> None:
    """Run the daemon as a blocking process."""
    
    service = PersistentVerificationService(
        repo_path=repo_path,
        constitution_path=constitution_path,
    )
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        service.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        service.stop()


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point for persistent verification daemon."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run persistent layered verification daemon"
    )
    parser.add_argument(
        "--repo", "-r",
        default=".",
        help="Path to git repository (default: current directory)"
    )
    parser.add_argument(
        "--constitution", "-c",
        default=None,
        help="Path to constitution file"
    )
    parser.add_argument(
        "--poll-interval", "-p",
        type=float,
        default=None,
        help="Poll interval in seconds (default: from CVA_POLL_INTERVAL or 5.0)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=int,
        default=None,
        help="Escalation threshold score (default: from CVA_ESCALATION_THRESHOLD or 20)"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM escalation (quick scan only)"
    )
    
    args = parser.parse_args()
    
    # Override environment from CLI args
    if args.poll_interval:
        os.environ["CVA_POLL_INTERVAL"] = str(args.poll_interval)
    if args.threshold:
        os.environ["CVA_ESCALATION_THRESHOLD"] = str(args.threshold)
    if args.no_llm:
        os.environ["CVA_ENABLE_LLM_ESCALATION"] = "false"
    
    run_daemon(
        repo_path=args.repo,
        constitution_path=args.constitution,
    )


if __name__ == "__main__":
    main()
