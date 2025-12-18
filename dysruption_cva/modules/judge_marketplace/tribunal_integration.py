"""
Tribunal Integration - Bridge between Judge Marketplace and Tribunal

Provides adapter classes and methods for integrating the modular judge
marketplace system with the existing Tribunal infrastructure.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from ..schemas import JudgeRole, JudgeVerdict, VerdictStatus
from .models import JudgeConfig, JudgeDomain, JudgeResult, VerdictSeverity
from .plugin import JudgePlugin
from .registry import JudgeRegistry, get_registry


class TribunalAdapter:
    """
    Adapts the Judge Marketplace system to work with the existing Tribunal.
    
    Converts between:
    - JudgeResult (marketplace) <-> JudgeVerdict (tribunal schemas)
    - JudgePlugin <-> Tribunal judge config dict
    - Async evaluation <-> Sync tribunal flow
    
    Usage:
        adapter = TribunalAdapter(get_registry())
        
        # Run all active judges on code
        results = await adapter.evaluate_all(code, file_path, context)
        
        # Convert to tribunal format
        verdicts = [adapter.to_tribunal_verdict(r) for r in results]
    """
    
    # Map marketplace domains to tribunal roles
    DOMAIN_TO_ROLE = {
        JudgeDomain.ARCHITECTURE: JudgeRole.ARCHITECT,
        JudgeDomain.SECURITY: JudgeRole.SECURITY,
        JudgeDomain.INTENT: JudgeRole.USER_PROXY,
        JudgeDomain.USER_PROXY: JudgeRole.USER_PROXY,
        # Compliance domains map to security for tribunal
        JudgeDomain.HIPAA: JudgeRole.SECURITY,
        JudgeDomain.PCI_DSS: JudgeRole.SECURITY,
        JudgeDomain.GDPR: JudgeRole.SECURITY,
        JudgeDomain.SOC2: JudgeRole.SECURITY,
        # Others default to architect
        JudgeDomain.PERFORMANCE: JudgeRole.ARCHITECT,
        JudgeDomain.ACCESSIBILITY: JudgeRole.USER_PROXY,
        JudgeDomain.TESTING: JudgeRole.ARCHITECT,
        JudgeDomain.DOCUMENTATION: JudgeRole.USER_PROXY,
        JudgeDomain.API_DESIGN: JudgeRole.ARCHITECT,
        JudgeDomain.DATABASE: JudgeRole.ARCHITECT,
        JudgeDomain.FRONTEND: JudgeRole.USER_PROXY,
        JudgeDomain.DEVOPS: JudgeRole.ARCHITECT,
        JudgeDomain.CUSTOM: JudgeRole.ARCHITECT,
    }
    
    # Map severity levels
    SEVERITY_TO_CONFIDENCE = {
        VerdictSeverity.CRITICAL: 0.95,
        VerdictSeverity.HIGH: 0.85,
        VerdictSeverity.MEDIUM: 0.70,
        VerdictSeverity.LOW: 0.55,
        VerdictSeverity.INFO: 0.40,
    }
    
    def __init__(self, registry: Optional[JudgeRegistry] = None):
        """Initialize adapter with a registry."""
        self.registry = registry or get_registry()
    
    # =========================================================================
    # EVALUATION
    # =========================================================================
    
    async def evaluate_with_judge(
        self,
        judge_name: str,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> Optional[JudgeResult]:
        """
        Evaluate code with a specific judge.
        
        Args:
            judge_name: Name of the judge to use
            code_content: Code to evaluate
            file_path: Path to the file
            context: Optional context dict
            
        Returns:
            JudgeResult or None if judge not found
        """
        judge = self.registry.get_judge(judge_name)
        if not judge:
            logger.warning(f"Judge not found: {judge_name}")
            return None
        
        config = self.registry.get_config(judge_name)
        return await judge.evaluate(code_content, file_path, context, config)
    
    async def evaluate_all(
        self,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> List[Tuple[JudgePlugin, JudgeResult]]:
        """
        Evaluate code with all active judges.
        
        Args:
            code_content: Code to evaluate
            file_path: Path to the file
            context: Optional context dict
            
        Returns:
            List of (judge, result) tuples
        """
        active_judges = self.registry.get_active_judges()
        results = []
        
        # Run evaluations concurrently
        tasks = []
        for judge in active_judges:
            config = self.registry.get_config(judge.name)
            tasks.append(judge.evaluate(code_content, file_path, context, config))
        
        if tasks:
            evaluated = await asyncio.gather(*tasks, return_exceptions=True)
            
            for judge, result in zip(active_judges, evaluated):
                if isinstance(result, Exception):
                    logger.error(f"Judge {judge.name} failed: {result}")
                    # Create error result
                    result = judge.create_result(
                        score=0.5,
                        explanation=f"Evaluation failed: {str(result)}",
                        issues=[],
                    )
                results.append((judge, result))
        
        return results
    
    async def evaluate_by_domain(
        self,
        domain: JudgeDomain,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> List[Tuple[JudgePlugin, JudgeResult]]:
        """Evaluate code with all judges for a specific domain."""
        domain_judges = self.registry.get_judges_for_domain(domain)
        results = []
        
        for judge in domain_judges:
            config = self.registry.get_config(judge.name)
            result = await judge.evaluate(code_content, file_path, context, config)
            results.append((judge, result))
        
        return results
    
    def evaluate_sync(
        self,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> List[Tuple[JudgePlugin, JudgeResult]]:
        """Synchronous wrapper for evaluate_all."""
        return asyncio.run(self.evaluate_all(code_content, file_path, context))
    
    # =========================================================================
    # FORMAT CONVERSION
    # =========================================================================
    
    def to_tribunal_verdict(
        self,
        judge: JudgePlugin,
        result: JudgeResult,
        criterion_id: int = 0,
    ) -> JudgeVerdict:
        """
        Convert a JudgeResult to tribunal JudgeVerdict format.
        
        Args:
            judge: The judge that produced the result
            result: The marketplace JudgeResult
            criterion_id: Optional criterion ID
            
        Returns:
            JudgeVerdict compatible with tribunal schemas
        """
        # Map domain to tribunal role
        role = self.DOMAIN_TO_ROLE.get(judge.domain, JudgeRole.ARCHITECT)
        
        # Convert score from 0-1 to 1-10
        score_10 = int(result.score * 10)
        score_10 = max(1, min(10, score_10))  # Clamp to 1-10
        
        # Determine verdict status
        if result.veto:
            status = VerdictStatus.VETO
        elif result.passed:
            status = VerdictStatus.PASS
        else:
            status = VerdictStatus.FAIL
        
        # Calculate confidence from issue severities
        confidence = self._calculate_confidence(result)
        
        # Convert issues to string list
        issues = [issue.message for issue in result.issues]
        
        # Extract suggestions from metadata or issues
        suggestions = []
        for issue in result.issues:
            if issue.suggestion:
                suggestions.append(issue.suggestion)
        
        return JudgeVerdict(
            judge_role=role,
            criterion_id=criterion_id,
            score=score_10,
            status=status,
            explanation=result.explanation,
            issues=issues,
            suggestions=suggestions,
            confidence=confidence,
            model_used=judge.default_model,
        )
    
    def from_tribunal_config(
        self,
        tribunal_judge_config: Dict[str, Any],
    ) -> JudgeConfig:
        """
        Convert tribunal judge config dict to JudgeConfig.
        
        Args:
            tribunal_judge_config: Dict from tribunal.judges
            
        Returns:
            JudgeConfig instance
        """
        return JudgeConfig(
            name=tribunal_judge_config.get("name", "unknown"),
            enabled=True,
            weight=tribunal_judge_config.get("weight", 1.0),
            veto_enabled=tribunal_judge_config.get("veto_enabled", False),
            threshold=0.7,
            model=tribunal_judge_config.get("model"),
        )
    
    def to_tribunal_judge_config(
        self,
        judge: JudgePlugin,
        config: Optional[JudgeConfig] = None,
    ) -> Dict[str, Any]:
        """
        Convert a judge plugin to tribunal judge config dict format.
        
        Args:
            judge: The judge plugin
            config: Optional config (uses judge defaults if None)
            
        Returns:
            Dict compatible with tribunal.judges
        """
        config = config or judge.get_config()
        role = self.DOMAIN_TO_ROLE.get(judge.domain, JudgeRole.ARCHITECT)
        
        return {
            "name": judge.display_name,
            "role": role,
            "model": config.model or judge.default_model,
            "description": judge.description,
            "weight": config.weight,
            "veto_enabled": config.veto_enabled,
        }
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _calculate_confidence(self, result: JudgeResult) -> float:
        """Calculate confidence from result issues."""
        if not result.issues:
            return 0.7  # Default confidence
        
        # Weight by severity
        total_weight = 0.0
        weighted_confidence = 0.0
        
        for issue in result.issues:
            conf = self.SEVERITY_TO_CONFIDENCE.get(issue.severity, 0.5)
            weight = 1.0 + (conf * 0.5)  # Higher severity = more weight
            weighted_confidence += conf * weight
            total_weight += weight
        
        return weighted_confidence / total_weight if total_weight > 0 else 0.7
    
    def check_veto(self, results: List[Tuple[JudgePlugin, JudgeResult]]) -> Optional[str]:
        """
        Check if any judge triggered a veto.
        
        Args:
            results: List of (judge, result) tuples
            
        Returns:
            Veto reason string if veto triggered, None otherwise
        """
        veto_judges = self.registry.get_veto_judges()
        veto_judge_names = {j.name for j in veto_judges}
        
        for judge, result in results:
            if judge.name in veto_judge_names and result.veto:
                return f"Veto triggered by {judge.display_name}: {result.explanation}"
        
        return None
    
    def calculate_consensus(
        self,
        results: List[Tuple[JudgePlugin, JudgeResult]],
        consensus_ratio: float = 0.67,
    ) -> Tuple[bool, float, str]:
        """
        Calculate consensus from multiple judge results.
        
        Args:
            results: List of (judge, result) tuples
            consensus_ratio: Required ratio for consensus
            
        Returns:
            Tuple of (passed, average_score, explanation)
        """
        if not results:
            return False, 0.0, "No judge results"
        
        # Check for veto first
        veto_reason = self.check_veto(results)
        if veto_reason:
            return False, 0.0, veto_reason
        
        # Calculate weighted average
        total_weight = 0.0
        weighted_score = 0.0
        pass_count = 0
        
        for judge, result in results:
            config = self.registry.get_config(judge.name)
            weight = config.weight if config else 1.0
            
            weighted_score += result.score * weight
            total_weight += weight
            
            if result.passed:
                pass_count += 1
        
        avg_score = weighted_score / total_weight if total_weight > 0 else 0.0
        pass_ratio = pass_count / len(results)
        
        # Consensus requires both score threshold and ratio
        passed = avg_score >= 0.7 and pass_ratio >= consensus_ratio
        
        explanation = (
            f"Consensus: {pass_count}/{len(results)} judges passed "
            f"(ratio: {pass_ratio:.2%}), avg score: {avg_score:.2f}"
        )
        
        return passed, avg_score, explanation


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_tribunal_adapter(
    config_path: Optional[str] = None,
    auto_discover: bool = True,
) -> TribunalAdapter:
    """
    Create a configured TribunalAdapter.
    
    Args:
        config_path: Optional path to config.yaml
        auto_discover: Whether to auto-register core judges
        
    Returns:
        Configured TribunalAdapter
    """
    registry = get_registry()
    
    # Load config if provided
    if config_path:
        registry.load_from_config(config_path)
    
    # Auto-register core judges
    if auto_discover:
        try:
            from .core import ArchitectJudge, SecurityJudge, UserProxyJudge
            
            registry.register(ArchitectJudge())
            registry.register(SecurityJudge())
            registry.register(UserProxyJudge())
            
            logger.info("Registered core judges: architect, security, user_proxy")
        except ImportError as e:
            logger.warning(f"Failed to import core judges: {e}")
    
    return TribunalAdapter(registry)
