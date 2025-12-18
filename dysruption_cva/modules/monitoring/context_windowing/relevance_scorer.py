"""
Relevance Scorer for Intelligent Context Windowing.

Scores code windows based on their relevance to the current criterion
being checked, enabling prioritized context selection.

This layer determines WHAT is most important to include.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

try:
    from .ast_window_analyzer import CodeWindow
except ImportError:
    from ast_window_analyzer import CodeWindow


# Security-sensitive patterns that should always be included
SECURITY_PATTERNS = [
    # Secrets and credentials
    (r"(?i)(api[_-]?key|secret|password|token|credential)", "secret_handling"),
    (r"(?i)(aws|azure|gcp|stripe|github).*(?:key|token|secret)", "cloud_credential"),
    (r"-----BEGIN.*PRIVATE.*KEY", "private_key"),
    
    # Dangerous functions
    (r"\beval\s*\(", "eval_usage"),
    (r"\bexec\s*\(", "exec_usage"),
    (r"pickle\.loads?", "pickle_usage"),
    (r"yaml\.load\s*\([^,)]*\)", "unsafe_yaml"),
    
    # Injection patterns
    (r"(?i)execute\s*\([^)]*[%f]", "sql_injection"),
    (r"(?i)innerHTML\s*=", "xss_pattern"),
    (r"subprocess.*shell\s*=\s*True", "shell_injection"),
    (r"\bos\.system\s*\(", "command_injection"),
    
    # Authentication/Authorization
    (r"(?i)(auth|login|logout|session|jwt|oauth)", "auth_related"),
    (r"@(?:requires_auth|login_required|authenticated)", "auth_decorator"),
    
    # Cryptography
    (r"(?i)(encrypt|decrypt|hash|sign|verify)", "crypto_operation"),
    (r"(?i)(md5|sha1)\s*\(", "weak_hash"),
]

# Criterion-specific keyword patterns
CRITERION_KEYWORDS = {
    "security": [
        "auth", "login", "password", "secret", "token", "key", "credential",
        "encrypt", "decrypt", "hash", "sign", "verify", "permission", "role",
        "access", "validate", "sanitize", "escape", "inject", "xss", "csrf",
    ],
    "architecture": [
        "class", "interface", "abstract", "inherit", "pattern", "factory",
        "singleton", "observer", "decorator", "module", "component", "service",
        "repository", "controller", "model", "view", "router", "middleware",
    ],
    "performance": [
        "cache", "async", "await", "concurrent", "parallel", "thread", "pool",
        "batch", "bulk", "optimize", "index", "query", "n+1", "lazy", "eager",
    ],
    "testing": [
        "test", "mock", "stub", "fixture", "assert", "expect", "describe",
        "it", "spec", "coverage", "setup", "teardown", "before", "after",
    ],
    "error_handling": [
        "try", "catch", "except", "raise", "throw", "error", "exception",
        "finally", "handle", "recover", "fallback", "retry", "timeout",
    ],
    "data_validation": [
        "validate", "schema", "type", "check", "verify", "sanitize", "clean",
        "parse", "format", "constraint", "required", "optional", "enum",
    ],
}


@dataclass
class ScoredWindow:
    """A code window with relevance scores."""
    window: CodeWindow
    overall_score: float = 0.0       # 0.0-1.0
    security_score: float = 0.0      # Security pattern matches
    criterion_score: float = 0.0     # Criterion keyword matches
    change_score: float = 0.0        # How much is changed
    import_score: float = 0.0        # Import dependency score
    keyword_matches: List[str] = field(default_factory=list)
    security_matches: List[str] = field(default_factory=list)
    should_include: bool = True      # Based on threshold
    inclusion_reason: str = ""       # Why included/excluded
    
    @property
    def is_security_critical(self) -> bool:
        return self.security_score >= 0.3 or len(self.security_matches) > 0


class RelevanceScorer:
    """
    Scores code windows for relevance to the current criterion.
    
    Usage:
        scorer = RelevanceScorer()
        scored = scorer.score_windows(
            windows=file_windows,
            criterion_type="security",
            criterion_text="Verify authentication is implemented"
        )
    """
    
    # Weighting factors for overall score
    WEIGHT_SECURITY = 0.35
    WEIGHT_CRITERION = 0.30
    WEIGHT_CHANGE = 0.25
    WEIGHT_IMPORT = 0.10
    
    def __init__(
        self,
        inclusion_threshold: float = 0.2,  # Minimum score to include
        always_include_security: bool = True,
        always_include_imports: bool = True,
        always_include_changed: bool = True,
    ):
        self.inclusion_threshold = inclusion_threshold
        self.always_include_security = always_include_security
        self.always_include_imports = always_include_imports
        self.always_include_changed = always_include_changed
        
        # Compile security patterns
        self._security_patterns = [
            (re.compile(pattern), name)
            for pattern, name in SECURITY_PATTERNS
        ]
    
    def score_windows(
        self,
        windows: List[CodeWindow],
        criterion_type: Optional[str] = None,
        criterion_text: Optional[str] = None,
        referenced_symbols: Optional[Set[str]] = None,
    ) -> List[ScoredWindow]:
        """
        Score all windows based on relevance.
        
        Args:
            windows: List of code windows to score
            criterion_type: Type of criterion (security, architecture, etc.)
            criterion_text: Full criterion description
            referenced_symbols: Symbols referenced by changed code
            
        Returns:
            List of scored windows, sorted by relevance
        """
        scored: List[ScoredWindow] = []
        
        # Extract keywords from criterion text
        criterion_keywords = self._extract_keywords(criterion_text or "")
        
        # Add type-specific keywords
        if criterion_type and criterion_type in CRITERION_KEYWORDS:
            criterion_keywords.update(CRITERION_KEYWORDS[criterion_type])
        
        for window in windows:
            scored_window = self._score_window(
                window=window,
                criterion_keywords=criterion_keywords,
                referenced_symbols=referenced_symbols or set(),
            )
            scored.append(scored_window)
        
        # Sort by overall score (descending)
        scored.sort(key=lambda x: x.overall_score, reverse=True)
        
        return scored
    
    def _score_window(
        self,
        window: CodeWindow,
        criterion_keywords: Set[str],
        referenced_symbols: Set[str],
    ) -> ScoredWindow:
        """Score a single window."""
        content_lower = window.content.lower()
        
        # Security score
        security_score, security_matches = self._calculate_security_score(window.content)
        
        # Criterion keyword score
        criterion_score, keyword_matches = self._calculate_criterion_score(
            content_lower, criterion_keywords
        )
        
        # Change density score
        change_score = self._calculate_change_score(window)
        
        # Import/reference score
        import_score = self._calculate_import_score(
            window, referenced_symbols
        )
        
        # Calculate overall score
        overall_score = (
            self.WEIGHT_SECURITY * security_score +
            self.WEIGHT_CRITERION * criterion_score +
            self.WEIGHT_CHANGE * change_score +
            self.WEIGHT_IMPORT * import_score
        )
        
        # Determine inclusion
        should_include, reason = self._determine_inclusion(
            window=window,
            overall_score=overall_score,
            security_score=security_score,
        )
        
        return ScoredWindow(
            window=window,
            overall_score=overall_score,
            security_score=security_score,
            criterion_score=criterion_score,
            change_score=change_score,
            import_score=import_score,
            keyword_matches=keyword_matches,
            security_matches=security_matches,
            should_include=should_include,
            inclusion_reason=reason,
        )
    
    def _calculate_security_score(self, content: str) -> Tuple[float, List[str]]:
        """Calculate security relevance score."""
        matches: List[str] = []
        
        for pattern, name in self._security_patterns:
            if pattern.search(content):
                matches.append(name)
        
        if not matches:
            return 0.0, []
        
        # More matches = higher score, capped at 1.0
        score = min(1.0, len(matches) * 0.25)
        
        return score, matches
    
    def _calculate_criterion_score(
        self,
        content_lower: str,
        keywords: Set[str]
    ) -> Tuple[float, List[str]]:
        """Calculate criterion keyword match score."""
        matches: List[str] = []
        
        for keyword in keywords:
            if keyword.lower() in content_lower:
                matches.append(keyword)
        
        if not matches or not keywords:
            return 0.0, []
        
        # Ratio of matched keywords
        score = len(matches) / len(keywords)
        
        return min(1.0, score), matches
    
    def _calculate_change_score(self, window: CodeWindow) -> float:
        """Calculate score based on change density."""
        if not window.is_changed:
            return 0.1  # Import sections get a small base score
        
        if not window.change_lines:
            return 0.5  # Changed but no specific lines tracked
        
        # Ratio of changed lines to total lines
        total_lines = window.line_count
        changed_lines = len(window.change_lines)
        
        if total_lines <= 0:
            return 0.5
        
        ratio = changed_lines / total_lines
        
        # Boost for high change density
        return min(1.0, ratio * 1.5)
    
    def _calculate_import_score(
        self,
        window: CodeWindow,
        referenced_symbols: Set[str]
    ) -> float:
        """Calculate score based on import/reference relationships."""
        if window.is_import_section:
            return 1.0  # Imports are always important
        
        if not referenced_symbols:
            return 0.0
        
        # Check if window's symbol is referenced
        if window.symbol_name and window.symbol_name in referenced_symbols:
            return 1.0
        
        # Check if any referenced symbol appears in content
        content_lower = window.content.lower()
        matches = sum(
            1 for sym in referenced_symbols
            if sym.lower() in content_lower
        )
        
        if matches > 0:
            return min(1.0, matches * 0.3)
        
        return 0.0
    
    def _determine_inclusion(
        self,
        window: CodeWindow,
        overall_score: float,
        security_score: float,
    ) -> Tuple[bool, str]:
        """Determine if window should be included."""
        # Always include imports
        if self.always_include_imports and window.is_import_section:
            return True, "imports_always_included"
        
        # Always include security-sensitive code
        if self.always_include_security and security_score >= 0.25:
            return True, "security_critical"
        
        # Always include changed code
        if self.always_include_changed and window.is_changed and window.change_lines:
            return True, "contains_changes"
        
        # Check threshold
        if overall_score >= self.inclusion_threshold:
            return True, f"score_{overall_score:.2f}_above_threshold"
        
        return False, f"score_{overall_score:.2f}_below_threshold"
    
    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract meaningful keywords from criterion text."""
        # Remove common words and extract meaningful terms
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "dare", "ought", "used", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into",
            "through", "during", "before", "after", "above", "below",
            "between", "under", "over", "and", "or", "but", "if", "then",
            "else", "when", "where", "how", "what", "which", "who", "this",
            "that", "these", "those", "it", "its", "all", "each", "every",
            "both", "few", "more", "most", "other", "some", "such", "no",
            "not", "only", "same", "so", "than", "too", "very", "just",
            "also", "now", "here", "there", "any", "code", "file", "function",
            "class", "method", "implement", "ensure", "verify", "check",
        }
        
        # Extract words
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text.lower())
        
        # Filter and return
        return {
            word for word in words
            if word not in stop_words and len(word) >= 3
        }


