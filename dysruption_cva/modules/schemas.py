"""
Dysruption CVA - Core Data Structures (Pydantic Schemas)
Version: 1.1

Defines all data models used throughout the CVA pipeline:
- FileNode: Represents a file in the codebase
- Invariant: A requirement extracted from spec.txt with category/severity
- JudgeVerdict: Individual judge's assessment
- ConsensusResult: Final tribunal verdict with veto logic
- Patch: Unified diff fix suggestion
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Phase 2: shared contract models (optional dependency)
try:
    from catalyze_contract import (
        Initiator as ContractInitiator,
        SuccessSpec as ContractSuccessSpec,
        IntentEnvelope as ContractIntentEnvelope,
        TriggerScanMode as ContractTriggerScanMode,
        TriggerScanRequest as ContractTriggerScanRequest,
        TriggerScanResponse as ContractTriggerScanResponse,
        TribunalSeverity as ContractTribunalSeverity,
        TribunalVerdictType as ContractTribunalVerdictType,
        TribunalVerdictItem as ContractTribunalVerdictItem,
        TribunalMetrics as ContractTribunalMetrics,
        VerdictStatus as ContractVerdictStatus,
        VerdictResponse as ContractVerdictResponse,
    )
except Exception:
    ContractInitiator = None
    ContractSuccessSpec = None
    ContractIntentEnvelope = None
    ContractTriggerScanMode = None
    ContractTriggerScanRequest = None
    ContractTriggerScanResponse = None
    ContractTribunalSeverity = None
    ContractTribunalVerdictType = None
    ContractVerdictStatus = None
    ContractVerdictResponse = None
    ContractTribunalVerdictItem = None
    ContractTribunalMetrics = None


# =============================================================================
# ENUMS
# =============================================================================


class InvariantCategory(str, Enum):
    """Category of an extracted invariant requirement."""

    SECURITY = "security"
    FUNCTIONALITY = "functionality"
    STYLE = "style"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    DOCUMENTATION = "documentation"


class InvariantSeverity(str, Enum):
    """Severity level of an invariant requirement."""

    CRITICAL = "critical"  # Must pass, failure = veto
    HIGH = "high"  # Strong weight in scoring
    MEDIUM = "medium"  # Standard weight
    LOW = "low"  # Minor, advisory


class VerdictStatus(str, Enum):
    """Status of a judge's verdict."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    ERROR = "error"
    SKIPPED = "skipped"
    VETO = "veto"  # Security veto triggered


class JudgeRole(str, Enum):
    """Role/perspective of a tribunal judge."""

    ARCHITECT = "architect"  # Architecture, logic, design patterns
    SECURITY = "security"  # Vulnerabilities, data exposure, auth
    USER_PROXY = "user_proxy"  # User intent alignment, UX


class PipelineStatus(str, Enum):
    """Current status of the CVA pipeline."""

    IDLE = "idle"
    WATCHING = "watching"
    SCANNING = "scanning"
    PARSING = "parsing"
    STATIC_ANALYSIS = "static_analysis"
    JUDGING = "judging"
    PATCHING = "patching"
    COMPLETE = "complete"
    ERROR = "error"


# =============================================================================
# TRIBUNAL API (Constitution + Intent + Verdicts)
# =============================================================================


if ContractTribunalVerdictType is not None:
    TribunalVerdictType = ContractTribunalVerdictType  # type: ignore
else:
    class TribunalVerdictType(str, Enum):
        CONSTITUTION = "constitution"
        INTENT = "intent"


if ContractTribunalSeverity is not None:
    TribunalSeverity = ContractTribunalSeverity  # type: ignore
else:
    class TribunalSeverity(str, Enum):
        CRITICAL = "critical"
        HIGH = "high"
        MEDIUM = "medium"
        LOW = "low"


class ConstitutionInfo(BaseModel):
    path: str
    commit_hash: Optional[str] = None
    snippet_length: int = Field(..., ge=0)


class ConstitutionHistoryItem(BaseModel):
    commit_hash: str
    author: Optional[str] = None
    authored_at: Optional[str] = None
    subject: Optional[str] = None


if ContractInitiator is not None:
    Initiator = ContractInitiator  # type: ignore
