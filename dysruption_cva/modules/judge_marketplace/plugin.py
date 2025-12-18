"""
Judge Marketplace - Plugin Interface

Abstract base class defining the contract all judge plugins must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from .models import JudgeConfig, JudgeDomain, JudgeResult, JudgeIssue, VerdictSeverity

if TYPE_CHECKING:
    pass


class JudgePlugin(ABC):
    """
    Abstract base class for all judge plugins.
    
    To create a custom judge:
    1. Subclass JudgePlugin
    2. Implement required abstract properties and methods
    3. Register with JudgeRegistry
    
    Example:
        class MyCustomJudge(JudgePlugin):
            @property
            def name(self) -> str:
                return "my_custom_judge"
            
            @property
            def display_name(self) -> str:
                return "My Custom Judge"
            
            @property
            def domain(self) -> JudgeDomain:
                return JudgeDomain.CUSTOM
            
            def get_system_prompt(self) -> str:
                return "You are a custom code reviewer..."
            
            async def evaluate(self, code_context, success_spec, config):
                # Your evaluation logic
                return JudgeResult(score=8.0, explanation="Looks good!")
    """
    
    # =========================================================================
    # ABSTRACT PROPERTIES (must implement)
    # =========================================================================
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this judge (lowercase, underscores).
        
        Example: "hipaa_compliance", "security", "architect"
        """
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Human-readable name for UI display.
        
        Example: "HIPAA Compliance Judge", "Security Analyst"
        """
        pass
    
    @property
    @abstractmethod
    def domain(self) -> JudgeDomain:
        """
        Primary domain this judge specializes in.
        
        Used for filtering and categorization.
        """
        pass
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the system prompt for LLM evaluation.
        
        This should include:
        - Role description
        - Scoring rubric
        - Output format instructions
        - Any domain-specific criteria
        """
        pass
    
    @abstractmethod
    async def evaluate(
        self,
        code_context: str,
        success_spec: Dict[str, Any],
        config: Optional[JudgeConfig] = None,
    ) -> JudgeResult:
        """
        Evaluate code against the success specification.
        
        Args:
            code_context: The code to evaluate (with file paths)
            success_spec: The success specification dict
            config: Optional configuration overrides
            
        Returns:
            JudgeResult with score, explanation, and issues
        """
        pass
    
    # =========================================================================
    # OPTIONAL PROPERTIES (can override)
    # =========================================================================
    
    @property
    def description(self) -> str:
        """Detailed description of what this judge evaluates."""
        return f"Evaluates code for {self.domain.value} concerns."
    
    @property
    def version(self) -> str:
        """Version of this judge plugin."""
        return "1.0.0"
    
    @property
    def author(self) -> str:
        """Author of this judge plugin."""
        return "CVA Team"
    
    @property
    def default_weight(self) -> float:
        """Default weight in consensus calculation (1.0 = normal)."""
        return 1.0
    
    @property
    def default_model(self) -> str:
        """Default LLM model for this judge."""
        return "anthropic/claude-sonnet-4-20250514"
    
    @property
    def supports_veto(self) -> bool:
        """Whether this judge can trigger a veto (block pass)."""
        return False
    
    @property
    def default_veto_threshold(self) -> float:
        """Score below which veto triggers (if supports_veto)."""
        return 4.0
    
    @property
    def tags(self) -> List[str]:
        """Tags for categorization and search."""
        return [self.domain.value]
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def validate(self) -> bool:
        """
        Validate that this judge is properly configured.
        
        Returns True if valid, False otherwise.
        """
        try:
            if not self.name or not self.name.replace("_", "").isalnum():
                logger.warning(f"Invalid judge name: {self.name}")
                return False
            
            if not self.display_name:
                logger.warning(f"Missing display_name for judge: {self.name}")
                return False
            
            if not self.get_system_prompt():
                logger.warning(f"Empty system prompt for judge: {self.name}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Judge validation failed: {e}")
            return False
    
    def get_config(self) -> JudgeConfig:
        """Get default configuration for this judge."""
        return JudgeConfig(
            name=self.name,
            enabled=True,
            model=self.default_model,
            weight=self.default_weight,
            veto_enabled=self.supports_veto,
            veto_threshold=self.default_veto_threshold,
        )
    
    def create_result(
        self,
        score: float,
        explanation: str,
        issues: Optional[List[JudgeIssue]] = None,
        suggestions: Optional[List[str]] = None,
        veto: bool = False,
        veto_reason: str = "",
        confidence: float = 0.8,
        **metadata,
    ) -> JudgeResult:
        """
        Helper to create a properly formatted JudgeResult.
        
        Automatically fills in judge metadata.
        """
        return JudgeResult(
            score=max(1.0, min(10.0, score)),  # Clamp to 1-10
            explanation=explanation,
            confidence=confidence,
            issues=issues or [],
            suggestions=suggestions or [],
            veto=veto,
            veto_reason=veto_reason,
            judge_name=self.name,
            domain=self.domain.value,
            metadata=metadata,
        )
    
    def create_issue(
        self,
        severity: VerdictSeverity,
        message: str,
        file_path: Optional[str] = None,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        suggested_fix: Optional[str] = None,
        rule_id: Optional[str] = None,
    ) -> JudgeIssue:
        """Helper to create a JudgeIssue."""
        return JudgeIssue(
            severity=severity,
            message=message,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            suggested_fix=suggested_fix,
            rule_id=f"{self.name}:{rule_id}" if rule_id else None,
        )
    
    def __repr__(self) -> str:
        return f"<JudgePlugin:{self.name} domain={self.domain.value}>"
    
    def __str__(self) -> str:
        return self.display_name


