"""
Workflow Chain

Composes multiple workflows into a sequential execution pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from .base import Workflow, WorkflowContext, WorkflowResult, WorkflowStatus


class ChainExecutionMode(str, Enum):
    """How the chain handles workflow failures."""
    
    # Stop chain on first failure
    FAIL_FAST = "fail_fast"
    
    # Continue even if workflows fail
    CONTINUE_ON_FAILURE = "continue_on_failure"
    
    # Only stop if workflow explicitly requests abort
    ABORT_ON_REQUEST = "abort_on_request"


@dataclass
class ChainResult:
    """Result of executing an entire workflow chain."""
    
    chain_id: str
    chain_name: str
    
    # Overall status
    status: WorkflowStatus
    overall_score: float = 0.0
    
    # Individual results
    workflow_results: List[WorkflowResult] = field(default_factory=list)
    
    # Summary counts
    total_workflows: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_ms: int = 0
    
    # Abort info
    was_aborted: bool = False
    abort_reason: str = ""
    aborted_by_workflow: str = ""
    
    # Accumulated issues from all workflows
    all_issues: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        """Check if all workflows passed."""
        return self.status == WorkflowStatus.PASSED
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 - 1.0)."""
        executed = self.passed_count + self.failed_count
        if executed == 0:
            return 0.0
        return self.passed_count / executed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chain_id": self.chain_id,
            "chain_name": self.chain_name,
            "status": self.status.value,
            "overall_score": self.overall_score,
            "total_workflows": self.total_workflows,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "success_rate": self.success_rate,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_ms": self.total_duration_ms,
            "was_aborted": self.was_aborted,
            "abort_reason": self.abort_reason,
            "aborted_by_workflow": self.aborted_by_workflow,
            "workflow_results": [r.to_dict() for r in self.workflow_results],
            "all_issues": self.all_issues,
        }


