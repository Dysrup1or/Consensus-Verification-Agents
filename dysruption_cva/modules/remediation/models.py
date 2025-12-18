"""
Data Models for Autonomous Remediation Agent

Defines Pydantic models and enums for:
- Issue detection and classification
- Fix generation and application
- Pattern learning
- Run tracking
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class IssueCategory(str, Enum):
    """Category of detected issue."""
    TYPE_ERROR = "type_error"
    RUNTIME_ERROR = "runtime_error"
    TEST_FAILURE = "test_failure"
    LINT_ERROR = "lint_error"
    SECURITY = "security"
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    LOGIC_ERROR = "logic_error"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    UNKNOWN = "unknown"


class IssueSeverity(str, Enum):
    """Severity level of detected issue."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ApprovalLevel(str, Enum):
    """Required approval level for a fix."""
    AUTO = "auto"           # No approval needed, apply immediately
    REVIEW = "review"       # Logged but auto-applied
    CONFIRM = "confirm"     # Requires explicit confirmation
    MANUAL = "manual"       # Human must apply manually


class FixStrategy(str, Enum):
    """Strategy for applying fixes."""
    DIRECT_PATCH = "direct_patch"       # Simple code replacement
    REFACTOR = "refactor"               # Larger code restructuring
    ADD_DEPENDENCY = "add_dependency"   # Add missing imports/packages
    CONFIGURATION = "configuration"     # Config file changes
    ROLLBACK = "rollback"               # Revert to previous state
    MULTI_FILE = "multi_file"           # Coordinated changes across files
    STAGED = "staged"                   # Apply incrementally


class HealthState(str, Enum):
    """Health state after fix application."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"       # Some issues but functional
    UNHEALTHY = "unhealthy"     # Requires rollback
    UNKNOWN = "unknown"         # Cannot determine


class RollbackScope(str, Enum):
    """Scope of rollback operation."""
    PATCH = "patch"             # Single patch
    ITERATION = "iteration"     # All patches in iteration
    RUN = "run"                 # Entire remediation run
    SESSION = "session"         # All runs in session


class SandboxMode(str, Enum):
    """Mode for sandbox validation."""
    MEMORY = "memory"           # Virtual filesystem (in-memory)
    TEMP_DIR = "temp"           # Copy to temp directory
    DOCKER = "docker"           # Isolated container
    GIT_WORKTREE = "worktree"   # Git worktree isolation


class RemediationStatus(str, Enum):
    """Status of a remediation run."""
    PENDING = "pending"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    ABORTED = "aborted"
    ROLLED_BACK = "rolled_back"


class FixStatus(str, Enum):
    """Status of an individual fix."""
    PENDING = "pending"
    GENERATING = "generating"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    APPLYING = "applying"
    APPLIED = "applied"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"
    REVERTED = "reverted"


# =============================================================================
# ISSUE MODELS
# =============================================================================


class RemediationIssue(BaseModel):
    """
    An issue detected from tribunal verdict that may be auto-fixable.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    remediation_run_id: Optional[str] = None
    
    # Classification
    category: IssueCategory
    severity: IssueSeverity
    
    # Location
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    
    # Description
    message: str = ""
    raw_output: str = ""
    criterion_id: Optional[str] = None
    
    # Auto-fix assessment
    auto_fixable: bool = False
    fix_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Root cause (set by root cause analyzer)
    root_cause_id: Optional[str] = None
    is_symptom: bool = False
    
    # Timestamps
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "remediation_run_id": self.remediation_run_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "message": self.message,
            "auto_fixable": 1 if self.auto_fixable else 0,
            "fix_confidence": self.fix_confidence,
            "root_cause_id": self.root_cause_id,
            "detected_at": self.detected_at.isoformat(),
        }


