"""
Dysruption CVA - Refinement Module (Module E: Consensus-Based Prompt Refinement)

Analyzes REPORT.md failures and generates consensus-based refinement prompts
using feedback from the tribunal judges.

Features:
- Parses REPORT.md to extract failed criteria and judge feedback
- Uses tribunal consensus to weight importance of issues
- Generates targeted refinement prompts for iterative improvement
- Tracks improvement history across verification runs

Version: 2.0
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from loguru import logger

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class FailedCriterion:
    """Represents a failed criterion from REPORT.md"""
    criterion_id: str
    criterion_type: str  # security, functionality, style
    description: str
    score: float
    majority_ratio: float
    veto_triggered: bool
    issues: List[str]
    suggestions: List[str]
    relevant_files: List[str]
    judge_feedback: Dict[str, str]  # judge_name -> feedback


@dataclass
class ImprovementSuggestion:
    """A prioritized improvement suggestion"""
    priority: int  # 1 = highest
    criterion_id: str
    category: str
    title: str
    description: str
    affected_files: List[str]
    estimated_effort: str  # low, medium, high
    consensus_score: float  # 0.0-1.0, how much judges agree


@dataclass
class RefinementPrompt:
    """A generated refinement prompt for the user"""
    prompt_type: str  # fix_prompt, architecture_review, security_audit
    target_audience: str  # developer, ai_assistant, reviewer
    primary_prompt: str
    context_summary: str
    priority_issues: List[ImprovementSuggestion]
    success_criteria: List[str]
    estimated_time: str
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class RefinementHistory:
    """Tracks improvement history across runs"""
    run_id: str
    timestamp: datetime
    initial_score: float
    final_score: float
    criteria_fixed: List[str]
    criteria_still_failing: List[str]
    refinement_prompts_used: List[str]


# =============================================================================
# REPORT PARSER
# =============================================================================


class ReportParser:
    """Parses REPORT.md to extract structured failure information."""

    def __init__(self, report_path: str = "REPORT.md"):
        self.report_path = Path(report_path)

    def parse(self) -> Tuple[Dict[str, Any], List[FailedCriterion]]:
        """
        Parse REPORT.md and extract summary and failed criteria.
        
        Returns:
            Tuple of (summary_dict, list_of_failed_criteria)
        """
        if not self.report_path.exists():
            logger.warning(f"Report not found: {self.report_path}")
            return {}, []

        content = self.report_path.read_text(encoding="utf-8")
        
        summary = self._parse_summary(content)
        failed_criteria = self._parse_failed_criteria(content)
        
        return summary, failed_criteria

    def _parse_summary(self, content: str) -> Dict[str, Any]:
        """Extract summary section from report."""
        summary = {
            "overall_verdict": "UNKNOWN",
            "overall_score": 0.0,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "veto_triggered": False,
            "static_issues": 0,
        }

        # Parse overall verdict
        verdict_match = re.search(r"\*\*Overall Verdict\*\*\s*\|\s*[🔴❌✅⚠️🚫]*\s*\*\*(\w+)\*\*", content)
        if verdict_match:
            summary["overall_verdict"] = verdict_match.group(1)

        # Parse score
        score_match = re.search(r"\*\*Overall Score\*\*\s*\|\s*[🟢🟡🔴]*\s*([\d.]+)/10", content)
        if score_match:
            summary["overall_score"] = float(score_match.group(1))

        # Parse criteria counts
        passed_match = re.search(r"\*\*Criteria Passed\*\*\s*\|\s*(\d+)/(\d+)", content)
        if passed_match:
            summary["passed"] = int(passed_match.group(1))
            summary["total"] = int(passed_match.group(2))

        failed_match = re.search(r"\*\*Criteria Failed\*\*\s*\|\s*(\d+)/(\d+)", content)
        if failed_match:
            summary["failed"] = int(failed_match.group(1))

        # Parse veto status
        if "🚫 Yes" in content or "VETO TRIGGERED" in content:
            summary["veto_triggered"] = True

        # Parse static issues
        static_match = re.search(r"\*\*Static Analysis Issues\*\*\s*\|\s*(\d+)", content)
        if static_match:
            summary["static_issues"] = int(static_match.group(1))

        return summary

    def _parse_failed_criteria(self, content: str) -> List[FailedCriterion]:
        """Extract failed criteria with judge feedback."""
        failed = []
        
        # Pattern for criterion blocks
        # Matches: #### ❌ S1: Description or #### 🚫 F2: Description
        criterion_pattern = re.compile(
            r"####\s*[❌🚫⚠️]\s*([SF]?\d+):\s*(.+?)(?:\s*🚫\*\*VETO\*\*)?\n"
            r".*?- \*\*Score\*\*:\s*[🟢🟡🔴]*\s*([\d.]+)/10\n"
            r".*?- \*\*Majority\*\*:\s*([\d.]+)%\n"
            r".*?- \*\*Verdict\*\*:\s*(\w+)",
            re.DOTALL
        )

        # Find all failed criteria
        for match in criterion_pattern.finditer(content):
            criterion_id = match.group(1)
            description = match.group(2).strip()
            score = float(match.group(3))
            majority = float(match.group(4)) / 100
            verdict = match.group(5)
            
            # Skip passed criteria
            if verdict == "PASS":
                continue

            # Determine type from ID prefix
            if criterion_id.startswith("S"):
                ctype = "security"
            elif criterion_id.startswith("F"):
                ctype = "functionality"
            else:
                ctype = "style"

            # Extract judge details from the collapsible section
            judge_section_start = match.end()
            judge_section_end = content.find("####", judge_section_start)
            if judge_section_end == -1:
                judge_section_end = len(content)
            
            judge_section = content[judge_section_start:judge_section_end]
            
            # Parse judge feedback
            judge_feedback = {}
            issues = []
            suggestions = []
            
            # Pattern: **Judge Name** (Score: X/10): feedback...
            judge_pattern = re.compile(
                r"\*\*([^*]+)\*\*\s*\(Score:\s*(\d+)/10(?:\s*🚫VETO)?\):\s*([^*]+?)(?=\*\*|\Z)",
                re.DOTALL
            )
            
            for judge_match in judge_pattern.finditer(judge_section):
                judge_name = judge_match.group(1).strip()
                feedback = judge_match.group(3).strip()
                judge_feedback[judge_name] = feedback
                
                # Extract issues from feedback (look for issue patterns)
                if "issue" in feedback.lower() or "problem" in feedback.lower():
                    issues.append(feedback[:200])
            
            # Look for files mentioned
            file_pattern = re.compile(r"\*\*Files\*\*:\s*([^\n]+)")
            files_match = file_pattern.search(judge_section)
            relevant_files = []
            if files_match:
                files_str = files_match.group(1)
                relevant_files = [f.strip() for f in files_str.split(",") if f.strip() != "N/A"]

            veto_triggered = "VETO" in verdict or "🚫" in description

            failed.append(FailedCriterion(
                criterion_id=criterion_id,
                criterion_type=ctype,
                description=description,
                score=score,
                majority_ratio=majority,
                veto_triggered=veto_triggered,
                issues=issues,
                suggestions=suggestions,
                relevant_files=relevant_files,
                judge_feedback=judge_feedback,
            ))

        logger.info(f"Parsed {len(failed)} failed criteria from report")
        return failed


# =============================================================================
# REFINEMENT GENERATOR
# =============================================================================


class RefinementGenerator:
    """
    Generates consensus-based refinement prompts from tribunal feedback.
    Uses weighted judge feedback to prioritize issues.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.llms_config = self.config.get("llms", {})
        self.synthesizer_model = self.llms_config.get("synthesizer", {}).get(
            "model", "anthropic/claude-sonnet-4-20250514"
        )

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML."""
        config_file = Path(config_path)
        if not config_file.exists():
            return {}
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def prioritize_issues(
        self, 
        failed_criteria: List[FailedCriterion]
    ) -> List[ImprovementSuggestion]:
        """
        Prioritize issues based on consensus and severity.
        
        Priority order:
        1. Veto-triggered (security) issues
        2. Low-score security issues
        3. Low-score functionality issues
        4. Style issues
        """
        suggestions = []
        
        # Sort criteria by priority
        def priority_key(c: FailedCriterion) -> Tuple[int, float]:
            type_priority = {
                "security": 0,
                "functionality": 1,
                "style": 2,
            }
            veto_bonus = -100 if c.veto_triggered else 0
            return (type_priority.get(c.criterion_type, 3) + veto_bonus, c.score)
        
        sorted_criteria = sorted(failed_criteria, key=priority_key)
        
        for i, criterion in enumerate(sorted_criteria, 1):
            # Calculate consensus score (how much judges agree)
            if criterion.judge_feedback:
                # More judges mentioning issues = higher consensus
                consensus = min(1.0, len(criterion.judge_feedback) / 3.0)
            else:
                consensus = criterion.majority_ratio
            
            # Estimate effort based on score gap
            score_gap = 7 - criterion.score  # 7 is pass threshold
            if score_gap <= 2:
                effort = "low"
            elif score_gap <= 4:
                effort = "medium"
            else:
                effort = "high"
            
            suggestions.append(ImprovementSuggestion(
                priority=i,
                criterion_id=criterion.criterion_id,
                category=criterion.criterion_type,
                title=criterion.description[:80],
                description=self._summarize_feedback(criterion),
                affected_files=criterion.relevant_files[:5],
                estimated_effort=effort,
                consensus_score=consensus,
            ))
        
        return suggestions

    def _summarize_feedback(self, criterion: FailedCriterion) -> str:
        """Summarize judge feedback into actionable description."""
        parts = []
        
        if criterion.veto_triggered:
            parts.append("🚫 VETO: Critical security issue requiring immediate fix.")
        
        parts.append(f"Score: {criterion.score}/10 (need 7+ to pass)")
        
        for judge, feedback in criterion.judge_feedback.items():
            # Take first sentence or 100 chars
            short_feedback = feedback.split(".")[0][:100]
            parts.append(f"• {judge}: {short_feedback}")
        
        return "\n".join(parts)

    def generate_refinement_prompt(
        self,
        summary: Dict[str, Any],
        failed_criteria: List[FailedCriterion],
        spec_summary: Optional[str] = None,
        file_tree: Optional[Dict[str, str]] = None,
    ) -> RefinementPrompt:
        """
        Generate a comprehensive refinement prompt based on tribunal feedback.
        
        Uses consensus weighting to prioritize the most important issues
        that all judges agree need fixing.
        """
        # Prioritize issues
        priority_issues = self.prioritize_issues(failed_criteria)
        
        # Build context summary
        context_parts = [
            f"## Verification Summary",
            f"- Overall Verdict: {summary.get('overall_verdict', 'FAIL')}",
            f"- Score: {summary.get('overall_score', 0)}/10",
            f"- Passed: {summary.get('passed', 0)}/{summary.get('total', 0)} criteria",
            f"- Veto Triggered: {'Yes' if summary.get('veto_triggered') else 'No'}",
        ]
        
        if summary.get("veto_triggered"):
            context_parts.append("\n⚠️ SECURITY VETO: A critical security issue was identified.")
        
        context_summary = "\n".join(context_parts)
        
        # Build primary prompt
        prompt_parts = [
            "# Code Refinement Required",
            "",
            "The Dysruption CVA has identified issues that need to be fixed.",
            "Below are the prioritized issues based on consensus from multiple AI judges.",
            "",
            "## Priority Issues to Fix",
        ]
        
        # Add top 5 priority issues
        for issue in priority_issues[:5]:
            prompt_parts.append(f"\n### P{issue.priority}: [{issue.category.upper()}] {issue.title}")
            prompt_parts.append(issue.description)
            if issue.affected_files:
                prompt_parts.append(f"Files: {', '.join(issue.affected_files)}")
            prompt_parts.append(f"Effort: {issue.estimated_effort} | Consensus: {issue.consensus_score:.0%}")
        
        # Add success criteria
        success_criteria = [
            f"Score of 7+/10 on all criteria",
            f"No security veto triggers",
            f"Consensus pass from at least 2/3 judges",
        ]
        
        if any(c.criterion_type == "security" for c in failed_criteria):
            success_criteria.insert(0, "All security vulnerabilities addressed")
        
        prompt_parts.append("\n## Success Criteria")
        for sc in success_criteria:
            prompt_parts.append(f"- {sc}")
        
        # Estimate time
        high_effort = sum(1 for i in priority_issues if i.estimated_effort == "high")
        med_effort = sum(1 for i in priority_issues if i.estimated_effort == "medium")
        estimated_hours = high_effort * 2 + med_effort * 1 + len(priority_issues) * 0.5
        estimated_time = f"{estimated_hours:.1f} hours"
        
        primary_prompt = "\n".join(prompt_parts)
        
        return RefinementPrompt(
            prompt_type="fix_prompt",
            target_audience="ai_assistant",
            primary_prompt=primary_prompt,
            context_summary=context_summary,
            priority_issues=priority_issues,
            success_criteria=success_criteria,
            estimated_time=estimated_time,
        )

    async def generate_with_llm(
        self,
        summary: Dict[str, Any],
        failed_criteria: List[FailedCriterion],
        spec_summary: Optional[str] = None,
    ) -> RefinementPrompt:
        """
        Use LLM to generate a more sophisticated refinement prompt.
        Falls back to rule-based generation if LLM fails.
        """
        if not LITELLM_AVAILABLE:
            logger.warning("LiteLLM not available, using rule-based generation")
            return self.generate_refinement_prompt(summary, failed_criteria, spec_summary)
        
        try:
            # Build LLM prompt
            system_prompt = """You are an expert code review advisor. Your task is to analyze 