class BaseLLMJudge(JudgePlugin):
    """
    Base class for judges that use LLM for evaluation.
    
    Provides common LLM calling infrastructure.
    """
    
    async def evaluate(
        self,
        code_context: str,
        success_spec: Dict[str, Any],
        config: Optional[JudgeConfig] = None,
    ) -> JudgeResult:
        """
        Evaluate using LLM.
        
        Subclasses can override _build_user_prompt and _parse_response
        for customization.
        """
        import json
        import time
        
        try:
            import litellm
        except ImportError:
            return self.create_result(
                score=5.0,
                explanation="LiteLLM not available for LLM-based evaluation",
                confidence=0.0,
            )
        
        config = config or self.get_config()
        model = config.model or self.default_model
        
        system_prompt = self.get_system_prompt()
        user_prompt = self._build_user_prompt(code_context, success_spec)
        
        start_time = time.time()
        
        try:
            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                timeout=config.timeout_seconds,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            content = response.choices[0].message.content
            result = self._parse_response(content)
            result.model_used = model
            result.latency_ms = latency_ms
            result.token_count = response.usage.total_tokens if response.usage else 0
            
            # Check veto threshold
            if config.veto_enabled and result.score < config.veto_threshold:
                result.veto = True
                result.veto_reason = f"Score {result.score:.1f} below threshold {config.veto_threshold}"
            
            return result
            
        except Exception as e:
            logger.error(f"Judge {self.name} evaluation failed: {e}")
            return self.create_result(
                score=5.0,
                explanation=f"Evaluation error: {str(e)[:200]}",
                confidence=0.0,
            )
    
    def _build_user_prompt(
        self,
        code_context: str,
        success_spec: Dict[str, Any],
    ) -> str:
        """Build the user prompt for evaluation."""
        import json
        
        spec_json = json.dumps(success_spec, indent=2, ensure_ascii=False)[:50000]
        code_truncated = code_context[:100000]
        
        return f"""## SUCCESS SPECIFICATION:
{spec_json}

## CODE TO EVALUATE:
{code_truncated}

Evaluate this code against the specification and provide your assessment."""
    
    def _parse_response(self, content: str) -> JudgeResult:
        """Parse LLM response into JudgeResult."""
        import json
        import re
        
        # Try to extract JSON from response
        try:
            # Look for JSON block
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try parsing entire content as JSON
                data = json.loads(content)
            
            issues = []
            for issue_data in data.get("issues", []):
                if isinstance(issue_data, str):
                    issues.append(self.create_issue(VerdictSeverity.MEDIUM, issue_data))
                elif isinstance(issue_data, dict):
                    issues.append(JudgeIssue(
                        severity=VerdictSeverity(issue_data.get("severity", "medium")),
                        message=issue_data.get("message", ""),
                        file_path=issue_data.get("file"),
                        line_start=issue_data.get("line_start"),
                        line_end=issue_data.get("line_end"),
                        suggested_fix=issue_data.get("suggested_fix"),
                    ))
            
            return self.create_result(
                score=float(data.get("score", 5.0)),
                explanation=data.get("explanation", ""),
                issues=issues,
                suggestions=data.get("suggestions", []),
                confidence=float(data.get("confidence", 0.8)),
            )
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Fallback: extract score from text
            score_match = re.search(r'score[:\s]+(\d+(?:\.\d+)?)', content, re.IGNORECASE)
            score = float(score_match.group(1)) if score_match else 5.0
            
            return self.create_result(
                score=score,
                explanation=content[:2000],
                confidence=0.5,
            )