else:
    class Initiator(BaseModel):
        # Assumption required by spec: initiator must provide a callback target.
        callback_url: str = Field(..., min_length=8)
        # Optional bearer token forwarded to callback.
        callback_bearer_token: Optional[str] = None


if ContractSuccessSpec is not None:
    SuccessSpec = ContractSuccessSpec  # type: ignore
else:
    class SuccessSpec(BaseModel):
        # Backward-compatible schema for intent preservation.
        #
        # Catalyze (Promptly) fields:
        intent_summary: Optional[str] = Field(default=None, max_length=2000)
        key_constraints: List[str] = Field(default_factory=list)
        expected_behavior: Optional[str] = Field(default=None, max_length=2000)

        # Legacy/minimal contract fields (kept for existing clients):
        acceptance_criteria: List[str] = Field(default_factory=list)
        notes: Optional[str] = Field(default=None, max_length=4000)

        @field_validator("key_constraints", "acceptance_criteria")
        @classmethod
        def _limit_list_sizes(cls, v: List[str]) -> List[str]:
            # Defensive cap: avoid unbounded lists causing prompt/context bloat.
            if not v:
                return []
            return [str(x)[:500] for x in v[:50]]


if ContractIntentEnvelope is not None:
    IntentEnvelope = ContractIntentEnvelope  # type: ignore
else:
    class IntentEnvelope(BaseModel):
        run_id: UUID
        project_id: str = Field(..., min_length=1, max_length=128)
        initiator: Optional[Initiator] = None
        commit_hash: Optional[str] = Field(default=None, max_length=64)
        success_spec: SuccessSpec


if ContractTriggerScanMode is not None:
    TriggerScanMode = ContractTriggerScanMode  # type: ignore
else:
    class TriggerScanMode(str, Enum):
        DIFF = "diff"
        FULL = "full"


if ContractTriggerScanRequest is not None:
    TriggerScanRequest = ContractTriggerScanRequest  # type: ignore
else:
    class TriggerScanRequest(BaseModel):
        run_id: UUID
        mode: TriggerScanMode = TriggerScanMode.DIFF


if ContractTribunalVerdictItem is not None:
    TribunalVerdictItem = ContractTribunalVerdictItem  # type: ignore
else:
    class TribunalVerdictItem(BaseModel):
        id: str
        type: TribunalVerdictType
        rule_id: str
        severity: TribunalSeverity
        file: Optional[str] = None
        line_start: int = Field(..., ge=1)
        line_end: int = Field(..., ge=1)
        message: str
        suggested_fix: Optional[str] = None
        auto_fixable: bool = False
        confidence: float = Field(..., ge=0.0, le=1.0)


if ContractTribunalMetrics is not None:
    TribunalMetrics = ContractTribunalMetrics  # type: ignore
else:
    class TribunalMetrics(BaseModel):
        scan_time_ms: int = Field(..., ge=0)
        token_count: int = Field(..., ge=0)
        llm_latency_ms: Optional[int] = Field(default=None, ge=0)
        violations_count: int = Field(..., ge=0)


if ContractTriggerScanResponse is not None:
    TriggerScanResponse = ContractTriggerScanResponse  # type: ignore
else:
    class TriggerScanResponse(BaseModel):
        run_id: UUID
        status: str
        verdicts_url: str
        partial: bool = False
        skipped_imports: List[str] = Field(default_factory=list)
        unevaluated_rules: List[str] = Field(default_factory=list)
        metrics: TribunalMetrics


# =============================================================================
# TRIBUNAL TELEMETRY (Phase 0)
# =============================================================================


class TelemetryCoverage(BaseModel):
    included_files_count: int = Field(..., ge=0)
    header_covered_count: int = Field(..., ge=0)
    full_text_covered_count: int = Field(..., ge=0)
    slice_covered_count: int = Field(..., ge=0)
    truncated_files: List[str] = Field(default_factory=list)
    unknown_files: List[str] = Field(default_factory=list)

    changed_files_total: int = Field(..., ge=0)
    changed_files_fully_covered_count: int = Field(..., ge=0)
    changed_files_header_covered_count: int = Field(..., ge=0)
    changed_files_unknown_count: int = Field(..., ge=0)
    fully_covered_percent_of_changed: float = Field(..., ge=0.0, le=100.0)

    # Phase 2: explicit forced-file mechanism (rollup).
    forced_files_count: int = Field(default=0, ge=0)

    # Explicit mapping of skipped/not-fully-covered reasons.
    # Keys should be repo-relative paths; values are reason codes.
    skip_reasons: Dict[str, str] = Field(default_factory=dict)


