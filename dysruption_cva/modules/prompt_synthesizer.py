"""
Dysruption CVA - Prompt Synthesizer Module
Generates actionable fix prompts from tribunal verdicts.

Version: 1.0

This module takes the output of a failed tribunal verdict and synthesizes
a comprehensive, prioritized prompt that can be given to an AI coding assistant
(like GitHub Copilot, Claude, GPT-4) to fix the identified issues.

Key Features:
- Aggregates issues from all judges (Architect, Security, User Proxy)
- Prioritizes by severity (critical > high > medium > low)
- Security issues always first (respects veto protocol)
- Generates multiple prompt variations for different contexts
- Estimates complexity and provides strategy recommendations
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from loguru import logger

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.error("LiteLLM not available. Install with: pip install litellm")


# =============================================================================
# SCHEMAS
# =============================================================================

@dataclass
class PriorityIssue:
    """A prioritized issue from the tribunal verdict."""
    severity: str  # critical, high, medium, low
    category: str  # security, functionality, style
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    judge_source: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class PromptRecommendation:
    """Complete prompt recommendation output."""
    primary_prompt: str
    priority_issues: List[PriorityIssue]
    strategy: str
    complexity: str  # low, medium, high
    alternative_prompts: List[str]
    context_files: List[str]
    estimated_tokens: int
    generation_time_ms: int
    veto_addressed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "primary_prompt": self.primary_prompt,
            "priority_issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "description": i.description,
                    "file_path": i.file_path,
                    "line_number": i.line_number,
                    "judge_source": i.judge_source,
                    "suggestion": i.suggestion,
                }
                for i in self.priority_issues
            ],
            "strategy": self.strategy,
            "complexity": self.complexity,
            "alternative_prompts": self.alternative_prompts,
            "context_files": self.context_files,
            "estimated_tokens": self.estimated_tokens,
            "generation_time_ms": self.generation_time_ms,
            "veto_addressed": self.veto_addressed,
        }


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

SYNTHESIZER_SYSTEM_PROMPT = """You are an expert prompt engineer specializing in creating effective prompts for AI coding assistants.

Your task is to take a code verification report (with issues and suggestions from multiple AI judges) and synthesize a SINGLE, COMPREHENSIVE, ACTIONABLE prompt that another AI coding assistant can use to fix all identified issues.

## Prompt Engineering Principles:
1. **Context First**: Start with what the code is supposed to do (from the spec)
2. **Prioritize Security**: Always address security issues first (especially if veto was triggered)
3. **Be Specific**: Include file paths, line numbers, and exact issue descriptions
4. **Provide Examples**: When possible, show the pattern of the fix needed
5. **Chain of Thought**: Structure the prompt to guide the AI through fixes logically
6. **Verification**: Include how to verify each fix was applied correctly

## Priority Order:
1. 🚫 VETO issues (security with high confidence) - MUST be fixed first
2. 🔴 CRITICAL severity issues
3. 🟠 HIGH severity issues
4. 🟡 MEDIUM severity issues
5. 🟢 LOW severity issues

## Prompt Structure:
The primary prompt should follow this structure:
```
## Context
[What the code is supposed to do, key requirements]

## Critical Issues to Fix
[Numbered list of security/critical issues with file:line references]

## Additional Issues
[Other issues grouped by category]

## Implementation Notes
[Specific guidance on how to implement fixes]

## Verification Steps
[How to verify fixes are correct]
```

## Output Format (STRICT JSON):
{
    "primary_prompt": "The complete, ready-to-use prompt for the AI assistant...",
    "priority_issues": [
        {
            "severity": "critical|high|medium|low",
            "category": "security|functionality|style",
            "description": "Issue description",
            "file_path": "path/to/file.py",
            "line_number": 42,
            "suggestion": "How to fix this"
        }
    ],
    "strategy": "Brief description of the recommended fix approach",
    "complexity": "low|medium|high",
    "alternative_prompts": [
        "Alternative prompt for a different approach...",
        "Simpler prompt focusing only on critical issues..."
    ],
    "context_files": ["file1.py", "file2.py"]
}