class WorkflowChain:
    """
    Composes multiple workflows into a sequential execution chain.
    
    Features:
    - Sequential execution with context passing
    - Multiple failure handling modes
    - Pre/post hooks for customization
    - Result aggregation
    - Abort support
    
    Example:
        chain = WorkflowChain("full_verification")
        chain.add(LintWorkflow())
        chain.add(SecurityWorkflow())
        chain.add(FullVerificationWorkflow())
        
        result = await chain.execute(context)
        print(f"Chain passed: {result.passed}")
    """
    
    def __init__(
        self,
        name: str = "workflow_chain",
        mode: ChainExecutionMode = ChainExecutionMode.ABORT_ON_REQUEST,
    ):
        """
        Initialize workflow chain.
        
        Args:
            name: Human-readable chain name
            mode: How to handle workflow failures
        """
        self.name = name
        self.mode = mode
        self._workflows: List[Workflow] = []
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    def add(self, workflow: Workflow) -> "WorkflowChain":
        """
        Add a workflow to the chain.
        
        Args:
            workflow: Workflow instance to add
            
        Returns:
            Self for fluent chaining
        """
        self._workflows.append(workflow)
        return self
    
    def add_many(self, workflows: List[Workflow]) -> "WorkflowChain":
        """
        Add multiple workflows to the chain.
        
        Args:
            workflows: List of workflow instances
            
        Returns:
            Self for fluent chaining
        """
        self._workflows.extend(workflows)
        return self
    
    def insert(self, index: int, workflow: Workflow) -> "WorkflowChain":
        """
        Insert a workflow at a specific position.
        
        Args:
            index: Position to insert at
            workflow: Workflow instance
            
        Returns:
            Self for fluent chaining
        """
        self._workflows.insert(index, workflow)
        return self
    
    def clear(self) -> "WorkflowChain":
        """Remove all workflows from the chain."""
        self._workflows.clear()
        return self
    
    def on_pre_execute(self, hook: Callable) -> "WorkflowChain":
        """Add a hook called before chain execution."""
        self._pre_hooks.append(hook)
        return self
    
    def on_post_execute(self, hook: Callable) -> "WorkflowChain":
        """Add a hook called after chain execution."""
        self._post_hooks.append(hook)
        return self
    
    # =========================================================================
    # EXECUTION
    # =========================================================================
    
    async def execute(
        self,
        context: Optional[WorkflowContext] = None,
        file_tree: Optional[Dict[str, str]] = None,
        spec_content: str = "",
        target_dir: str = "",
    ) -> ChainResult:
        """
        Execute all workflows in sequence.
        
        Args:
            context: Existing context (or will be created)
            file_tree: Files to verify (used if no context)
            spec_content: Spec content (used if no context)
            target_dir: Target directory (used if no context)
            
        Returns:
            ChainResult with aggregated results
        """
        # Initialize chain result
        chain_id = str(uuid.uuid4())[:8]
        started_at = datetime.now()
        
        result = ChainResult(
            chain_id=chain_id,
            chain_name=self.name,
            status=WorkflowStatus.RUNNING,
            total_workflows=len(self._workflows),
            started_at=started_at,
        )
        
        # Create or update context
        if context is None:
            context = WorkflowContext(
                file_tree=file_tree or {},
                spec_content=spec_content,
                target_dir=target_dir,
            )
        
        context.chain_id = chain_id
        context.total_workflows = len(self._workflows)
        
        # Run pre-hooks
        for hook in self._pre_hooks:
            try:
                await hook(context) if callable(hook) else None
            except Exception as e:
                logger.warning(f"Pre-hook failed: {e}")
        
        logger.info(f"Starting workflow chain '{self.name}' with {len(self._workflows)} workflows")
        
        # Execute workflows sequentially
        for i, workflow in enumerate(self._workflows):
            context.workflow_index = i
            
            # Check if should abort
            if context.should_abort:
                result.was_aborted = True
                result.abort_reason = context.abort_reason
                logger.warning(f"Chain aborted before {workflow.name}: {context.abort_reason}")
                break
            
            # Check if workflow should run
            try:
                should_run = await workflow.should_run(context)
            except Exception as e:
                logger.error(f"Error in {workflow.name}.should_run(): {e}")
                should_run = True  # Default to running
            
            if not should_run:
                logger.debug(f"Skipping workflow: {workflow.name}")
                result.skipped_count += 1
                result.workflow_results.append(
                    WorkflowResult(
                        workflow_name=workflow.name,
                        workflow_type=workflow.workflow_type,
                        status=WorkflowStatus.SKIPPED,
                        message="Workflow skipped based on should_run()",
                    )
                )
                continue
            
            # Execute workflow
            workflow_result = await self._execute_single(workflow, context)
            result.workflow_results.append(workflow_result)
            
            # Update counts
            if workflow_result.passed:
                result.passed_count += 1
            elif workflow_result.failed:
                result.failed_count += 1
            
            # Accumulate issues
            result.all_issues.extend(workflow_result.issues)
            for issue in workflow_result.issues:
                context.add_issue(
                    workflow_name=workflow.name,
                    file_path=issue.get("file", ""),
                    line=issue.get("line", 0),
                    message=issue.get("message", ""),
                    severity=issue.get("severity", "medium"),
                )
            
            # Check failure handling
            if workflow_result.failed:
                if self.mode == ChainExecutionMode.FAIL_FAST:
                    logger.info(f"Chain failing fast after {workflow.name} failure")
                    result.was_aborted = True
                    result.abort_reason = "Fail-fast mode triggered"
                    result.aborted_by_workflow = workflow.name
                    break
                
                if workflow.abort_on_fail:
                    logger.info(f"Chain aborting due to {workflow.name} abort_on_fail")
                    result.was_aborted = True
                    result.abort_reason = f"Workflow {workflow.name} requires abort on fail"
                    result.aborted_by_workflow = workflow.name
                    break
                
            if workflow_result.should_abort_chain:
                if self.mode != ChainExecutionMode.CONTINUE_ON_FAILURE:
                    result.was_aborted = True
                    result.abort_reason = workflow_result.abort_reason
                    result.aborted_by_workflow = workflow.name
                    break
        
        # Calculate final status
        completed_at = datetime.now()
        result.completed_at = completed_at
        result.total_duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        
        if result.was_aborted:
            result.status = WorkflowStatus.ABORTED
        elif result.failed_count > 0:
            result.status = WorkflowStatus.FAILED
        elif result.passed_count == 0 and result.skipped_count > 0:
            result.status = WorkflowStatus.SKIPPED
        else:
            result.status = WorkflowStatus.PASSED
        
        # Calculate overall score (weighted average)
        scored_results = [r for r in result.workflow_results if r.status != WorkflowStatus.SKIPPED]
        if scored_results:
            result.overall_score = sum(r.score for r in scored_results) / len(scored_results)
        
        # Run post-hooks
        for hook in self._post_hooks:
            try:
                await hook(context, result) if callable(hook) else None
            except Exception as e:
                logger.warning(f"Post-hook failed: {e}")
        
        logger.info(
            f"Chain '{self.name}' completed: {result.status.value} "
            f"(passed={result.passed_count}, failed={result.failed_count}, skipped={result.skipped_count})"
        )
        
        return result
    
    async def _execute_single(
        self,
        workflow: Workflow,
        context: WorkflowContext,
    ) -> WorkflowResult:
        """Execute a single workflow with error handling."""
        started_at = datetime.now()
        
        try:
            # Pre-execute hook
            await workflow.pre_execute(context)
            
            # Main execution
            result = await workflow.execute(context)
            result.started_at = started_at
            result.completed_at = datetime.now()
            result.duration_ms = int((result.completed_at - started_at).total_seconds() * 1000)
            
            # Post-execute hook
            result = await workflow.post_execute(context, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Workflow {workflow.name} failed with exception: {e}")
            return WorkflowResult(
                workflow_name=workflow.name,
                workflow_type=workflow.workflow_type,
                status=WorkflowStatus.ERROR,
                score=0.0,
                message=f"Exception: {str(e)}",
                started_at=started_at,
                completed_at=datetime.now(),
            )
    
    # =========================================================================
    # INTROSPECTION
    # =========================================================================
    
    @property
    def workflows(self) -> List[Workflow]:
        """Get list of workflows in chain."""
        return self._workflows.copy()
    
    @property
    def workflow_names(self) -> List[str]:
        """Get list of workflow names."""
        return [w.name for w in self._workflows]
    
    def __len__(self) -> int:
        """Number of workflows in chain."""
        return len(self._workflows)
    
    def __repr__(self) -> str:
        return f"WorkflowChain(name='{self.name}', workflows={self.workflow_names})"