class TelemetryCost(BaseModel):
    lane1_deterministic_tokens: int = Field(..., ge=0)
    lane2_llm_input_tokens_est: int = Field(..., ge=0)
    lane2_llm_stable_prefix_tokens_est: int = Field(..., ge=0)
    lane2_llm_variable_suffix_tokens_est: int = Field(..., ge=0)


class TelemetryCache(BaseModel):
    cached_vs_uncached: str = Field(..., description="unknown|cached|uncached")
    reason: Optional[str] = None
    # Phase 5: provider cost primitives (best-effort; may remain unknown).
    intent: Optional[str] = Field(default=None, description="e.g. stable_prefix_split")
    provider_cache_signal: Optional[str] = Field(default=None, description="provider-reported cache signal if available")


class TelemetryLatency(BaseModel):
    run_started_at: str
    run_final_at: str
    ttff_ms: int = Field(..., ge=0)
    time_to_final_ms: int = Field(..., ge=0)
    # Optional sub-step timings (best-effort)
    diff_detection_ms: Optional[int] = Field(default=None, ge=0)
    import_resolution_ms: Optional[int] = Field(default=None, ge=0)
    context_build_ms: Optional[int] = Field(default=None, ge=0)
    llm_latency_ms: Optional[int] = Field(default=None, ge=0)

    # Phase 5: batch primitive rollups (lane2). Optional because most runs are single-call.
    lane2_llm_batch_size: Optional[int] = Field(default=None, ge=0)
    lane2_llm_batch_mode: Optional[str] = Field(default=None, description="single|concurrent|provider_batch|sequential")
    lane2_llm_per_item_latency_ms: Optional[List[int]] = Field(default=None)


class TelemetrySkipped(BaseModel):
    skipped_imports: List[str] = Field(default_factory=list)


class TelemetryRouter(BaseModel):
    lane_requested: str
    lane_used: str
    provider: str
    model: str
    reason: str
    fallback_chain: List[Dict[str, str]] = Field(default_factory=list)


class RunTelemetry(BaseModel):
    run_id: str
    project_id: str
    mode: str
    coverage: TelemetryCoverage
    cost: TelemetryCost
    cache: TelemetryCache
    latency: TelemetryLatency
    skipped: TelemetrySkipped
    router: Optional[TelemetryRouter] = None
    error: Optional[str] = None


# =============================================================================
# FILE TREE MODELS
# =============================================================================


class FileMetadata(BaseModel):
    """Metadata about a source file."""

    path: str = Field(..., description="Relative path from project root")
    absolute_path: str = Field(..., description="Absolute filesystem path")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    lines: int = Field(..., ge=0, description="Number of lines")
    language: str = Field(..., description="Detected programming language")
    last_modified: datetime = Field(..., description="Last modification timestamp")
    hash: str = Field(..., description="SHA256 hash of file contents")
    is_dirty: bool = Field(default=False, description="Changed since last scan")


class FileNode(BaseModel):
    """
    Represents a single file in the codebase with content and metadata.

    Used to build the file tree that gets passed to tribunal judges.
    """

    metadata: FileMetadata = Field(..., description="File metadata")
    content: str = Field(..., description="Full file content as string")
    syntax_valid: bool = Field(default=True, description="Whether file has valid syntax")
    static_issues: List[Dict[str, Any]] = Field(
        default_factory=list, description="Issues from pylint/bandit"
    )

    @property
    def path(self) -> str:
        """Convenience accessor for relative path."""
        return self.metadata.path

    @property
    def is_python(self) -> bool:
        """Check if this is a Python file."""
        return self.metadata.language.lower() == "python"


class FileTree(BaseModel):
    """
    Complete file tree of the scanned project.

    Output of the Watcher module, input to Parser and Tribunal.
    """

    root_path: str = Field(..., description="Absolute path to project root")
    scan_timestamp: datetime = Field(
        default_factory=datetime.now, description="When scan was performed"
    )
    files: Dict[str, FileNode] = Field(
        default_factory=dict, description="Map of relative path to FileNode"
    )
    dirty_files: List[str] = Field(
        default_factory=list, description="Files changed since last scan"
    )
    total_lines: int = Field(default=0, description="Total lines across all files")
    languages: Dict[str, int] = Field(
        default_factory=dict, description="Language distribution (lang -> file count)"
    )

    def get_dirty_nodes(self) -> List[FileNode]:
        """Get only the files that changed since last scan."""
        return [self.files[path] for path in self.dirty_files if path in self.files]


