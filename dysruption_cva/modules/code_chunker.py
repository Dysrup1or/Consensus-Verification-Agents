"""
Dysruption CVA - Code Chunker Module
Version: 1.0

Splits code files into semantic chunks for embedding.
Uses AST-based parsing for Python and regex fallback for other languages.

Chunking Strategy:
1. Python: Parse AST, extract functions, classes, and module-level docstrings
2. TypeScript/JavaScript: Regex-based function/class extraction
3. Fallback: Fixed-size line chunks with overlap

Design Decisions:
- Max chunk size: 512 tokens (~2000 chars) to fit embedding model context
- Min chunk size: 50 tokens (~200 chars) to ensure meaningful content
- Overlap: 10% between chunks for context continuity
- Preserve complete syntactic units when possible

Usage:
    from modules.code_chunker import CodeChunker, chunk_file
    
    chunker = CodeChunker()
    chunks = chunker.chunk_python_file(content, "modules/tribunal.py")
    
    # Or use convenience function
    chunks = chunk_file(content, "modules/tribunal.py")
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger


# =============================================================================
# CONSTANTS
# =============================================================================

# Token estimation: ~4 chars per token for code
CHARS_PER_TOKEN = 4

# Chunk size limits
MAX_CHUNK_TOKENS = 512
MIN_CHUNK_TOKENS = 50
MAX_CHUNK_CHARS = MAX_CHUNK_TOKENS * CHARS_PER_TOKEN  # ~2048 chars
MIN_CHUNK_CHARS = MIN_CHUNK_TOKENS * CHARS_PER_TOKEN  # ~200 chars

# Overlap for context continuity
CHUNK_OVERLAP_RATIO = 0.1

# File extensions by language
PYTHON_EXTENSIONS = {".py", ".pyw", ".pyi"}
JS_TS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
MARKDOWN_EXTENSIONS = {".md", ".mdx", ".markdown"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class CodeChunk:
    """A semantic chunk of code for embedding."""
    
    chunk_id: int
    chunk_type: str  # 'function', 'class', 'method', 'module', 'docstring', 'block'
    content: str
    start_line: int
    end_line: int
    name: Optional[str] = None  # Function/class name if applicable
    parent_name: Optional[str] = None  # Parent class for methods
    token_estimate: int = 0
    
    def __post_init__(self):
        if self.token_estimate == 0:
            self.token_estimate = len(self.content) // CHARS_PER_TOKEN


@dataclass
class ChunkingResult:
    """Result of chunking a file."""
    
    file_path: str
    language: str
    chunks: List[CodeChunk] = field(default_factory=list)
    total_lines: int = 0
    total_tokens_estimate: int = 0
    parse_errors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.chunks and self.total_tokens_estimate == 0:
            self.total_tokens_estimate = sum(c.token_estimate for c in self.chunks)


# =============================================================================
# CODE CHUNKER CLASS
# =============================================================================


class CodeChunker:
    """
    Splits code files into semantic chunks for embedding.
    
    Supports:
    - Python: AST-based parsing
    - JavaScript/TypeScript: Regex-based parsing
    - Markdown: Section-based parsing
    - Fallback: Line-based chunking
    """
    
    def __init__(
        self,
        max_chunk_tokens: int = MAX_CHUNK_TOKENS,
        min_chunk_tokens: int = MIN_CHUNK_TOKENS,
        overlap_ratio: float = CHUNK_OVERLAP_RATIO,
    ):
        self.max_chunk_tokens = max_chunk_tokens
        self.min_chunk_tokens = min_chunk_tokens
        self.max_chunk_chars = max_chunk_tokens * CHARS_PER_TOKEN
        self.min_chunk_chars = min_chunk_tokens * CHARS_PER_TOKEN
        self.overlap_ratio = overlap_ratio
    
    def detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        
        if ext in PYTHON_EXTENSIONS:
            return "python"
        elif ext in JS_TS_EXTENSIONS:
            return "javascript"  # Treat JS/TS the same
        elif ext in MARKDOWN_EXTENSIONS:
            return "markdown"
        elif ext in CONFIG_EXTENSIONS:
            return "config"
        else:
            return "unknown"
    
    def chunk_file(self, content: str, file_path: str) -> ChunkingResult:
        """
        Chunk a file based on its language.
        
        Args:
            content: File content as string
            file_path: Path to file (for language detection)
            
        Returns:
            ChunkingResult with list of chunks
        """
        language = self.detect_language(file_path)
        lines = content.split("\n")
        
        try:
            if language == "python":
                chunks = self._chunk_python(content, file_path)
            elif language == "javascript":
                chunks = self._chunk_javascript(content, file_path)
            elif language == "markdown":
                chunks = self._chunk_markdown(content, file_path)
            else:
                chunks = self._chunk_fallback(content, file_path)
            
            # Ensure all chunks have IDs
            for i, chunk in enumerate(chunks):
                chunk.chunk_id = i
            
            # Split oversized chunks
            chunks = self._split_oversized_chunks(chunks)
            
            # Re-number after splitting
            for i, chunk in enumerate(chunks):
                chunk.chunk_id = i
            
            return ChunkingResult(
                file_path=file_path,
                language=language,
                chunks=chunks,
                total_lines=len(lines),
            )
            
        except Exception as e:
            logger.warning(f"Chunking failed for {file_path}: {e}, using fallback")
            chunks = self._chunk_fallback(content, file_path)
            return ChunkingResult(
                file_path=file_path,
                language=language,
                chunks=chunks,
                total_lines=len(lines),
                parse_errors=[str(e)],
            )
    
    # =========================================================================
    # PYTHON CHUNKING (AST-based)
    # =========================================================================
    
    def _chunk_python(self, content: str, file_path: str) -> List[CodeChunk]:
        """Chunk Python file using AST parsing."""
        chunks: List[CodeChunk] = []
        lines = content.split("\n")
        
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.debug(f"Python syntax error in {file_path}: {e}")
            return self._chunk_fallback(content, file_path)
        
        # Extract module docstring
        if (ast.get_docstring(tree) and tree.body and 
            isinstance(tree.body[0], ast.Expr) and 
            isinstance(tree.body[0].value, ast.Constant)):
            docstring_node = tree.body[0]
            docstring = ast.get_docstring(tree) or ""
            chunks.append(CodeChunk(
                chunk_id=0,
                chunk_type="docstring",
                content=f'"""{docstring}"""',
                start_line=docstring_node.lineno,
                end_line=docstring_node.end_lineno or docstring_node.lineno,
                name="module_docstring",
            ))
        
        # Extract imports as a single chunk
        import_lines = []
        import_start = None
        import_end = None
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if import_start is None:
                    import_start = node.lineno
                import_end = node.end_lineno or node.lineno
        
        if import_start and import_end:
            import_content = "\n".join(lines[import_start-1:import_end])
            if len(import_content) >= self.min_chunk_chars:
                chunks.append(CodeChunk(
                    chunk_id=0,
                    chunk_type="imports",
                    content=import_content,
                    start_line=import_start,
                    end_line=import_end,
                    name="imports",
                ))
        
        # Extract top-level functions and classes
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                chunk = self._extract_function_chunk(node, lines)
                if chunk:
                    chunks.append(chunk)
                    
            elif isinstance(node, ast.ClassDef):
                # Extract class with methods
                class_chunks = self._extract_class_chunks(node, lines)
                chunks.extend(class_chunks)
        
        # If no chunks extracted, fall back to line-based
        if not chunks:
            return self._chunk_fallback(content, file_path)
        
        return chunks
    
    def _extract_function_chunk(
        self, 
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef], 
        lines: List[str],
        parent_class: Optional[str] = None,
    ) -> Optional[CodeChunk]:
        """Extract a function as a chunk."""
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        
        # Include decorators
        if node.decorator_list:
            start_line = min(d.lineno for d in node.decorator_list)
        
        content = "\n".join(lines[start_line-1:end_line])
        
        if len(content) < self.min_chunk_chars:
            return None
        
        chunk_type = "method" if parent_class else "function"
        
        return CodeChunk(
            chunk_id=0,
            chunk_type=chunk_type,
            content=content,
            start_line=start_line,
            end_line=end_line,
            name=node.name,
            parent_name=parent_class,
        )
    
    def _extract_class_chunks(
        self, 
        node: ast.ClassDef, 
        lines: List[str]
    ) -> List[CodeChunk]:
        """Extract class header and methods as separate chunks."""
        chunks: List[CodeChunk] = []
        
        start_line = node.lineno
        if node.decorator_list:
            start_line = min(d.lineno for d in node.decorator_list)
        
        # Find where class body starts (after class definition line)
        class_def_end = node.lineno
        
        # Get class header (class definition + docstring)
        header_end = class_def_end
        if node.body:
            first_item = node.body[0]
            if (isinstance(first_item, ast.Expr) and 
                isinstance(first_item.value, ast.Constant) and
                isinstance(first_item.value.value, str)):
                header_end = first_item.end_lineno or first_item.lineno
        
        header_content = "\n".join(lines[start_line-1:header_end])
        if len(header_content) >= self.min_chunk_chars:
            chunks.append(CodeChunk(
                chunk_id=0,
                chunk_type="class",
                content=header_content,
                start_line=start_line,
                end_line=header_end,
                name=node.name,
            ))
        
        # Extract methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._extract_function_chunk(item, lines, parent_class=node.name)
                if chunk:
                    chunks.append(chunk)
        
        # If class has no extractable methods, chunk the whole class
        if len(chunks) <= 1:
            end_line = node.end_lineno or start_line
            full_content = "\n".join(lines[start_line-1:end_line])
            if len(full_content) >= self.min_chunk_chars:
                chunks = [CodeChunk(
                    chunk_id=0,
                    chunk_type="class",
                    content=full_content,
                    start_line=start_line,
                    end_line=end_line,
                    name=node.name,
                )]
        
        return chunks
    
    # =========================================================================
    # JAVASCRIPT/TYPESCRIPT CHUNKING (Regex-based)
    # =========================================================================
    
    def _chunk_javascript(self, content: str, file_path: str) -> List[CodeChunk]:
        """Chunk JavaScript/TypeScript file using regex patterns."""
        chunks: List[CodeChunk] = []
        lines = content.split("\n")
        
        # Patterns for functions and classes
        patterns = [
            # Function declarations
            (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
            # Arrow functions assigned to const/let/var
            (r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>", "function"),
            # Class declarations
            (r"^(?:export\s+)?class\s+(\w+)", "class"),
            # Method definitions in classes
            (r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*{", "method"),
        ]
        
        current_chunk_start = 0
        current_chunk_type = "block"
        current_chunk_name = None
        brace_depth = 0
        
        for i, line in enumerate(lines):
            # Track brace depth
            brace_depth += line.count("{") - line.count("}")
            
            # Check for new definition
            for pattern, chunk_type in patterns:
                match = re.match(pattern, line)
                if match:
                    # Save previous chunk if exists
                    if i > current_chunk_start:
                        chunk_content = "\n".join(lines[current_chunk_start:i])
                        if len(chunk_content) >= self.min_chunk_chars:
                            chunks.append(CodeChunk(
                                chunk_id=0,
                                chunk_type=current_chunk_type,
                                content=chunk_content,
                                start_line=current_chunk_start + 1,
                                end_line=i,
                                name=current_chunk_name,
                            ))
                    
                    current_chunk_start = i
                    current_chunk_type = chunk_type
                    current_chunk_name = match.group(1) if match.groups() else None
                    break
        
        # Add final chunk
        if current_chunk_start < len(lines):
            chunk_content = "\n".join(lines[current_chunk_start:])
            if len(chunk_content) >= self.min_chunk_chars:
                chunks.append(CodeChunk(
                    chunk_id=0,
                    chunk_type=current_chunk_type,
                    content=chunk_content,
                    start_line=current_chunk_start + 1,
                    end_line=len(lines),
                    name=current_chunk_name,
                ))
        
        if not chunks:
            return self._chunk_fallback(content, file_path)
        
        return chunks
    
    # =========================================================================
    # MARKDOWN CHUNKING (Section-based)
    # =========================================================================
    
    def _chunk_markdown(self, content: str, file_path: str) -> List[CodeChunk]:
        """Chunk Markdown file by sections."""
        chunks: List[CodeChunk] = []
        lines = content.split("\n")
        
        current_section_start = 0
        current_section_name = "intro"
        current_section_level = 0
        
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
        
        for i, line in enumerate(lines):
            match = heading_pattern.match(line)
            if match:
                # Save previous section
                if i > current_section_start:
                    section_content = "\n".join(lines[current_section_start:i])
                    if len(section_content) >= self.min_chunk_chars:
                        chunks.append(CodeChunk(
                            chunk_id=0,
                            chunk_type="section",
                            content=section_content,
                            start_line=current_section_start + 1,
                            end_line=i,
                            name=current_section_name,
                        ))
                
                current_section_start = i
                current_section_level = len(match.group(1))
                current_section_name = match.group(2).strip()
        
        # Add final section
        if current_section_start < len(lines):
            section_content = "\n".join(lines[current_section_start:])
            if len(section_content) >= self.min_chunk_chars:
                chunks.append(CodeChunk(
                    chunk_id=0,
                    chunk_type="section",
                    content=section_content,
                    start_line=current_section_start + 1,
                    end_line=len(lines),
                    name=current_section_name,
                ))
        
        if not chunks:
            return self._chunk_fallback(content, file_path)
        
        return chunks
    
    # =========================================================================
    # FALLBACK CHUNKING (Line-based)
    # =========================================================================
    
    def _chunk_fallback(self, content: str, file_path: str) -> List[CodeChunk]:
        """Fallback chunking by fixed line count with overlap."""
        chunks: List[CodeChunk] = []
        lines = content.split("\n")
        
        # Estimate lines per chunk
        avg_line_length = len(content) / max(len(lines), 1)
        lines_per_chunk = int(self.max_chunk_chars / max(avg_line_length, 1))
        lines_per_chunk = max(lines_per_chunk, 20)  # At least 20 lines
        
        overlap_lines = int(lines_per_chunk * self.overlap_ratio)
        
        start = 0
        chunk_id = 0
        
        while start < len(lines):
            end = min(start + lines_per_chunk, len(lines))
            chunk_content = "\n".join(lines[start:end])
            
            if len(chunk_content) >= self.min_chunk_chars:
                chunks.append(CodeChunk(
                    chunk_id=chunk_id,
                    chunk_type="block",
                    content=chunk_content,
                    start_line=start + 1,
                    end_line=end,
                ))
                chunk_id += 1
            
            start = end - overlap_lines
            if start >= len(lines) - overlap_lines:
                break
        
        return chunks
    
    # =========================================================================
    # CHUNK SIZE MANAGEMENT
    # =========================================================================
    
    def _split_oversized_chunks(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        """Split chunks that exceed max size."""
        result: List[CodeChunk] = []
        
        for chunk in chunks:
            if chunk.token_estimate <= self.max_chunk_tokens:
                result.append(chunk)
            else:
                # Split the oversized chunk
                sub_chunks = self._split_chunk(chunk)
                result.extend(sub_chunks)
        
        return result
    
    def _split_chunk(self, chunk: CodeChunk) -> List[CodeChunk]:
        """Split a single oversized chunk into smaller pieces."""
        lines = chunk.content.split("\n")
        sub_chunks: List[CodeChunk] = []
        
        # Estimate lines needed
        avg_line_length = len(chunk.content) / max(len(lines), 1)
        lines_per_sub = int(self.max_chunk_chars / max(avg_line_length, 1))
        lines_per_sub = max(lines_per_sub, 10)
        
        overlap = int(lines_per_sub * self.overlap_ratio)
        
        start = 0
        sub_id = 0
        
        while start < len(lines):
            end = min(start + lines_per_sub, len(lines))
            sub_content = "\n".join(lines[start:end])
            
            sub_chunks.append(CodeChunk(
                chunk_id=0,  # Will be reassigned
                chunk_type=chunk.chunk_type,
                content=sub_content,
                start_line=chunk.start_line + start,
                end_line=chunk.start_line + end - 1,
                name=f"{chunk.name}_part{sub_id}" if chunk.name else None,
                parent_name=chunk.parent_name,
            ))
            
            sub_id += 1
            start = end - overlap
            if start >= len(lines) - overlap:
                break
        
        return sub_chunks


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def chunk_file(content: str, file_path: str) -> ChunkingResult:
    """Convenience function to chunk a file."""
    chunker = CodeChunker()
    return chunker.chunk_file(content, file_path)


def chunk_files(file_contents: Dict[str, str]) -> Dict[str, ChunkingResult]:
    """Chunk multiple files."""
    chunker = CodeChunker()
    results = {}
    
    for file_path, content in file_contents.items():
        results[file_path] = chunker.chunk_file(content, file_path)
    
    return results


def estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    return len(text) // CHARS_PER_TOKEN
