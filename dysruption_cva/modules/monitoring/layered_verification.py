"""Layered Constitutional Verification System.

This module implements a tiered verification approach:
- Layer 0: Git diff detection (detects what changed)
- Layer 1: Quick constitutional scan (regex only, free/local)
- Layer 2: Issue ranking with threshold escalation
- Layer 3: Full LLM verification (expensive, only when threshold exceeded)

Usage:
    daemon = LayeredVerificationDaemon(repo_path="/path/to/repo", constitution_path="constitution.md")
    await daemon.start()  # Runs persistent loop
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger


# =============================================================================
# LAYER 0: Git Diff Detector
# =============================================================================

@dataclass
class GitDiffResult:
    """Result from git diff detection."""
    changed_files: List[str]
    added_files: List[str]
    deleted_files: List[str]
    diff_content: str
    current_commit: str
    previous_commit: str
    has_changes: bool


class GitDiffDetector:
    """Detects file changes using git diff.
    
    This is more reliable than file system watching for detecting actual
    committed or staged changes.
    """
    
    def __init__(self, repo_path: str) -> None:
        self.repo_path = Path(repo_path).resolve()
        self._last_verified_commit: Optional[str] = None
        self._file_hashes: Dict[str, str] = {}
    
    def get_current_commit(self) -> Optional[str]:
        """Get the current HEAD commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Failed to get current commit: {e}")
        return None
    
    def get_uncommitted_changes(self) -> List[str]:
        """Get list of files with uncommitted changes (staged + unstaged)."""
        try:
            # Get staged changes
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            # Get unstaged changes
            unstaged = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            files = set()
            if staged.returncode == 0:
                files.update(staged.stdout.strip().split("\n"))
            if unstaged.returncode == 0:
                files.update(unstaged.stdout.strip().split("\n"))
            return [f for f in files if f]
        except Exception as e:
            logger.warning(f"Failed to get uncommitted changes: {e}")
            return []
    
    def get_diff_since_commit(self, since_commit: str) -> GitDiffResult:
        """Get diff between a commit and current HEAD."""
        current = self.get_current_commit() or "HEAD"
        
        try:
            # Get list of changed files with status
            result = subprocess.run(
                ["git", "diff", "--name-status", since_commit, "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            added: List[str] = []
            deleted: List[str] = []
            modified: List[str] = []
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        status, filepath = parts
                        if status.startswith("A"):
                            added.append(filepath)
                        elif status.startswith("D"):
                            deleted.append(filepath)
                        elif status.startswith("M") or status.startswith("R"):
                            modified.append(filepath)
            
            # Get actual diff content (limited for large diffs)
            diff_result = subprocess.run(
                ["git", "diff", "--stat", since_commit, "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            diff_content = diff_result.stdout if diff_result.returncode == 0 else ""
            
            all_changed = added + modified
            
            return GitDiffResult(
                changed_files=all_changed,
                added_files=added,
                deleted_files=deleted,
                diff_content=diff_content,
                current_commit=current,
                previous_commit=since_commit,
                has_changes=bool(all_changed or deleted)
            )
            
        except Exception as e:
            logger.error(f"Failed to get diff since {since_commit}: {e}")
            return GitDiffResult(
                changed_files=[],
                added_files=[],
                deleted_files=[],
                diff_content="",
                current_commit=current,
                previous_commit=since_commit,
                has_changes=False
            )
    
    def detect_changes(self) -> GitDiffResult:
        """Detect changes since last verification.
        
        Returns changes between last_verified_commit and current HEAD,
        plus any uncommitted changes.
        """
        current = self.get_current_commit()
        
        if self._last_verified_commit is None:
            # First run - just track current state
            uncommitted = self.get_uncommitted_changes()
            return GitDiffResult(
                changed_files=uncommitted,
                added_files=[],
                deleted_files=[],
                diff_content="",
                current_commit=current or "unknown",
                previous_commit="initial",
                has_changes=bool(uncommitted)
            )
        
        # Get committed changes since last verification
        result = self.get_diff_since_commit(self._last_verified_commit)
        
        # Also include uncommitted changes
        uncommitted = self.get_uncommitted_changes()
        for f in uncommitted:
            if f not in result.changed_files:
                result.changed_files.append(f)
        
        result = GitDiffResult(
            changed_files=result.changed_files,
            added_files=result.added_files,
            deleted_files=result.deleted_files,
            diff_content=result.diff_content,
            current_commit=current or "unknown",
            previous_commit=self._last_verified_commit,
            has_changes=bool(result.changed_files or result.deleted_files)
        )
        
        return result
    
    def mark_verified(self, commit: Optional[str] = None) -> None:
        """Mark current state as verified."""
        self._last_verified_commit = commit or self.get_current_commit()


# =============================================================================
# LAYER 1: Quick Constitutional Scan (Regex Only - FREE)
# =============================================================================

@dataclass
class QuickViolation:
    """A violation found during quick scan."""
    rule_id: str
    severity: str  # "critical", "high", "medium", "low"
    file: str
    line_start: int
    message: str
    pattern_matched: str


@dataclass
class QuickScanResult:
    """Result from quick constitutional scan."""
    violations: List[QuickViolation]
    files_scanned: int
    scan_time_ms: int
    total_score: int


class QuickConstitutionalScanner:
    """Fast local-only scanner using regex patterns.
    
    This is the "cheap" layer that runs locally without any API calls.
    Patterns are extracted from the constitution file.
    """
    
    # Default security patterns to check (always run these)
    DEFAULT_PATTERNS: List[Dict[str, Any]] = [
        # Secret Detection (inspired by Semgrep's 630+ credential patterns)
        {
            "rule_id": "SEC001",
            "severity": "critical",
            "pattern": r"(?i)(api[_-]?key|secret|password|token|credentials?)\s*=\s*['\"][^'\"]{8,}['\"]",
            "message": "Potential hardcoded secret detected"
        },
        {
            "rule_id": "SEC001b",
            "severity": "critical",
            "pattern": r"(?i)(?:aws|azure|gcp|github|gitlab|stripe|twilio|sendgrid|slack)[_-]?(?:secret|key|token)\s*=",
            "message": "Cloud/service credential detected"
        },
        {
            "rule_id": "SEC001c",
            "severity": "critical",
            "pattern": r"(?:sk_live_|pk_live_|rk_live_|sk_test_|pk_test_)[a-zA-Z0-9]+",
            "message": "Stripe API key detected"
        },
        {
            "rule_id": "SEC001d",
            "severity": "critical",
            "pattern": r"ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]+",
            "message": "GitHub personal access token detected"
        },
        # Code Execution
        {
            "rule_id": "SEC002",
            "severity": "critical",
            "pattern": r"\beval\s*\(",
            "message": "Use of eval() is dangerous"
        },
        {
            "rule_id": "SEC003",
            "severity": "high",
            "pattern": r"\bexec\s*\(",
            "message": "Use of exec() should be avoided"
        },
        {
            "rule_id": "SEC004",
            "severity": "high",
            "pattern": r"(?i)private[_-]?key|-----BEGIN\s+(RSA|PRIVATE|EC)\s+",
            "message": "Private key material detected"
        },
        {
            "rule_id": "SEC005",
            "severity": "medium",
            "pattern": r"\bos\.system\s*\(",
            "message": "os.system() can be a security risk"
        },
        {
            "rule_id": "SEC006",
            "severity": "medium",
            "pattern": r"subprocess\..*shell\s*=\s*True",
            "message": "subprocess with shell=True can be dangerous"
        },
        # XSS Detection (comprehensive patterns)
        {
            "rule_id": "XSS001",
            "severity": "high",
            "pattern": r"(?i)innerHTML\s*=|document\.write\s*\(",
            "message": "Potential XSS - unsafe DOM manipulation"
        },
        {
            "rule_id": "XSS002",
            "severity": "medium",
            "pattern": r"dangerouslySetInnerHTML",
            "message": "React dangerouslySetInnerHTML can enable XSS"
        },
        {
            "rule_id": "XSS003",
            "severity": "high",
            "pattern": r"\$\([^)]+\)\.html\s*\([^)]*(?:request|input|user|data)",
            "message": "jQuery .html() with user input - potential XSS"
        },
        {
            "rule_id": "XSS004",
            "severity": "critical",
            "pattern": r"(?i)render_template_string\s*\([^)]*(?:request|input|user)",
            "message": "Flask render_template_string with user input - SSTI/XSS"
        },
        {
            "rule_id": "XSS005",
            "severity": "medium",
            "pattern": r"\|\s*safe\s*}}|mark_safe\s*\(",
            "message": "Template safe filter - verify input is sanitized"
        },
        {
            "rule_id": "XSS006",
            "severity": "high",
            "pattern": r"(?i)v-html\s*=|ng-bind-html\s*=",
            "message": "Vue/Angular raw HTML binding - potential XSS"
        },
        {
            "rule_id": "XSS007",
            "severity": "medium",
            "pattern": r"(?i)insertAdjacentHTML\s*\(|outerHTML\s*=",
            "message": "DOM insertion method - verify input sanitization"
        },
        # Path Traversal
        {
            "rule_id": "PATH001",
            "severity": "high",
            "pattern": r"\.\./|\.\.\\\\",
            "message": "Path traversal pattern detected"
        },
        # SQL Injection (comprehensive patterns)
        {
            "rule_id": "SQL001",
            "severity": "critical",
            "pattern": r"(?i)(execute|cursor\.execute)\s*\(\s*[\"'].*\%[sd]",
            "message": "Potential SQL injection (string formatting in query)"
        },
        {
            "rule_id": "SQL002",
            "severity": "critical",
            "pattern": r"(?i)(?:select|insert|update|delete|drop)\s+.*\+\s*(?:request|input|user|params)",
            "message": "Potential SQL injection via string concatenation"
        },
        {
            "rule_id": "SQL003",
            "severity": "critical",
            "pattern": r"(?i)(?:execute|query|raw)\s*\(\s*f[\"']",
            "message": "Potential SQL injection (f-string in query)"
        },
        {
            "rule_id": "SQL004",
            "severity": "critical",
            "pattern": r"(?i)(?:execute|query)\s*\([^)]*\.format\s*\(",
            "message": "Potential SQL injection (.format() in query)"
        },
        {
            "rule_id": "SQL005",
            "severity": "high",
            "pattern": r"(?i)objects\.raw\s*\([^)]*\+|objects\.raw\s*\(\s*f[\"']|objects\.extra\s*\(",
            "message": "Django ORM raw/extra query - verify parameterization"
        },
        {
            "rule_id": "SQL006",
            "severity": "high",
            "pattern": r"(?i)text\s*\(\s*f[\"']|text\s*\([^)]*\.format\s*\(",
            "message": "SQLAlchemy text() with string interpolation"
        },
        {
            "rule_id": "SQL007",
            "severity": "critical",
            "pattern": r"(?i)(?:execute|query|run)\s*\(\s*['\"](?:select|insert|update|delete|drop)[^'\"]*['\"]?\s*\+",
            "message": "SQL query string concatenation detected"
        },
        # SSRF Detection (new)
        {
            "rule_id": "SSRF001",
            "severity": "high",
            "pattern": r"requests\.(?:get|post|put|delete)\s*\(\s*(?:request\.|user_|input|url_param)",
            "message": "Potential SSRF - user-controlled URL in request"
        },
        # Deserialization
        {
            "rule_id": "DES001",
            "severity": "critical",
            "pattern": r"pickle\.loads?\s*\(|yaml\.load\s*\([^,)]*\)|marshal\.loads?\s*\(",
            "message": "Unsafe deserialization detected"
        },
        # Cryptography
        {
            "rule_id": "CRYPTO001",
            "severity": "medium",
            "pattern": r"(?i)md5\s*\(|sha1\s*\(",
            "message": "Weak cryptographic hash function"
        },
        {
            "rule_id": "CRYPTO002",
            "severity": "high",
            "pattern": r"(?i)random\.random\s*\(|Math\.random\s*\(",
            "message": "Insecure random number generator (use secrets module)"
        },
        # Debug/Development
        {
            "rule_id": "DEBUG001",
            "severity": "medium",
            "pattern": r"(?i)debug\s*=\s*True|DEBUG_MODE\s*=\s*True",
            "message": "Debug mode enabled - disable in production"
        },
    ]
    
    # Severity scores for ranking
    SEVERITY_SCORES = {
        "critical": 25,
        "high": 10,
        "medium": 5,
        "low": 1,
        "info": 0
    }
    
    def __init__(self, constitution_path: Optional[str] = None) -> None:
        self.patterns = list(self.DEFAULT_PATTERNS)
        self._compiled_patterns: List[Tuple[re.Pattern, Dict[str, Any]]] = []
        
        if constitution_path:
            self._load_constitution_patterns(constitution_path)
        
        self._compile_patterns()
    
    def _load_constitution_patterns(self, constitution_path: str) -> None:
        """Extract regex patterns from constitution file."""
        try:
            content = Path(constitution_path).read_text(encoding="utf-8")
            
            # Look for JSON block with tribunal_rules
            import json
            match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", content)
            if match:
                data = json.loads(match.group(1))
                rules = data.get("tribunal_rules", [])
                for rule in rules:
                    if rule.get("type") == "regex" and rule.get("pattern"):
                        self.patterns.append({
                            "rule_id": rule.get("rule_id", "CONST"),
                            "severity": rule.get("severity", "medium"),
                            "pattern": rule["pattern"],
                            "message": rule.get("message", "Constitution rule violation")
                        })
        except Exception as e:
            logger.warning(f"Failed to load constitution patterns: {e}")
    
    def _compile_patterns(self) -> None:
        """Pre-compile all regex patterns for performance."""
        self._compiled_patterns = []
        for p in self.patterns:
            try:
                compiled = re.compile(p["pattern"])
                self._compiled_patterns.append((compiled, p))
            except re.error as e:
                logger.warning(f"Invalid pattern {p.get('rule_id')}: {e}")
    
    def scan_file(self, file_path: str, content: Optional[str] = None) -> List[QuickViolation]:
        """Scan a single file for violations."""
        violations: List[QuickViolation] = []
        
        if content is None:
            try:
                content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return violations
        
        for compiled, pattern_info in self._compiled_patterns:
            for match in compiled.finditer(content):
                # Calculate line number
                line_start = content.count("\n", 0, match.start()) + 1
                
                # Context-based false positive filtering
                # Get the line containing the match
                line_start_pos = content.rfind("\n", 0, match.start()) + 1
                line_end_pos = content.find("\n", match.end())
                if line_end_pos == -1:
                    line_end_pos = len(content)
                full_line = content[line_start_pos:line_end_pos]
                
                # Also get surrounding context (100 chars before and after)
                start_ctx = max(0, match.start() - 100)
                end_ctx = min(len(content), match.end() + 100)
                context = content[start_ctx:end_ctx]
                
                # Skip if this looks like validation/checking code (not actual usage)
                if pattern_info["rule_id"] == "PATH001":
                    validation_indicators = [
                        "startswith(", "endswith(", "if ", "raise ", 
                        "HTTPException", "error", "detail=", "message=",
                        "# ", '"""', "'''",  # Comments and docstrings
                    ]
                    if any(ind in context for ind in validation_indicators):
                        continue  # Skip - likely validation code
                    # Skip if the match is inside a string literal (error messages, examples)
                    if full_line.count('"') >= 2 or full_line.count("'") >= 2:
                        continue  # Likely in a string literal
                
                violations.append(QuickViolation(
                    rule_id=pattern_info["rule_id"],
                    severity=pattern_info["severity"],
                    file=str(file_path),
                    line_start=line_start,
                    message=pattern_info["message"],
                    pattern_matched=match.group(0)[:100]  # Truncate for safety
                ))
        
        return violations
    
    def scan_files(self, file_paths: List[str], base_path: Optional[str] = None) -> QuickScanResult:
        """Scan multiple files and aggregate results."""
        start = time.time()
        all_violations: List[QuickViolation] = []
        
        for fp in file_paths:
            full_path = Path(base_path) / fp if base_path else Path(fp)
            if full_path.exists() and full_path.is_file():
                violations = self.scan_file(str(full_path))
                all_violations.extend(violations)
        
        elapsed_ms = int((time.time() - start) * 1000)
        
        # Calculate total score
        total_score = sum(
            self.SEVERITY_SCORES.get(v.severity, 0)
            for v in all_violations
        )
        
        return QuickScanResult(
            violations=all_violations,
            files_scanned=len(file_paths),
            scan_time_ms=elapsed_ms,
            total_score=total_score
        )


# =============================================================================
# LAYER 2: Issue Ranker + Threshold Check
# =============================================================================

@dataclass
class EscalationDecision:
    """Decision on whether to escalate to LLM verification."""
    should_escalate: bool
    reason: str
    score: int
    threshold: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int


class IssueRanker:
    """Ranks issues and decides whether to escalate to expensive verification.
    
    The threshold system:
    - Any CRITICAL violation → immediate escalation
    - Score > threshold → escalation
    - Multiple HIGH violations → escalation
    """
    
    DEFAULT_THRESHOLD = 20  # Total score needed to trigger LLM
    MAX_CRITICALS_BEFORE_ESCALATE = 0  # Any critical = escalate
    MAX_HIGHS_BEFORE_ESCALATE = 2  # More than 2 highs = escalate
    
    def __init__(self, threshold: int = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold
    
    def evaluate(self, scan_result: QuickScanResult) -> EscalationDecision:
        """Evaluate scan results and decide on escalation."""
        
        # Count by severity
        critical_count = sum(1 for v in scan_result.violations if v.severity == "critical")
        high_count = sum(1 for v in scan_result.violations if v.severity == "high")
        medium_count = sum(1 for v in scan_result.violations if v.severity == "medium")
        low_count = sum(1 for v in scan_result.violations if v.severity == "low")
        
        # Decision logic
        should_escalate = False
        reason = "No issues requiring escalation"
        
        if critical_count > self.MAX_CRITICALS_BEFORE_ESCALATE:
            should_escalate = True
            reason = f"Critical violation detected ({critical_count} critical issues)"
        elif high_count > self.MAX_HIGHS_BEFORE_ESCALATE:
            should_escalate = True
            reason = f"Multiple high-severity issues ({high_count} high issues)"
        elif scan_result.total_score > self.threshold:
            should_escalate = True
            reason = f"Score {scan_result.total_score} exceeds threshold {self.threshold}"
        
        return EscalationDecision(
            should_escalate=should_escalate,
            reason=reason,
            score=scan_result.total_score,
            threshold=self.threshold,
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count
        )


# =============================================================================
# LAYER 3: Full LLM Verification (Expensive)
# =============================================================================

async def run_full_llm_verification(
    *,
    target_dir: str,
    constitution_path: str,
    changed_files: List[str],
) -> Dict[str, Any]:
    """Trigger full LLM-based verification.
    
    This integrates with the existing run_verification_pipeline.
    Only called when threshold is exceeded.
    """
    try:
        from modules.api import RunConfig, RunState, _runs, run_verification_pipeline
        import uuid
        
        run_id = f"layer3-{uuid.uuid4().hex[:8]}"
        
        config = RunConfig(
            target_dir=target_dir,
            spec_path="spec.txt",
            spec_content=Path(constitution_path).read_text(encoding="utf-8") if Path(constitution_path).exists() else "",
            config_path="config.yaml",
            generate_patches=False,
            watch_mode=False,
        )
        _runs[run_id] = RunState(run_id, config)
        
        await run_verification_pipeline(run_id)
        
        # Get results
        result = _runs.get(run_id)
        return {
            "run_id": run_id,
            "status": "completed" if result else "unknown",
            "verdict_path": getattr(result, "verdict_path", None),
        }
        
    except Exception as e:
        logger.error(f"Full LLM verification failed: {e}")
        return {"error": str(e)}


# =============================================================================
# PERSISTENT DAEMON: Ties All Layers Together
# =============================================================================

@dataclass
class VerificationCycleResult:
    """Result of one verification cycle."""
    timestamp: datetime
    git_diff: GitDiffResult
    quick_scan: Optional[QuickScanResult]
    escalation: Optional[EscalationDecision]
    llm_result: Optional[Dict[str, Any]]
    total_time_ms: int


class LayeredVerificationDaemon:
    """Persistent daemon running layered verification.
    
    This is the main entry point for continuous verification.
    It ties together all layers and runs them in a loop.
    """
    
    def __init__(
        self,
        repo_path: str,
        constitution_path: Optional[str] = None,
        poll_interval_seconds: float = 5.0,
        escalation_threshold: int = 20,
        on_violation_callback: Optional[callable] = None,
        on_escalation_callback: Optional[callable] = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.constitution_path = constitution_path
        self.poll_interval = poll_interval_seconds
        self.escalation_threshold = escalation_threshold
        self.on_violation_callback = on_violation_callback
        self.on_escalation_callback = on_escalation_callback
        
        # Initialize layers
        self.git_detector = GitDiffDetector(str(self.repo_path))
        self.quick_scanner = QuickConstitutionalScanner(constitution_path)
        self.ranker = IssueRanker(threshold=escalation_threshold)
        
        # State
        self._running = False
        self._last_result: Optional[VerificationCycleResult] = None
        self._history: List[VerificationCycleResult] = []
        
        # Supported file extensions for scanning
        self._code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs"}
    
    def _filter_code_files(self, files: List[str]) -> List[str]:
        """Filter to only code files we should scan."""
        return [
            f for f in files
            if Path(f).suffix.lower() in self._code_extensions
            and not any(ignore in f for ignore in ["node_modules", "__pycache__", ".git", "venv"])
        ]
    
    async def run_cycle(self) -> VerificationCycleResult:
        """Run one verification cycle through all layers."""
        start = time.time()
        
        # Layer 0: Detect changes
        logger.debug("Layer 0: Detecting git changes...")
        git_diff = self.git_detector.detect_changes()
        
        quick_scan = None
        escalation = None
        llm_result = None
        
        if git_diff.has_changes:
            # Filter to code files only
            code_files = self._filter_code_files(git_diff.changed_files)
            
            if code_files:
                # Layer 1: Quick scan
                logger.debug(f"Layer 1: Quick scanning {len(code_files)} files...")
                quick_scan = self.quick_scanner.scan_files(code_files, base_path=str(self.repo_path))
                
                if quick_scan.violations:
                    logger.info(f"Quick scan found {len(quick_scan.violations)} violations (score: {quick_scan.total_score})")
                    
                    if self.on_violation_callback:
                        try:
                            self.on_violation_callback(quick_scan)
                        except Exception as e:
                            logger.warning(f"Violation callback error: {e}")
                
                # Layer 2: Evaluate threshold
                logger.debug("Layer 2: Evaluating escalation threshold...")
                escalation = self.ranker.evaluate(quick_scan)
                
                if escalation.should_escalate:
                    logger.warning(f"Escalating to LLM verification: {escalation.reason}")
                    
                    if self.on_escalation_callback:
                        try:
                            self.on_escalation_callback(escalation)
                        except Exception as e:
                            logger.warning(f"Escalation callback error: {e}")
                    
                    # Layer 3: Full LLM verification
                    logger.info("Layer 3: Running full LLM verification...")
                    llm_result = await run_full_llm_verification(
                        target_dir=str(self.repo_path),
                        constitution_path=self.constitution_path or "",
                        changed_files=code_files,
                    )
            
            # Mark current state as verified
            self.git_detector.mark_verified()
        
        elapsed_ms = int((time.time() - start) * 1000)
        
        result = VerificationCycleResult(
            timestamp=datetime.utcnow(),
            git_diff=git_diff,
            quick_scan=quick_scan,
            escalation=escalation,
            llm_result=llm_result,
            total_time_ms=elapsed_ms
        )
        
        self._last_result = result
        self._history.append(result)
        
        # Keep last 100 results
        if len(self._history) > 100:
            self._history = self._history[-100:]
        
        return result
    
    async def start(self) -> None:
        """Start the persistent verification loop."""
        self._running = True
        logger.info(f"Starting layered verification daemon for {self.repo_path}")
        logger.info(f"Poll interval: {self.poll_interval}s, Escalation threshold: {self.escalation_threshold}")
        
        # Initial commit tracking
        initial_commit = self.git_detector.get_current_commit()
        if initial_commit:
            self.git_detector.mark_verified(initial_commit)
            logger.info(f"Initial commit: {initial_commit[:12]}")
        
        while self._running:
            try:
                result = await self.run_cycle()
                
                if result.git_diff.has_changes:
                    logger.info(
                        f"Cycle complete: {len(result.git_diff.changed_files)} files changed, "
                        f"quick_violations={len(result.quick_scan.violations) if result.quick_scan else 0}, "
                        f"escalated={result.escalation.should_escalate if result.escalation else False}, "
                        f"time={result.total_time_ms}ms"
                    )
                
            except Exception as e:
                logger.exception(f"Verification cycle error: {e}")
            
            await asyncio.sleep(self.poll_interval)
    
    def stop(self) -> None:
        """Stop the verification loop."""
        self._running = False
        logger.info("Stopping layered verification daemon")
    
    @property
    def last_result(self) -> Optional[VerificationCycleResult]:
        """Get the most recent verification result."""
        return self._last_result
    
    @property
    def history(self) -> List[VerificationCycleResult]:
        """Get verification history."""
        return list(self._history)


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Example usage of the layered verification daemon."""
    import sys
    
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "."
    constitution_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    def on_violation(scan_result: QuickScanResult):
        for v in scan_result.violations:
            print(f"  ⚠️  [{v.severity.upper()}] {v.rule_id}: {v.message}")
            print(f"      File: {v.file}:{v.line_start}")
    
    def on_escalation(decision: EscalationDecision):
        print(f"\n🚨 ESCALATING TO LLM: {decision.reason}")
        print(f"   Score: {decision.score}/{decision.threshold}")
    
    daemon = LayeredVerificationDaemon(
        repo_path=repo_path,
        constitution_path=constitution_path,
        poll_interval_seconds=3.0,
        escalation_threshold=20,
        on_violation_callback=on_violation,
        on_escalation_callback=on_escalation,
    )
    
    try:
        await daemon.start()
    except KeyboardInterrupt:
        daemon.stop()
        print("\nDaemon stopped.")


if __name__ == "__main__":
    asyncio.run(main())