# =============================================================================
# INVARIANT MODELS
# =============================================================================


class Invariant(BaseModel):
    """
    A single extracted requirement/invariant from the specification.

    Invariants are categorized by type (security, functionality, style)
    and severity to enable weighted scoring and veto logic.
    """

    id: int = Field(..., ge=1, description="Unique invariant ID")
    description: str = Field(..., min_length=5, description="What this requirement specifies")
    category: InvariantCategory = Field(..., description="Category of requirement")
    severity: InvariantSeverity = Field(
        default=InvariantSeverity.MEDIUM, description="Severity level"
    )
    keywords: List[str] = Field(
        default_factory=list, description="Keywords for relevance matching"
    )
    source_line: Optional[str] = Field(
        default=None, description="Original line from spec.txt"
    )

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        """Ensure description is meaningful."""
        if not v.strip():
            raise ValueError("Description cannot be empty or whitespace")
        return v.strip()


class InvariantSet(BaseModel):
    """
    Complete set of extracted invariants with category coverage tracking.

    Ensures all three required categories are represented.
    """

    invariants: List[Invariant] = Field(default_factory=list)
    extraction_timestamp: datetime = Field(default_factory=datetime.now)
    spec_hash: str = Field(..., description="Hash of source spec.txt")
    categories_covered: Dict[str, int] = Field(
        default_factory=dict, description="Count per category"
    )

    def has_required_categories(self) -> bool:
        """Check if Security, Functionality, and Style are all covered."""
        required = {
            InvariantCategory.SECURITY,
            InvariantCategory.FUNCTIONALITY,
            InvariantCategory.STYLE,
        }
        covered = {
            InvariantCategory(cat)
            for cat, count in self.categories_covered.items()
            if count > 0
        }
        return required.issubset(covered)

    def missing_categories(self) -> List[InvariantCategory]:
        """Return list of required categories with zero coverage."""
        required = [
            InvariantCategory.SECURITY,
            InvariantCategory.FUNCTIONALITY,
            InvariantCategory.STYLE,
        ]
        return [
            cat
            for cat in required
            if self.categories_covered.get(cat.value, 0) == 0
        ]

    def by_category(self, category: InvariantCategory) -> List[Invariant]:
        """Get all invariants of a specific category."""
        return [inv for inv in self.invariants if inv.category == category]


# =============================================================================
# JUDGE VERDICT MODELS
# =============================================================================


class IssueDetail(BaseModel):
    """A specific issue identified by a judge."""

    description: str = Field(..., description="What the issue is")
    file_path: Optional[str] = Field(default=None, description="Affected file")
    line_number: Optional[int] = Field(default=None, ge=1, description="Line number")
    suggestion: Optional[str] = Field(default=None, description="How to fix")
    invariant_id: Optional[int] = Field(
        default=None, description="Related invariant ID"
    )


class JudgeVerdict(BaseModel):
    """
    Individual verdict from a single tribunal judge.

    Each judge evaluates code against invariants from their perspective
    (architecture, security, user intent) and provides a scored assessment.
    """

    judge_role: JudgeRole = Field(..., description="Which judge rendered this verdict")
    model_used: str = Field(..., description="LLM model identifier used")
    status: VerdictStatus = Field(..., description="Overall pass/fail status")
    score: float = Field(..., ge=0.0, le=10.0, description="Score out of 10")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Judge's confidence")
    explanation: str = Field(..., description="Detailed reasoning")
    issues: List[IssueDetail] = Field(
        default_factory=list, description="Specific issues found"
    )
    suggestions: List[str] = Field(
        default_factory=list, description="Improvement suggestions"
    )
    invariants_checked: List[int] = Field(
        default_factory=list, description="IDs of invariants evaluated"
    )
    execution_time_ms: int = Field(..., ge=0, description="Time to render verdict")

    @property
    def is_pass(self) -> bool:
        """Check if verdict is passing."""
        return self.status == VerdictStatus.PASS

    @property
    def is_veto_eligible(self) -> bool:
        """Check if this verdict can trigger a veto (Security with high confidence FAIL)."""
        return (
            self.judge_role == JudgeRole.SECURITY
            and self.status == VerdictStatus.FAIL
            and self.confidence > 0.8
        )