Generate prompts that are:
- Self-contained (include all necessary context)
- Actionable (clear steps, not vague suggestions)
- Testable (include verification criteria)
- Appropriately scoped (not overwhelming, but complete)"""


QUICK_FIX_PROMPT_TEMPLATE = """You are a senior developer. Fix these {issue_count} issues in {file_count} files:

{issues_list}

Requirements from spec:
{spec_summary}

Provide complete fixed code for each file."""


SECURITY_FOCUS_PROMPT_TEMPLATE = """🚨 SECURITY ALERT: This code has critical security vulnerabilities that MUST be fixed.

## Veto Reason
{veto_reason}

## Security Issues (Fix ALL of these FIRST):
{security_issues}

## Affected Files:
{affected_files}

## Original Requirements:
{spec_summary}

Fix all security issues before addressing any other concerns. Ensure:
1. No SQL injection vulnerabilities
2. No hardcoded secrets
3. Proper input validation
4. Secure authentication/authorization
5. Safe error handling (no sensitive data in errors)"""


# =============================================================================
# PROMPT SYNTHESIZER CLASS
# =============================================================================

class PromptSynthesizer:
    """
    Synthesizes actionable fix prompts from tribunal verdicts.
    
    Takes the comprehensive output from the tribunal (all judge verdicts,
    issues, suggestions) and generates a single, prioritized prompt that
    can be given to an AI coding assistant to fix the code.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.llms_config = self.config.get("llms", {})
        self.retry_config = self.config.get("retry", {})
        
        # Use Claude for synthesis (best at prompt engineering)
        # Fall back to architect model if specific synthesizer not configured
        synthesizer_config = self.llms_config.get("synthesizer", {})
        self.model = synthesizer_config.get(
            "model", 
            self.llms_config.get("architect", {}).get("model", "anthropic/claude-sonnet-4-20250514")
        )
        self.max_tokens = synthesizer_config.get("max_tokens", 8192)
        self.temperature = synthesizer_config.get("temperature", 0.3)
        
        # Retry settings
        self.max_attempts = self.retry_config.get("max_attempts", 3)
        self.backoff_seconds = self.retry_config.get("backoff_seconds", 2)

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return {}

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def _call_llm(self, messages: List[Dict], max_tokens: int = None) -> Optional[str]:
        """Call LLM with retry logic."""
        if not LITELLM_AVAILABLE:
            raise RuntimeError("LiteLLM not available")

        max_tokens = max_tokens or self.max_tokens

        for attempt in range(1, self.max_attempts + 1):
            try:
                logger.debug(f"Synthesizer LLM call (attempt {attempt}/{self.max_attempts})")

                response = litellm.completion(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=self.temperature,
                )

                content = response.choices[0].message.content
                return content

            except Exception as e:
                logger.warning(f"Synthesizer LLM call failed (attempt {attempt}): {e}")
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    raise

        return None

    def _extract_issues_from_verdict(
        self, verdict_data: Dict[str, Any]
    ) -> List[PriorityIssue]:
        """
        Extract and prioritize all issues from a tribunal verdict.
        
        Args:
            verdict_data: The full verdict dictionary from tribunal
            
        Returns:
            Sorted list of PriorityIssue objects
        """
        issues: List[PriorityIssue] = []
        
        # Severity order for sorting
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        category_order = {"security": 0, "functionality": 1, "style": 2}
        
        # Extract from criterion_results
        for criterion in verdict_data.get("criterion_results", []):
            criterion_type = criterion.get("criterion_type", "functionality")
            
            # Determine severity based on verdict
            if criterion.get("veto_triggered"):
                severity = "critical"
            elif criterion.get("average_score", 10) < 4:
                severity = "critical"
            elif criterion.get("average_score", 10) < 6:
                severity = "high"
            elif criterion.get("average_score", 10) < 7:
                severity = "medium"
            else:
                severity = "low"
            
            # Extract issues from individual judge scores
            for score in criterion.get("scores", []):
                judge_name = score.get("judge_name", "Unknown")
                
                for issue_text in score.get("issues", []):
                    issues.append(PriorityIssue(
                        severity=severity,
                        category=criterion_type,
                        description=issue_text,
                        file_path=criterion.get("relevant_files", [None])[0],
                        line_number=None,
                        judge_source=judge_name,
                        suggestion=None,
                    ))
                
                for suggestion in score.get("suggestions", []):
                    # Find related issue or create standalone
                    if issues:
                        issues[-1].suggestion = suggestion
        
        # Extract from static analysis results
        for static_result in verdict_data.get("static_analysis_results", []):
            tool = static_result.get("tool", "unknown")
            file_path = static_result.get("file_path", "unknown")
            
            for issue in static_result.get("issues", []):
                is_critical = issue.get("is_critical", False)
                severity = "critical" if is_critical else "medium"
                
                issues.append(PriorityIssue(
                    severity=severity,
                    category="security" if tool == "bandit" else "style",
                    description=issue.get("message", str(issue)),
                    file_path=file_path,
                    line_number=issue.get("line", issue.get("line_number")),
                    judge_source=f"Static Analysis ({tool})",
                    suggestion=None,
                ))
        
        # Sort by severity and category
        issues.sort(key=lambda x: (
            severity_order.get(x.severity, 99),
            category_order.get(x.category, 99),
        ))
        
        return issues

    def _estimate_complexity(self, issues: List[PriorityIssue]) -> str:
        """Estimate fix complexity based on issues."""
        critical_count = sum(1 for i in issues if i.severity == "critical")
        high_count = sum(1 for i in issues if i.severity == "high")
        total = len(issues)
        
        if critical_count >= 3 or total >= 10:
            return "high"
        elif critical_count >= 1 or high_count >= 3 or total >= 5:
            return "medium"
        else:
            return "low"

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation."""
        return len(text) // 4

    def _format_issues_for_prompt(self, issues: List[PriorityIssue]) -> str:
        """Format issues into a readable list for the prompt."""
        lines = []
        current_category = None
        
        for i, issue in enumerate(issues, 1):
            if issue.category != current_category:
                current_category = issue.category
                emoji = {"security": "🔐", "functionality": "⚙️", "style": "🎨"}.get(
                    current_category, "📋"
                )
                lines.append(f"\n### {emoji} {current_category.upper()} ISSUES\n")
            
            severity_emoji = {
                "critical": "🚨",
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢",
            }.get(issue.severity, "⚪")
            
            location = ""
            if issue.file_path:
                location = f" in `{issue.file_path}`"
                if issue.line_number:
                    location += f" (line {issue.line_number})"
            
            lines.append(f"{i}. {severity_emoji} **[{issue.severity.upper()}]** {issue.description}{location}")
            
            if issue.suggestion:
                lines.append(f"   💡 Suggestion: {issue.suggestion}")
        
        return "\n".join(lines)

    def _generate_quick_fix_prompt(
        self,
        issues: List[PriorityIssue],
        spec_summary: str,
    ) -> str:
        """Generate a quick, focused fix prompt."""
        unique_files = set(i.file_path for i in issues if i.file_path)
        
        issues_text = "\n".join(
            f"- [{i.severity.upper()}] {i.description} ({i.file_path or 'unknown'}:{i.line_number or '?'})"
            for i in issues[:10]  # Top 10 issues only
        )
        
        return QUICK_FIX_PROMPT_TEMPLATE.format(
            issue_count=len(issues),
            file_count=len(unique_files),
            issues_list=issues_text,
            spec_summary=spec_summary[:500],
        )

    def _generate_security_focus_prompt(
        self,
        issues: List[PriorityIssue],
        veto_reason: Optional[str],
        spec_summary: str,
    ) -> str:
        """Generate a security-focused prompt for veto situations."""
        security_issues = [i for i in issues if i.category == "security"]
        affected_files = list(set(i.file_path for i in security_issues if i.file_path))
        
        issues_text = "\n".join(
            f"- [{i.severity.upper()}] {i.description}\n  File: {i.file_path or 'unknown'}:{i.line_number or '?'}\n  Fix: {i.suggestion or 'See above'}"
            for i in security_issues
        )
        
        return SECURITY_FOCUS_PROMPT_TEMPLATE.format(
            veto_reason=veto_reason or "Security judge failed verification with high confidence",
            security_issues=issues_text,
            affected_files="\n".join(f"- {f}" for f in affected_files),
            spec_summary=spec_summary[:500],
        )

    def synthesize(
        self,
        verdict_data: Dict[str, Any],
        spec_summary: str,
        file_tree: Optional[Dict[str, str]] = None,
    ) -> PromptRecommendation:
        """
        Main synthesis method. Takes tribunal verdict and generates fix prompts.
        
        Args:
            verdict_data: Full verdict from tribunal (as dict)
            spec_summary: Summary of the original spec requirements
            file_tree: Optional dict of file paths to content
            
        Returns:
            PromptRecommendation with primary and alternative prompts
        """
        start_time = time.time()
        
        logger.info("Synthesizing fix prompt from tribunal verdict...")
        
        # Extract and prioritize issues
        issues = self._extract_issues_from_verdict(verdict_data)
        
        if not issues:
            logger.warning("No issues found in verdict - nothing to fix")
            return PromptRecommendation(
                primary_prompt="No issues found! The code passed verification.",
                priority_issues=[],
                strategy="No fixes needed",
                complexity="low",
                alternative_prompts=[],
                context_files=[],
                estimated_tokens=0,
                generation_time_ms=0,
                veto_addressed=False,
            )
        
        logger.info(f"Found {len(issues)} issues to address")
        
        # Check for veto
        veto_triggered = verdict_data.get("veto_triggered", False)
        veto_reason = verdict_data.get("veto_reason")
        
        # Get unique files
        context_files = list(set(i.file_path for i in issues if i.file_path))[:10]
        
        # Build context for LLM
        formatted_issues = self._format_issues_for_prompt(issues)
        
        # Include relevant code snippets if available
        code_context = ""
        if file_tree:
            for file_path in context_files[:5]:
                if file_path in file_tree:
                    content = file_tree[file_path]
                    # Truncate large files
                    if len(content) > 2000:
                        content = content[:2000] + "\n... (truncated)"
                    code_context += f"\n### {file_path}\n```\n{content}\n```\n"
        
        # Build prompt for synthesizer
        user_prompt = f"""Generate a comprehensive fix prompt based on this verification report.