class RootCause(BaseModel):
    """
    Root cause analysis result linking related issues.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Primary issue
    primary_issue_id: str
    description: str = ""
    
    # Related symptoms
    symptom_issue_ids: List[str] = Field(default_factory=list)
    
    # Affected scope
    affected_files: List[str] = Field(default_factory=list)
    
    # Fix order recommendation
    fix_order: List[str] = Field(default_factory=list)  # Issue IDs in order
    
    # Analysis metadata
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    analysis_method: str = "pattern_match"  # pattern_match, dependency_chain, llm


# =============================================================================
# FIX MODELS
# =============================================================================


class PatchData(BaseModel):
    """
    A single patch to apply to a file.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str
    
    # Diff
    diff: str = ""
    
    # Content (for direct application)
    original_content: str = ""
    patched_content: str = ""
    
    # Location hints
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class RemediationFix(BaseModel):
    """
    A generated fix for an issue.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    issue_id: str
    remediation_run_id: Optional[str] = None
    root_cause_id: Optional[str] = None
    
    # Generation metadata
    iteration: int = 1
    strategy: FixStrategy = FixStrategy.DIRECT_PATCH
    
    # Approval
    approval_level: ApprovalLevel = ApprovalLevel.CONFIRM
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    # The actual fix
    patches: List[PatchData] = Field(default_factory=list)
    
    # Confidence and metadata
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_review: bool = True
    breaking_change: bool = False
    
    # LLM generation info
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
    generation_time_ms: Optional[int] = None
    
    # Validation
    sandbox_result: Optional[str] = None  # pass, fail, error
    sandbox_output: Optional[str] = None
    
    # Application status
    status: FixStatus = FixStatus.PENDING
    applied_at: Optional[datetime] = None
    
    # Verification
    verified: bool = False
    verification_result: Optional[str] = None
    verification_output: Optional[str] = None
    
    # Rollback
    reverted: bool = False
    reverted_at: Optional[datetime] = None
    revert_reason: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        import json
        return {
            "id": self.id,
            "issue_id": self.issue_id,
            "iteration": self.iteration,
            "strategy": self.strategy.value,
            "approval_level": self.approval_level.value,
            "patch_content": json.dumps([p.model_dump() for p in self.patches]),
            "sandbox_result": self.sandbox_result,
            "applied": 1 if self.status in (FixStatus.APPLIED, FixStatus.VERIFIED) else 0,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "verified": 1 if self.verified else 0,
            "verification_result": self.verification_result,
            "reverted": 1 if self.reverted else 0,
            "reverted_at": self.reverted_at.isoformat() if self.reverted_at else None,
            "revert_reason": self.revert_reason,
            "confidence": self.confidence,
            "llm_model": self.llm_model,
            "llm_tokens_used": self.llm_tokens_used,
            "generation_time_ms": self.generation_time_ms,
        }


# =============================================================================
# RUN MODELS
# =============================================================================


class RemediationRun(BaseModel):
    """
    A remediation run tracking all issues and fixes for a verification run.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    verdict_id: Optional[str] = None  # Reference to tribunal verdict
    
    # Status
    status: RemediationStatus = RemediationStatus.PENDING
    
    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Statistics
    iterations: int = 0
    fixes_applied: int = 0
    fixes_reverted: int = 0
    
    # Health
    health_state: Optional[HealthState] = None
    
    # Error info
    error: Optional[str] = None
    
    # Collections (populated during run)
    issues: List[RemediationIssue] = Field(default_factory=list)
    fixes: List[RemediationFix] = Field(default_factory=list)
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "verdict_id": self.verdict_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "iterations": self.iterations,
            "fixes_applied": self.fixes_applied,
            "fixes_reverted": self.fixes_reverted,
            "health_state": self.health_state.value if self.health_state else None,
            "error": self.error,
        }


# =============================================================================
# PATTERN MODELS
# =============================================================================


class FixPattern(BaseModel):
    """
    A learned pattern for fixing a type of issue.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Pattern identification
    issue_signature: str  # Hash of issue characteristics
    category: IssueCategory
    
    # Pattern content
    fix_template: str  # Generalized fix approach
    example_diff: Optional[str] = None
    
    # Statistics
    success_count: int = 0
    failure_count: int = 0
    avg_confidence: float = 0.5
    
    # Timestamps
    last_used: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "issue_signature": self.issue_signature,
            "fix_template": self.fix_template,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_confidence": self.avg_confidence,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# =============================================================================
# AUDIT MODELS
# =============================================================================


class AuditAction(str, Enum):
    """Types of audit log actions."""
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_ABORTED = "run_aborted"
    ISSUE_DETECTED = "issue_detected"
    FIX_GENERATED = "fix_generated"
    FIX_APPROVED = "fix_approved"
    FIX_REJECTED = "fix_rejected"
    FIX_APPLIED = "fix_applied"
    FIX_VERIFIED = "fix_verified"
    FIX_REVERTED = "fix_reverted"
    ROLLBACK_INITIATED = "rollback_initiated"
    ROLLBACK_COMPLETED = "rollback_completed"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    KILL_SWITCH_DEACTIVATED = "kill_switch_deactivated"
    RATE_LIMIT_HIT = "rate_limit_hit"
    COOLDOWN_STARTED = "cooldown_started"


class AuditLogEntry(BaseModel):
    """
    An immutable audit log entry.
    """
    id: Optional[int] = None  # Auto-increment in DB
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    remediation_run_id: Optional[str] = None
    action: AuditAction
    details: Optional[str] = None  # JSON string with additional info
    actor: str = "agent"  # agent, user, system


# =============================================================================
# EVENT MODELS (for WebSocket)
# =============================================================================


class RemediationEventType(str, Enum):
    """Types of WebSocket events."""
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    DETECTING_ISSUES = "detecting_issues"
    ISSUES_DETECTED = "issues_detected"
    NO_ISSUES = "no_issues"
    ANALYZING_ROOT_CAUSES = "analyzing_root_causes"
    ROOT_CAUSES_IDENTIFIED = "root_causes_identified"
    ITERATION_STARTED = "iteration_started"
    GENERATING_FIX = "generating_fix"
    FIX_GENERATED = "fix_generated"
    FIX_PENDING_APPROVAL = "fix_pending_approval"
    APPLYING_FIX = "applying_fix"
    FIX_APPLIED = "fix_applied"
    FIX_BLOCKED = "fix_blocked"
    FIX_FAILED = "fix_failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    HEALTH_CHECKING = "health_checking"
    HEALTH_CHECKED = "health_checked"
    SAFETY_BLOCKED = "safety_blocked"
    KILL_SWITCH = "kill_switch"
    ERROR = "error"


class RemediationEvent(BaseModel):
    """
    WebSocket event for remediation updates.
    """
    type: RemediationEventType
    run_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(default_factory=dict)

