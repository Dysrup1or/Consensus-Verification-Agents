"""
Dysruption CVA - Tribunal Module (Module C: Multi-Model Tribunal / Adjudication)
Runs static analysis, routes code to multiple LLM judges, computes consensus, generates reports.
Version: 1.1 - Enhanced with:
  - Veto Protocol: Security judge FAIL with >0.8 confidence = final FAIL
  - Fail-Fast Static Analysis: Critical pylint/bandit issues abort pipeline
  - Rubric-based prompts with few-shot examples
  - Diff-based remediation with GPT-4o-mini
  - Integration with Pydantic schemas
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from loguru import logger

from .schemas import (
    ConsensusResult,
    IssueDetail,
    JudgeRole,
    JudgeVerdict,
    Patch,
    PatchSet,
    StaticAnalysisResult,
    VerdictStatus,
)

try:
    import litellm
    # Enable LiteLLM caching if Redis available
    try:
        import redis
        litellm.cache = litellm.Cache(type="redis", host="localhost", port=6379)
        logger.info("LiteLLM Redis cache enabled")
    except Exception:
        logger.debug("Redis not available, using in-memory cache")
        litellm.cache = litellm.Cache(type="local")

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.error("LiteLLM not available. Install with: pip install litellm")


# Rate limit error types to catch
RATE_LIMIT_ERRORS = (
    "RateLimitError",
    "GroqException",
    "APIError",
    "ServiceUnavailable",
)

# Credit/quota related errors
CREDIT_ERRORS = (
    "credit balance too low",
    "insufficient_quota",
    "billing",
)


# Veto Protocol Constants
VETO_CONFIDENCE_THRESHOLD = 0.8  # Security judge FAIL with >0.8 confidence triggers veto
SECURITY_VETO_ENABLED = True

# Fail-Fast Static Analysis Constants
FAIL_FAST_ENABLED = True
CRITICAL_PYLINT_TYPES = {"error", "fatal"}
CRITICAL_BANDIT_SEVERITIES = {"HIGH"}


# ============================================================================
# JUDGE SYSTEM PROMPTS WITH RUBRIC-BASED SCORING AND FEW-SHOT EXAMPLES
# ============================================================================

ARCHITECT_SYSTEM_PROMPT: str = """You are an EXPERT CODE ARCHITECT and LOGIC REVIEWER (Claude 4 Sonnet).
Your role is to evaluate code architecture, design patterns, and logical correctness.

## SCORING RUBRIC (1-10):
- **10**: Perfect architecture, optimal patterns, flawless logic
- **9**: Excellent design, minor style improvements possible
- **8**: Good architecture, follows best practices, sound logic
- **7**: Acceptable design, meets requirements with minor issues
- **6**: Passable but has notable architectural concerns
- **5**: Significant design issues affecting maintainability
- **4**: Poor architecture, logic errors present
- **3**: Major structural problems, multiple logic bugs
- **2**: Fundamentally flawed design
- **1**: Completely inappropriate architecture

