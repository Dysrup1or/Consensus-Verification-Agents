"""
Remediation Engine - Core Orchestrator

Coordinates the autonomous remediation workflow:
1. Issue Detection (from verdict)
2. Root Cause Analysis
3. Safety Pre-flight Checks
4. Fix Generation (LLM)
5. Sandbox Validation (optional)
6. Patch Application
7. Health Monitoring
8. Rollback (if needed)

This is the main entry point for autonomous remediation.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from .detector import IssueDetector
from .generator import FixGenerator, PatchApplicator
from .models import (
    ApprovalLevel,
    AuditAction,
    FixStatus,
    HealthState,
    RemediationEvent,
    RemediationEventType,
    RemediationFix,
    RemediationIssue,
    RemediationRun,
    RemediationStatus,
    RootCause,
)
from .safety import (
    SafetyConfig,
    SafetyController,
    is_kill_switch_active,
)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class RemediationConfig:
    """Configuration for the remediation engine."""
    # Autonomy level
    enabled: bool = True
    auto_apply: bool = True
    max_iterations: int = 5
    
    # Safety config (nested)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    
    # Sandbox settings
    use_sandbox: bool = True
    sandbox_timeout_seconds: int = 60
    
    # Health monitoring
    health_check_interval_seconds: int = 10
    health_check_max_failures: int = 3
    rollback_on_health_failure: bool = True
    
    # LLM settings
    llm_model: str = "gpt-4"
    llm_max_tokens: int = 2000
    llm_temperature: float = 0.2
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RemediationConfig":
        """Create from dictionary."""
        config = cls()
        
        if "enabled" in data:
            config.enabled = bool(data["enabled"])
        if "auto_apply" in data:
            config.auto_apply = bool(data["auto_apply"])
        if "max_iterations" in data:
            config.max_iterations = int(data["max_iterations"])
        if "use_sandbox" in data:
            config.use_sandbox = bool(data["use_sandbox"])
        if "safety" in data:
            config.safety = SafetyConfig.from_dict(data["safety"])
        if "llm_model" in data:
            config.llm_model = data["llm_model"]
        
        return config


# =============================================================================
# EVENT EMITTER
# =============================================================================


class EventEmitter:
    """Emits remediation events to registered listeners."""
    
    def __init__(self):
        self._listeners: List[Callable[[RemediationEvent], None]] = []
        self._async_listeners: List[Callable[[RemediationEvent], Any]] = []
    
    def add_listener(self, callback: Callable[[RemediationEvent], None]):
        """Add a synchronous listener."""
        self._listeners.append(callback)
    
    def add_async_listener(self, callback: Callable[[RemediationEvent], Any]):
        """Add an async listener."""
        self._async_listeners.append(callback)
    
    def emit(self, event: RemediationEvent):
        """Emit an event to all listeners."""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Event listener error: {e}")
    
    async def emit_async(self, event: RemediationEvent):
        """Emit an event to all listeners (async)."""
        self.emit(event)
        
        for listener in self._async_listeners:
            try:
                await listener(event)
            except Exception as e:
                logger.error(f"Async event listener error: {e}")


# =============================================================================
# REMEDIATION ENGINE
# =============================================================================


class RemediationEngine:
    """
    Main orchestrator for autonomous remediation.
    
    Usage:
        engine = RemediationEngine(project_root, config, db_path)
        run = await engine.remediate(verdict)
    """
    
    def __init__(
        self,
        project_root: Path,
        config: RemediationConfig,
        db_path: Optional[str] = None,
        llm_client: Optional[Any] = None,
    ):
        self.project_root = project_root
        self.config = config
        self.db_path = db_path
        self.llm_client = llm_client
        
        # Components
        self.safety = SafetyController(config.safety, db_path, project_root)
        self.detector = IssueDetector(project_root)
        self.generator = FixGenerator(project_root, llm_client)
        self.applicator = PatchApplicator(project_root)
        
        # Events
        self.events = EventEmitter()
        
        # State
        self._current_run: Optional[RemediationRun] = None
        self._file_backups: Dict[str, str] = {}
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    async def remediate(
        self,
        verdict: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> RemediationRun:
        """
        Main entry point: remediate issues from a verdict.
        
        Args:
            verdict: The tribunal verdict containing issues
            run_id: Optional run ID (generated if not provided)
        
        Returns:
            RemediationRun with results
        """
        run_id = run_id or str(uuid.uuid4())
        
        # Initialize run
        run = RemediationRun(
            id=run_id,
            verdict_id=verdict.get("id", verdict.get("verdict_id")),
            status=RemediationStatus.STARTED,
            started_at=datetime.utcnow(),
            issues=[],
            fixes=[],
            health_state=HealthState.UNKNOWN,
        )
        self._current_run = run
        
        await self._emit(RemediationEventType.RUN_STARTED, {"run_id": run_id})
        
        try:
            # Pre-flight safety check
            safe, issues = self.safety.pre_flight_check()
            if not safe:
                run.status = RemediationStatus.BLOCKED
                run.error = f"Safety check failed: {', '.join(issues)}"
                await self._emit(RemediationEventType.SAFETY_BLOCKED, {"issues": issues})
                return await self._finalize_run(run)
            
            # Phase 1: Detect issues
            detected_issues = await self._detect_issues(verdict, run_id)
            run.issues = detected_issues
            
            if not detected_issues:
                run.status = RemediationStatus.COMPLETED
                await self._emit(RemediationEventType.NO_ISSUES, {})
                return await self._finalize_run(run)
            
            # Phase 2: Analyze root causes
            root_causes = await self._analyze_root_causes(detected_issues)
            
            # Phase 3: Generate and apply fixes
            run.status = RemediationStatus.IN_PROGRESS
            
            for iteration in range(self.config.max_iterations):
                # Check kill switch each iteration
                kill_active, kill_reason = self.safety.check_kill_switch()
                if kill_active:
                    run.status = RemediationStatus.ABORTED
                    run.error = f"Kill switch activated: {kill_reason}"
                    await self._emit(RemediationEventType.KILL_SWITCH, {"reason": kill_reason})
                    break
                
                # Generate fixes for remaining issues
                unfixed = [i for i in run.issues if not self._is_issue_fixed(i, run.fixes)]
                
                if not unfixed:
                    break
                
                await self._emit(RemediationEventType.ITERATION_STARTED, {
                    "iteration": iteration + 1,
                    "unfixed_count": len(unfixed),
                })
                
                # Generate and apply fix for highest priority issue
                issue = self._prioritize_issues(unfixed)[0]
                
                fix = await self._generate_fix(issue, root_causes)
                if fix and fix.status != FixStatus.FAILED:
                    run.fixes.append(fix)
                    
                    # Try to apply if auto-apply is enabled
                    if self.config.auto_apply and self.safety.can_auto_apply(fix):
                        success = await self._apply_fix(fix, run)
                        
                        if not success:
                            # Rollback and try next issue
                            await self._rollback_fix(fix)
                            continue
                        
                        # Health check after apply
                        if self.config.rollback_on_health_failure:
                            healthy = await self._health_check(run)
                            if not healthy:
                                await self._rollback_fix(fix)
                                fix.status = FixStatus.REVERTED
                                run.health_state = HealthState.DEGRADED
                
                run.iterations = iteration + 1
            
            # Determine final status
            applied_count = sum(1 for f in run.fixes if f.status == FixStatus.APPLIED)
            reverted_count = sum(1 for f in run.fixes if f.status == FixStatus.REVERTED)
            
            if applied_count > 0 and reverted_count == 0:
                run.status = RemediationStatus.COMPLETED
            elif applied_count > 0 and reverted_count > 0:
                run.status = RemediationStatus.PARTIAL
            elif reverted_count > 0:
                run.status = RemediationStatus.ROLLED_BACK
            else:
                run.status = RemediationStatus.COMPLETED
            
            return await self._finalize_run(run)
            
        except Exception as e:
            logger.exception(f"Remediation failed: {e}")
            run.status = RemediationStatus.FAILED
            run.error = str(e)
            await self._emit(RemediationEventType.ERROR, {"error": str(e)})
            return await self._finalize_run(run)
    
    # =========================================================================
    # DETECTION PHASE
    # =========================================================================
    
    async def _detect_issues(
        self,
        verdict: Dict[str, Any],
        run_id: str,
    ) -> List[RemediationIssue]:
        """Detect issues from verdict."""
        await self._emit(RemediationEventType.DETECTING_ISSUES, {})
        
        issues = self.detector.extract_from_verdict(verdict, run_id)
        
        await self._emit(RemediationEventType.ISSUES_DETECTED, {
            "count": len(issues),
            "issues": [{"id": i.id, "category": i.category.value} for i in issues],
        })
        
        return issues
    
    async def _analyze_root_causes(
        self,
        issues: List[RemediationIssue],
    ) -> Dict[str, RootCause]:
        """Analyze root causes for issue groups."""
        await self._emit(RemediationEventType.ANALYZING_ROOT_CAUSES, {})
        
        root_causes: Dict[str, RootCause] = {}
        
        groups = self.detector.group_related_issues(issues)
        
        for group in groups:
            root_cause = self.detector.identify_root_cause(group)
            if root_cause:
                root_causes[root_cause.primary_issue_id] = root_cause
        
        await self._emit(RemediationEventType.ROOT_CAUSES_IDENTIFIED, {
            "count": len(root_causes),
        })
        
        return root_causes
    
    # =========================================================================
    # FIX GENERATION PHASE
    # =========================================================================
    
    async def _generate_fix(
        self,
        issue: RemediationIssue,
        root_causes: Dict[str, RootCause],
    ) -> Optional[RemediationFix]:
        """Generate a fix for an issue."""
        await self._emit(RemediationEventType.GENERATING_FIX, {
            "issue_id": issue.id,
            "category": issue.category.value,
        })
        
        # Check if this issue has a root cause
        root_cause = root_causes.get(issue.id)
        symptom_issues = None
        
        if root_cause:
            symptom_issues = [
                i for i in self._current_run.issues
                if i.id in root_cause.symptom_issue_ids
            ]
        
        fix = await self.generator.generate_fix(issue, root_cause, symptom_issues)
        
        if fix:
            # Classify approval level
            fix.approval_level = self.safety.classify_approval_level(
                issue, fix.confidence
            )
            
            await self._emit(RemediationEventType.FIX_GENERATED, {
                "fix_id": fix.id,
                "confidence": fix.confidence,
                "approval_level": fix.approval_level.value,
            })
        
        return fix
    
    # =========================================================================
    # APPLICATION PHASE
    # =========================================================================
    
    async def _apply_fix(
        self,
        fix: RemediationFix,
        run: RemediationRun,
    ) -> bool:
        """Apply a fix to the codebase."""
        await self._emit(RemediationEventType.APPLYING_FIX, {"fix_id": fix.id})
        
        # Check blast radius
        files = [p.file_path for p in fix.patches]
        lines = sum(len(p.diff.split("\n")) for p in fix.patches)
        
        blast_ok, blast_reason = self.safety.check_blast_radius(files, lines)
        if not blast_ok:
            fix.status = FixStatus.BLOCKED
            await self._emit(RemediationEventType.FIX_BLOCKED, {
                "fix_id": fix.id,
                "reason": blast_reason,
            })
            return False
        
        # Create backups
        for patch in fix.patches:
            backup = self.applicator.create_backup(patch.file_path)
            if backup:
                self._file_backups[patch.file_path] = backup
                self._persist_backup(run.id, patch.file_path, backup)
        
        # Apply patches
        all_success = True
        applied_patches = []
        
        for patch in fix.patches:
            success, error = self.applicator.apply_patch(patch)
            
            if success:
                applied_patches.append(patch)
            else:
                logger.error(f"Patch failed: {error}")
                all_success = False
                
                # Rollback already applied patches
                for applied in applied_patches:
                    backup = self._file_backups.get(applied.file_path)
                    if backup:
                        self.applicator.revert_patch(applied.file_path, backup)
                
                break
        
        if all_success:
            fix.status = FixStatus.APPLIED
            fix.applied_at = datetime.utcnow()
            self.safety.record_fix_applied()
            
            await self._emit(RemediationEventType.FIX_APPLIED, {"fix_id": fix.id})
            
            # Log audit
            self.safety.log_action(
                AuditAction.FIX_APPLIED,
                {"fix_id": fix.id, "files": files},
                run.id,
            )
        else:
            fix.status = FixStatus.FAILED
            await self._emit(RemediationEventType.FIX_FAILED, {
                "fix_id": fix.id,
                "error": error,
            })
        
        return all_success
    
    async def _rollback_fix(self, fix: RemediationFix):
        """Rollback a fix."""
        await self._emit(RemediationEventType.ROLLING_BACK, {"fix_id": fix.id})
        
        for patch in fix.patches:
            backup = self._file_backups.get(patch.file_path)
            if backup:
                success, error = self.applicator.revert_patch(patch.file_path, backup)
                if not success:
                    logger.error(f"Rollback failed: {error}")
        
        fix.status = FixStatus.REVERTED
        self.safety.record_fix_reverted()
        
        self.safety.log_action(
            AuditAction.FIX_REVERTED,
            {"fix_id": fix.id},
            self._current_run.id if self._current_run else None,
        )
        
        await self._emit(RemediationEventType.ROLLED_BACK, {"fix_id": fix.id})
    
    # =========================================================================
    # HEALTH MONITORING
    # =========================================================================
    
    async def _health_check(self, run: RemediationRun) -> bool:
        """
        Run health check after applying a fix.
        
        This should verify that the codebase still works.
        """
        await self._emit(RemediationEventType.HEALTH_CHECKING, {})
        
        # TODO: Implement actual health checks
        # - Run fast test suite
        # - Type check
        # - Lint check
        # - Import check
        
        # For now, assume healthy
        run.health_state = HealthState.HEALTHY
        
        await self._emit(RemediationEventType.HEALTH_CHECKED, {
            "state": run.health_state.value,
        })
        
        return run.health_state == HealthState.HEALTHY
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def _prioritize_issues(
        self,
        issues: List[RemediationIssue],
    ) -> List[RemediationIssue]:
        """Sort issues by priority for fixing."""
        def priority(issue: RemediationIssue) -> tuple:
            # Higher confidence = higher priority
            # Higher severity = higher priority
            severity_order = {
                "critical": 0,
                "high": 1,
                "medium": 2,
                "low": 3,
            }
            return (
                severity_order.get(issue.severity.value, 10),
                -issue.fix_confidence,
            )
        
        return sorted(issues, key=priority)
    
    def _is_issue_fixed(
        self,
        issue: RemediationIssue,
        fixes: List[RemediationFix],
    ) -> bool:
        """Check if an issue has been fixed."""
        for fix in fixes:
            if fix.issue_id == issue.id and fix.status == FixStatus.APPLIED:
                return True
        return False
    
    async def _finalize_run(self, run: RemediationRun) -> RemediationRun:
        """Finalize a remediation run."""
        run.completed_at = datetime.utcnow()
        
        # Calculate stats
        run.fixes_applied = sum(1 for f in run.fixes if f.status == FixStatus.APPLIED)
        run.fixes_reverted = sum(1 for f in run.fixes if f.status == FixStatus.REVERTED)
        
        # Persist to database
        self._persist_run(run)
        
        await self._emit(RemediationEventType.RUN_COMPLETED, {
            "run_id": run.id,
            "status": run.status.value,
            "fixes_applied": run.fixes_applied,
            "fixes_reverted": run.fixes_reverted,
        })
        
        # Log audit
        self.safety.log_action(
            AuditAction.RUN_COMPLETED,
            {
                "status": run.status.value,
                "issues_count": len(run.issues),
                "fixes_applied": run.fixes_applied,
            },
            run.id,
        )
        
        return run
    
    async def _emit(self, event_type: RemediationEventType, data: Dict[str, Any]):
        """Emit a remediation event."""
        event = RemediationEvent(
            type=event_type,
            run_id=self._current_run.id if self._current_run else None,
            timestamp=datetime.utcnow(),
            data=data,
        )
        await self.events.emit_async(event)
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def _persist_run(self, run: RemediationRun):
        """Persist run to database."""
        if not self.db_path:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO remediation_runs
                   (id, verdict_id, status, started_at, completed_at,
                    iterations, fixes_applied, fixes_reverted, health_state, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.verdict_id,
                    run.status.value,
                    run.started_at.isoformat() if run.started_at else None,
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.iterations,
                    run.fixes_applied,
                    run.fixes_reverted,
                    run.health_state.value if run.health_state else None,
                    run.error,
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to persist run: {e}")
    
    def _persist_backup(self, run_id: str, file_path: str, content: str):
        """Persist file backup to database."""
        if not self.db_path:
            return
        
        try:
            import hashlib
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT INTO remediation_file_backups
                   (remediation_run_id, file_path, original_content, backup_hash, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, file_path, content, content_hash, datetime.utcnow().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to persist backup: {e}")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_engine(
    project_root: Path,
    config_dict: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> RemediationEngine:
    """Create a remediation engine from config dictionary."""
    config = RemediationConfig.from_dict(config_dict or {})
    return RemediationEngine(project_root, config, db_path, llm_client)


async def quick_remediate(
    project_root: Path,
    verdict: Dict[str, Any],
    **kwargs,
) -> RemediationRun:
    """Quick one-shot remediation."""
    engine = create_engine(project_root, **kwargs)
    return await engine.remediate(verdict)
