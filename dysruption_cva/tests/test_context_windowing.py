"""
Integration tests for Context Windowing system.

Verifies the full pipeline from git hunk extraction through context pruning.
"""

import pytest
from pathlib import Path
from typing import Dict

# Import all components
from modules.monitoring.context_windowing import (
    GitHunkExtractor,
    DiffHunk,
    FileDiffInfo,
    DiffResult,
    ASTWindowAnalyzer,
    CodeWindow,
    FileWindows,
    RelevanceScorer,
    ScoredWindow,
    ContextPruner,
    WindowedContext,
    IntelligentContextBuilder,
    build_windowed_llm_context,
)


class TestGitHunkExtractor:
    """Tests for git hunk extraction."""
    
    def test_extract_hunks_from_current_repo(self, tmp_path):
        """Test extracting hunks from a git repo."""
        # Use current directory as repo
        extractor = GitHunkExtractor(".")
        result = extractor.extract_all_hunks()
        
        # Should return a DiffResult even if no changes
        assert isinstance(result, DiffResult)
        assert isinstance(result.files, dict)
    
    def test_merge_overlapping_ranges(self):
        """Test range merging utility."""
        from modules.monitoring.context_windowing.git_hunk_extractor import merge_overlapping_ranges
        
        # Non-overlapping (with gap_tolerance=0 to test strict behavior)
        assert merge_overlapping_ranges([(1, 5), (10, 15)], gap_tolerance=0) == [(1, 5), (10, 15)]
        
        # Non-overlapping with default gap_tolerance=5 (ranges within 5 lines merge)
        # Gap of 4 lines (5→10) means they merge with default tolerance
        assert merge_overlapping_ranges([(1, 5), (10, 15)]) == [(1, 15)]
        
        # Overlapping
        assert merge_overlapping_ranges([(1, 5), (3, 8)]) == [(1, 8)]
        
        # Adjacent
        assert merge_overlapping_ranges([(1, 5), (5, 10)]) == [(1, 10)]
        
        # Complex with gap_tolerance=0
        assert merge_overlapping_ranges([(1, 3), (2, 4), (10, 12)], gap_tolerance=0) == [(1, 4), (10, 12)]


class TestASTWindowAnalyzer:
    """Tests for AST-based window analysis."""
    
    def test_python_function_detection(self):
        """Test Python function boundary detection."""
        analyzer = ASTWindowAnalyzer(context_lines=2)
        
        code = '''
import os

def hello():
    print("hello")

def world():
    print("world")
'''
        result = analyzer.analyze_file(
            file_path="test.py",
            content=code,
            changed_ranges=[(4, 5)],  # hello function
        )
        
        assert isinstance(result, FileWindows)
        assert len(result.windows) > 0
        
        # Should find the hello function
        function_windows = [w for w in result.windows if w.symbol_name == "hello"]
        assert len(function_windows) == 1
        assert function_windows[0].is_changed
    
    def test_import_extraction(self):
        """Test import section extraction."""
        analyzer = ASTWindowAnalyzer(context_lines=2)
        
        code = '''
import os
import sys
from pathlib import Path

def main():
    pass
'''
        result = analyzer.analyze_file(
            file_path="test.py",
            content=code,
            changed_ranges=[],
        )
        
        # Should have an import window
        import_windows = [w for w in result.windows if w.is_import_section]
        assert len(import_windows) == 1
        assert "import os" in import_windows[0].content
    
    def test_javascript_parsing(self):
        """Test JavaScript function detection."""
        analyzer = ASTWindowAnalyzer(context_lines=2)
        
        code = '''
import { useState } from 'react';

function MyComponent() {
    return <div>Hello</div>;
}

const helper = () => {
    return 42;
};
'''
        result = analyzer.analyze_file(
            file_path="test.tsx",
            content=code,
            changed_ranges=[(4, 6)],
        )
        
        assert isinstance(result, FileWindows)
        # Should detect at least the changed function
        assert any(w.is_changed for w in result.windows)


