"""
Safety Controller for Autonomous Remediation Agent

Implements guardrails to ensure safe autonomous operation:
- Kill switch (emergency stop)
- Rate limiting (fixes per time window)
- Blast radius control (limit scope of changes)
- Approval gateway (classify fix approval levels)
- Cooldown periods (after reverts)
"""

from __future__ import annotations

import fnmatch
import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .models import (
    ApprovalLevel,
    AuditAction,
    AuditLogEntry,
    IssueCategory,
    IssueSeverity,
    RemediationFix,
    RemediationIssue,
)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class BlastRadiusLimits:
    """Limits on the scope of autonomous changes."""
    max_files_per_run: int = 10
    max_lines_changed: int = 500
    max_functions_modified: int = 20
    max_patch_size_bytes: int = 50_000
    
    forbidden_paths: List[str] = field(default_factory=lambda: [
        "*.env",
        "*.env.*",
        "*.secret*",
        "**/credentials/**",
        "**/secrets/**",
        "**/config/prod*",
        "**/config/production*",
        "docker-compose.prod.yml",
        "docker-compose.production.yml",
        "**/deploy/**",
        "**/infrastructure/**",
        "**/.git/**",
        "**/node_modules/**",
        "**/__pycache__/**",
        "**/.venv/**",
        "**/venv/**",
    ])
    
    def is_path_forbidden(self, path: str) -> bool:
        """Check if a path matches any forbidden pattern."""
        normalized = path.replace("\\", "/")
        for pattern in self.forbidden_paths:
            if fnmatch.fnmatch(normalized, pattern):
                return True
            # Also check just the filename
            if fnmatch.fnmatch(Path(normalized).name, pattern):
                return True
        return False


@dataclass
class RateLimits:
    """Rate limiting configuration."""
    max_fixes_per_hour: int = 50
    max_fixes_per_day: int = 200
    max_reverts_before_lockout: int = 5
    cooldown_after_revert_minutes: int = 30


@dataclass
class ApprovalThresholds:
    """Thresholds for automatic approval."""
    auto_threshold: float = 0.9          # Above this = AUTO
    review_threshold: float = 0.7        # Above this = REVIEW
    confirm_threshold: float = 0.5       # Above this = CONFIRM
    # Below confirm_threshold = MANUAL
    
    security_requires_manual: bool = True
    breaking_changes_require_manual: bool = True


@dataclass
class SafetyConfig:
    """Complete safety configuration."""
    enabled: bool = True
    
    blast_radius: BlastRadiusLimits = field(default_factory=BlastRadiusLimits)
    rate_limits: RateLimits = field(default_factory=RateLimits)
    approval: ApprovalThresholds = field(default_factory=ApprovalThresholds)
    
    # Kill switch file path (alternative to DB)
    kill_switch_file: str = ".cva-remediation-stop"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SafetyConfig":
        """Create from dictionary (e.g., config.yaml section)."""
        config = cls()
        
        if "enabled" in data:
            config.enabled = bool(data["enabled"])
        
        if "blast_radius" in data:
            br = data["blast_radius"]
            config.blast_radius = BlastRadiusLimits(
                max_files_per_run=br.get("max_files_per_run", 10),
                max_lines_changed=br.get("max_lines_changed", 500),
                max_functions_modified=br.get("max_functions_modified", 20),
                max_patch_size_bytes=br.get("max_patch_size_bytes", 50_000),
                forbidden_paths=br.get("forbidden_paths", config.blast_radius.forbidden_paths),
            )
        
        if "rate_limits" in data:
            rl = data["rate_limits"]
            config.rate_limits = RateLimits(
                max_fixes_per_hour=rl.get("max_fixes_per_hour", 50),
                max_fixes_per_day=rl.get("max_fixes_per_day", 200),
                max_reverts_before_lockout=rl.get("max_reverts_before_lockout", 5),
                cooldown_after_revert_minutes=rl.get("cooldown_after_revert_minutes", 30),
            )
        
        if "approval" in data:
            ap = data["approval"]
            config.approval = ApprovalThresholds(
                auto_threshold=ap.get("auto_threshold", 0.9),
                review_threshold=ap.get("review_threshold", 0.7),
                confirm_threshold=ap.get("confirm_threshold", 0.5),
                security_requires_manual=ap.get("security_requires_manual", True),
                breaking_changes_require_manual=ap.get("breaking_changes_require_manual", True),
            )
        
        if "kill_switch_file" in data:
            config.kill_switch_file = data["kill_switch_file"]
        
        return config
    
    @classmethod
    def from_env(cls) -> "SafetyConfig":
        """Create from environment variables."""
        config = cls()
        
        if os.getenv("CVA_REMEDIATION_ENABLED") == "false":
            config.enabled = False
        
        # Blast radius
        if val := os.getenv("CVA_REMEDIATION_MAX_FILES"):
            config.blast_radius.max_files_per_run = int(val)
        
        if val := os.getenv("CVA_REMEDIATION_MAX_LINES"):
            config.blast_radius.max_lines_changed = int(val)
        
        if val := os.getenv("CVA_REMEDIATION_FORBIDDEN_PATHS"):
            config.blast_radius.forbidden_paths = val.split(",")
        
        # Rate limits
        if val := os.getenv("CVA_REMEDIATION_MAX_FIXES_PER_HOUR"):
            config.rate_limits.max_fixes_per_hour = int(val)
        
        if val := os.getenv("CVA_REMEDIATION_MAX_FIXES_PER_DAY"):
            config.rate_limits.max_fixes_per_day = int(val)
        
        # Approval
        if val := os.getenv("CVA_REMEDIATION_AUTO_APPROVE_THRESHOLD"):
            config.approval.auto_threshold = float(val)
        
        if os.getenv("CVA_REMEDIATION_SECURITY_REQUIRES_MANUAL") == "false":
            config.approval.security_requires_manual = False
        
        return config


