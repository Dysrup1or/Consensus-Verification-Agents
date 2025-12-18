"""
Workflow Composition System

Enables chaining multiple verification workflows (lint -> security -> full)
for progressive verification with early exit on critical failures.

Constitutional Requirements Addressed:
- "chain workflows (lint → security → full)" from spec_cva.txt
- Progressive verification with abort on critical failures
- Shared context between workflow stages

Example Usage:
    from modules.workflows import create_standard_chain, WorkflowContext
    
    # Create standard chain
    chain = create_standard_chain()
    
    # Execute with files
    context = WorkflowContext(
        file_tree={"app.py": "...code..."},
        spec_content="User spec...",
    )
    result = await chain.execute(context)
    
    print(f"Chain passed: {result.passed}")
    print(f"Score: {result.overall_score}")
"""

from .base import (
    Workflow,
    WorkflowResult,
    WorkflowStatus,
    WorkflowContext,
)
from .chain import WorkflowChain, ChainResult, ChainExecutionMode
from .predefined import (
    LintWorkflow,
    SecurityWorkflow,
    StyleWorkflow,
    FullVerificationWorkflow,
    # Factory functions
    create_standard_chain,
    create_fast_chain,
    create_security_chain,
)

__all__ = [
    # Base classes
    "Workflow",
    "WorkflowResult",
    "WorkflowStatus",
    "WorkflowContext",
    # Chain classes
    "WorkflowChain",
    "ChainResult",
    "ChainExecutionMode",
    # Predefined workflows
    "LintWorkflow",
    "SecurityWorkflow",
    "StyleWorkflow",
    "FullVerificationWorkflow",
    # Factory functions
    "create_standard_chain",
    "create_fast_chain",
    "create_security_chain",
]
