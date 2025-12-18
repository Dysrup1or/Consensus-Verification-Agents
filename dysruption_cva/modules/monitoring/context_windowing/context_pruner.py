"""
Context Pruner for Intelligent Context Windowing.

Assembles the final windowed context within token budget,
prioritizing high-relevance windows.

This is the final assembly layer that produces the optimized context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

try:
    from .ast_window_analyzer import CodeWindow, FileWindows, ASTWindowAnalyzer
    from .git_hunk_extractor import GitHunkExtractor, DiffResult
    from .relevance_scorer import RelevanceScorer, ScoredWindow
except ImportError:
    from ast_window_analyzer import CodeWindow, FileWindows, ASTWindowAnalyzer
    from git_hunk_extractor import GitHunkExtractor, DiffResult
    from relevance_scorer import RelevanceScorer, ScoredWindow


@dataclass
class WindowedContext:
    """The final assembled context for LLM consumption."""
    context_text: str                          # The actual text to send
    total_tokens: int                          # Tokens in context_text
    original_tokens: int                       # What full context would have been
    savings_percent: float                     # Percentage saved
    files_included: int                        # Number of files with content
    files_excluded: int                        # Files dropped due to budget
    windows_included: int                      # Number of windows included
    windows_excluded: int                      # Windows dropped
    included_windows: List[ScoredWindow] = field(default_factory=list)
    excluded_windows: List[ScoredWindow] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class ContextPruner:
    """
    Assembles optimized context from scored windows within budget.
    
    Usage:
        pruner = ContextPruner(token_budget=50000)
        context = pruner.prune(scored_windows, file_contents)
    """
    
    def __init__(
        self,
        token_budget: int = 50000,
        reserve_for_response: int = 4000,  # Reserve tokens for LLM response
        always_include_imports: bool = True,
        always_include_security: bool = True,
    ):
        self.token_budget = token_budget
        self.reserve = reserve_for_response
        self.always_include_imports = always_include_imports
        self.always_include_security = always_include_security
        self._effective_budget = token_budget - reserve_for_response
    
    def prune(
        self,
        scored_windows: List[ScoredWindow],
        file_contents: Optional[Dict[str, str]] = None,
    ) -> WindowedContext:
        """
        Prune windows to fit within token budget.
        
        Args:
            scored_windows: List of scored windows (should be pre-sorted by relevance)
            file_contents: Optional dict of full file contents for fallback
            
        Returns:
            WindowedContext with assembled text and metrics
        """
        included: List[ScoredWindow] = []
        excluded: List[ScoredWindow] = []
        
        current_tokens = 0
        original_tokens = sum(sw.window.estimated_tokens for sw in scored_windows)
        
        # Group windows by file for organization
        by_file: Dict[str, List[ScoredWindow]] = {}
        for sw in scored_windows:
            if sw.window.file_path not in by_file:
                by_file[sw.window.file_path] = []
            by_file[sw.window.file_path].append(sw)
        
        # First pass: include must-haves (imports, security, changed)
        must_include: List[ScoredWindow] = []
        others: List[ScoredWindow] = []
        
        for sw in scored_windows:
            if self.always_include_imports and sw.window.is_import_section:
                must_include.append(sw)
            elif self.always_include_security and sw.is_security_critical:
                must_include.append(sw)
            elif sw.window.is_changed and sw.window.change_lines:
                must_include.append(sw)
            else:
                others.append(sw)
        
        # Include must-haves first
        for sw in must_include:
            tokens = sw.window.estimated_tokens
            if current_tokens + tokens <= self._effective_budget:
                included.append(sw)
                current_tokens += tokens
            else:
                excluded.append(sw)
                logger.debug(f"Excluded must-have window due to budget: {sw.window.file_path}")
        
        # Then add others by score until budget exhausted
        for sw in others:
            if not sw.should_include:
                excluded.append(sw)
                continue
            
            tokens = sw.window.estimated_tokens
            if current_tokens + tokens <= self._effective_budget:
                included.append(sw)
                current_tokens += tokens
            else:
                excluded.append(sw)
        
        # Build the final context text
        context_text = self._build_context_text(included)
        
        # Calculate metrics
        files_included = len(set(sw.window.file_path for sw in included))
        files_excluded = len(set(sw.window.file_path for sw in excluded)) - files_included
        files_excluded = max(0, files_excluded)
        
        savings_percent = 0.0
        if original_tokens > 0:
            savings_percent = 100.0 * (1.0 - current_tokens / original_tokens)
        
        return WindowedContext(
            context_text=context_text,
            total_tokens=current_tokens,
            original_tokens=original_tokens,
            savings_percent=savings_percent,
            files_included=files_included,
            files_excluded=files_excluded,
            windows_included=len(included),
            windows_excluded=len(excluded),
            included_windows=included,
            excluded_windows=excluded,
            metadata={
                "budget": self.token_budget,
                "reserve": self.reserve,
                "effective_budget": self._effective_budget,
            }
        )
    
    def _build_context_text(self, windows: List[ScoredWindow]) -> str:
        """Build the final context text from included windows."""
        # Group by file and sort by line number within file
        by_file: Dict[str, List[ScoredWindow]] = {}
        for sw in windows:
            if sw.window.file_path not in by_file:
                by_file[sw.window.file_path] = []
            by_file[sw.window.file_path].append(sw)
        
        # Sort files alphabetically, imports first
        file_order = sorted(by_file.keys())
        
        parts: List[str] = []
        
        for file_path in file_order:
            file_windows = by_file[file_path]
            # Sort by start line
            file_windows.sort(key=lambda x: x.window.start_line)
            
            # File header
            parts.append(f"# FILE: {file_path}")
            
            for sw in file_windows:
                window = sw.window
                
                # Add window header with context
                if window.is_import_section:
                    parts.append(f"# [imports]")
                elif window.symbol_name:
                    parts.append(f"# [{window.symbol_type}: {window.symbol_name}] (lines {window.start_line}-{window.end_line})")
                else:
                    parts.append(f"# [lines {window.start_line}-{window.end_line}]")
                
                # Add content
                parts.append(window.content)
                parts.append("")  # Blank line between windows
            
            parts.append("")  # Blank line between files
        
        return "\n".join(parts)


class IntelligentContextBuilder:
    """
    High-level API for building intelligently windowed context.
    
    Combines all components: hunk extraction, AST analysis, 
    relevance scoring, and pruning.
    
    Usage:
        builder = IntelligentContextBuilder(
            repo_path="/path/to/repo",
            token_budget=50000
        )
        context = builder.build_context(
            changed_files=["src/auth.py"],
            criterion_type="security",
            criterion_text="Verify authentication"
        )
    """
    
    def __init__(
        self,
        repo_path: str,
        token_budget: int = 50000,
        context_lines: int = 5,
        inclusion_threshold: float = 0.2,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.token_budget = token_budget
        self.context_lines = context_lines
        self.inclusion_threshold = inclusion_threshold
        
        # Initialize components
        self.hunk_extractor = GitHunkExtractor(str(self.repo_path))
        self.ast_analyzer = ASTWindowAnalyzer(context_lines=context_lines)
        self.relevance_scorer = RelevanceScorer(inclusion_threshold=inclusion_threshold)
        self.pruner = ContextPruner(token_budget=token_budget)
    
    def build_context(
        self,
        changed_files: Optional[List[str]] = None,
        file_contents: Optional[Dict[str, str]] = None,
        criterion_type: Optional[str] = None,
        criterion_text: Optional[str] = None,
        use_git_hunks: bool = True,
    ) -> WindowedContext:
        """
        Build optimized context for LLM verification.
        
        Args:
            changed_files: List of changed file paths (auto-detected if None)
            file_contents: Dict of file paths to contents (auto-loaded if None)
            criterion_type: Type of criterion being checked
            criterion_text: Full criterion description
            use_git_hunks: Whether to use git diff for precise change detection
            
        Returns:
            WindowedContext with optimized content
        """
        # Extract git hunks
        if use_git_hunks:
            diff_result = self.hunk_extractor.extract_all_hunks(files=changed_files)
        else:
            diff_result = DiffResult()
        
        # If no git hunks but we have changed_files, treat entire files as changed
        if not diff_result.files and changed_files:
            for file_path in changed_files:
                diff_result.files[file_path] = None  # Will trigger full file inclusion
        
        # Load file contents if not provided
        if file_contents is None:
            file_contents = {}
            for file_path in diff_result.files:
                full_path = self.repo_path / file_path
                if full_path.exists():
                    try:
                        file_contents[file_path] = full_path.read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        logger.warning(f"Failed to read {file_path}: {e}")
        
        # Analyze each file
        all_windows: List[CodeWindow] = []
        
        for file_path, content in file_contents.items():
            if not content:
                continue
            
            # Get changed line ranges for this file
            if file_path in diff_result.files and diff_result.files[file_path]:
                file_info = diff_result.files[file_path]
                changed_ranges = [(h.start_line, h.end_line) for h in file_info.hunks]
            else:
                # No hunks - treat as full file (for newly added files or when git unavailable)
                lines = content.splitlines()
                changed_ranges = [(1, len(lines))] if lines else []
            
            # Analyze with AST
            file_windows = self.ast_analyzer.analyze_file(
                file_path=file_path,
                content=content,
                changed_ranges=changed_ranges,
            )
            
            all_windows.extend(file_windows.windows)
        
        # Score windows
        scored_windows = self.relevance_scorer.score_windows(
            windows=all_windows,
            criterion_type=criterion_type,
            criterion_text=criterion_text,
        )
        
        # Prune to budget
        context = self.pruner.prune(scored_windows, file_contents)
        
        # Add metadata
        context.metadata.update({
            "files_analyzed": len(file_contents),
            "total_windows": len(all_windows),
            "git_hunks_used": use_git_hunks and bool(diff_result.files),
            "criterion_type": criterion_type,
        })
        
        return context
    
    def build_context_for_files(
        self,
        file_texts: Dict[str, str],
        criterion_type: Optional[str] = None,
        criterion_text: Optional[str] = None,
    ) -> WindowedContext:
        """
        Build context from pre-loaded file contents (no git).
        
        Useful when files are already loaded or for non-git scenarios.
        """
        return self.build_context(
            changed_files=list(file_texts.keys()),
            file_contents=file_texts,
            criterion_type=criterion_type,
            criterion_text=criterion_text,
            use_git_hunks=False,
        )


def build_windowed_llm_context(
    repo_path: str,
    file_texts: Dict[str, str],
    token_budget: int = 50000,
    criterion_type: Optional[str] = None,
    criterion_text: Optional[str] = None,
) -> Tuple[str, Dict]:
    """
    Convenience function to build windowed context.
    
    Drop-in replacement for full file context building.
    
    Returns:
        Tuple of (context_string, metrics_dict)
    """
    builder = IntelligentContextBuilder(
        repo_path=repo_path,
        token_budget=token_budget,
    )
    
    result = builder.build_context_for_files(
        file_texts=file_texts,
        criterion_type=criterion_type,
        criterion_text=criterion_text,
    )
    
    metrics = {
        "original_tokens": result.original_tokens,
        "windowed_tokens": result.total_tokens,
        "savings_percent": result.savings_percent,
        "files_included": result.files_included,
        "windows_included": result.windows_included,
    }
    
    return result.context_text, metrics


if __name__ == "__main__":
    # Demo with the current repo
    import sys
    
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    builder = IntelligentContextBuilder(
        repo_path=repo_path,
        token_budget=50000,
    )
    
    result = builder.build_context(
        criterion_type="security",
        criterion_text="Verify no hardcoded secrets or SQL injection",
    )
    
    print(f"=" * 60)
    print("INTELLIGENT CONTEXT WINDOWING RESULTS")
    print(f"=" * 60)
    print(f"Original tokens:  {result.original_tokens:,}")
    print(f"Windowed tokens:  {result.total_tokens:,}")
    print(f"Savings:          {result.savings_percent:.1f}%")
    print(f"Files included:   {result.files_included}")
    print(f"Windows included: {result.windows_included}")
    print(f"Windows excluded: {result.windows_excluded}")
    print()
    
    if result.included_windows:
        print("Included windows:")
        for sw in result.included_windows[:5]:
            print(f"  - {sw.window.file_path}: {sw.window.symbol_name or 'lines ' + str(sw.window.start_line)}")
            print(f"    Score: {sw.overall_score:.2f}, Reason: {sw.inclusion_reason}")
    
    print()
    print(f"Context preview (first 500 chars):")
    print("-" * 40)
    print(result.context_text[:500])