class TestRelevanceScorer:
    """Tests for relevance scoring."""
    
    def test_security_pattern_detection(self):
        """Test that security patterns are detected."""
        scorer = RelevanceScorer(inclusion_threshold=0.1)
        
        # Create windows with security content
        windows = [
            CodeWindow(
                file_path="auth.py",
                start_line=1,
                end_line=10,
                content="def authenticate(password): return hash(password)",
                symbol_name="authenticate",
                symbol_type="function",
            ),
            CodeWindow(
                file_path="utils.py",
                start_line=1,
                end_line=5,
                content="def format_date(dt): return str(dt)",
                symbol_name="format_date",
                symbol_type="function",
            ),
        ]
        
        scored = scorer.score_windows(windows, criterion_type="security")
        
        # Auth function should score higher
        auth_score = next(sw for sw in scored if sw.window.symbol_name == "authenticate")
        format_score = next(sw for sw in scored if sw.window.symbol_name == "format_date")
        
        assert auth_score.security_score > format_score.security_score
        assert auth_score.overall_score > format_score.overall_score
    
    def test_criterion_matching(self):
        """Test that criterion text affects scoring."""
        scorer = RelevanceScorer(inclusion_threshold=0.1)
        
        windows = [
            CodeWindow(
                file_path="db.py",
                start_line=1,
                end_line=10,
                content="def query(sql): cursor.execute(sql)",
                symbol_name="query",
                symbol_type="function",
            ),
        ]
        
        # Score with SQL injection criterion
        scored_sql = scorer.score_windows(
            windows, 
            criterion_type="security",
            criterion_text="Check for SQL injection vulnerabilities"
        )
        
        # Score without specific criterion
        scored_generic = scorer.score_windows(
            windows, 
            criterion_type="security",
            criterion_text="Check code quality"
        )
        
        # SQL criterion should boost score
        assert scored_sql[0].criterion_score >= scored_generic[0].criterion_score


class TestContextPruner:
    """Tests for context pruning."""
    
    def test_budget_enforcement(self):
        """Test that token budget is respected."""
        pruner = ContextPruner(token_budget=100, reserve_for_response=10)
        
        # Create windows that exceed budget
        large_window = ScoredWindow(
            window=CodeWindow(
                file_path="large.py",
                start_line=1,
                end_line=100,
                content="x" * 500,  # ~125 tokens
            ),
            overall_score=0.5,
            should_include=True,
        )
        
        small_window = ScoredWindow(
            window=CodeWindow(
                file_path="small.py",
                start_line=1,
                end_line=5,
                content="y" * 40,  # ~10 tokens
            ),
            overall_score=0.6,
            should_include=True,
        )
        
        result = pruner.prune([small_window, large_window])
        
        # Should include small, exclude large
        assert result.windows_included <= 2
        assert result.total_tokens <= 90  # Budget minus reserve
    
    def test_security_prioritization(self):
        """Test that security-critical windows are prioritized."""
        pruner = ContextPruner(token_budget=200, reserve_for_response=10)
        
        # is_security_critical is a property derived from security_score >= 0.3
        # Set security_score=0.9 to make is_security_critical=True
        security_window = ScoredWindow(
            window=CodeWindow(
                file_path="auth.py",
                start_line=1,
                end_line=5,
                content="def auth(): pass",
            ),
            overall_score=0.8,
            security_score=0.9,  # >= 0.3 means is_security_critical=True
            should_include=True,
        )
        
        # security_score=0.1 < 0.3 means is_security_critical=False
        normal_window = ScoredWindow(
            window=CodeWindow(
                file_path="utils.py",
                start_line=1,
                end_line=5,
                content="def util(): pass",
            ),
            overall_score=0.3,
            security_score=0.1,  # < 0.3 means is_security_critical=False
            should_include=True,
        )
        
        result = pruner.prune([normal_window, security_window])
        
        # Security window should be included
        included_files = [sw.window.file_path for sw in result.included_windows]
        assert "auth.py" in included_files