## Verification Summary
- Overall Verdict: {verdict_data.get('overall_verdict', 'UNKNOWN')}
- Overall Score: {verdict_data.get('overall_score', 0)}/10
- Issues Found: {len(issues)}
- Veto Triggered: {veto_triggered}
{f'- Veto Reason: {veto_reason}' if veto_reason else ''}

## Original Specification Requirements
{spec_summary[:1500]}

## Identified Issues (Prioritized)
{formatted_issues}

## Relevant Code Context
{code_context if code_context else 'No code context available'}

Generate a comprehensive, actionable prompt following the structure in your instructions.
Output ONLY valid JSON matching the schema."""

        # Call LLM
        response = self._call_llm([
            {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        
        # Parse response
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse synthesizer response: {e}")
            # Fallback to simple prompt generation
            result = {
                "primary_prompt": self._generate_quick_fix_prompt(issues, spec_summary),
                "priority_issues": [],
                "strategy": "Fix issues in order of severity",
                "complexity": self._estimate_complexity(issues),
                "alternative_prompts": [],
                "context_files": context_files,
            }
        
        # Build alternative prompts
        alternative_prompts = result.get("alternative_prompts", [])
        
        # Always add a quick-fix alternative
        alternative_prompts.append(self._generate_quick_fix_prompt(issues, spec_summary))
        
        # Add security-focused alternative if veto
        if veto_triggered:
            alternative_prompts.insert(
                0,
                self._generate_security_focus_prompt(issues, veto_reason, spec_summary)
            )
        
        # Convert priority_issues from response to PriorityIssue objects
        priority_issues_data = result.get("priority_issues", [])
        priority_issues = []
        for pi_data in priority_issues_data:
            priority_issues.append(PriorityIssue(
                severity=pi_data.get("severity", "medium"),
                category=pi_data.get("category", "functionality"),
                description=pi_data.get("description", ""),
                file_path=pi_data.get("file_path"),
                line_number=pi_data.get("line_number"),
                judge_source=pi_data.get("judge_source"),
                suggestion=pi_data.get("suggestion"),
            ))
        
        # Use extracted issues if response didn't include any
        if not priority_issues:
            priority_issues = issues
        
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        recommendation = PromptRecommendation(
            primary_prompt=result.get("primary_prompt", ""),
            priority_issues=priority_issues,
            strategy=result.get("strategy", "Fix issues in priority order"),
            complexity=result.get("complexity", self._estimate_complexity(issues)),
            alternative_prompts=alternative_prompts[:3],  # Max 3 alternatives
            context_files=result.get("context_files", context_files),
            estimated_tokens=self._estimate_tokens(result.get("primary_prompt", "")),
            generation_time_ms=generation_time_ms,
            veto_addressed=veto_triggered,
        )
        
        logger.info(
            f"Synthesized fix prompt: {recommendation.complexity} complexity, "
            f"{len(recommendation.priority_issues)} priority issues, "
            f"{generation_time_ms}ms"
        )
        
        return recommendation

    def save_recommendation(
        self,
        recommendation: PromptRecommendation,
        output_path: str = "fix_prompt.json",
    ) -> str:
        """Save recommendation to JSON file."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(recommendation.to_dict(), f, indent=2)
        
        logger.info(f"Saved fix prompt to: {output_path}")
        return output_path


