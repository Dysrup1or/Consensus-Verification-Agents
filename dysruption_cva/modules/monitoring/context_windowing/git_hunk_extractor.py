"""
Git Hunk Extractor for Intelligent Context Windowing.

Extracts changed line ranges from git diff output to enable
targeted context windowing instead of sending full files to LLMs.

This is the foundation layer that identifies WHAT changed.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger


@dataclass
class DiffHunk:
    """A single contiguous change in a file."""
    file_path: str
    start_line: int      # 1-indexed, in the NEW file
    end_line: int        # 1-indexed, inclusive
    change_type: str     # "add", "modify", "delete", "context"
    old_start: int       # Line number in old file (0 if pure add)
    old_count: int       # Lines removed
    new_count: int       # Lines added
    content: str         # The actual changed lines (without +/- prefixes)
    raw_diff: str        # Raw diff output for this hunk


@dataclass
class FileDiffInfo:
    """All diff information for a single file."""
    file_path: str
    hunks: List[DiffHunk] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    is_new_file: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    old_path: Optional[str] = None  # For renames


@dataclass
class DiffResult:
    """Complete diff extraction result."""
    files: Dict[str, FileDiffInfo] = field(default_factory=dict)
    total_files_changed: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    base_commit: Optional[str] = None
    head_commit: Optional[str] = None


class GitHunkExtractor:
    """
    Extracts structured diff hunks from git repositories.
    
    Usage:
        extractor = GitHunkExtractor("/path/to/repo")
        result = extractor.extract_hunks()
        
        for file_path, file_info in result.files.items():
            for hunk in file_info.hunks:
                print(f"{file_path}:{hunk.start_line}-{hunk.end_line}")
    """
    
    # Regex patterns for parsing git diff output
    DIFF_FILE_HEADER = re.compile(r'^diff --git a/(.+) b/(.+)$')
    HUNK_HEADER = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
    NEW_FILE_MODE = re.compile(r'^new file mode')
    DELETED_FILE_MODE = re.compile(r'^deleted file mode')
    RENAME_FROM = re.compile(r'^rename from (.+)$')
    RENAME_TO = re.compile(r'^rename to (.+)$')
    
    def __init__(
        self,
        repo_path: str,
        context_lines: int = 3,  # Lines of context around changes
    ):
        self.repo_path = Path(repo_path).resolve()
        self.context_lines = context_lines
        
    def _run_git(self, *args: str, check: bool = True) -> Tuple[bool, str]:
        """Run a git command and return (success, output)."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if check and result.returncode != 0:
                return False, result.stderr or ""
            return True, result.stdout or ""
        except subprocess.TimeoutExpired:
            return False, "Git command timed out"
        except FileNotFoundError:
            return False, "Git not found"
        except Exception as e:
            return False, str(e)
    
    def get_current_commit(self) -> Optional[str]:
        """Get the current HEAD commit hash."""
        success, output = self._run_git("rev-parse", "HEAD", check=False)
        if success and output.strip():
            return output.strip()[:12]
        return None
    
    def extract_hunks(
        self,
        base_ref: str = "HEAD",
        staged_only: bool = False,
        unstaged_only: bool = False,
        files: Optional[List[str]] = None,
    ) -> DiffResult:
        """
        Extract diff hunks from git.
        
        Args:
            base_ref: Base reference for comparison (default: HEAD)
            staged_only: Only get staged changes
            unstaged_only: Only get unstaged working tree changes
            files: Optional list of files to limit diff to
            
        Returns:
            DiffResult with all hunks organized by file
        """
        result = DiffResult()
        result.base_commit = base_ref
        result.head_commit = self.get_current_commit()
        
        # Build git diff command
        diff_args = ["diff", f"-U{self.context_lines}"]
        
        if staged_only:
            diff_args.append("--cached")
        elif unstaged_only:
            # No additional args needed for working tree diff
            pass
        else:
            # Both staged and unstaged (compare to HEAD)
            diff_args.append("HEAD")
        
        if files:
            diff_args.append("--")
            diff_args.extend(files)
        
        success, diff_output = self._run_git(*diff_args, check=False)
        
        if not success:
            logger.warning(f"Git diff failed: {diff_output}")
            return result
        
        if not diff_output.strip():
            logger.debug("No changes detected")
            return result
        
        # Parse the diff output
        result = self._parse_diff_output(diff_output)
        result.base_commit = base_ref
        result.head_commit = self.get_current_commit()
        
        return result
    
    def extract_staged_hunks(self, files: Optional[List[str]] = None) -> DiffResult:
        """Extract hunks for staged changes only."""
        return self.extract_hunks(staged_only=True, files=files)
    
    def extract_unstaged_hunks(self, files: Optional[List[str]] = None) -> DiffResult:
        """Extract hunks for unstaged working tree changes."""
        return self.extract_hunks(unstaged_only=True, files=files)
    
    def extract_all_hunks(self, files: Optional[List[str]] = None) -> DiffResult:
        """Extract hunks for all changes (staged + unstaged vs HEAD)."""
        return self.extract_hunks(files=files)
    
    def _parse_diff_output(self, diff_output: str) -> DiffResult:
        """Parse git diff output into structured hunks."""
        result = DiffResult()
        
        lines = diff_output.split('\n')
        current_file: Optional[FileDiffInfo] = None
        current_hunk_lines: List[str] = []
        current_hunk_header: Optional[re.Match] = None
        in_hunk = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check for new file header
            file_match = self.DIFF_FILE_HEADER.match(line)
            if file_match:
                # Save previous hunk if any
                if current_file and current_hunk_header and current_hunk_lines:
                    hunk = self._create_hunk(
                        current_file.file_path,
                        current_hunk_header,
                        current_hunk_lines
                    )
                    if hunk:
                        current_file.hunks.append(hunk)
                        current_file.total_additions += hunk.new_count
                        current_file.total_deletions += hunk.old_count
                
                # Start new file
                old_path, new_path = file_match.groups()
                current_file = FileDiffInfo(file_path=new_path)
                current_hunk_lines = []
                current_hunk_header = None
                in_hunk = False
                
                # Check for new/deleted/renamed file
                i += 1
                while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('diff --git'):
                    if self.NEW_FILE_MODE.match(lines[i]):
                        current_file.is_new_file = True
                    elif self.DELETED_FILE_MODE.match(lines[i]):
                        current_file.is_deleted = True
                    elif self.RENAME_FROM.match(lines[i]):
                        current_file.is_renamed = True
                        match = self.RENAME_FROM.match(lines[i])
                        if match:
                            current_file.old_path = match.group(1)
                    i += 1
                continue
            
            # Check for hunk header
            hunk_match = self.HUNK_HEADER.match(line)
            if hunk_match and current_file:
                # Save previous hunk if any
                if current_hunk_header and current_hunk_lines:
                    hunk = self._create_hunk(
                        current_file.file_path,
                        current_hunk_header,
                        current_hunk_lines
                    )
                    if hunk:
                        current_file.hunks.append(hunk)
                        current_file.total_additions += hunk.new_count
                        current_file.total_deletions += hunk.old_count
                
                # Start new hunk
                current_hunk_header = hunk_match
                current_hunk_lines = [line]
                in_hunk = True
                i += 1
                continue
            
            # Collect hunk content
            if in_hunk and current_file:
                current_hunk_lines.append(line)
            
            i += 1
        
        # Save final hunk
        if current_file and current_hunk_header and current_hunk_lines:
            hunk = self._create_hunk(
                current_file.file_path,
                current_hunk_header,
                current_hunk_lines
            )
            if hunk:
                current_file.hunks.append(hunk)
                current_file.total_additions += hunk.new_count
                current_file.total_deletions += hunk.old_count
        
        # Add final file to result
        if current_file:
            result.files[current_file.file_path] = current_file
        
        # Calculate totals
        result.total_files_changed = len(result.files)
        for file_info in result.files.values():
            result.total_additions += file_info.total_additions
            result.total_deletions += file_info.total_deletions
        
        return result
    
    def _create_hunk(
        self,
        file_path: str,
        header_match: re.Match,
        hunk_lines: List[str]
    ) -> Optional[DiffHunk]:
        """Create a DiffHunk from parsed header and lines."""
        try:
            old_start = int(header_match.group(1))
            old_count = int(header_match.group(2) or 1)
            new_start = int(header_match.group(3))
            new_count = int(header_match.group(4) or 1)
            
            # Extract actual content (without the header line)
            content_lines = hunk_lines[1:] if hunk_lines else []
            
            # Separate additions and deletions
            additions = [l[1:] for l in content_lines if l.startswith('+')]
            deletions = [l[1:] for l in content_lines if l.startswith('-')]
            context = [l[1:] if l.startswith(' ') else l for l in content_lines 
                      if not l.startswith('+') and not l.startswith('-')]
            
            # Determine change type
            if old_count == 0:
                change_type = "add"
            elif new_count == 0:
                change_type = "delete"
            else:
                change_type = "modify"
            
            # Build clean content (the new version, for context windowing)
            clean_content_lines = []
            for l in content_lines:
                if l.startswith('+'):
                    clean_content_lines.append(l[1:])
                elif l.startswith(' '):
                    clean_content_lines.append(l[1:])
                # Skip deletions in clean content
            
            return DiffHunk(
                file_path=file_path,
                start_line=new_start,
                end_line=new_start + max(0, new_count - 1),
                change_type=change_type,
                old_start=old_start,
                old_count=len(deletions),
                new_count=len(additions),
                content='\n'.join(clean_content_lines),
                raw_diff='\n'.join(hunk_lines),
            )
        except Exception as e:
            logger.warning(f"Failed to parse hunk: {e}")
            return None
    
    def get_changed_line_ranges(
        self,
        files: Optional[List[str]] = None
    ) -> Dict[str, List[Tuple[int, int]]]:
        """
        Convenience method to get just the line ranges for each file.
        
        Returns:
            Dict mapping file path to list of (start, end) line tuples
        """
        result = self.extract_all_hunks(files=files)
        
        ranges: Dict[str, List[Tuple[int, int]]] = {}
        for file_path, file_info in result.files.items():
            ranges[file_path] = [
                (hunk.start_line, hunk.end_line)
                for hunk in file_info.hunks
            ]
        
        return ranges