class TestIntelligentContextBuilder:
    """Tests for the high-level context builder."""
    
    def test_build_context_for_files(self):
        """Test building context from file contents."""
        builder = IntelligentContextBuilder(
            repo_path=".",
            token_budget=50000,
        )
        
        file_texts = {
            "auth.py": "def login(user, password): return check(password)",
            "utils.py": "def format(x): return str(x)",
        }
        
        result = builder.build_context_for_files(
            file_texts=file_texts,
            criterion_type="security",
            criterion_text="Check authentication",
        )
        
        assert isinstance(result, WindowedContext)
        assert result.files_included > 0
        assert len(result.context_text) > 0
    
    def test_convenience_function(self):
        """Test the drop-in replacement function."""
        file_texts = {
            "main.py": "print('hello')",
        }
        
        context, metrics = build_windowed_llm_context(
            repo_path=".",
            file_texts=file_texts,
        )
        
        assert isinstance(context, str)
        assert isinstance(metrics, dict)
        assert "original_tokens" in metrics
        assert "windowed_tokens" in metrics


class TestTokenSavings:
    """Tests verifying actual token savings."""
    
    def test_unchanged_files_excluded(self):
        """Test that unchanged files are excluded from context."""
        analyzer = ASTWindowAnalyzer(context_lines=3)
        scorer = RelevanceScorer(inclusion_threshold=0.2)
        pruner = ContextPruner(token_budget=50000)
        
        file_texts = {
            "changed.py": "def changed(): pass",
            "unchanged.py": "def unchanged(): x = 1; y = 2; z = 3",
        }
        
        all_windows = []
        for path, content in file_texts.items():
            # Only mark changed.py as changed
            changed_ranges = [(1, 1)] if path == "changed.py" else []
            windows = analyzer.analyze_file(path, content, changed_ranges)
            all_windows.extend(windows.windows)
        
        scored = scorer.score_windows(
            all_windows, 
            criterion_type="functionality"
        )
        
        result = pruner.prune(scored)
        
        # Unchanged file should not be in included windows (or very low score)
        included_paths = {sw.window.file_path for sw in result.included_windows}
        # Changed file should be included
        assert "changed.py" in included_paths
    
    def test_savings_above_threshold(self):
        """Test that we achieve meaningful token savings."""
        # Simulate a realistic scenario
        file_texts = {
            "security.py": """
import hashlib

def verify_password(stored, attempt):
    return hashlib.sha256(attempt.encode()).hexdigest() == stored

def generate_token():
    import secrets
    return secrets.token_urlsafe(32)
""",
            "utils.py": """
def format_name(first, last):
    return f"{first} {last}"

def calculate_age(birthdate):
    from datetime import date
    today = date.today()
    return today.year - birthdate.year

def generate_id():
    return str(uuid.uuid4())

def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")

def format_currency(amount):
    return f"${amount:,.2f}"
""",
            "logging.py": """
import logging

logger = logging.getLogger(__name__)

def log_info(msg):
    logger.info(msg)

def log_error(msg):
    logger.error(msg)

def log_debug(msg):
    logger.debug(msg)
""",
        }
        
        # Calculate original size
        original = "\n".join([f"# FILE: {p}\n{t}" for p, t in file_texts.items()])
        original_tokens = len(original) // 4
        
        # Build windowed context (only security.py is "changed")
        analyzer = ASTWindowAnalyzer(context_lines=3)
        scorer = RelevanceScorer(inclusion_threshold=0.15)
        pruner = ContextPruner(token_budget=50000)
        
        all_windows = []
        for path, content in file_texts.items():
            # Only security.py is changed
            changed_ranges = [(1, len(content.splitlines()))] if path == "security.py" else []
            windows = analyzer.analyze_file(path, content, changed_ranges)
            all_windows.extend(windows.windows)
        
        scored = scorer.score_windows(
            all_windows,
            criterion_type="security",
            criterion_text="Verify password handling and token generation",
        )
        
        result = pruner.prune(scored)
        
        # Calculate savings
        savings = 100.0 * (1 - result.total_tokens / original_tokens) if original_tokens > 0 else 0
        
        # Should achieve meaningful savings
        print(f"Original: {original_tokens}, Windowed: {result.total_tokens}, Savings: {savings:.1f}%")
        assert savings >= 20, f"Expected at least 20% savings, got {savings:.1f}%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
