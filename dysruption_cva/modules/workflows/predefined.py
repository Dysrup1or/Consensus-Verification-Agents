"""
Predefined Workflows

Standard workflow implementations for common verification patterns.
These integrate with the existing tribunal and sandbox runner systems.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .base import Workflow, WorkflowContext, WorkflowResult, WorkflowStatus


class LintWorkflow(Workflow):
    """
    Fast static analysis workflow using pylint and bandit.
    
    This is typically the first workflow in a chain - it's fast and
    catches obvious issues before spending time/tokens on LLM judges.
    """
    
    @property
    def name(self) -> str:
        return "lint_check"
    
    @property
    def workflow_type(self) -> str:
        return "lint"
    
    @property
    def description(self) -> str:
        return "Static analysis with pylint and bandit"
    
    @property
    def abort_on_fail(self) -> bool:
        # Fatal syntax errors should abort the chain
        return True
    
    @property
    def file_patterns(self) -> List[str]:
        return ["*.py"]
    
    @property
    def estimated_duration_ms(self) -> int:
        return 5000  # ~5 seconds
    
    def __init__(
        self,
        run_pylint: bool = True,
        run_bandit: bool = True,
        fail_on_fatal_only: bool = True,
    ):
        self.run_pylint = run_pylint
        self.run_bandit = run_bandit
        self.fail_on_fatal_only = fail_on_fatal_only
    
    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Run static analysis tools."""
        
        # Filter to Python files
        py_files = self.filter_files(context.file_tree)
        
        if not py_files:
            return self.create_result(
                status=WorkflowStatus.SKIPPED,
                message="No Python files to analyze",
            )
        
        issues: List[Dict[str, Any]] = []
        fatal_issues = False
        
        # Create temp directory with files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write files
            for path, content in py_files.items():
                file_path = Path(tmpdir) / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
            
            # Run pylint
            if self.run_pylint:
                pylint_issues = await self._run_pylint(tmpdir, list(py_files.keys()))
                for issue in pylint_issues:
                    if issue.get("type") == "fatal":
                        fatal_issues = True
                issues.extend(pylint_issues)
            
            # Run bandit
            if self.run_bandit:
                bandit_issues = await self._run_bandit(tmpdir)
                for issue in bandit_issues:
                    if issue.get("severity") == "HIGH":
                        # High severity security issues are concerning but not fatal
                        pass
                issues.extend(bandit_issues)
        
        # Determine status and score
        if fatal_issues:
            status = WorkflowStatus.FAILED
            score = 0.0
            message = "Fatal syntax errors detected"
            abort_chain = True
        elif len(issues) > 20:
            status = WorkflowStatus.FAILED
            score = 0.3
            message = f"Too many issues: {len(issues)}"
            abort_chain = False
        elif len(issues) > 0:
            status = WorkflowStatus.PASSED
            score = max(0.5, 1.0 - (len(issues) * 0.05))
            message = f"Found {len(issues)} issues"
            abort_chain = False
        else:
            status = WorkflowStatus.PASSED
            score = 1.0
            message = "No issues found"
            abort_chain = False
        
        return self.create_result(
            status=status,
            score=score,
            message=message,
            issues=issues,
            abort_chain=abort_chain,
            abort_reason="Fatal syntax errors" if fatal_issues else "",
        )
    
    async def _run_pylint(self, tmpdir: str, files: List[str]) -> List[Dict]:
        """Run pylint and parse results."""
        try:
            result = subprocess.run(
                [
                    "pylint",
                    "--output-format=json",
                    "--disable=all",
                    "--enable=E,F",  # Errors and Fatal only
                    *files,
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=60,
            )
            
            if result.stdout:
                import json
                try:
                    data = json.loads(result.stdout)
                    return [
                        {
                            "tool": "pylint",
                            "type": item.get("type", "error"),
                            "file": item.get("path", ""),
                            "line": item.get("line", 0),
                            "message": item.get("message", ""),
                            "symbol": item.get("symbol", ""),
                            "severity": "high" if item.get("type") == "fatal" else "medium",
                        }
                        for item in data
                    ]
                except json.JSONDecodeError:
                    return []
            return []
        except subprocess.TimeoutExpired:
            logger.warning("Pylint timed out")
            return []
        except FileNotFoundError:
            logger.debug("Pylint not installed")
            return []
        except Exception as e:
            logger.error(f"Pylint error: {e}")
            return []
    
    async def _run_bandit(self, tmpdir: str) -> List[Dict]:
        """Run bandit and parse results."""
        try:
            result = subprocess.run(
                ["bandit", "-r", "-f", "json", "."],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=60,
            )
            
            if result.stdout:
                import json
                try:
                    data = json.loads(result.stdout)
                    return [
                        {
                            "tool": "bandit",
                            "type": "security",
                            "file": item.get("filename", ""),
                            "line": item.get("line_number", 0),
                            "message": item.get("issue_text", ""),
                            "severity": item.get("issue_severity", "MEDIUM"),
                            "confidence": item.get("issue_confidence", "MEDIUM"),
                        }
                        for item in data.get("results", [])
                    ]
                except json.JSONDecodeError:
                    return []
            return []
        except subprocess.TimeoutExpired:
            logger.warning("Bandit timed out")
            return []
        except FileNotFoundError:
            logger.debug("Bandit not installed")
            return []
        except Exception as e:
            logger.error(f"Bandit error: {e}")
            return []


class SecurityWorkflow(Workflow):
    """
    Security-focused verification workflow.
    
    Combines bandit analysis with security judge evaluation.
    Uses the judge marketplace if available.
    """
    
    @property
    def name(self) -> str:
        return "security_scan"
    
    @property
    def workflow_type(self) -> str:
        return "security"
    
    @property
    def description(self) -> str:
        return "Security vulnerability scanning and assessment"
    
    @property
    def abort_on_fail(self) -> bool:
        return True  # Security failures should abort
    
    @property
    def file_patterns(self) -> List[str]:
        return ["*.py", "*.js", "*.ts", "*.java"]
    
    @property
    def estimated_duration_ms(self) -> int:
        return 15000  # ~15 seconds with LLM
    
    def __init__(self, use_llm_judge: bool = True):
        self.use_llm_judge = use_llm_judge
    
    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Run security analysis."""
        
        issues: List[Dict] = []
        security_score = 1.0
        
        # Run bandit for Python files
        py_files = {k: v for k, v in context.file_tree.items() if k.endswith(".py")}
        
        if py_files:
            with tempfile.TemporaryDirectory() as tmpdir:
                for path, content in py_files.items():
                    file_path = Path(tmpdir) / path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content, encoding="utf-8")
                
                # Reuse bandit runner
                lint_workflow = LintWorkflow(run_pylint=False, run_bandit=True)
                bandit_issues = await lint_workflow._run_bandit(tmpdir)
                issues.extend(bandit_issues)
                
                # Penalize score based on severity
                for issue in bandit_issues:
                    if issue.get("severity") == "HIGH":
                        security_score -= 0.2
                    elif issue.get("severity") == "MEDIUM":
                        security_score -= 0.1
                    else:
                        security_score -= 0.05
        
        # Use LLM security judge if enabled
        if self.use_llm_judge and context.file_tree:
            try:
                llm_result = await self._run_security_judge(context)
                if llm_result:
                    issues.extend(llm_result.get("issues", []))
                    llm_score = llm_result.get("score", 1.0)
                    # Weight LLM score higher
                    security_score = (security_score + llm_score * 2) / 3
            except Exception as e:
                logger.warning(f"Security judge failed: {e}")
        
        security_score = max(0.0, min(1.0, security_score))
        
        # Determine status
        if security_score < 0.5:
            status = WorkflowStatus.FAILED
            message = f"Security score too low: {security_score:.2f}"
        elif len([i for i in issues if i.get("severity") == "HIGH"]) > 0:
            status = WorkflowStatus.FAILED
            message = "High severity security issues found"
        else:
            status = WorkflowStatus.PASSED
            message = f"Security check passed (score: {security_score:.2f})"
        
        return self.create_result(
            status=status,
            score=security_score,
            message=message,
            issues=issues,
            abort_chain=status == WorkflowStatus.FAILED,
            abort_reason="Security vulnerabilities detected" if status == WorkflowStatus.FAILED else "",
        )
    
    async def _run_security_judge(self, context: WorkflowContext) -> Optional[Dict]:
        """Run LLM security judge evaluation."""
        try:
            # Try to use judge marketplace
            from ..judge_marketplace import JudgeRegistry
            
            registry = JudgeRegistry()
            security_judges = registry.get_judges_by_domain("security")
            
            if security_judges:
                judge = security_judges[0]
                result = await judge.evaluate(context.file_tree, context.spec_content)
                return {
                    "issues": result.get("issues", []),
                    "score": result.get("score", 0.5),
                }
        except ImportError:
            logger.debug("Judge marketplace not available")
        except Exception as e:
            logger.debug(f"Judge marketplace error: {e}")
        
        # Fallback: Direct LLM call
        try:
            import litellm
            
            code_sample = "\n".join(
                f"# {path}\n{content[:500]}"
                for path, content in list(context.file_tree.items())[:5]
            )
            
            response = await litellm.acompletion(
                model=os.getenv("CVA_SECURITY_MODEL", "gpt-4o-mini"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a security expert. Analyze code for vulnerabilities. Respond with JSON: {\"score\": 0.0-1.0, \"issues\": [{\"file\": str, \"line\": int, \"message\": str, \"severity\": \"HIGH\"|\"MEDIUM\"|\"LOW\"}]}",
                    },
                    {
                        "role": "user",
                        "content": f"Analyze this code for security issues:\n\n{code_sample}",
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            
            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.debug(f"Direct LLM security check failed: {e}")
            return None


class StyleWorkflow(Workflow):
    """
    Code style and architecture verification workflow.
    
    Focuses on code quality, consistency, and best practices.
    """
    
    @property
    def name(self) -> str:
        return "style_check"
    
    @property
    def workflow_type(self) -> str:
        return "style"
    
    @property
    def description(self) -> str:
        return "Code style, consistency, and best practices"
    
    @property
    def abort_on_fail(self) -> bool:
        return False  # Style issues are not critical
    
    @property
    def file_patterns(self) -> List[str]:
        return ["*.py", "*.js", "*.ts"]
    
    @property
    def estimated_duration_ms(self) -> int:
        return 10000
    
    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Run style analysis."""
        
        issues: List[Dict] = []
        style_score = 1.0
        
        # Filter files
        files = self.filter_files(context.file_tree)
        
        if not files:
            return self.create_result(
                status=WorkflowStatus.SKIPPED,
                message="No applicable files",
            )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write files
            for path, content in files.items():
                file_path = Path(tmpdir) / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
            
            # Run pylint for style (convention messages)
            py_files = [p for p in files.keys() if p.endswith(".py")]
            if py_files:
                pylint_issues = await self._run_pylint_style(tmpdir, py_files)
                issues.extend(pylint_issues)
                style_score -= len(pylint_issues) * 0.02
        
        style_score = max(0.0, min(1.0, style_score))
        
        status = WorkflowStatus.PASSED if style_score >= 0.7 else WorkflowStatus.FAILED
        
        return self.create_result(
            status=status,
            score=style_score,
            message=f"Style score: {style_score:.2f} ({len(issues)} issues)",
            issues=issues,
            suggestions=[
                "Consider running 'black' or 'ruff' for auto-formatting",
                "Use consistent naming conventions",
            ] if issues else [],
        )
    
    async def _run_pylint_style(self, tmpdir: str, files: List[str]) -> List[Dict]:
        """Run pylint for style issues."""
        try:
            result = subprocess.run(
                [
                    "pylint",
                    "--output-format=json",
                    "--disable=all",
                    "--enable=C",  # Convention only
                    "--max-line-length=120",
                    *files,
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=60,
            )
            
            if result.stdout:
                import json
                try:
                    data = json.loads(result.stdout)
                    return [
                        {
                            "tool": "pylint",
                            "type": "style",
                            "file": item.get("path", ""),
                            "line": item.get("line", 0),
                            "message": item.get("message", ""),
                            "symbol": item.get("symbol", ""),
                            "severity": "low",
                        }
                        for item in data
                    ]
                except json.JSONDecodeError:
                    return []
            return []
        except Exception as e:
            logger.debug(f"Pylint style check failed: {e}")
            return []


class FullVerificationWorkflow(Workflow):
    """
    Complete 3-judge tribunal verification workflow.
    
    This is the most thorough verification, using the full tribunal
    system with Architect, User-Proxy, and Security judges.
    """
    
    @property
    def name(self) -> str:
        return "full_verification"
    
    @property
    def workflow_type(self) -> str:
        return "verification"
    
    @property
    def description(self) -> str:
        return "Complete tribunal verification with 3 LLM judges"
    
    @property
    def abort_on_fail(self) -> bool:
        return False  # Let the chain continue to report all issues
    
    @property
    def estimated_duration_ms(self) -> int:
        return 60000  # ~60 seconds with LLM calls
    
    def __init__(
        self,
        use_self_heal: bool = False,
        max_remediation_attempts: int = 2,
    ):
        self.use_self_heal = use_self_heal
        self.max_remediation_attempts = max_remediation_attempts
    
    async def execute(self, context: WorkflowContext) -> WorkflowResult:
        """Run full tribunal verification."""
        
        try:
            from ..tribunal import Tribunal
            
            # Initialize tribunal
            tribunal = Tribunal()
            
            # Run verification
            result = await tribunal.verify(
                file_tree=context.file_tree,
                spec_content=context.spec_content,
                target_dir=context.target_dir,
            )
            
            # Convert tribunal result to workflow result
            if result.final_verdict == "PASS":
                status = WorkflowStatus.PASSED
            elif result.final_verdict == "FAIL":
                status = WorkflowStatus.FAILED
            else:
                status = WorkflowStatus.FAILED
            
            # Extract issues from verdict
            issues = []
            for judge_verdict in result.judge_verdicts:
                for issue in judge_verdict.issues:
                    issues.append({
                        "judge": judge_verdict.role.value,
                        "file": issue.file,
                        "line": issue.line,
                        "message": issue.message,
                        "severity": issue.severity,
                    })
            
            return self.create_result(
                status=status,
                score=result.consensus_score,
                message=f"Tribunal verdict: {result.final_verdict}",
                issues=issues,
                suggestions=result.remediation_suggestions if hasattr(result, "remediation_suggestions") else [],
                raw_output=result.to_dict() if hasattr(result, "to_dict") else None,
            )
            
        except ImportError as e:
            logger.error(f"Tribunal not available: {e}")
            return self.create_result(
                status=WorkflowStatus.ERROR,
                message=f"Tribunal import error: {e}",
            )
        except Exception as e:
            logger.error(f"Tribunal verification failed: {e}")
            return self.create_result(
                status=WorkflowStatus.ERROR,
                message=f"Tribunal error: {e}",
            )


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_standard_chain():
    """
    Create the standard verification workflow chain.
    
    Order: Lint -> Security -> Full Verification
    
    Returns:
        WorkflowChain configured with standard workflows
    """
    from .chain import WorkflowChain, ChainExecutionMode
    
    chain = WorkflowChain(
        name="standard_verification",
        mode=ChainExecutionMode.ABORT_ON_REQUEST,
    )
    
    chain.add(LintWorkflow())
    chain.add(SecurityWorkflow())
    chain.add(FullVerificationWorkflow())
    
    return chain


def create_fast_chain():
    """
    Create a fast verification chain (no LLM calls).
    
    Order: Lint -> Style
    
    Returns:
        WorkflowChain with static analysis only
    """
    from .chain import WorkflowChain, ChainExecutionMode
    
    chain = WorkflowChain(
        name="fast_verification",
        mode=ChainExecutionMode.CONTINUE_ON_FAILURE,
    )
    
    chain.add(LintWorkflow())
    chain.add(StyleWorkflow())
    
    return chain


def create_security_chain():
    """
    Create a security-focused verification chain.
    
    Order: Security -> Full (with security judge priority)
    
    Returns:
        WorkflowChain focused on security
    """
    from .chain import WorkflowChain, ChainExecutionMode
    
    chain = WorkflowChain(
        name="security_verification",
        mode=ChainExecutionMode.FAIL_FAST,
    )
    
    chain.add(SecurityWorkflow(use_llm_judge=True))
    chain.add(FullVerificationWorkflow())
    
    return chain