def score_and_filter_windows(
    windows: List[CodeWindow],
    criterion_type: Optional[str] = None,
    criterion_text: Optional[str] = None,
    inclusion_threshold: float = 0.2,
) -> List[ScoredWindow]:
    """
    Convenience function to score and filter windows.
    
    Returns only windows that should be included.
    """
    scorer = RelevanceScorer(inclusion_threshold=inclusion_threshold)
    scored = scorer.score_windows(
        windows=windows,
        criterion_type=criterion_type,
        criterion_text=criterion_text,
    )
    
    return [sw for sw in scored if sw.should_include]


if __name__ == "__main__":
    # Demo usage
    sample_windows = [
        CodeWindow(
            file_path="auth.py",
            start_line=1,
            end_line=10,
            symbol_name="authenticate",
            symbol_type="function",
            content="def authenticate(user, password):\n    token = generate_jwt(user)\n    return token",
            is_changed=True,
            change_lines=[2, 3],
        ),
        CodeWindow(
            file_path="utils.py",
            start_line=1,
            end_line=5,
            symbol_name="format_date",
            symbol_type="function",
            content="def format_date(dt):\n    return dt.strftime('%Y-%m-%d')",
            is_changed=False,
            change_lines=[],
        ),
        CodeWindow(
            file_path="db.py",
            start_line=1,
            end_line=8,
            symbol_name="query",
            symbol_type="function",
            content="def query(sql):\n    return cursor.execute(f'{sql}')",
            is_changed=True,
            change_lines=[2],
        ),
    ]
    
    scorer = RelevanceScorer()
    scored = scorer.score_windows(
        windows=sample_windows,
        criterion_type="security",
        criterion_text="Ensure authentication is secure and no SQL injection"
    )
    
    print("Scored Windows:")
    print("-" * 60)
    for sw in scored:
        print(f"{sw.window.symbol_name}: {sw.overall_score:.2f}")
        print(f"  Security: {sw.security_score:.2f} {sw.security_matches}")
        print(f"  Criterion: {sw.criterion_score:.2f} {sw.keyword_matches}")
        print(f"  Include: {sw.should_include} ({sw.inclusion_reason})")
        print()