def merge_overlapping_ranges(
    ranges: List[Tuple[int, int]],
    gap_tolerance: int = 5
) -> List[Tuple[int, int]]:
    """
    Merge overlapping or adjacent line ranges.
    
    Args:
        ranges: List of (start, end) tuples
        gap_tolerance: Merge ranges within this many lines of each other
        
    Returns:
        Merged list of (start, end) tuples
    """
    if not ranges:
        return []
    
    # Sort by start line
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    
    merged = [sorted_ranges[0]]
    
    for start, end in sorted_ranges[1:]:
        prev_start, prev_end = merged[-1]
        
        # Check if ranges overlap or are close enough to merge
        if start <= prev_end + gap_tolerance + 1:
            # Merge with previous range
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            # Start new range
            merged.append((start, end))
    
    return merged


if __name__ == "__main__":
    # Demo usage
    import sys
    
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    extractor = GitHunkExtractor(repo_path)
    result = extractor.extract_all_hunks()
    
    print(f"Files changed: {result.total_files_changed}")
    print(f"Total additions: {result.total_additions}")
    print(f"Total deletions: {result.total_deletions}")
    print()
    
    for file_path, file_info in result.files.items():
        print(f"📄 {file_path}")
        if file_info.is_new_file:
            print("   [NEW FILE]")
        for hunk in file_info.hunks:
            print(f"   Lines {hunk.start_line}-{hunk.end_line} ({hunk.change_type})")
        print()