# =============================================================================
# KILL SWITCH
# =============================================================================


def is_kill_switch_active(
    db_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Check if kill switch is active.
    
    Checks:
    1. Environment variable CVA_REMEDIATION_KILL_SWITCH
    2. File-based trigger (.cva-remediation-stop)
    3. Database state
    
    Returns:
        Tuple of (is_active, reason)
    """
    # 1. Environment variable
    if os.getenv("CVA_REMEDIATION_KILL_SWITCH", "").lower() == "true":
        return True, "Environment variable CVA_REMEDIATION_KILL_SWITCH=true"
    
    # 2. File-based trigger
    if project_root:
        stop_file = project_root / ".cva-remediation-stop"
        if stop_file.exists():
            reason = "Stop file exists"
            try:
                content = stop_file.read_text(encoding="utf-8").strip()
                if content:
                    reason = f"Stop file: {content}"
            except Exception:
                pass
            return True, reason
    
    # 3. Database state
    if db_path and Path(db_path).exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT active, reason FROM remediation_kill_switch WHERE id = 1"
            )
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0]:
                return True, row[1] or "Kill switch activated in database"
        except Exception as e:
            logger.warning(f"Failed to check kill switch in DB: {e}")
    
    return False, None


def activate_kill_switch(
    reason: str,
    activated_by: str = "system",
    db_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """
    Activate the kill switch.
    
    Returns:
        True if successfully activated
    """
    now = datetime.utcnow().isoformat()
    
    # File-based (most reliable)
    if project_root:
        try:
            stop_file = project_root / ".cva-remediation-stop"
            stop_file.write_text(f"{reason}\nActivated by: {activated_by}\nAt: {now}", encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to create stop file: {e}")
    
    # Database
    if db_path:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                """UPDATE remediation_kill_switch 
                   SET active = 1, activated_at = ?, activated_by = ?, reason = ?
                   WHERE id = 1""",
                (now, activated_by, reason)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to activate kill switch in DB: {e}")
    
    logger.warning(f"KILL SWITCH ACTIVATED: {reason} (by {activated_by})")
    return True


def deactivate_kill_switch(
    db_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """
    Deactivate the kill switch.
    
    Returns:
        True if successfully deactivated
    """
    # Remove file
    if project_root:
        try:
            stop_file = project_root / ".cva-remediation-stop"
            if stop_file.exists():
                stop_file.unlink()
        except Exception as e:
            logger.error(f"Failed to remove stop file: {e}")
    
    # Database
    if db_path:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                """UPDATE remediation_kill_switch 
                   SET active = 0, activated_at = NULL, activated_by = NULL, reason = NULL
                   WHERE id = 1"""
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to deactivate kill switch in DB: {e}")
    
    logger.info("Kill switch deactivated")
    return True


# =============================================================================
# SAFETY CONTROLLER
# =============================================================================


class SafetyController:
    """
    Central safety controller for autonomous remediation.
    
    Enforces:
    - Kill switch checking
    - Rate limiting
    - Blast radius limits
    - Approval level classification
    - Cooldown periods
    """
    
    def __init__(
        self,
        config: SafetyConfig,
        db_path: Optional[str] = None,
        project_root: Optional[Path] = None,
    ):
        self.config = config
        self.db_path = db_path
        self.project_root = project_root
        
        # In-memory counters (backup if DB unavailable)
        self._hourly_fixes = 0
        self._daily_fixes = 0
        self._recent_reverts = 0
        self._cooldown_until: Optional[datetime] = None
        self._hour_start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        self._day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # =========================================================================
    # KILL SWITCH
    # =========================================================================
    
    def check_kill_switch(self) -> Tuple[bool, Optional[str]]:
        """Check if kill switch is active."""
        return is_kill_switch_active(self.db_path, self.project_root)
    
    def activate_emergency_stop(self, reason: str, actor: str = "system") -> bool:
        """Activate emergency stop."""
        success = activate_kill_switch(reason, actor, self.db_path, self.project_root)
        if success:
            self._log_audit(AuditAction.KILL_SWITCH_ACTIVATED, {"reason": reason, "actor": actor})
        return success
    
    # =========================================================================
    # RATE LIMITING
    # =========================================================================
    
    def check_rate_limit(self) -> Tuple[bool, Optional[str]]:
        """
        Check if rate limit allows another fix.
        
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        now = datetime.utcnow()
        
        # Check cooldown
        if self._cooldown_until and now < self._cooldown_until:
            remaining = (self._cooldown_until - now).total_seconds() / 60
            return False, f"In cooldown period ({remaining:.1f} minutes remaining)"
        
        # Reset counters if window expired
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if current_hour > self._hour_start:
            self._hourly_fixes = 0
            self._hour_start = current_hour
        
        if current_day > self._day_start:
            self._daily_fixes = 0
            self._day_start = current_day
        
        # Check limits
        if self._hourly_fixes >= self.config.rate_limits.max_fixes_per_hour:
            return False, f"Hourly limit reached ({self.config.rate_limits.max_fixes_per_hour})"
        
        if self._daily_fixes >= self.config.rate_limits.max_fixes_per_day:
            return False, f"Daily limit reached ({self.config.rate_limits.max_fixes_per_day})"
        
        return True, None
    
    def record_fix_applied(self):
        """Record that a fix was applied."""
        self._hourly_fixes += 1
        self._daily_fixes += 1
        self._persist_rate_limit()
    
    def record_fix_reverted(self):
        """Record that a fix was reverted."""
        self._recent_reverts += 1
        
        if self._recent_reverts >= self.config.rate_limits.max_reverts_before_lockout:
            self._start_cooldown()
    
    def _start_cooldown(self):
        """Start cooldown period after too many reverts."""
        self._cooldown_until = datetime.utcnow() + timedelta(
            minutes=self.config.rate_limits.cooldown_after_revert_minutes
        )
        self._recent_reverts = 0
        
        self._log_audit(
            AuditAction.COOLDOWN_STARTED,
            {"until": self._cooldown_until.isoformat()}
        )
        
        logger.warning(
            f"Cooldown started until {self._cooldown_until.isoformat()} "
            f"after {self.config.rate_limits.max_reverts_before_lockout} reverts"
        )
    
    def _persist_rate_limit(self):
        """Persist rate limit state to database."""
        if not self.db_path:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            now = datetime.utcnow()
            
            # Upsert hourly
            hour_start = now.replace(minute=0, second=0, microsecond=0).isoformat()
            conn.execute(
                """INSERT INTO remediation_rate_limits 
                   (window_start, window_type, fixes_count, cooldown_until)
                   VALUES (?, 'hourly', 1, ?)
                   ON CONFLICT(window_start, window_type) DO UPDATE SET
                   fixes_count = fixes_count + 1,
                   cooldown_until = ?""",
                (hour_start, self._cooldown_until.isoformat() if self._cooldown_until else None,
                 self._cooldown_until.isoformat() if self._cooldown_until else None)
            )
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to persist rate limit: {e}")
    
    # =========================================================================
    # BLAST RADIUS
    # =========================================================================
    
    def check_blast_radius(
        self,
        files_to_modify: List[str],
        lines_changed: int = 0,
        patch_size_bytes: int = 0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if proposed changes are within blast radius limits.
        
        Returns:
            Tuple of (allowed, reason_if_denied)
        """
        br = self.config.blast_radius
        
        # Check file count
        if len(files_to_modify) > br.max_files_per_run:
            return False, f"Too many files ({len(files_to_modify)} > {br.max_files_per_run})"
        
        # Check lines changed
        if lines_changed > br.max_lines_changed:
            return False, f"Too many lines changed ({lines_changed} > {br.max_lines_changed})"
        
        # Check patch size
        if patch_size_bytes > br.max_patch_size_bytes:
            return False, f"Patch too large ({patch_size_bytes} > {br.max_patch_size_bytes} bytes)"
        
        # Check forbidden paths
        for file_path in files_to_modify:
            if br.is_path_forbidden(file_path):
                return False, f"Path is forbidden: {file_path}"
        
        return True, None
    
    def filter_forbidden_paths(self, paths: List[str]) -> Tuple[List[str], List[str]]:
        """
        Filter paths into allowed and forbidden.
        
        Returns:
            Tuple of (allowed_paths, forbidden_paths)
        """
        allowed = []
        forbidden = []
        
        for path in paths:
            if self.config.blast_radius.is_path_forbidden(path):
                forbidden.append(path)
            else:
                allowed.append(path)
        
        return allowed, forbidden
    
    # =========================================================================
    # APPROVAL GATEWAY
    # =========================================================================
    
    def classify_approval_level(
        self,
        issue: RemediationIssue,
        fix_confidence: float,
        is_breaking_change: bool = False,
    ) -> ApprovalLevel:
        """
        Classify the required approval level for a fix.
        
        Based on:
        - Issue category (security vs style)
        - Fix confidence score
        - Whether it's a breaking change
        """
        ap = self.config.approval
        
        # Security issues require manual if configured
        if issue.category == IssueCategory.SECURITY and ap.security_requires_manual:
            return ApprovalLevel.MANUAL
        
        # Breaking changes require manual if configured
        if is_breaking_change and ap.breaking_changes_require_manual:
            return ApprovalLevel.MANUAL
        
        # Critical severity gets extra scrutiny
        if issue.severity == IssueSeverity.CRITICAL:
            # Bump up one level
            if fix_confidence >= ap.auto_threshold:
                return ApprovalLevel.REVIEW
            elif fix_confidence >= ap.review_threshold:
                return ApprovalLevel.CONFIRM
            else:
                return ApprovalLevel.MANUAL
        
        # Standard classification by confidence
        if fix_confidence >= ap.auto_threshold:
            return ApprovalLevel.AUTO
        elif fix_confidence >= ap.review_threshold:
            return ApprovalLevel.REVIEW
        elif fix_confidence >= ap.confirm_threshold:
            return ApprovalLevel.CONFIRM
        else:
            return ApprovalLevel.MANUAL
    
    def can_auto_apply(self, fix: RemediationFix) -> bool:
        """Check if a fix can be auto-applied without user interaction."""
        return fix.approval_level in (ApprovalLevel.AUTO, ApprovalLevel.REVIEW)
    
    # =========================================================================
    # PRE-FLIGHT CHECK
    # =========================================================================
    
    def pre_flight_check(
        self,
        files_to_modify: Optional[List[str]] = None,
        lines_changed: int = 0,
    ) -> Tuple[bool, List[str]]:
        """
        Run all safety checks before starting remediation.
        
        Returns:
            Tuple of (all_passed, list_of_issues)
        """
        issues = []
        
        # 1. Kill switch
        kill_active, kill_reason = self.check_kill_switch()
        if kill_active:
            issues.append(f"Kill switch active: {kill_reason}")
        
        # 2. Rate limit
        rate_ok, rate_reason = self.check_rate_limit()
        if not rate_ok:
            issues.append(f"Rate limit: {rate_reason}")
        
        # 3. Blast radius (if paths provided)
        if files_to_modify:
            blast_ok, blast_reason = self.check_blast_radius(
                files_to_modify, lines_changed
            )
            if not blast_ok:
                issues.append(f"Blast radius: {blast_reason}")
        
        return len(issues) == 0, issues
    
    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================
    
    def _log_audit(
        self,
        action: AuditAction,
        details: Optional[Dict[str, Any]] = None,
        remediation_run_id: Optional[str] = None,
        actor: str = "system",
    ):
        """Log an audit entry."""
        if not self.db_path:
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT INTO remediation_audit_log 
                   (timestamp, remediation_run_id, action, details, actor)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.utcnow().isoformat(),
                    remediation_run_id,
                    action.value,
                    json.dumps(details) if details else None,
                    actor,
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to log audit entry: {e}")
    
    def log_action(
        self,
        action: AuditAction,
        details: Optional[Dict[str, Any]] = None,
        remediation_run_id: Optional[str] = None,
        actor: str = "agent",
    ):
        """Public method to log an action."""
        self._log_audit(action, details, remediation_run_id, actor)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_safety_controller_from_config(
    config_dict: Dict[str, Any],
    db_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> SafetyController:
    """Create a safety controller from config dictionary."""
    safety_config = SafetyConfig.from_dict(config_dict.get("safety", {}))
    return SafetyController(safety_config, db_path, project_root)


def create_safety_controller_from_env(
    db_path: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> SafetyController:
    """Create a safety controller from environment variables."""
    safety_config = SafetyConfig.from_env()
    return SafetyController(safety_config, db_path, project_root)