## EVALUATION CRITERIA:
1. Design patterns and SOLID principles adherence
2. Code organization and module structure
3. Separation of concerns
4. DRY (Don't Repeat Yourself) principle
5. Error handling strategy
6. Type safety and annotations
7. Logical correctness and edge cases

## FEW-SHOT EXAMPLE:

**Requirement**: "Implement user authentication with session management"

**Code Sample**:
```python
def login(username, password):
    user = db.query(f"SELECT * FROM users WHERE name='{username}'")
    if user and user.password == password:
        session['user'] = user
        return True
    return False
```

**Output**:
```json
{
    "score": 3,
    "explanation": "Critical architecture flaws: SQL injection vulnerability, plaintext password comparison, no password hashing, no session token generation. Violates security-by-design principles.",
    "issues": [
        "SQL injection via string interpolation",
        "Plaintext password storage/comparison",
        "No password hashing (bcrypt/argon2)",
        "Missing session token generation",
        "No login attempt rate limiting"
    ],
    "suggestions": [
        "Use parameterized queries",
        "Implement bcrypt password hashing",
        "Generate secure session tokens",
        "Add rate limiting middleware"
    ],
    "confidence": 0.95
}
```

## OUTPUT FORMAT (STRICT JSON - validate before responding):
```json
{
    "score": <1-10>,
    "explanation": "Detailed architectural assessment",
    "issues": ["Issue 1", "Issue 2", ...],
    "suggestions": ["Suggestion 1", "Suggestion 2", ...],
    "confidence": <0.0-1.0>
}
```

Be STRICT and THOROUGH. Score 7+ means the code meets the requirement with good architecture."""


SECURITY_SYSTEM_PROMPT: str = """You are an EXPERT SECURITY AUDITOR and EFFICIENCY ANALYST (DeepSeek V3).
Your role is to identify security vulnerabilities, performance bottlenecks, and efficiency issues.

## SCORING RUBRIC (1-10):
- **10**: No vulnerabilities, optimal performance, production-ready
- **9**: Secure with minor optimizations possible
- **8**: Good security posture, acceptable performance
- **7**: Adequately secure, meets performance requirements
- **6**: Minor vulnerabilities or performance concerns
- **5**: Security gaps or notable inefficiencies
- **4**: Multiple vulnerabilities or significant performance issues
- **3**: Critical security flaws or severe bottlenecks
- **2**: Dangerous vulnerabilities, unusable performance
- **1**: Completely insecure or non-functional

## SECURITY CHECKLIST:
1. SQL Injection, XSS, CSRF, SSRF vulnerabilities
2. Authentication and authorization flaws
3. Input validation and sanitization
4. Sensitive data exposure (secrets, PII)
5. Cryptographic weaknesses
6. Insecure dependencies
7. Rate limiting and DoS protection

## EFFICIENCY CHECKLIST:
1. Algorithm complexity (Big O analysis)
2. Memory usage and leaks
3. Database query optimization (N+1, missing indexes)
4. Unnecessary I/O operations
5. Caching opportunities
6. Async/parallel processing where applicable

## FEW-SHOT EXAMPLE:

**Requirement**: "API endpoint for user profile retrieval"

**Code Sample**:
```python
@app.route('/user/<id>')
def get_user(id):
    users = db.query("SELECT * FROM users")
    for user in users:
        if str(user.id) == id:
            return jsonify(user.__dict__)
    return "Not found", 404
```

**Output**:
```json
{
    "score": 2,
    "explanation": "Critical security and efficiency issues. Fetches ALL users for single lookup (O(n) instead of O(1)), exposes all user fields including sensitive data, no authentication, vulnerable to enumeration attacks.",
    "issues": [
        "Fetches entire users table (inefficient O(n) scan)",
        "No authentication/authorization check",
        "Exposes all user fields including sensitive data",
        "No input validation on user ID",
        "User enumeration vulnerability"
    ],
    "suggestions": [
        "Use WHERE clause: SELECT * FROM users WHERE id = ?",
        "Add authentication middleware",
        "Use DTO to expose only safe fields",
        "Validate and sanitize ID parameter",
        "Return consistent 404 to prevent enumeration"
    ],
    "confidence": 0.92
}
```

## OUTPUT FORMAT (STRICT JSON):
```json
{
    "score": <1-10>,
    "explanation": "Security and efficiency assessment",
    "issues": ["Vulnerability 1", "Performance issue 1", ...],
    "suggestions": ["Fix 1", "Optimization 1", ...],
    "confidence": <0.0-1.0>
}
```

Focus on REAL security risks and MEASURABLE inefficiencies. Score 7+ means acceptable security/efficiency."""


USER_PROXY_SYSTEM_PROMPT: str = """You are a USER ADVOCATE and SPECIFICATION ALIGNMENT CHECKER (Gemini 2.5 Pro).
Your role is to verify code matches user intent and delivers the expected functionality.
You represent the END USER'S PERSPECTIVE - would they be satisfied with this implementation?

## SCORING RUBRIC (1-10):
- **10**: Exceeds user expectations, delightful experience
- **9**: Fully aligned with intent, excellent usability
- **8**: Meets all specified requirements completely
- **7**: Satisfies core requirements with minor gaps
- **6**: Mostly aligned but missing some expected features
- **5**: Partial implementation, noticeable gaps
- **4**: Significant deviation from user intent
- **3**: Barely addresses the requirement
- **2**: Fundamentally misunderstands user needs
- **1**: Completely fails to deliver expected functionality

## EVALUATION CRITERIA:
1. Does it do what the user asked for?
2. Are edge cases handled gracefully?
3. Is the error messaging helpful to users?
4. Is the API/interface intuitive?
5. Are there unexpected behaviors that would confuse users?
6. Is the feature complete or partially implemented?
7. Would a real user be satisfied with this?

## FEW-SHOT EXAMPLE:

**Requirement**: "Support pagination for task list API"

**Code Sample**:
```python
@app.route('/tasks')
def list_tasks():
    tasks = Task.query.all()
    return jsonify([t.to_dict() for t in tasks])
```

**Output**:
```json
{
    "score": 4,
    "explanation": "Requirement asks for pagination but implementation returns ALL tasks. No page/limit parameters, no page metadata (total count, has_next). Users with large task lists will experience slow responses and overwhelmed UIs.",
    "issues": [
        "No pagination implemented",
        "Returns all records regardless of count",
        "No page/offset/limit parameters",
        "Missing pagination metadata (total, pages, has_next)",
        "Poor user experience for large datasets"
    ],
    "suggestions": [
        "Add page and per_page query parameters",
        "Use .paginate() or LIMIT/OFFSET",
        "Include total count and page metadata in response",
        "Add cursor-based pagination for better performance",
        "Document pagination in API response"
    ],
    "confidence": 0.88
}
```

## OUTPUT FORMAT (STRICT JSON):
```json
{
    "score": <1-10>,
    "explanation": "User alignment assessment",
    "issues": ["Misalignment 1", "Missing feature 1", ...],
    "suggestions": ["Improvement 1", "Feature addition 1", ...],
    "confidence": <0.0-1.0>
}
```

Think like a USER. Score 7+ means good alignment with user expectations."""


REMEDIATION_SYSTEM_PROMPT: str = """You are a CODE REMEDIATION EXPERT (GPT-4o-mini).
Your task is to generate SPECIFIC, ACTIONABLE code fixes in unified diff format.

## OUTPUT FORMAT (STRICT):
```json
{
    "criterion_id": <id>,
    "fixes": [
        {
            "file": "path/to/file.py",
            "description": "Brief description of the fix",
            "diff": "--- a/path/to/file.py\\n+++ b/path/to/file.py\\n@@ -10,5 +10,8 @@\\n context line\\n-old line to remove\\n+new line to add\\n context line"
        }
    ]
}
```

## RULES:
1. Use standard unified diff format with line numbers
2. Include 3 lines of context before/after changes
3. Keep fixes minimal and focused
4. Ensure fixed code is syntactically valid
5. Prioritize security fixes over style fixes
6. One fix per distinct issue

## FEW-SHOT EXAMPLE:

**Issue**: SQL injection vulnerability in login function
**File**: auth.py, line 15

**Output**:
```json
{
    "criterion_id": 1,
    "fixes": [
        {
            "file": "auth.py",
            "description": "Fix SQL injection using parameterized query",
            "diff": "--- a/auth.py\\n+++ b/auth.py\\n@@ -13,7 +13,7 @@\\n def login(username, password):\\n     '''Authenticate user'''\\n-    user = db.query(f\\\"SELECT * FROM users WHERE name='{username}'\\\")\\n+    user = db.query(\\\"SELECT * FROM users WHERE name = ?\\\", (username,))\\n     if user and verify_password(user.password_hash, password):\\n         return create_session(user)"
        }
    ]
}
```

Generate MINIMAL, CORRECT fixes. Validate syntax before responding."""


class Verdict(Enum):
    """Verdict enumeration (maps to VerdictStatus in schemas)."""

    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    VETO = "VETO"  # New: Security judge veto


@dataclass
class JudgeScore:
    """Score from a single judge."""

    judge_name: str
    judge_role: JudgeRole
    model: str
    score: int
    explanation: str
    pass_verdict: bool
    confidence: float
    issues: List[str]
    suggestions: List[str]
    is_veto_eligible: bool = False  # True if security judge + FAIL + confidence > 0.8


@dataclass
class CriterionResult:
    """Result for a single criterion."""

    criterion_id: int
    criterion_type: str  # 'security', 'functionality', or 'style'
    criterion_desc: str
    scores: List[JudgeScore]
    average_score: float
    consensus_verdict: Verdict
    majority_ratio: float
    final_explanation: str
    relevant_files: List[str]
    veto_triggered: bool = False
    veto_reason: Optional[str] = None


@dataclass
class StaticAnalysisIssue:
    """Individual static analysis issue."""

    tool: str
    file_path: str
    line: int
    column: int
    message: str
    severity: str
    is_critical: bool = False


@dataclass
class StaticAnalysisFileResult:
    """Result from static analysis tools for a file."""

    tool: str
    file_path: str
    issues: List[Dict[str, Any]]
    severity_counts: Dict[str, int]
    has_critical: bool = False
    critical_count: int = 0


@dataclass
class TribunalVerdict:
    """Final tribunal verdict with veto protocol support."""

    timestamp: str
    overall_verdict: Verdict
    overall_score: float
    total_criteria: int
    passed_criteria: int
    failed_criteria: int
    static_analysis_issues: int
    criterion_results: List[CriterionResult]
    static_analysis_results: List[StaticAnalysisFileResult]
    remediation_suggestions: List[Dict[str, Any]]
    execution_time_seconds: float
    # Veto Protocol fields
    veto_triggered: bool = False
    veto_reason: Optional[str] = None
    veto_judge: Optional[str] = None
    # Fail-Fast fields
    static_analysis_aborted: bool = False
    abort_reason: Optional[str] = None


class Tribunal:
    """
    Multi-model tribunal for code adjudication.
    Uses multiple LLM judges to evaluate code against criteria.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.llms_config = self.config.get("llms", {})
        self.thresholds = self.config.get("thresholds", {})
        self.retry_config = self.config.get("retry", {})
        self.output_config = self.config.get("output", {})
        self.static_config = self.config.get("static_analysis", {})
        self.remediation_config = self.config.get("remediation", {})
        self.fallback_config = self.config.get("fallback", {})

        # Thresholds
        self.pass_score = self.thresholds.get("pass_score", 7)
        self.consensus_ratio = self.thresholds.get("consensus_ratio", 0.67)
        self.chunk_size_tokens = self.thresholds.get("chunk_size_tokens", 10000)
        self.context_window = self.thresholds.get("context_window", 128000)

        # Retry settings
        self.max_attempts = self.retry_config.get("max_attempts", 3)
        self.backoff_seconds = self.retry_config.get("backoff_seconds", 2)

        # Judge configurations - v2.0 uses rate-limit-resilient models
        self.judges = {
            "architect": {
                "name": "Architect Judge (Claude Sonnet 4)",
                "role": JudgeRole.ARCHITECT,
                "model": self.llms_config.get("architect", {}).get(
                    "model", "anthropic/claude-sonnet-4-20250514"
                ),
                "description": "architecture, design patterns, and logic correctness",
                "weight": 1.2,  # Slightly higher weight for architecture
            },
            "security": {
                "name": "Security Judge (DeepSeek V3)",
                "role": JudgeRole.SECURITY,
                "model": self.llms_config.get("security", {}).get(
                    "model", "deepseek/deepseek-chat"
                ),
                "description": "security vulnerabilities and efficiency analysis",
                "weight": 1.3,  # Higher weight for security (veto judge)
                "veto_enabled": SECURITY_VETO_ENABLED,
            },
            "user_proxy": {
                "name": "User Proxy Judge (Gemini 2.0 Flash)",
                "role": JudgeRole.USER_PROXY,
                "model": self.llms_config.get("user_proxy", {}).get(
                    "model", "gemini/gemini-2.0-flash-exp"
                ),
                "description": "user intent alignment and specification compliance",
                "weight": 1.0,
            },
        }

        # Veto protocol settings
        self.veto_confidence_threshold = VETO_CONFIDENCE_THRESHOLD
        self.security_veto_enabled = SECURITY_VETO_ENABLED

        # Fail-fast settings
        self.fail_fast_enabled = self.static_config.get("fail_fast", FAIL_FAST_ENABLED)

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

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return len(text) // 4

    def _chunk_content(self, content: str, max_tokens: int) -> List[str]:
        """Split content into chunks that fit within token limit."""
        estimated_tokens = self._estimate_tokens(content)

        if estimated_tokens <= max_tokens:
            return [content]

        # Split by lines and group into chunks
        lines = content.split("\n")
        chunks = []
        current_chunk = []
        current_tokens = 0

        for line in lines:
            line_tokens = self._estimate_tokens(line)

            if current_tokens + line_tokens > max_tokens:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_tokens = line_tokens
            else:
                current_chunk.append(line)
                current_tokens += line_tokens

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        logger.debug(f"Split content into {len(chunks)} chunks")
        return chunks

    def _summarize_non_code(self, content: str) -> str:
        """Summarize non-code elements (comments, docstrings) for large files."""
        lines = content.split("\n")
        result_lines = []
        in_docstring = False
        docstring_count = 0

        for line in lines:
            stripped = line.strip()

            # Detect docstrings
            if '"""' in stripped or "'''" in stripped:
                in_docstring = not in_docstring
                if in_docstring:
                    docstring_count += 1
                    if docstring_count <= 3:  # Keep first few docstrings
                        result_lines.append(line)
                    else:
                        result_lines.append("    # [Docstring summarized]")
                continue

            if in_docstring:
                if docstring_count <= 3:
                    result_lines.append(line)
                continue

            # Keep code lines
            result_lines.append(line)

        return "\n".join(result_lines)

    def run_pylint(self, file_path: str, content: str) -> StaticAnalysisFileResult:
        """
        Run pylint on a Python file.
        Detects critical issues for fail-fast abort.
        """
        issues = []
        severity_counts = {"error": 0, "warning": 0, "convention": 0, "refactor": 0}
        has_critical = False
        critical_count = 0

        if not self.static_config.get("pylint", {}).get("enabled", True):
            return StaticAnalysisFileResult(
                tool="pylint",
                file_path=file_path,
                issues=[],
                severity_counts=severity_counts,
                has_critical=False,
                critical_count=0,
            )

        try:
            # Write content to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                temp_path = f.name

            try:
                # Run pylint
                disabled = self.static_config.get("pylint", {}).get("disable", [])
                disable_str = ",".join(disabled) if disabled else ""

                cmd = ["python", "-m", "pylint", "--output-format=json"]
                if disable_str:
                    cmd.append(f"--disable={disable_str}")
                cmd.append(temp_path)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.stdout:
                    try:
                        pylint_output = json.loads(result.stdout)
                        for issue in pylint_output:
                            issue_type = issue.get("type", "warning")
                            is_critical = issue_type in CRITICAL_PYLINT_TYPES

                            issues.append(
                                {
                                    "line": issue.get("line", 0),
                                    "column": issue.get("column", 0),
                                    "message": issue.get("message", ""),
                                    "symbol": issue.get("symbol", ""),
                                    "type": issue_type,
                                    "is_critical": is_critical,
                                }
                            )

                            if issue_type in severity_counts:
                                severity_counts[issue_type] += 1

                            if is_critical:
                                has_critical = True
                                critical_count += 1

                    except json.JSONDecodeError:
                        pass

            finally:
                os.unlink(temp_path)

        except subprocess.TimeoutExpired:
            logger.warning(f"Pylint timed out for {file_path}")
        except Exception as e:
            logger.warning(f"Pylint failed for {file_path}: {e}")

        if has_critical:
            logger.warning(
                f"CRITICAL: Pylint found {critical_count} critical issues in {file_path}"
            )

        return StaticAnalysisFileResult(
            tool="pylint",
            file_path=file_path,
            issues=issues,
            severity_counts=severity_counts,
            has_critical=has_critical,
            critical_count=critical_count,
        )

    def run_bandit(self, file_path: str, content: str) -> StaticAnalysisFileResult:
        """
        Run bandit security scanner on a Python file.
        Detects critical security issues for fail-fast abort.
        """
        issues = []
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        has_critical = False
        critical_count = 0

        if not self.static_config.get("bandit", {}).get("enabled", True):
            return StaticAnalysisFileResult(
                tool="bandit",
                file_path=file_path,
                issues=[],
                severity_counts=severity_counts,
                has_critical=False,
                critical_count=0,
            )

        try:
            # Write content to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                temp_path = f.name

            try:
                # Run bandit
                cmd = ["python", "-m", "bandit", "-f", "json", temp_path]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.stdout:
                    try:
                        bandit_output = json.loads(result.stdout)
                        for issue in bandit_output.get("results", []):
                            severity = issue.get("issue_severity", "LOW").upper()
                            is_critical = severity in CRITICAL_BANDIT_SEVERITIES

                            issues.append(
                                {
                                    "line": issue.get("line_number", 0),
                                    "severity": severity,
                                    "confidence": issue.get("issue_confidence", "LOW"),
                                    "message": issue.get("issue_text", ""),
                                    "test_id": issue.get("test_id", ""),
                                    "is_critical": is_critical,
                                }
                            )

                            severity_lower = severity.lower()
                            if severity_lower in severity_counts:
                                severity_counts[severity_lower] += 1

                            if is_critical:
                                has_critical = True
                                critical_count += 1

                    except json.JSONDecodeError:
                        pass

            finally:
                os.unlink(temp_path)

        except subprocess.TimeoutExpired:
            logger.warning(f"Bandit timed out for {file_path}")
        except Exception as e:
            logger.warning(f"Bandit failed for {file_path}: {e}")

        if has_critical:
            logger.warning(
                f"CRITICAL: Bandit found {critical_count} HIGH severity issues in {file_path}"
            )

        return StaticAnalysisFileResult(
            tool="bandit",
            file_path=file_path,
            issues=issues,
            severity_counts=severity_counts,
            has_critical=has_critical,
            critical_count=critical_count,
        )

    def run_static_analysis(
        self, file_tree: Dict[str, str], language: str, max_files: int = 50
    ) -> Tuple[List[StaticAnalysisFileResult], bool, Optional[str]]:
        """
        Run static analysis on files (limited to max_files to prevent hangs).
        Returns: (results, should_abort, abort_reason)

        Implements fail-fast: if critical issues found and fail_fast_enabled,
        returns True for should_abort.
        """
        results = []
        should_abort = False
        abort_reason = None
        critical_files = []

        if not self.static_config.get("enabled", True):
            logger.info("Static analysis disabled in config")
            return results, False, None

        # Filter Python files
        python_files = [(p, c) for p, c in file_tree.items() if p.endswith(".py")]
        total_files = len(python_files)
        
        # Limit to prevent extremely long runs
        if total_files > max_files:
            logger.warning(f"Limiting static analysis to {max_files} of {total_files} Python files")
            python_files = python_files[:max_files]
        
        logger.info(f"Running static analysis on {len(python_files)} Python files...")

        for idx, (file_path, content) in enumerate(python_files):
            if language == "python":
                # Log progress every 10 files
                if idx > 0 and idx % 10 == 0:
                    logger.info(f"Static analysis progress: {idx}/{len(python_files)} files")
                
                pylint_result = self.run_pylint(file_path, content)
                results.append(pylint_result)

                bandit_result = self.run_bandit(file_path, content)
                results.append(bandit_result)

                # Check for critical issues
                if pylint_result.has_critical or bandit_result.has_critical:
                    critical_files.append(file_path)

        total_issues = sum(len(r.issues) for r in results)
        total_critical = sum(r.critical_count for r in results)

        logger.info(
            f"Static analysis complete. Found {total_issues} issues "
            f"({total_critical} critical)."
        )

        # Fail-fast check
        if self.fail_fast_enabled and total_critical > 0:
            should_abort = True
            abort_reason = (
                f"Fail-fast triggered: {total_critical} critical issues found "
                f"in {len(critical_files)} files: {', '.join(critical_files[:3])}"
            )
            logger.error(f"FAIL-FAST: {abort_reason}")

        return results, should_abort, abort_reason

    def _call_llm(self, model: str, messages: List[Dict], max_tokens: int = 4096) -> Optional[str]:
        """
        Call LLM with enhanced retry logic, exponential backoff, jitter, and multi-tier fallback.
        
        Features:
        - 5 retry attempts with exponential backoff (2s, 4s, 8s, 16s, 32s)
        - Random jitter (1-10s) to avoid thundering herd
        - Multi-tier fallback chain
        - Credit/rate limit error detection with alerts
        - Response caching via LiteLLM Redis cache
        """
        if not LITELLM_AVAILABLE:
            raise RuntimeError("LiteLLM not available")

        # Get retry config
        max_attempts = self.retry_config.get("max_attempts", 5)
        base_backoff = self.retry_config.get("backoff_seconds", 2)
        backoff_multiplier = self.retry_config.get("backoff_multiplier", 2)
        max_backoff = self.retry_config.get("max_backoff_seconds", 60)
        jitter_range = self.retry_config.get("jitter_range", [1, 10])
        
        # Get fallback models
        fallback_models = self.fallback_config.get("models", [])
        if not fallback_models:
            legacy_model = self.fallback_config.get("model")
            if legacy_model:
                fallback_models = [legacy_model]
        
        # Build model chain: primary + fallbacks
        model_chain = [model] + [m for m in fallback_models if m != model]
        
        last_error = None
        
        for model_idx, current_model in enumerate(model_chain):
            is_fallback = model_idx > 0
            if is_fallback:
                logger.warning(f"Switching to fallback model {model_idx}: {current_model}")
            
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(f"LLM call to {current_model} (attempt {attempt}/{max_attempts})")

                    response = litellm.completion(
                        model=current_model, 
                        messages=messages, 
                        max_tokens=max_tokens, 
                        temperature=0.1,
                        timeout=60,  # 60 second timeout
                    )

                    content = response.choices[0].message.content
                    
                    if is_fallback:
                        logger.info(f"Fallback model {current_model} succeeded")
                    
                    return content

                except Exception as e:
                    error_str = str(e)
                    error_type = type(e).__name__
                    last_error = e
                    
                    # Check for credit/billing errors (don't retry, switch immediately)
                    is_credit_error = any(
                        credit_msg in error_str.lower() 
                        for credit_msg in CREDIT_ERRORS
                    )
                    if is_credit_error:
                        logger.error(
                            f"💳 CREDIT ALERT: {current_model} - {error_str[:100]}"
                        )
                        break  # Switch to next model immediately
                    
                    # Check for rate limit errors
                    is_rate_limit = (
                        error_type in RATE_LIMIT_ERRORS or
                        "rate" in error_str.lower() or
                        "limit" in error_str.lower() or
                        "429" in error_str
                    )
                    
                    if is_rate_limit:
                        logger.warning(
                            f"⚠️ RATE LIMIT: {current_model} (attempt {attempt}/{max_attempts})"
                        )
                    else:
                        logger.warning(
                            f"LLM error ({error_type}): {error_str[:100]}..."
                        )

                    if attempt < max_attempts:
                        # Calculate backoff with jitter
                        backoff = min(
                            base_backoff * (backoff_multiplier ** (attempt - 1)),
                            max_backoff
                        )
                        jitter = random.uniform(jitter_range[0], jitter_range[1])
                        sleep_time = backoff + jitter
                        
                        logger.info(f"Retrying in {sleep_time:.1f}s (backoff={backoff:.0f}s + jitter={jitter:.1f}s)")
                        time.sleep(sleep_time)
            
            # If we exhausted retries for this model, try next in chain
            logger.warning(f"Exhausted retries for {current_model}, trying next model...")
        
        # All models failed
        logger.error(f"All models in fallback chain failed. Last error: {last_error}")
        raise last_error if last_error else RuntimeError("All LLM models failed")

    def _parse_judge_response(self, response: str) -> Dict[str, Any]:
        """Parse judge response to extract score and details."""
        result = {
            "score": 5,
            "explanation": response,
            "issues": [],
            "suggestions": [],
            "pass_verdict": False,
            "confidence": 0.5,
        }

        # Try to extract JSON from response
        json_pattern = r"\{[\s\S]*\}"
        matches = re.findall(json_pattern, response)

        for match in matches:
            try:
                parsed = json.loads(match)
                if "score" in parsed:
                    result["score"] = int(parsed.get("score", 5))
                    result["explanation"] = parsed.get("explanation", response)
                    result["issues"] = parsed.get("issues", [])
                    result["suggestions"] = parsed.get("suggestions", [])
                    result["confidence"] = float(parsed.get("confidence", 0.7))
                    break
            except (json.JSONDecodeError, ValueError):
                continue

        # Fallback: extract score from text
        if result["score"] == 5:
            score_pattern = r"(?:score|rating)[:\s]*(\d+)(?:/10)?"
            score_match = re.search(score_pattern, response.lower())
            if score_match:
                result["score"] = min(10, max(1, int(score_match.group(1))))

        result["pass_verdict"] = result["score"] >= self.pass_score

        return result

    def _get_judge_prompt(
        self, judge_key: str, criterion: Dict, code_content: str, spec_summary: str
    ) -> Tuple[str, str]:
        """Generate system and user prompts for a judge using enhanced v1.1 prompts."""
        judge = self.judges[judge_key]

        # Use the enhanced rubric-based system prompts
        system_prompts = {
            "architect": ARCHITECT_SYSTEM_PROMPT,
            "security": SECURITY_SYSTEM_PROMPT,
            "user_proxy": USER_PROXY_SYSTEM_PROMPT,
        }

        user_prompt = f"""Evaluate this code against the following requirement:

## REQUIREMENT
- **ID**: {criterion['id']}
- **Type**: {"Technical" if criterion.get('type', 'technical') == 'technical' else "Functional"}
- **Description**: {criterion['desc']}

## OVERALL SPECIFICATION CONTEXT
{spec_summary}

## CODE TO REVIEW
```
{code_content}
```

## INSTRUCTIONS
1. Analyze the code against the specific requirement above
2. Consider the overall specification context
3. Apply the scoring rubric strictly
4. Identify ALL issues, not just obvious ones
5. Provide actionable suggestions for each issue
6. Rate your confidence in the assessment

Output your assessment as valid JSON matching the specified schema."""

        return system_prompts.get(judge_key, ARCHITECT_SYSTEM_PROMPT), user_prompt

    def evaluate_criterion(
        self,
        criterion: Dict,
        criterion_type: str,
        file_tree: Dict[str, str],
        spec_summary: str,
    ) -> CriterionResult:
        """
        Evaluate a single criterion across all relevant files.
        Tracks security judge veto eligibility.
        """
        logger.info(
            f"Evaluating criterion {criterion_type}:{criterion['id']}: "
            f"{criterion['desc'][:50]}..."
        )

        # Combine relevant code content
        code_content = ""
        relevant_files = []

        for file_path, content in file_tree.items():
            # Check if content might be relevant to criterion
            # For now, include all files (could be optimized with semantic search)
            if self._estimate_tokens(code_content + content) < self.chunk_size_tokens:
                code_content += f"\n\n# File: {file_path}\n{content}"
                relevant_files.append(file_path)

        # If content is too large, chunk and summarize
        if self._estimate_tokens(code_content) > self.chunk_size_tokens:
            code_content = self._summarize_non_code(code_content)

        # Get scores from all judges
        scores: List[JudgeScore] = []
        veto_triggered = False
        veto_reason = None

        for judge_key, judge_config in self.judges.items():
            try:
                system_prompt, user_prompt = self._get_judge_prompt(
                    judge_key, criterion, code_content, spec_summary
                )

                response = self._call_llm(
                    judge_config["model"],
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )

                if response:
                    parsed = self._parse_judge_response(response)

                    # Check for security judge veto eligibility
                    is_security = judge_config.get("role") == JudgeRole.SECURITY
                    is_veto_eligible = (
                        is_security
                        and not parsed["pass_verdict"]
                        and parsed["confidence"] > self.veto_confidence_threshold
                        and self.security_veto_enabled
                    )

                    if is_veto_eligible:
                        veto_triggered = True
                        veto_reason = (
                            f"Security Judge VETO: {parsed['explanation'][:200]}... "
                            f"(confidence: {parsed['confidence']:.0%})"
                        )
                        logger.warning(
                            f"VETO TRIGGERED by Security Judge: "
                            f"confidence {parsed['confidence']:.0%} > "
                            f"threshold {self.veto_confidence_threshold:.0%}"
                        )

                    scores.append(
                        JudgeScore(
                            judge_name=judge_config["name"],
                            judge_role=judge_config.get("role", JudgeRole.ARCHITECT),
                            model=judge_config["model"],
                            score=parsed["score"],
                            explanation=parsed["explanation"],
                            pass_verdict=parsed["pass_verdict"],
                            confidence=parsed["confidence"],
                            issues=parsed["issues"],
                            suggestions=parsed["suggestions"],
                            is_veto_eligible=is_veto_eligible,
                        )
                    )
                    logger.debug(
                        f"{judge_config['name']}: Score {parsed['score']}/10"
                        + (" [VETO]" if is_veto_eligible else "")
                    )

            except Exception as e:
                logger.error(f"Judge {judge_key} failed: {e}")
                scores.append(
                    JudgeScore(
                        judge_name=judge_config["name"],
                        judge_role=judge_config.get("role", JudgeRole.ARCHITECT),
                        model=judge_config["model"],
                        score=5,
                        explanation=f"Evaluation failed: {str(e)}",
                        pass_verdict=False,
                        confidence=0.0,
                        issues=["Evaluation failed"],
                        suggestions=[],
                        is_veto_eligible=False,
                    )
                )

        # Compute consensus
        if not scores:
            return CriterionResult(
                criterion_id=criterion["id"],
                criterion_type=criterion_type,
                criterion_desc=criterion["desc"],
                scores=[],
                average_score=0.0,
                consensus_verdict=Verdict.ERROR,
                majority_ratio=0.0,
                final_explanation="No judges could evaluate this criterion",
                relevant_files=relevant_files,
                veto_triggered=False,
                veto_reason=None,
            )

        # Weighted average score
        total_weight = 0
        weighted_sum = 0
        for score in scores:
            judge_key = next(
                (k for k, v in self.judges.items() if v.get("role") == score.judge_role),
                "unknown",
            )
            weight = self.judges.get(judge_key, {}).get("weight", 1.0) * score.confidence
            weighted_sum += score.score * weight
            total_weight += weight

        average_score = weighted_sum / total_weight if total_weight > 0 else 0

        # Majority vote
        pass_votes = sum(1 for s in scores if s.pass_verdict)
        majority_ratio = pass_votes / len(scores)

        # Determine consensus verdict (veto overrides everything)
        if veto_triggered:
            consensus_verdict = Verdict.VETO
        elif majority_ratio >= self.consensus_ratio and average_score >= self.pass_score:
            consensus_verdict = Verdict.PASS
        elif majority_ratio >= 0.5:
            consensus_verdict = Verdict.PARTIAL
        else:
            consensus_verdict = Verdict.FAIL

        # Compile final explanation
        explanations = [
            f"**{s.judge_name}** (Score: {s.score}/10"
            + (" 🚫VETO" if s.is_veto_eligible else "")
            + f"): {s.explanation[:200]}..."
            for s in scores
        ]
        final_explanation = "\n\n".join(explanations)

        logger.info(
            f"Criterion {criterion['id']}: {consensus_verdict.value} "
            f"(avg: {average_score:.1f}, majority: {majority_ratio:.0%})"
            + (f" - VETO: {veto_reason[:50]}..." if veto_triggered else "")
        )

        return CriterionResult(
            criterion_id=criterion["id"],
            criterion_type=criterion_type,
            criterion_desc=criterion["desc"],
            scores=scores,
            average_score=round(average_score, 2),
            consensus_verdict=consensus_verdict,
            majority_ratio=round(majority_ratio, 2),
            final_explanation=final_explanation,
            relevant_files=relevant_files,
            veto_triggered=veto_triggered,
            veto_reason=veto_reason,
        )

    def generate_remediation(
        self, failed_results: List[CriterionResult], file_tree: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Generate remediation suggestions for failed criteria using GPT-4o-mini with diff format."""
        if not self.remediation_config.get("enabled", False):
            return []

        remediation_model = self.llms_config.get("remediation", {}).get("model", "openai/gpt-4o-mini")
        max_fixes = self.remediation_config.get("max_fixes_per_file", 5)

        suggestions = []

        for result in failed_results[:max_fixes]:
            try:
                # Get relevant file content
                relevant_code = ""
                for file_path in result.relevant_files[:3]:
                    if file_path in file_tree:
                        content = file_tree[file_path][:3000]  # Limit content size
                        relevant_code += f"\n# === {file_path} ===\n{content}"

                # Compile issues from all judges
                all_issues = []
                all_suggestions = []
                for score in result.scores:
                    all_issues.extend(score.issues)
                    all_suggestions.extend(score.suggestions)

                # Remove duplicates while preserving order
                all_issues = list(dict.fromkeys(all_issues))
                all_suggestions = list(dict.fromkeys(all_suggestions))

                user_prompt = f"""Generate code fixes for this failed requirement:

## FAILED REQUIREMENT
- **ID**: {result.criterion_id}
- **Type**: {result.criterion_type}
- **Description**: {result.criterion_desc}
- **Score**: {result.average_score}/10

## IDENTIFIED ISSUES
{json.dumps(all_issues, indent=2)}

## SUGGESTED IMPROVEMENTS
{json.dumps(all_suggestions, indent=2)}

## RELEVANT CODE
{relevant_code}

## INSTRUCTIONS
Generate minimal, targeted fixes in unified diff format.
Each fix should address ONE specific issue.
Ensure fixed code is syntactically valid.
Prioritize security and correctness fixes.

Output valid JSON with the structure:
{{
    "criterion_id": {result.criterion_id},
    "fixes": [
        {{
            "file": "filename.py",
            "description": "What this fix addresses",
            "diff": "unified diff format with context"
        }}
    ]
}}"""

                response = self._call_llm(
                    remediation_model,
                    [
                        {"role": "system", "content": REMEDIATION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=2048,
                )

                if response:
                    # Extract JSON from response
                    json_match = re.search(r"\{[\s\S]*\}", response)
                    if json_match:
                        try:
                            fix_data = json.loads(json_match.group())
                            suggestions.append(fix_data)
                            logger.info(
                                f"Generated {len(fix_data.get('fixes', []))} fixes for criterion {result.criterion_id}"
                            )
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse remediation JSON for criterion {result.criterion_id}")

            except Exception as e:
                logger.warning(f"Remediation generation failed for criterion {result.criterion_id}: {e}")

        return suggestions

    def run(
        self,
        file_tree: Dict[str, str],
        criteria: Dict[str, List[Dict]],
        language: str = "python",
        precomputed_static_results: Optional[Tuple[List[StaticAnalysisFileResult], bool, Optional[str]]] = None,
    ) -> TribunalVerdict:
        """
        Main adjudication pipeline with Veto Protocol and Fail-Fast support.

        Args:
            file_tree: Dict of file paths to content
            criteria: Extracted invariants (security, functionality, style)
            language: Detected language
            precomputed_static_results: Optional tuple of (results, should_abort, abort_reason) 
                                      to skip re-running analysis.

        Returns:
            TribunalVerdict with all results including veto status
        """
        start_time = time.time()

        logger.info("=" * 60)
        logger.info("TRIBUNAL SESSION STARTING (v1.1 - Veto Protocol)")
        logger.info("=" * 60)

        # Run static analysis first with fail-fast check
        if precomputed_static_results:
            logger.info("Using precomputed static analysis results (skipping re-run)")
            static_results, should_abort, abort_reason = precomputed_static_results
        else:
            static_results, should_abort, abort_reason = self.run_static_analysis(
                file_tree, language
            )

        # Handle fail-fast abort
        if should_abort:
            logger.error("PIPELINE ABORTED: Fail-fast triggered by static analysis")
            execution_time = time.time() - start_time

            return TribunalVerdict(
                timestamp=datetime.now().isoformat(),
                overall_verdict=Verdict.FAIL,
                overall_score=0.0,
                total_criteria=0,
                passed_criteria=0,
                failed_criteria=0,
                static_analysis_issues=sum(len(r.issues) for r in static_results),
                criterion_results=[],
                static_analysis_results=static_results,
                remediation_suggestions=[],
                execution_time_seconds=round(execution_time, 2),
                veto_triggered=False,
                veto_reason=None,
                veto_judge=None,
                static_analysis_aborted=True,
                abort_reason=abort_reason,
            )

        # Build spec summary for context (v1.1 categories)
        spec_summary = "Security Requirements:\n"
        for item in criteria.get("security", []):
            spec_summary += f"- {item['desc']}\n"
        spec_summary += "\nFunctionality Requirements:\n"
        for item in criteria.get("functionality", []):
            spec_summary += f"- {item['desc']}\n"
        spec_summary += "\nStyle Requirements:\n"
        for item in criteria.get("style", []):
            spec_summary += f"- {item['desc']}\n"

        # Evaluate each criterion
        criterion_results: List[CriterionResult] = []
        any_veto_triggered = False
        veto_reason = None
        veto_judge = None

        # Process security criteria first (potential veto source)
        for criterion in criteria.get("security", []):
            result = self.evaluate_criterion(
                criterion, "security", file_tree, spec_summary
            )
            criterion_results.append(result)

            # Track veto
            if result.veto_triggered:
                any_veto_triggered = True
                if veto_reason is None:  # Keep first veto reason
                    veto_reason = result.veto_reason
                    veto_judge = "Security Judge"

        # Process functionality criteria
        for criterion in criteria.get("functionality", []):
            result = self.evaluate_criterion(
                criterion, "functionality", file_tree, spec_summary
            )
            criterion_results.append(result)

        # Process style criteria
        for criterion in criteria.get("style", []):
            result = self.evaluate_criterion(
                criterion, "style", file_tree, spec_summary
            )
            criterion_results.append(result)

        # Calculate overall verdict
        passed = sum(
            1
            for r in criterion_results
            if r.consensus_verdict in (Verdict.PASS,)
        )
        failed = sum(
            1
            for r in criterion_results
            if r.consensus_verdict in (Verdict.FAIL, Verdict.VETO)
        )
        total = len(criterion_results)

        if total == 0:
            overall_verdict = Verdict.ERROR
            overall_score = 0.0
        else:
            overall_score = sum(r.average_score for r in criterion_results) / total
            pass_ratio = passed / total

            # VETO PROTOCOL: Security veto overrides everything
            if any_veto_triggered:
                overall_verdict = Verdict.VETO
                logger.warning(
                    f"FINAL VERDICT: VETO (Security Judge veto triggered)"
                )
            elif pass_ratio >= self.consensus_ratio and overall_score >= self.pass_score:
                overall_verdict = Verdict.PASS
            elif pass_ratio >= 0.5:
                overall_verdict = Verdict.PARTIAL
            else:
                overall_verdict = Verdict.FAIL

        # Generate remediation for failed criteria
        failed_results = [
            r
            for r in criterion_results
            if r.consensus_verdict in (Verdict.FAIL, Verdict.VETO, Verdict.PARTIAL)
        ]
        remediation_suggestions = self.generate_remediation(failed_results, file_tree)

        # Calculate static analysis issue count
        static_issue_count = sum(len(r.issues) for r in static_results)

        execution_time = time.time() - start_time

        verdict = TribunalVerdict(
            timestamp=datetime.now().isoformat(),
            overall_verdict=overall_verdict,
            overall_score=round(overall_score, 2),
            total_criteria=total,
            passed_criteria=passed,
            failed_criteria=failed,
            static_analysis_issues=static_issue_count,
            criterion_results=criterion_results,
            static_analysis_results=static_results,
            remediation_suggestions=remediation_suggestions,
            execution_time_seconds=round(execution_time, 2),
            veto_triggered=any_veto_triggered,
            veto_reason=veto_reason,
            veto_judge=veto_judge,
            static_analysis_aborted=False,
            abort_reason=None,
        )

        logger.info("=" * 60)
        logger.info(f"TRIBUNAL VERDICT: {overall_verdict.value}")
        if any_veto_triggered:
            logger.info(f"🚫 VETO ACTIVATED by {veto_judge}")
        logger.info(f"Overall Score: {overall_score:.1f}/10")
        logger.info(f"Passed: {passed}/{total} | Failed: {failed}/{total}")
        logger.info(f"Execution Time: {execution_time:.1f}s")
        logger.info("=" * 60)

        return verdict

    def generate_report_md(self, verdict: TribunalVerdict) -> str:
        """Generate REPORT.md with color-coded sections and veto indicator."""

        # Color codes for terminal/markdown
        def status_emoji(v: Verdict) -> str:
            return {
                Verdict.PASS: "✅",
                Verdict.FAIL: "❌",
                Verdict.PARTIAL: "⚠️",
                Verdict.ERROR: "🔴",
                Verdict.VETO: "🚫",
            }.get(v, "❓")

        def score_color(score: float) -> str:
            if score >= 8:
                return "🟢"
            elif score >= 6:
                return "🟡"
            else:
                return "🔴"

        # Veto banner if triggered
        veto_banner = ""
        if verdict.veto_triggered:
            veto_banner = f"""
> 🚫 **SECURITY VETO TRIGGERED**
>
> The Security Judge vetoed this submission with high confidence.
> Reason: {verdict.veto_reason or 'Security requirements not met.'}

---

"""

        # Fail-fast banner if triggered
        abort_banner = ""
        if verdict.static_analysis_aborted:
            abort_banner = f"""
> ⛔ **PIPELINE ABORTED (FAIL-FAST)**
>
> Static analysis found critical issues. Pipeline was aborted before judge evaluation.
> Reason: {verdict.abort_reason or 'Critical static analysis errors.'}

---

"""

        report = f"""# Dysruption CVA Verification Report (v1.1)

**Generated**: {verdict.timestamp}
**Execution Time**: {verdict.execution_time_seconds}s

{abort_banner}{veto_banner}---

## 📊 Summary

| Metric | Value |
|--------|-------|
| **Overall Verdict** | {status_emoji(verdict.overall_verdict)} **{verdict.overall_verdict.value}** |
| **Overall Score** | {score_color(verdict.overall_score)} {verdict.overall_score}/10 |
| **Criteria Passed** | {verdict.passed_criteria}/{verdict.total_criteria} |
| **Criteria Failed** | {verdict.failed_criteria}/{verdict.total_criteria} |
| **Static Analysis Issues** | {verdict.static_analysis_issues} |
| **Veto Triggered** | {"🚫 Yes" if verdict.veto_triggered else "No"} |
| **Fail-Fast Triggered** | {"⛔ Yes" if verdict.static_analysis_aborted else "No"} |

---

## 🔍 Per-Criterion Breakdown

"""

        # Group by type (v1.1 categories)
        security = [
            r for r in verdict.criterion_results if r.criterion_type == "security"
        ]
        functionality = [
            r for r in verdict.criterion_results if r.criterion_type == "functionality"
        ]
        style = [r for r in verdict.criterion_results if r.criterion_type == "style"]

        if security:
            report += "### 🔐 Security Requirements\n\n"
            for r in security:
                veto_indicator = " 🚫**VETO**" if r.veto_triggered else ""
                report += f"""#### {status_emoji(r.consensus_verdict)} S{r.criterion_id}: {r.criterion_desc}{veto_indicator}

- **Score**: {score_color(r.average_score)} {r.average_score}/10
- **Majority**: {r.majority_ratio:.0%}
- **Verdict**: {r.consensus_verdict.value}
- **Files**: {', '.join(r.relevant_files[:5]) if r.relevant_files else 'N/A'}

<details>
<summary>Judge Details</summary>

{r.final_explanation}

</details>

"""

        if functionality:
            report += "### ⚙️ Functionality Requirements\n\n"
            for r in functionality:
                report += f"""#### {status_emoji(r.consensus_verdict)} F{r.criterion_id}: {r.criterion_desc}

- **Score**: {score_color(r.average_score)} {r.average_score}/10
- **Majority**: {r.majority_ratio:.0%}
- **Verdict**: {r.consensus_verdict.value}
- **Files**: {', '.join(r.relevant_files[:5]) if r.relevant_files else 'N/A'}

<details>
<summary>Judge Details</summary>

{r.final_explanation}

</details>

"""

        if style:
            report += "### 🎨 Style Requirements\n\n"
            for r in style:
                report += f"""#### {status_emoji(r.consensus_verdict)} ST{r.criterion_id}: {r.criterion_desc}

- **Score**: {score_color(r.average_score)} {r.average_score}/10
- **Majority**: {r.majority_ratio:.0%}
- **Verdict**: {r.consensus_verdict.value}
- **Files**: {', '.join(r.relevant_files[:5]) if r.relevant_files else 'N/A'}

<details>
<summary>Judge Details</summary>

{r.final_explanation}

</details>

"""

        # Static analysis section
        if verdict.static_analysis_results:
            report += "---\n\n## 🛠️ Static Analysis Issues\n\n"

            for result in verdict.static_analysis_results:
                if result.issues:
                    critical_badge = " ⛔**CRITICAL**" if result.has_critical else ""
                    report += f"### {result.tool.upper()} - {result.file_path}{critical_badge}\n\n"
                    report += (
                        f"**Severity Counts**: {json.dumps(result.severity_counts)}\n\n"
                    )

                    report += "| Line | Message | Type | Critical |\n"
                    report += "|------|---------|------|----------|\n"
                    for issue in result.issues[:10]:  # Limit to 10 per file
                        line = issue.get("line", "-")
                        msg = issue.get("message", issue.get("symbol", "Unknown"))[:50]
                        itype = issue.get("type", issue.get("severity", "info"))
                        is_crit = "⛔" if issue.get("is_critical") else ""
                        report += f"| {line} | {msg} | {itype} | {is_crit} |\n"

                    if len(result.issues) > 10:
                        report += f"\n*...and {len(result.issues) - 10} more issues*\n"
                    report += "\n"

        # Remediation section
        if verdict.remediation_suggestions:
            report += "---\n\n## 🔧 Suggested Fixes\n\n"

            for suggestion in verdict.remediation_suggestions:
                cid = suggestion.get("criterion_id", "?")
                report += f"### Fixes for Criterion {cid}\n\n"

                for fix in suggestion.get("fixes", []):
                    report += f"**File**: `{fix.get('file', 'unknown')}`\n\n"
                    report += f"**Issue**: {fix.get('description', 'N/A')}\n\n"

                    if fix.get("diff"):
                        report += f"**Diff**:\n```diff\n{fix['diff']}\n```\n\n"

        # Footer
        report += """---

## 📋 CI/CD Integration

This report was generated by **Dysruption CVA v1.1**.

### Models Used:
- **Extraction**: Gemini 1.5 Flash
- **Architect Judge**: Claude 4 Sonnet
- **Security Judge**: DeepSeek V3 (Veto Authority)
- **User Proxy Judge**: Gemini 2.5 Pro
- **Remediation**: GPT-4o-mini

### v1.1 Features:
- 🚫 **Veto Protocol**: Security judge FAIL with >80% confidence = final FAIL
- ⛔ **Fail-Fast**: Critical pylint/bandit issues abort pipeline
- 📋 **Category Coverage**: Security, Functionality, Style required

For CI/CD integration, use `verdict.json` which contains machine-readable results.

```bash
# Example GitHub Actions usage
if [ $(jq '.overall_verdict' verdict.json) == '"PASS"' ]; then
  echo "Verification passed!"
else
  echo "Verification failed!"
  exit 1
fi
```

---
*Generated by Dysruption Consensus Verifier Agent v1.1*
"""

        return report

    def generate_verdict_json(self, verdict: TribunalVerdict) -> Dict[str, Any]:
        """Generate JSON verdict for CI/CD integration with veto protocol support."""

        json_data = {
            "version": "1.1",
            "timestamp": verdict.timestamp,
            "overall_verdict": verdict.overall_verdict.value,
            "overall_score": verdict.overall_score,
            "total_criteria": verdict.total_criteria,
            "passed_criteria": verdict.passed_criteria,
            "failed_criteria": verdict.failed_criteria,
            "static_analysis_issues": verdict.static_analysis_issues,
            "execution_time_seconds": verdict.execution_time_seconds,
            # Veto Protocol
            "veto_protocol": {
                "triggered": verdict.veto_triggered,
                "reason": verdict.veto_reason,
                "judge": verdict.veto_judge,
                "threshold": self.veto_confidence_threshold,
            },
            # Fail-Fast
            "fail_fast": {
                "aborted": verdict.static_analysis_aborted,
                "reason": verdict.abort_reason,
            },
            "criteria": [],
            "static_analysis": [],
            "ci_cd": {
                "success": verdict.overall_verdict == Verdict.PASS,
                "exit_code": 0 if verdict.overall_verdict == Verdict.PASS else 1,
                "summary": f"{verdict.passed_criteria}/{verdict.total_criteria} criteria passed",
                "veto_active": verdict.veto_triggered,
            },
        }

        for r in verdict.criterion_results:
            json_data["criteria"].append(
                {
                    "id": r.criterion_id,
                    "type": r.criterion_type,
                    "description": r.criterion_desc,
                    "score": r.average_score,
                    "verdict": r.consensus_verdict.value,
                    "majority_ratio": r.majority_ratio,
                    "relevant_files": r.relevant_files,
                    "veto_triggered": r.veto_triggered,
                    "veto_reason": r.veto_reason,
                }
            )

        for r in verdict.static_analysis_results:
            json_data["static_analysis"].append(
                {
                    "tool": r.tool,
                    "file": r.file_path,
                    "issue_count": len(r.issues),
                    "severity_counts": r.severity_counts,
                    "has_critical": r.has_critical,
                    "critical_count": r.critical_count,
                }
            )

        return json_data

    def save_outputs(self, verdict: TribunalVerdict) -> Tuple[str, str]:
        """Save REPORT.md and verdict.json."""
        report_path = self.output_config.get("report_file", "REPORT.md")
        verdict_path = self.output_config.get("verdict_file", "verdict.json")

        # Generate and save report
        report_content = self.generate_report_md(verdict)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        logger.info(f"Saved report to: {report_path}")

        # Generate and save verdict JSON
        verdict_json = self.generate_verdict_json(verdict)
        with open(verdict_path, "w", encoding="utf-8") as f:
            json.dump(verdict_json, f, indent=2)
        logger.info(f"Saved verdict to: {verdict_path}")

        return report_path, verdict_path


def run_adjudication(
    file_tree: Dict[str, str],
    language: str = "python",
    criteria_path: str = "criteria.json",
    config_path: str = "config.yaml",
) -> TribunalVerdict:
    """
    Main entry point for the tribunal module.

    Args:
        file_tree: Dict of file paths to content
        language: Detected language
        criteria_path: Path to criteria.json
        config_path: Path to config.yaml

    Returns:
        TribunalVerdict with all results
    """
    # Load criteria
    with open(criteria_path, "r", encoding="utf-8") as f:
        criteria = json.load(f)

    tribunal = Tribunal(config_path)
    verdict = tribunal.run(file_tree, criteria, language)
    tribunal.save_outputs(verdict)

    return verdict


if __name__ == "__main__":
    # Test the tribunal module
    import sys

    logger.add(sys.stderr, level="DEBUG")

    # Sample test with v1.1 category structure
    file_tree = {
        "main.py": """
def hello():
    print("Hello World")

if __name__ == "__main__":
    hello()
"""
    }

    # v1.1 criteria structure
    criteria = {
        "security": [
            {"id": 1, "desc": "No hardcoded secrets in code", "severity": "critical"}
        ],
        "functionality": [
            {"id": 1, "desc": "Print a greeting message", "severity": "high"}
        ],
        "style": [
            {"id": 1, "desc": "Follow PEP 8 style guidelines", "severity": "medium"}
        ],
    }

    tribunal = Tribunal()
    verdict = tribunal.run(file_tree, criteria, "python")
    tribunal.save_outputs(verdict)

    print(f"\nVerdict: {verdict.overall_verdict.value}")
    print(f"Score: {verdict.overall_score}/10")
    print(f"Veto Triggered: {verdict.veto_triggered}")
    if verdict.veto_reason:
        print(f"Veto Reason: {verdict.veto_reason}")