verification failures and generate a clear, actionable refinement prompt that will help 
fix the identified issues. Focus on:
1. The most critical issues first (security vetoes, then low scores)
2. Specific, actionable steps to fix each issue
3. Success criteria that can be verified
4. Realistic time estimates"""

            user_content = f"""## Verification Failed

Summary:
{json.dumps(summary, indent=2)}

Failed Criteria:
{json.dumps([{
    "id": c.criterion_id,
    "type": c.criterion_type,
    "description": c.description,
    "score": c.score,
    "veto": c.veto_triggered,
    "issues": c.issues[:3],
    "files": c.relevant_files[:3],
} for c in failed_criteria], indent=2)}

Generate a comprehensive refinement prompt in JSON format with:
- primary_prompt: The main prompt text
- priority_issues: List of prioritized issues with titles and descriptions
- success_criteria: List of success criteria
- estimated_time: Time estimate string"""

            response = litellm.completion(
                model=self.synthesizer_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=4096,
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            
            # Try to parse JSON from response
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                data = json.loads(json_match.group())
                
                # Convert to RefinementPrompt
                priority_issues = [
                    ImprovementSuggestion(
                        priority=i+1,
                        criterion_id=p.get("criterion_id", f"I{i+1}"),
                        category=p.get("category", "general"),
                        title=p.get("title", "Issue"),
                        description=p.get("description", ""),
                        affected_files=p.get("files", []),
                        estimated_effort=p.get("effort", "medium"),
                        consensus_score=0.8,
                    )
                    for i, p in enumerate(data.get("priority_issues", []))
                ]
                
                return RefinementPrompt(
                    prompt_type="fix_prompt",
                    target_audience="ai_assistant",
                    primary_prompt=data.get("primary_prompt", content),
                    context_summary=f"Score: {summary.get('overall_score')}/10",
                    priority_issues=priority_issues,
                    success_criteria=data.get("success_criteria", []),
                    estimated_time=data.get("estimated_time", "Unknown"),
                )
            
            # If no JSON, use the raw response
            return RefinementPrompt(
                prompt_type="fix_prompt",
                target_audience="ai_assistant",
                primary_prompt=content,
                context_summary=f"Score: {summary.get('overall_score')}/10",
                priority_issues=self.prioritize_issues(failed_criteria),
                success_criteria=["Achieve passing score on all criteria"],
                estimated_time="Unknown",
            )
            
        except Exception as e:
            logger.warning(f"LLM refinement failed: {e}, using rule-based")
            return self.generate_refinement_prompt(summary, failed_criteria, spec_summary)


# =============================================================================
# MODULE ENTRY POINT
# =============================================================================


def analyze_and_refine(
    report_path: str = "REPORT.md",
    config_path: str = "config.yaml",
    spec_summary: Optional[str] = None,
) -> RefinementPrompt:
    """
    Main entry point: Analyze REPORT.md and generate refinement prompt.
    
    Args:
        report_path: Path to REPORT.md
        config_path: Path to config.yaml
        spec_summary: Optional specification summary for context
    
    Returns:
        RefinementPrompt with prioritized issues and actionable steps
    """
    # Parse report
    parser = ReportParser(report_path)
    summary, failed_criteria = parser.parse()
    
    if not failed_criteria:
        logger.info("No failed criteria found - verification passed!")
        return RefinementPrompt(
            prompt_type="success",
            target_audience="developer",
            primary_prompt="✅ All verification criteria passed! No refinements needed.",
            context_summary=f"Score: {summary.get('overall_score', 10)}/10",
            priority_issues=[],
            success_criteria=["All criteria met"],
            estimated_time="0 hours",
        )
    
    # Generate refinement prompt
    generator = RefinementGenerator(config_path)
    return generator.generate_refinement_prompt(
        summary=summary,
        failed_criteria=failed_criteria,
        spec_summary=spec_summary,
    )


def save_refinement_prompt(
    prompt: RefinementPrompt,
    output_path: str = "REFINEMENT.md",
) -> str:
    """Save refinement prompt to markdown file."""
    
    lines = [
        "# Refinement Prompt",
        f"Generated: {prompt.generated_at.isoformat()}",
        f"Type: {prompt.prompt_type}",
        f"Target: {prompt.target_audience}",
        f"Estimated Time: {prompt.estimated_time}",
        "",
        "---",
        "",
        "## Context",
        prompt.context_summary,
        "",
        "---",
        "",
        prompt.primary_prompt,
        "",
        "---",
        "",
        "## Success Criteria",
    ]
    
    for sc in prompt.success_criteria:
        lines.append(f"- [ ] {sc}")
    
    content = "\n".join(lines)
    
    Path(output_path).write_text(content, encoding="utf-8")
    logger.info(f"Saved refinement prompt to: {output_path}")
    
    return output_path


if __name__ == "__main__":
    import sys
    
    logger.add(sys.stderr, level="DEBUG")
    
    # Test the module
    prompt = analyze_and_refine()
    save_refinement_prompt(prompt)
    
    print("\n" + "=" * 60)
    print("REFINEMENT PROMPT")
    print("=" * 60)
    print(prompt.primary_prompt[:500] + "...")
    print(f"\nPriority Issues: {len(prompt.priority_issues)}")
    print(f"Estimated Time: {prompt.estimated_time}")
