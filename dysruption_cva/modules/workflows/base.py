"""
Workflow Base Classes

Abstract interfaces and data models for the workflow composition system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from ..schemas import FileTree, ConsensusResult


class WorkflowStatus(str, Enum):
    """Status of a workflow execution."""
    
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class WorkflowContext:
    """
    Context passed between workflows in a chain.
    
    Allows workflows to share information without tight coupling.
    """
    
    # Input data
    file_tree: Dict[str, str] = field(default_factory=dict)
    spec_content: str = ""
    target_dir: str = ""
    
    # Shared state between workflows
    shared_data: Dict[str, Any] = field(default_factory=dict)
    
    # Files that have been modified by previous workflows
    modified_files: Set[str] = field(default_factory=set)
    
    # Issues found by previous workflows
    accumulated_issues: List[Dict[str, Any]] = field(default_factory=list)
    
    # Workflow chain metadata
    chain_id: str = ""
    workflow_index: int = 0
    total_workflows: int = 0
    
    # Abort control
    should_abort: bool = False
    abort_reason: str = ""
    
    def add_issue(
        self,
        workflow_name: str,
        file_path: str,
        line: int,
        message: str,
        severity: str = "medium",
    ) -> None:
        """Add an issue to the accumulated list."""
        self.accumulated_issues.append({
            "workflow": workflow_name,
            "file": file_path,
            "line": line,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
        })
    
    def request_abort(self, reason: str) -> None:
        """Request that the workflow chain abort execution."""
        self.should_abort = True
        self.abort_reason = reason
        logger.warning(f"Workflow abort requested: {reason}")


@dataclass
class WorkflowResult:
    """Result of a single workflow execution."""
    
    # Identity
    workflow_name: str
    workflow_type: str
    
    # Outcome
    status: WorkflowStatus
    score: float = 0.0  # 0.0 - 1.0
    
    # Details
    message: str = ""
    issues: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    
    # Abort control
    should_abort_chain: bool = False
    abort_reason: str = ""
    
    # Raw data from underlying systems
    raw_output: Optional[Dict[str, Any]] = None
    
    @property
    def passed(self) -> bool:
        """Check if workflow passed."""
        return self.status == WorkflowStatus.PASSED
    
    @property
    def failed(self) -> bool:
        """Check if workflow failed."""
        return self.status in (WorkflowStatus.FAILED, WorkflowStatus.ABORTED, WorkflowStatus.ERROR)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "workflow_name": self.workflow_name,
            "workflow_type": self.workflow_type,
            "status": self.status.value,
            "score": self.score,
            "message": self.message,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "should_abort_chain": self.should_abort_chain,
            "abort_reason": self.abort_reason,
        }


class Workflow(ABC):
    """
    Abstract base class for all verification workflows.
    
    To create a custom workflow:
    1. Subclass Workflow
    2. Implement name, workflow_type, and execute()
    3. Optionally override should_run() for conditional execution
    
    Example:
        class MyCustomWorkflow(Workflow):
            @property
            def name(self) -> str:
                return "my_custom_workflow"
            
            @property
            def workflow_type(self) -> str:
                return "custom"
            
            async def execute(self, context: WorkflowContext) -> WorkflowResult:
                # Your verification logic
                return WorkflowResult(
                    workflow_name=self.name,
                    workflow_type=self.workflow_type,
                    status=WorkflowStatus.PASSED,
                    score=1.0,
                    message="All checks passed!"
                )
    """
    
    # =========================================================================
    # ABSTRACT PROPERTIES (must implement)
    # =========================================================================
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this workflow (lowercase, underscores).
        
        Example: "security_scan", "lint_check", "full_verification"
        """
        pass
    
    @property
    @abstractmethod
    def workflow_type(self) -> str:
        """
        Type of workflow for categorization.
        
        Standard types: "lint", "security", "style", "verification", "custom"
        """
        pass
    
    @abstractmethod
    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """
        Execute the workflow and return results.
        
        Args:
            context: WorkflowContext with file tree, spec, and shared state
            
        Returns:
            WorkflowResult with status, score, issues, etc.
        """
        pass
    
    # =========================================================================
    # OPTIONAL PROPERTIES (can override)
    # =========================================================================
    
    @property
    def description(self) -> str:
        """Human-readable description of this workflow."""
        return f"{self.name} workflow"
    
    @property
    def abort_on_fail(self) -> bool:
        """Whether to abort the chain if this workflow fails."""
        return False
    
    @property
    def required_context_keys(self) -> List[str]:
        """Keys that must be present in context.shared_data."""
        return []
    
    @property
    def file_patterns(self) -> List[str]:
        """File patterns this workflow applies to (empty = all files)."""
        return []
    
    @property
    def estimated_duration_ms(self) -> int:
        """Estimated execution time in milliseconds."""
        return 1000
    
    # =========================================================================
    # LIFECYCLE METHODS (can override)
    # =========================================================================
    
    async def should_run(self, context: WorkflowContext) -> bool:
        """
        Determine if this workflow should run given the context.
        
        Override to implement conditional execution based on:
        - Previous workflow results
        - File types present
        - Configuration flags
        
        Args:
            context: Current workflow context
            
        Returns:
            True if workflow should execute, False to skip
        """
        # Check required context keys
        for key in self.required_context_keys:
            if key not in context.shared_data:
                logger.debug(f"{self.name}: Missing required context key '{key}', skipping")
                return False
        
        return True
    
    async def pre_execute(self, context: WorkflowContext) -> None:
        """
        Hook called before execute().
        
        Use for setup, logging, or modifying context.
        """
        logger.debug(f"Starting workflow: {self.name}")
    
    async def post_execute(
        self,
        context: WorkflowContext,
        result: WorkflowResult,
    ) -> WorkflowResult:
        """
        Hook called after execute().
        
        Use for cleanup, result modification, or side effects.
        
        Returns:
            Optionally modified WorkflowResult
        """
        logger.debug(f"Completed workflow: {self.name} -> {result.status.value}")
        return result
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def create_result(
        self,
        status: WorkflowStatus,
        score: float = 0.0,
        message: str = "",
        issues: Optional[List[Dict]] = None,
        suggestions: Optional[List[str]] = None,
        abort_chain: bool = False,
        abort_reason: str = "",
    ) -> WorkflowResult:
        """Helper to create a WorkflowResult."""
        return WorkflowResult(
            workflow_name=self.name,
            workflow_type=self.workflow_type,
            status=status,
            score=score,
            message=message,
            issues=issues or [],
            suggestions=suggestions or [],
            should_abort_chain=abort_chain,
            abort_reason=abort_reason,
        )
    
    def filter_files(self, file_tree: Dict[str, str]) -> Dict[str, str]:
        """Filter file tree to only files matching this workflow's patterns."""
        if not self.file_patterns:
            return file_tree
        
        import fnmatch
        
        filtered = {}
        for path, content in file_tree.items():
            for pattern in self.file_patterns:
                if fnmatch.fnmatch(path, pattern):
                    filtered[path] = content
                    break
        
        return filtered
