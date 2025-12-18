"""
Judge Marketplace - Data Models

Core data structures for the judge plugin system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class JudgeDomain(str, Enum):
    """Standard domains for judge specialization."""
    
    # Core domains (built-in)
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    INTENT = "intent"  # Also known as user_proxy
    USER_PROXY = "user_proxy"  # Alias for INTENT
    
    # Compliance domains
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    GDPR = "gdpr"
    SOC2 = "soc2"
    
    # Quality domains
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    API_DESIGN = "api_design"
    DATABASE = "database"
    FRONTEND = "frontend"
    DEVOPS = "devops"
    
    # Industry domains
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    GAMING = "gaming"
    IOT = "iot"
    
    # Custom
    CUSTOM = "custom"


class VerdictSeverity(str, Enum):
    """Severity of issues found by a judge."""
    
    CRITICAL = "critical"  # Blocks deployment, triggers veto
    HIGH = "high"          # Serious issue, strong negative weight
    MEDIUM = "medium"      # Notable concern
    LOW = "low"            # Minor issue, advisory
    INFO = "info"          # Informational only


@dataclass
class JudgeIssue:
    """A specific issue identified by a judge."""
    
    severity: VerdictSeverity
    message: str
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    code_snippet: Optional[str] = None
    suggested_fix: Optional[str] = None
    rule_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_snippet": self.code_snippet,
            "suggested_fix": self.suggested_fix,
            "rule_id": self.rule_id,
        }


@dataclass
class JudgeResult:
    """
    Result from a judge evaluation.
    
    This is the standardized output format all judges must produce.
    """
    
    # Core scoring
    score: float                          # 1-10 score
    explanation: str                      # Human-readable explanation
    confidence: float = 0.8               # Confidence in result (0-1)
    
    # Issues and suggestions
    issues: List[JudgeIssue] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    # Veto mechanism
    veto: bool = False                    # Trigger veto?
    veto_reason: str = ""                 # Why veto was triggered
    
    # Metadata
    judge_name: str = ""                  # Which judge produced this
    domain: str = ""                      # Domain of evaluation
    model_used: str = ""                  # Which LLM model was used
    latency_ms: int = 0                   # Evaluation time
    token_count: int = 0                  # Tokens consumed
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "score": self.score,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "issues": [i.to_dict() for i in self.issues],
            "suggestions": self.suggestions,
            "veto": self.veto,
            "veto_reason": self.veto_reason,
            "judge_name": self.judge_name,
            "domain": self.domain,
            "model_used": self.model_used,
            "latency_ms": self.latency_ms,
            "token_count": self.token_count,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
    
    @property
    def passed(self) -> bool:
        """Whether this evaluation passed (score >= 7)."""
        return self.score >= 7.0 and not self.veto
    
    @property
    def critical_issues(self) -> List[JudgeIssue]:
        """Get only critical issues."""
        return [i for i in self.issues if i.severity == VerdictSeverity.CRITICAL]
    
    @property
    def high_issues(self) -> List[JudgeIssue]:
        """Get high severity issues."""
        return [i for i in self.issues if i.severity == VerdictSeverity.HIGH]


@dataclass
class JudgeConfig:
    """Configuration for a judge instance."""
    
    name: str                             # Judge identifier
    enabled: bool = True                  # Whether judge is active
    model: Optional[str] = None           # LLM model override
    weight: float = 1.0                   # Weight in consensus
    veto_enabled: bool = False            # Can this judge veto?
    veto_threshold: float = 4.0           # Score below which veto triggers
    timeout_seconds: int = 60             # Max evaluation time
    
    # Domain-specific patterns to look for
    patterns: List[str] = field(default_factory=list)
    
    # Extra configuration
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "model": self.model,
            "weight": self.weight,
            "veto_enabled": self.veto_enabled,
            "veto_threshold": self.veto_threshold,
            "timeout_seconds": self.timeout_seconds,
            "patterns": self.patterns,
            "extra": self.extra,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JudgeConfig":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            model=data.get("model"),
            weight=data.get("weight", 1.0),
            veto_enabled=data.get("veto_enabled", False),
            veto_threshold=data.get("veto_threshold", 4.0),
            timeout_seconds=data.get("timeout_seconds", 60),
            patterns=data.get("patterns", []),
            extra=data.get("extra", {}),
        )


@dataclass
class MarketplaceManifest:
    """Manifest for a judge plugin package."""
    
    name: str                             # Plugin name
    version: str                          # Semantic version
    author: str                           # Author name
    description: str                      # What this judge does
    domain: JudgeDomain                   # Primary domain
    
    # Requirements
    min_cva_version: str = "1.0.0"        # Minimum CVA version
    required_models: List[str] = field(default_factory=list)
    
    # Metadata
    homepage: Optional[str] = None
    license: str = "MIT"
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "domain": self.domain.value,
            "min_cva_version": self.min_cva_version,
            "required_models": self.required_models,
            "homepage": self.homepage,
            "license": self.license,
            "tags": self.tags,
        }
