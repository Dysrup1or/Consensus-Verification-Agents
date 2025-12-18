"""
Context Windowing Package for Intelligent Token Savings.

This package provides intelligent context windowing to reduce token usage
when sending code to LLMs for verification, achieving ~50% token savings.

Components:
- GitHunkExtractor: Extracts changed line ranges from git
- ASTWindowAnalyzer: Expands hunks to syntactic boundaries
- RelevanceScorer: Scores windows for criterion matching
- ContextPruner: Assembles context within budget
- IntelligentContextBuilder: High-level API combining all components
"""

from .git_hunk_extractor import (
    GitHunkExtractor,
    DiffHunk,
    FileDiffInfo,
    DiffResult,
    merge_overlapping_ranges,
)

from .ast_window_analyzer import (
    ASTWindowAnalyzer,
    CodeWindow,
    FileWindows,
    SymbolInfo,
    build_windowed_content,
)

from .relevance_scorer import (
    RelevanceScorer,
    ScoredWindow,
)

from .context_pruner import (
    ContextPruner,
    WindowedContext,
    IntelligentContextBuilder,
    build_windowed_llm_context,
)

__all__ = [
    # Git Hunk Extraction
    "GitHunkExtractor",
    "DiffHunk",
    "FileDiffInfo", 
    "DiffResult",
    "merge_overlapping_ranges",
    # AST Window Analysis
    "ASTWindowAnalyzer",
    "CodeWindow",
    "FileWindows",
    "SymbolInfo",
    "build_windowed_content",
    # Relevance Scoring
    "RelevanceScorer",
    "ScoredWindow",
    # Context Pruning
    "ContextPruner",
    "WindowedContext",
    # High-level API
    "IntelligentContextBuilder",
    "build_windowed_llm_context",
]
