"""
AST Window Analyzer for Intelligent Context Windowing.

Expands diff hunks to complete syntactic boundaries (functions, classes)
to ensure LLMs receive coherent code context.

This layer takes raw line ranges and expands them to meaningful code units.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from loguru import logger

try:
    from .git_hunk_extractor import DiffHunk, merge_overlapping_ranges
except ImportError:
    # Allow standalone testing
    from git_hunk_extractor import DiffHunk, merge_overlapping_ranges


@dataclass
class CodeWindow:
    """A window of code to include in context."""
    file_path: str
    start_line: int          # 1-indexed
    end_line: int            # 1-indexed, inclusive
    symbol_name: Optional[str] = None  # function/class name
    symbol_type: Optional[str] = None  # "function", "class", "method", "module"
    content: str = ""
    is_import_section: bool = False
    is_changed: bool = True  # Whether this window contains changes
    change_lines: List[int] = field(default_factory=list)  # Changed lines within window
    
    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1
    
    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate (4 chars per token)."""
        return max(1, (len(self.content) + 3) // 4)


@dataclass
class FileWindows:
    """All windows for a single file."""
    file_path: str
    windows: List[CodeWindow] = field(default_factory=list)
    imports_window: Optional[CodeWindow] = None
    total_lines: int = 0
    total_tokens: int = 0
    original_size: int = 0  # Full file token count
    
    @property
    def savings_percent(self) -> float:
        if self.original_size <= 0:
            return 0.0
        return 100.0 * (1.0 - self.total_tokens / self.original_size)


@dataclass
class SymbolInfo:
    """Information about a code symbol (function, class, etc.)."""
    name: str
    symbol_type: str  # "function", "class", "method", "async_function"
    start_line: int   # 1-indexed
    end_line: int     # 1-indexed
    parent: Optional[str] = None  # Parent class name for methods


class ASTWindowAnalyzer:
    """
    Analyzes code AST to expand diff hunks to syntactic boundaries.
    
    Usage:
        analyzer = ASTWindowAnalyzer()
        windows = analyzer.analyze_file(
            file_path="example.py",
            content=source_code,
            changed_ranges=[(10, 20), (50, 55)]
        )
    """
    
    def __init__(
        self,
        context_lines: int = 5,      # Lines before/after symbols
        min_window_size: int = 3,    # Minimum lines per window
        max_window_size: int = 200,  # Maximum lines per window
        merge_gap: int = 10,         # Merge windows within N lines
    ):
        self.context_lines = context_lines
        self.min_window_size = min_window_size
        self.max_window_size = max_window_size
        self.merge_gap = merge_gap
    
    def analyze_file(
        self,
        file_path: str,
        content: str,
        changed_ranges: List[Tuple[int, int]],
        include_imports: bool = True,
    ) -> FileWindows:
        """
        Analyze a file and create windows around changed ranges.
        
        Args:
            file_path: Path to the file (for naming)
            content: Full file content
            changed_ranges: List of (start, end) line tuples
            include_imports: Whether to always include import section
            
        Returns:
            FileWindows with all windows for this file
        """
        result = FileWindows(file_path=file_path)
        
        if not content:
            return result
        
        lines = content.splitlines()
        result.total_lines = len(lines)
        result.original_size = max(1, (len(content) + 3) // 4)
        
        # Get file extension for language-specific handling
        ext = Path(file_path).suffix.lower()
        
        # Extract symbols based on language
        if ext == ".py":
            symbols = self._extract_python_symbols(content)
        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            symbols = self._extract_js_symbols(content)
        else:
            symbols = []
        
        # Extract imports section
        if include_imports:
            import_window = self._extract_imports(file_path, content, ext)
            if import_window:
                result.imports_window = import_window
                result.windows.append(import_window)
        
        # Expand each changed range to symbol boundaries
        expanded_ranges: List[Tuple[int, int, Optional[str], Optional[str]]] = []
        
        for start, end in changed_ranges:
            # Find enclosing symbol
            enclosing = self._find_enclosing_symbol(start, end, symbols)
            
            if enclosing:
                # Expand to symbol boundaries with context
                new_start = max(1, enclosing.start_line - self.context_lines)
                new_end = min(len(lines), enclosing.end_line + self.context_lines)
                expanded_ranges.append((
                    new_start,
                    new_end,
                    enclosing.name,
                    enclosing.symbol_type
                ))
            else:
                # No enclosing symbol, just add context
                new_start = max(1, start - self.context_lines)
                new_end = min(len(lines), end + self.context_lines)
                expanded_ranges.append((new_start, new_end, None, None))
        
        # Merge overlapping ranges
        merged = self._merge_symbol_ranges(expanded_ranges)
        
        # Create windows
        for start, end, symbol_name, symbol_type in merged:
            # Clamp to max window size
            if end - start + 1 > self.max_window_size:
                end = start + self.max_window_size - 1
            
            # Extract content
            window_lines = lines[start - 1:end]
            window_content = '\n'.join(window_lines)
            
            # Skip if overlaps with import section
            if result.imports_window:
                if start <= result.imports_window.end_line:
                    start = result.imports_window.end_line + 1
                    if start > end:
                        continue
                    window_lines = lines[start - 1:end]
                    window_content = '\n'.join(window_lines)
            
            # Find which lines are actually changed
            change_lines = []
            for orig_start, orig_end in changed_ranges:
                for line in range(max(orig_start, start), min(orig_end, end) + 1):
                    if line not in change_lines:
                        change_lines.append(line)
            
            window = CodeWindow(
                file_path=file_path,
                start_line=start,
                end_line=end,
                symbol_name=symbol_name,
                symbol_type=symbol_type,
                content=window_content,
                is_changed=True,
                change_lines=sorted(change_lines),
            )
            
            result.windows.append(window)
        
        # Calculate totals
        result.total_tokens = sum(w.estimated_tokens for w in result.windows)
        
        return result
    
    def _extract_python_symbols(self, content: str) -> List[SymbolInfo]:
        """Extract function and class definitions from Python code."""
        symbols: List[SymbolInfo] = []
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            logger.debug("Failed to parse Python AST")
            return symbols
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol_type = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                
                # Check if it's a method (inside a class)
                # This is a simplification - would need parent tracking for full accuracy
                symbols.append(SymbolInfo(
                    name=node.name,
                    symbol_type=symbol_type,
                    start_line=node.lineno,
                    end_line=getattr(node, 'end_lineno', node.lineno),
                ))
            
            elif isinstance(node, ast.ClassDef):
                symbols.append(SymbolInfo(
                    name=node.name,
                    symbol_type="class",
                    start_line=node.lineno,
                    end_line=getattr(node, 'end_lineno', node.lineno),
                ))
        
        return symbols
    
    def _extract_js_symbols(self, content: str) -> List[SymbolInfo]:
        """Extract function and class definitions from JavaScript/TypeScript."""
        symbols: List[SymbolInfo] = []
        lines = content.splitlines()
        
        # Regex patterns for JS/TS
        patterns = [
            # function name(...) or async function name(...)
            (r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(', 'function'),
            # const name = (...) => or const name = function(...)
            (r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)\s*=>|function)', 'function'),
            # class Name
            (r'^\s*(?:export\s+)?class\s+(\w+)', 'class'),
            # method: name(...) or name(...) inside class
            (r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]', 'method'),
        ]
        
        # Simple brace-counting approach to find end lines
        for i, line in enumerate(lines, 1):
            for pattern, symbol_type in patterns:
                match = re.match(pattern, line)
                if match:
                    name = match.group(1)
                    # Find the end by counting braces
                    end_line = self._find_block_end(lines, i - 1)
                    symbols.append(SymbolInfo(
                        name=name,
                        symbol_type=symbol_type,
                        start_line=i,
                        end_line=end_line,
                    ))
                    break
        
        return symbols
    
    def _find_block_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end of a code block by counting braces."""
        brace_count = 0
        started = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            for char in line:
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
            
            if started and brace_count <= 0:
                return i + 1  # 1-indexed
        
        return len(lines)  # End of file
    
    def _extract_imports(
        self,
        file_path: str,
        content: str,
        ext: str
    ) -> Optional[CodeWindow]:
        """Extract the imports section of a file."""
        lines = content.splitlines()
        
        if ext == ".py":
            return self._extract_python_imports(file_path, lines)
        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            return self._extract_js_imports(file_path, lines)
        
        return None
    
    def _extract_python_imports(
        self,
        file_path: str,
        lines: List[str]
    ) -> Optional[CodeWindow]:
        """Extract Python import statements."""
        import_lines = []
        last_import_line = 0
        in_multiline_import = False
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Check for import statements
            if stripped.startswith(('import ', 'from ')) or in_multiline_import:
                import_lines.append(i)
                last_import_line = i
                
                # Check for multiline imports
                if '(' in stripped and ')' not in stripped:
                    in_multiline_import = True
                elif in_multiline_import and ')' in stripped:
                    in_multiline_import = False
            
            elif stripped.startswith('#') or not stripped:
                # Allow comments and blank lines at the top
                if last_import_line > 0 or i <= 10:
                    continue
            
            elif last_import_line > 0:
                # We've passed the imports section
                break
        
        if not import_lines:
            return None
        
        start = min(import_lines)
        end = max(import_lines)
        
        content = '\n'.join(lines[start - 1:end])
        
        return CodeWindow(
            file_path=file_path,
            start_line=start,
            end_line=end,
            symbol_name="imports",
            symbol_type="imports",
            content=content,
            is_import_section=True,
            is_changed=False,
        )
    
    def _extract_js_imports(
        self,
        file_path: str,
        lines: List[str]
    ) -> Optional[CodeWindow]:
        """Extract JavaScript/TypeScript import statements."""
        import_lines = []
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Check for import/require statements
            if stripped.startswith('import ') or 'require(' in stripped:
                import_lines.append(i)
            elif stripped.startswith('//') or not stripped:
                # Allow comments and blank lines
                continue
            elif import_lines:
                # We've passed the imports
                break
        
        if not import_lines:
            return None
        
        start = min(import_lines)
        end = max(import_lines)
        
        content = '\n'.join(lines[start - 1:end])
        
        return CodeWindow(
            file_path=file_path,
            start_line=start,
            end_line=end,
            symbol_name="imports",
            symbol_type="imports",
            content=content,
            is_import_section=True,
            is_changed=False,
        )
    
    def _find_enclosing_symbol(
        self,
        start: int,
        end: int,
        symbols: List[SymbolInfo]
    ) -> Optional[SymbolInfo]:
        """Find the smallest symbol that encloses the given line range."""
        enclosing: Optional[SymbolInfo] = None
        min_size = float('inf')
        
        for symbol in symbols:
            if symbol.start_line <= start and symbol.end_line >= end:
                size = symbol.end_line - symbol.start_line
                if size < min_size:
                    min_size = size
                    enclosing = symbol
        
        return enclosing
    
    def _merge_symbol_ranges(
        self,
        ranges: List[Tuple[int, int, Optional[str], Optional[str]]]
    ) -> List[Tuple[int, int, Optional[str], Optional[str]]]:
        """Merge overlapping or close ranges, preserving symbol info."""
        if not ranges:
            return []
        
        # Sort by start line
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        
        merged: List[Tuple[int, int, Optional[str], Optional[str]]] = [sorted_ranges[0]]
        
        for start, end, name, stype in sorted_ranges[1:]:
            prev_start, prev_end, prev_name, prev_stype = merged[-1]
            
            # Check if ranges overlap or are close enough to merge
            if start <= prev_end + self.merge_gap + 1:
                # Merge with previous range
                new_end = max(prev_end, end)
                # Keep the more specific symbol name
                new_name = name if name else prev_name
                new_stype = stype if stype else prev_stype
                merged[-1] = (prev_start, new_end, new_name, new_stype)
            else:
                merged.append((start, end, name, stype))
        
        return merged


def build_windowed_content(
    file_path: str,
    content: str,
    changed_ranges: List[Tuple[int, int]],
    context_lines: int = 5,
) -> Tuple[str, int, int]:
    """
    Convenience function to build windowed content for a single file.
    
    Returns:
        Tuple of (windowed_content, original_tokens, windowed_tokens)
    """
    analyzer = ASTWindowAnalyzer(context_lines=context_lines)
    result = analyzer.analyze_file(file_path, content, changed_ranges)
    
    # Build combined content
    parts = []
    for window in result.windows:
        if window.symbol_name:
            parts.append(f"# {window.symbol_type}: {window.symbol_name} (lines {window.start_line}-{window.end_line})")
        else:
            parts.append(f"# lines {window.start_line}-{window.end_line}")
        parts.append(window.content)
        parts.append("")
    
    windowed_content = '\n'.join(parts)
    original_tokens = result.original_size
    windowed_tokens = result.total_tokens
    
    return windowed_content, original_tokens, windowed_tokens


if __name__ == "__main__":
    # Demo with a sample Python file
    sample_code = '''
import os
import sys
from pathlib import Path

class MyClass:
    """A sample class."""
    
    def __init__(self, name):
        self.name = name
    
    def greet(self):
        print(f"Hello, {self.name}")
    
    def farewell(self):
        print(f"Goodbye, {self.name}")

def helper_function(x, y):
    """A helper function."""
    return x + y

def another_function():
    """Another function."""
    pass
'''
    
    analyzer = ASTWindowAnalyzer()
    
    # Simulate a change in the greet method (lines 11-12)
    result = analyzer.analyze_file(
        file_path="sample.py",
        content=sample_code,
        changed_ranges=[(11, 12)]
    )
    
    print(f"Original size: {result.original_size} tokens")
    print(f"Windowed size: {result.total_tokens} tokens")
    print(f"Savings: {result.savings_percent:.1f}%")
    print()
    
    for window in result.windows:
        print(f"Window: {window.symbol_name or 'unknown'} ({window.symbol_type})")
        print(f"  Lines: {window.start_line}-{window.end_line}")
        print(f"  Tokens: {window.estimated_tokens}")
        print()