# =============================================================================
# CONSENSUS RESULT MODELS
# =============================================================================


class StaticAnalysisResult(BaseModel):
    """Results from pylint/bandit static analysis."""

    tool: str = Field(..., description="Tool name (pylint/bandit)")
    passed: bool = Field(..., description="Whether check passed")
    critical_issues: int = Field(default=0, ge=0, description="Critical issue count")
    total_issues: int = Field(default=0, ge=0, description="Total issue count")
    issues: List[Dict[str, Any]] = Field(
        default_factory=list, description="Detailed issues"
    )
    execution_time_ms: int = Field(default=0, ge=0)
    aborted_pipeline: bool = Field(
        default=False, description="Whether this caused fail-fast abort"
    )


class ConsensusResult(BaseModel):
    """
    Final tribunal verdict combining all judge opinions.

    Implements the Veto Protocol: If the Security Judge votes FAIL with
    confidence > 0.8, the final verdict is FAIL regardless of other votes.
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    overall_status: VerdictStatus = Field(..., description="Final consensus status")
    weighted_score: float = Field(..., ge=0.0, le=10.0, description="Weighted score")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Consensus confidence")

    # Individual verdicts
    verdicts: Dict[str, JudgeVerdict] = Field(
        ..., description="Map of judge role to verdict"
    )

    # Veto logic
    veto_triggered: bool = Field(
        default=False,
        description="True if Security Judge vetoed with high confidence",
    )
    veto_reason: Optional[str] = Field(
        default=None, description="Explanation if veto was triggered"
    )

    # Static analysis
    static_analysis: List[StaticAnalysisResult] = Field(
        default_factory=list, description="Pylint/bandit results"
    )
    static_analysis_aborted: bool = Field(
        default=False, description="Whether static analysis caused abort"
    )

    # Metadata
    total_invariants: int = Field(default=0, ge=0)
    invariants_passed: int = Field(default=0, ge=0)
    execution_time_ms: int = Field(default=0, ge=0)
    files_analyzed: int = Field(default=0, ge=0)

    @property
    def pass_rate(self) -> float:
        """Calculate invariant pass rate."""
        if self.total_invariants == 0:
            return 0.0
        return self.invariants_passed / self.total_invariants

    @property
    def is_passing(self) -> bool:
        """Check if final verdict is passing (considers veto)."""
        if self.veto_triggered:
            return False
        return self.overall_status == VerdictStatus.PASS


# =============================================================================
# PATCH MODELS
# =============================================================================


class Patch(BaseModel):
    """
    A unified diff patch generated to fix identified issues.

    Generated by the patcher (gpt-4o-mini) when the tribunal fails.
    """

    file_path: str = Field(..., description="File to patch")
    original_content: str = Field(..., description="Original file content")
    patched_content: str = Field(..., description="Content after applying patch")
    unified_diff: str = Field(..., description="Unified diff format")
    issues_addressed: List[int] = Field(
        default_factory=list, description="Invariant IDs this patch addresses"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in fix correctness"
    )
    requires_review: bool = Field(
        default=True, description="Whether human review is recommended"
    )
    generated_by: str = Field(default="gpt-4o-mini", description="Model that generated")
    generation_time_ms: int = Field(default=0, ge=0)


class PatchSet(BaseModel):
    """Collection of patches for a failed verification run."""

    patches: List[Patch] = Field(default_factory=list)
    total_issues_addressed: int = Field(default=0, ge=0)
    generation_timestamp: datetime = Field(default_factory=datetime.now)
    estimated_fix_coverage: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Proportion of issues with patches"
    )


# =============================================================================
# PIPELINE STATUS MODELS
# =============================================================================


class PipelineState(BaseModel):
    """Current state of the CVA verification pipeline."""

    status: PipelineStatus = Field(default=PipelineStatus.IDLE)
    current_phase: str = Field(default="idle")
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    message: str = Field(default="")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    # Phase results (populated as pipeline progresses)
    file_tree: Optional[FileTree] = None
    invariants: Optional[InvariantSet] = None
    consensus: Optional[ConsensusResult] = None
    patches: Optional[PatchSet] = None


class RunConfig(BaseModel):
    """Configuration for a verification run."""

    target_dir: str = Field(..., description="Directory to verify")
    spec_path: str = Field(default="spec.txt", description="Path to spec file")
    spec_content: Optional[str] = Field(default=None, description="Constitution text content (overrides spec_path)")
    config_path: str = Field(default="config.yaml", description="Path to config")
    generate_patches: bool = Field(
        default=True, description="Generate fix patches on failure"
    )
    fail_fast: bool = Field(
        default=True, description="Abort on critical static analysis issues"
    )
    watch_mode: bool = Field(default=False, description="Enable file watching")
    debounce_seconds: float = Field(
        default=3.0, ge=0.5, le=30.0, description="Debounce delay for watch mode"
    )


# =============================================================================
# API MODELS
# =============================================================================


class RunRequest(BaseModel):
    """Request body for /run endpoint."""

    target_dir: str = Field(..., description="Directory to analyze")
    spec_path: Optional[str] = Field(default=None, description="Path to spec file")
    spec_content: Optional[str] = Field(default=None, description="Constitution text content (alternative to spec_path)")
    watch_mode: bool = Field(default=False)
    generate_patches: bool = Field(default=True)


class RunResponse(BaseModel):
    """Response from /run endpoint."""

    run_id: str = Field(..., description="Unique run identifier")
    status: PipelineStatus
    message: str


class StatusResponse(BaseModel):
    """Response from /status endpoint."""

    run_id: str
    state: PipelineState


class VerdictResponse(BaseModel):
    """Response from /verdict endpoint."""

    run_id: str
    consensus: Optional[ConsensusResult]
    patches: Optional[PatchSet]
    ready: bool = Field(default=False)
    
    # NEW: Raw content for frontend download
    report_markdown: Optional[str] = Field(
        default=None, description="Full REPORT.md content for download"
    )
    patch_diff: Optional[str] = Field(
        default=None, description="Combined unified diff of all patches"
    )


class WebSocketMessage(BaseModel):
    """Message format for WebSocket streaming."""

    type: str = Field(..., description="Message type: status, progress, verdict, error")
    run_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# PROMPT RECOMMENDATION MODELS
# =============================================================================


class PriorityIssue(BaseModel):
    """A prioritized issue extracted from tribunal verdict."""
    
    severity: str = Field(..., description="critical, high, medium, or low")
    category: str = Field(..., description="security, functionality, or style")
    description: str = Field(..., description="Issue description")
    file_path: Optional[str] = Field(default=None, description="Affected file")
    line_number: Optional[int] = Field(default=None, ge=1, description="Line number")
    judge_source: Optional[str] = Field(default=None, description="Which judge identified this")
    suggestion: Optional[str] = Field(default=None, description="How to fix")


class PromptRecommendation(BaseModel):
    """
    Synthesized prompt recommendation for fixing identified issues.
    
    Generated by the Prompt Synthesizer after a failed verification run.
    Contains a comprehensive, actionable prompt that can be given to an
    AI coding assistant to fix all identified issues.
    """
    
    primary_prompt: str = Field(..., description="Main fix prompt for AI assistant")
    priority_issues: List[PriorityIssue] = Field(
        default_factory=list, description="Prioritized list of issues to fix"
    )
    strategy: str = Field(..., description="Recommended fix approach")
    complexity: str = Field(
        default="medium", description="Estimated fix complexity: low, medium, high"
    )
    alternative_prompts: List[str] = Field(
        default_factory=list, description="Alternative prompt variations"
    )
    context_files: List[str] = Field(
        default_factory=list, description="Files the AI should read first"
    )
    estimated_tokens: int = Field(default=0, ge=0, description="Estimated token count")
    generation_time_ms: int = Field(default=0, ge=0, description="Time to generate")
    veto_addressed: bool = Field(
        default=False, description="Whether security veto is addressed"
    )


class PromptResponse(BaseModel):
    """Response from /prompt endpoint."""
    
    run_id: str
    ready: bool = Field(default=False)
    message: str = Field(default="")
    prompt: Optional[PromptRecommendation] = None
