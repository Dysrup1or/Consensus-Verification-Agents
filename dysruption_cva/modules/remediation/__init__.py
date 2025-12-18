"""
Autonomous Remediation Agent

A fully autonomous system for detecting, diagnosing, and fixing code issues
discovered during CVA verification runs.

Components:
- models: Data models for issues, fixes, patterns
- detector: Issue extraction from tribunal verdicts
- safety: Safety controller with guardrails
- generator: LLM-based fix generation
- engine: Main orchestrator
"""

from .models import (
    RemediationIssue,
    RemediationFix,
    RemediationRun,
    FixPattern,
    IssueCategory,
    IssueSeverity,
    ApprovalLevel,
    FixStrategy,
    HealthState,
    RollbackScope,
    SandboxMode,
    RemediationStatus,
    FixStatus,
    AuditAction,
    RemediationEventType,
    PatchData,
    RootCause,
    AuditLogEntry,
    RemediationEvent,
)

from .safety import (
    SafetyController,
    BlastRadiusLimits,
    RateLimits,
    ApprovalThresholds,
    SafetyConfig,
    is_kill_switch_active,
    activate_kill_switch,
    deactivate_kill_switch,
    create_safety_controller_from_config,
    create_safety_controller_from_env,
)

from .detector import (
    IssueDetector,
    FileLocation,
    extract_file_location,
    extract_all_locations,
    CATEGORY_PATTERNS,
    AUTO_FIXABLE_CATEGORIES,
)

from .generator import (
    FixGenerator,
    PatchApplicator,
    ContextBuilder,
    FixContext,
)

from .engine import (
    RemediationEngine,
    RemediationConfig,
    EventEmitter,
    create_engine,
    quick_remediate,
)

__all__ = [
    # Enums
    "IssueCategory",
    "IssueSeverity",
    "ApprovalLevel",
    "FixStrategy",
    "HealthState",
    "RollbackScope",
    "SandboxMode",
    "RemediationStatus",
    "FixStatus",
    "AuditAction",
    "RemediationEventType",
    # Models
    "RemediationIssue",
    "RemediationFix",
    "RemediationRun",
    "FixPattern",
    "PatchData",
    "RootCause",
    "AuditLogEntry",
    "RemediationEvent",
    # Safety
    "SafetyController",
    "BlastRadiusLimits",
    "RateLimits",
    "ApprovalThresholds",
    "SafetyConfig",
    "is_kill_switch_active",
    "activate_kill_switch",
    "deactivate_kill_switch",
    "create_safety_controller_from_config",
    "create_safety_controller_from_env",
    # Detector
    "IssueDetector",
    "FileLocation",
    "extract_file_location",
    "extract_all_locations",
    "CATEGORY_PATTERNS",
    "AUTO_FIXABLE_CATEGORIES",
    # Generator
    "FixGenerator",
    "PatchApplicator",
    "ContextBuilder",
    "FixContext",
    # Engine
    "RemediationEngine",
    "RemediationConfig",
    "EventEmitter",
    "create_engine",
    "quick_remediate",
]