# =============================================================================
# MODULE ENTRY POINT
# =============================================================================

def synthesize_fix_prompt(
    verdict_data: Dict[str, Any],
    spec_summary: str,
    file_tree: Optional[Dict[str, str]] = None,
    config_path: str = "config.yaml",
    output_path: Optional[str] = None,
) -> PromptRecommendation:
    """
    Main entry point for prompt synthesis.
    
    Args:
        verdict_data: Full tribunal verdict as dictionary
        spec_summary: Summary of original spec requirements
        file_tree: Optional dict of file paths to content
        config_path: Path to config.yaml
        output_path: Optional path to save the recommendation
        
    Returns:
        PromptRecommendation with synthesized fix prompts
    """
    synthesizer = PromptSynthesizer(config_path)
    recommendation = synthesizer.synthesize(verdict_data, spec_summary, file_tree)
    
    if output_path:
        synthesizer.save_recommendation(recommendation, output_path)
    
    return recommendation


if __name__ == "__main__":
    # Test the module
    import sys
    
    logger.add(sys.stderr, level="DEBUG")
    
    # Sample verdict data for testing
    test_verdict = {
        "overall_verdict": "FAIL",
        "overall_score": 4.5,
        "veto_triggered": True,
        "veto_reason": "SQL injection vulnerability detected with 92% confidence",
        "criterion_results": [
            {
                "criterion_type": "security",
                "average_score": 3.0,
                "veto_triggered": True,
                "relevant_files": ["auth.py"],
                "scores": [
                    {
                        "judge_name": "Security Judge",
                        "issues": [
                            "SQL injection in login function",
                            "Hardcoded database password",
                        ],
                        "suggestions": [
                            "Use parameterized queries",
                            "Move credentials to environment variables",
                        ],
                    }
                ],
            }
        ],
        "static_analysis_results": [
            {
                "tool": "bandit",
                "file_path": "auth.py",
                "issues": [
                    {"line": 15, "message": "Possible SQL injection", "is_critical": True}
                ],
            }
        ],
    }
    
    test_spec = """
    Build a secure authentication system with:
    - JWT-based login
    - Bcrypt password hashing
    - Rate limiting on auth endpoints
    """
    
    recommendation = synthesize_fix_prompt(
        test_verdict,
        test_spec,
        config_path="config.yaml",
        output_path="fix_prompt.json",
    )
    
    print("\n=== SYNTHESIZED FIX PROMPT ===")
    print(recommendation.primary_prompt)
    print(f"\nComplexity: {recommendation.complexity}")
    print(f"Strategy: {recommendation.strategy}")
