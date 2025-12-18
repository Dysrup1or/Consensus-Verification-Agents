"""
Judge Marketplace - Modular Judge Plugin System

A plugin architecture for domain-extensible code verification judges.
Enables custom judges for HIPAA, PCI-DSS, GDPR, and other compliance domains.

Usage:
    from modules.judge_marketplace import (
        JudgePlugin,
        BaseLLMJudge,
        JudgeResult,
        JudgeConfig,
        JudgeDomain,
        get_registry,
        register_judge,
        create_tribunal_adapter,
    )
    
    # Create custom judge
    class MyCustomJudge(BaseLLMJudge):
        @property
        def name(self) -> str:
            return "my_custom_judge"
        
        @property
        def domain(self) -> JudgeDomain:
            return JudgeDomain.CUSTOM
        
        def get_system_prompt(self) -> str:
            return "You are a custom code reviewer..."
    
    # Register with global registry
    register_judge(MyCustomJudge())
    
    # Integrate with Tribunal
    adapter = create_tribunal_adapter()
    results = await adapter.evaluate_all(code, file_path)
"""

from .models import (
    JudgeConfig,
    JudgeDomain,
    JudgeIssue,
    JudgeResult,
    MarketplaceManifest,
    VerdictSeverity,
)
from .plugin import BaseLLMJudge, JudgePlugin
from .registry import (
    JudgeRegistry,
    get_judge,
    get_registry,
    register_judge,
)
from .tribunal_integration import (
    TribunalAdapter,
    create_tribunal_adapter,
)

__all__ = [
    # Models
    "JudgeConfig",
    "JudgeDomain",
    "JudgeIssue",
    "JudgeResult",
    "MarketplaceManifest",
    "VerdictSeverity",
    # Plugin
    "JudgePlugin",
    "BaseLLMJudge",
    # Registry
    "JudgeRegistry",
    "get_registry",
    "register_judge",
    "get_judge",
    # Integration
    "TribunalAdapter",
    "create_tribunal_adapter",
]

__version__ = "1.0.0"
