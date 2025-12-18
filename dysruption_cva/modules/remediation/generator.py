"""
Fix Generator for Autonomous Remediation Agent

Generates code fixes using LLM-based reasoning:
- Builds context for the LLM (file content, error, related code)
- Constructs prompts for fix generation
- Parses LLM responses into structured patches
- Validates generated patches syntactically
- Supports multiple fix strategies
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .models import (
    ApprovalLevel,
    FixStatus,
    FixStrategy,
    IssueCategory,
    IssueSeverity,
    PatchData,
    RemediationFix,
    RemediationIssue,
    RootCause,
)


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================


SYSTEM_PROMPT = """You are an expert code repair agent. Your task is to analyze code issues and generate precise, minimal fixes.

Guidelines:
1. Generate the SMALLEST possible fix that resolves the issue
2. Preserve existing code style and formatting
3. Do not introduce new dependencies unless absolutely necessary
4. Ensure the fix is syntactically correct
5. Explain your reasoning briefly
6. If you cannot fix the issue confidently, say so

Output format for fixes:
```fix
FILE: <file_path>
---ORIGINAL---
<original_code_lines>
---FIXED---
<fixed_code_lines>
```

You may generate multiple fix blocks if the issue spans multiple files or locations."""


ISSUE_PROMPT_TEMPLATE = """## Issue to Fix

**Category**: {category}
**Severity**: {severity}
**File**: {file_path}
**Line**: {line_number}

**Error Message**:
{message}

**Raw Output** (if available):
{raw_output}

## File Content

```{language}
{file_content}
```

{related_context}

## Task

Generate a fix for this issue. The fix should:
1. Address the root cause, not just the symptom
2. Be minimal and focused
3. Not break existing functionality
4. Follow the codebase's style conventions

Respond with your analysis and the fix in the specified format."""


ROOT_CAUSE_PROMPT_TEMPLATE = """## Root Cause Analysis

A group of related issues has been identified with a common root cause.

**Root Cause**: {root_description}
**Affected Files**: {affected_files}

### Primary Issue
{primary_issue}

### Related Issues (symptoms)
{symptom_issues}

## File Contents

{file_contents}

## Task

Generate a fix that addresses the ROOT CAUSE. Fixing the root cause should resolve all related symptom issues.

Respond with your analysis and the fix in the specified format."""


VALIDATION_PROMPT_TEMPLATE = """## Validate Fix

Original code:
```{language}
{original}
```

Proposed fix:
```{language}
{fixed}
```

Issue being fixed: {issue_message}

Does this fix:
1. Correctly address the issue?
2. Introduce any new problems?
3. Follow proper coding conventions?

Respond with:
- VALID: if the fix is correct
- INVALID: <reason> if there's a problem"""


# =============================================================================
# CONTEXT BUILDER
# =============================================================================


@dataclass
class FixContext:
    """Context gathered for fix generation."""
    issue: RemediationIssue
    file_content: str
    file_language: str
    surrounding_lines: Tuple[int, int]  # start, end lines included
    related_files: Dict[str, str] = field(default_factory=dict)
    import_context: List[str] = field(default_factory=list)
    root_cause: Optional[RootCause] = None
    symptom_issues: List[RemediationIssue] = field(default_factory=list)


class ContextBuilder:
    """Builds context for fix generation."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    def build_context(
        self,
        issue: RemediationIssue,
        root_cause: Optional[RootCause] = None,
        symptom_issues: Optional[List[RemediationIssue]] = None,
        context_lines: int = 50,
    ) -> Optional[FixContext]:
        """Build context for generating a fix."""
        if not issue.file_path:
            logger.warning(f"Issue {issue.id} has no file path, cannot build context")
            return None
        
        file_path = self.project_root / issue.file_path
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return None
        
        try:
            file_content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None
        
        # Determine language from extension
        language = self._detect_language(file_path)
        
        # Calculate surrounding lines
        lines = file_content.split("\n")
        total_lines = len(lines)
        
        if issue.line_number:
            start = max(1, issue.line_number - context_lines)
            end = min(total_lines, issue.line_number + context_lines)
        else:
            start = 1
            end = min(total_lines, 200)  # Limit for files without line info
        
        # Build import context
        import_context = self._extract_imports(file_content, language)
        
        # Get related files
        related_files = {}
        if root_cause and symptom_issues:
            for symptom in symptom_issues:
                if symptom.file_path and symptom.file_path != issue.file_path:
                    symptom_path = self.project_root / symptom.file_path
                    if symptom_path.exists():
                        try:
                            related_files[symptom.file_path] = symptom_path.read_text(encoding="utf-8")
                        except Exception:
                            pass
        
        return FixContext(
            issue=issue,
            file_content=file_content,
            file_language=language,
            surrounding_lines=(start, end),
            related_files=related_files,
            import_context=import_context,
            root_cause=root_cause,
            symptom_issues=symptom_issues or [],
        )
    
    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sql": "sql",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".md": "markdown",
        }
        return ext_map.get(file_path.suffix.lower(), "text")
    
    def _extract_imports(self, content: str, language: str) -> List[str]:
        """Extract import statements from file."""
        imports = []
        
        if language in ("python",):
            # Python imports
            for match in re.finditer(r"^(?:from\s+\S+\s+)?import\s+.+$", content, re.MULTILINE):
                imports.append(match.group())
        
        elif language in ("typescript", "javascript"):
            # JS/TS imports
            for match in re.finditer(r"^import\s+.+$", content, re.MULTILINE):
                imports.append(match.group())
        
        return imports[:20]  # Limit to first 20 imports


# =============================================================================
# FIX GENERATOR
# =============================================================================


class FixGenerator:
    """
    Generates code fixes using LLM.
    
    Supports multiple fix strategies:
    - DIRECT_PATCH: Simple code replacement
    - REFACTOR: Larger code restructuring
    - ADD_DEPENDENCY: Add missing imports/packages
    - CONFIGURATION: Config file changes
    - ROLLBACK: Revert to previous state
    """
    
    def __init__(
        self,
        project_root: Path,
        llm_client: Optional[Any] = None,
    ):
        self.project_root = project_root
        self.llm_client = llm_client
        self.context_builder = ContextBuilder(project_root)
    
    async def generate_fix(
        self,
        issue: RemediationIssue,
        root_cause: Optional[RootCause] = None,
        symptom_issues: Optional[List[RemediationIssue]] = None,
        strategy: Optional[FixStrategy] = None,
    ) -> Optional[RemediationFix]:
        """
        Generate a fix for an issue.
        
        Args:
            issue: The issue to fix
            root_cause: Root cause if this is part of a group
            symptom_issues: Related symptom issues
            strategy: Override strategy (auto-detected if None)
        
        Returns:
            RemediationFix with patches, or None if generation failed
        """
        # Build context
        context = self.context_builder.build_context(
            issue, root_cause, symptom_issues
        )
        
        if not context:
            return self._create_failed_fix(issue, "Could not build context")
        
        # Determine strategy
        if strategy is None:
            strategy = self._determine_strategy(issue, context)
        
        # Build prompt
        prompt = self._build_prompt(context, strategy)
        
        # Call LLM
        try:
            response = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._create_failed_fix(issue, f"LLM error: {str(e)}")
        
        # Parse response into patches
        patches = self._parse_fix_response(response, context)
        
        if not patches:
            return self._create_failed_fix(issue, "No valid patches in LLM response")
        
        # Extract explanation
        explanation = self._extract_explanation(response)
        
        # Create fix object
        fix = RemediationFix(
            id=str(uuid.uuid4()),
            issue_id=issue.id,
            root_cause_id=root_cause.id if root_cause else None,
            strategy=strategy,
            patches=patches,
            explanation=explanation,
            confidence=self._calculate_confidence(issue, patches),
            created_at=datetime.utcnow(),
            status=FixStatus.PENDING,
        )
        
        return fix
    
    def generate_fix_sync(
        self,
        issue: RemediationIssue,
        root_cause: Optional[RootCause] = None,
        symptom_issues: Optional[List[RemediationIssue]] = None,
        strategy: Optional[FixStrategy] = None,
    ) -> Optional[RemediationFix]:
        """Synchronous wrapper for generate_fix."""
        import asyncio
        
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.generate_fix(issue, root_cause, symptom_issues, strategy)
            )
        finally:
            loop.close()
    
    # =========================================================================
    # STRATEGY DETERMINATION
    # =========================================================================
    
    def _determine_strategy(
        self,
        issue: RemediationIssue,
        context: FixContext,
    ) -> FixStrategy:
        """Determine the best fix strategy for an issue."""
        category = issue.category
        
        if category == IssueCategory.IMPORT_ERROR:
            return FixStrategy.ADD_DEPENDENCY
        
        if category == IssueCategory.LINT_ERROR:
            return FixStrategy.DIRECT_PATCH
        
        if category == IssueCategory.SYNTAX_ERROR:
            return FixStrategy.DIRECT_PATCH
        
        if category == IssueCategory.TYPE_ERROR:
            # Check if it's a simple type annotation fix
            if "type" in issue.message.lower() and issue.line_number:
                return FixStrategy.DIRECT_PATCH
            return FixStrategy.REFACTOR
        
        if category == IssueCategory.DOCUMENTATION:
            return FixStrategy.DIRECT_PATCH
        
        if category in (IssueCategory.LOGIC_ERROR, IssueCategory.TEST_FAILURE):
            return FixStrategy.REFACTOR
        
        if category == IssueCategory.SECURITY:
            return FixStrategy.REFACTOR
        
        return FixStrategy.DIRECT_PATCH
    
    # =========================================================================
    # PROMPT BUILDING
    # =========================================================================
    
    def _build_prompt(
        self,
        context: FixContext,
        strategy: FixStrategy,
    ) -> str:
        """Build the LLM prompt for fix generation."""
        issue = context.issue
        
        # Format related context
        related_context = ""
        if context.related_files:
            related_context = "\n## Related Files\n"
            for path, content in context.related_files.items():
                # Truncate if too long
                if len(content) > 2000:
                    content = content[:2000] + "\n... (truncated)"
                related_context += f"\n### {path}\n```\n{content}\n```\n"
        
        # Format file content with line numbers
        lines = context.file_content.split("\n")
        start, end = context.surrounding_lines
        numbered_lines = []
        for i, line in enumerate(lines[start-1:end], start=start):
            marker = ">>>" if i == issue.line_number else "   "
            numbered_lines.append(f"{marker} {i:4d} | {line}")
        file_with_lines = "\n".join(numbered_lines)
        
        prompt = ISSUE_PROMPT_TEMPLATE.format(
            category=issue.category.value,
            severity=issue.severity.value,
            file_path=issue.file_path,
            line_number=issue.line_number or "N/A",
            message=issue.message,
            raw_output=issue.raw_output or "N/A",
            language=context.file_language,
            file_content=file_with_lines,
            related_context=related_context,
        )
        
        # Add strategy hint
        strategy_hints = {
            FixStrategy.DIRECT_PATCH: "Generate a minimal, direct patch.",
            FixStrategy.REFACTOR: "This may require restructuring code. Consider broader changes.",
            FixStrategy.ADD_DEPENDENCY: "Focus on adding missing imports or dependencies.",
            FixStrategy.CONFIGURATION: "This is a configuration issue. Check config files.",
        }
        
        if strategy in strategy_hints:
            prompt += f"\n\n**Strategy Hint**: {strategy_hints[strategy]}"
        
        return prompt
    
    # =========================================================================
    # LLM INTERACTION
    # =========================================================================
    
    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM to generate a fix."""
        if self.llm_client is None:
            # Fallback: return a mock response for testing
            logger.warning("No LLM client configured, using mock response")
            return self._mock_llm_response(prompt)
        
        # Use the configured LLM client
        try:
            response = await self.llm_client.generate(
                system=SYSTEM_PROMPT,
                prompt=prompt,
                max_tokens=2000,
                temperature=0.2,  # Low temperature for precise fixes
            )
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _mock_llm_response(self, prompt: str) -> str:
        """Generate a mock response for testing."""
        return """Based on the error, I'll provide a minimal fix.

Analysis:
The issue appears to be a simple syntax or type error that can be fixed with a direct patch.

```fix
FILE: example.py
---ORIGINAL---
def example():
    return x
---FIXED---
def example():
    return None
```

This fix addresses the issue by providing a default return value."""
    
    # =========================================================================
    # RESPONSE PARSING
    # =========================================================================
    
    def _parse_fix_response(
        self,
        response: str,
        context: FixContext,
    ) -> List[PatchData]:
        """Parse LLM response into PatchData objects."""
        patches = []
        
        # Find all fix blocks
        fix_pattern = r"```fix\s*\n(.*?)```"
        matches = re.findall(fix_pattern, response, re.DOTALL)
        
        for match in matches:
            patch = self._parse_fix_block(match, context)
            if patch:
                patches.append(patch)
        
        # Also try alternative format: ```diff
        diff_pattern = r"```diff\s*\n(.*?)```"
        diff_matches = re.findall(diff_pattern, response, re.DOTALL)
        
        for match in diff_matches:
            patch = self._parse_diff_block(match, context)
            if patch:
                patches.append(patch)
        
        return patches
    
    def _parse_fix_block(
        self,
        block: str,
        context: FixContext,
    ) -> Optional[PatchData]:
        """Parse a fix block into a PatchData object."""
        lines = block.strip().split("\n")
        
        # Find FILE line
        file_path = None
        for line in lines:
            if line.startswith("FILE:"):
                file_path = line.split(":", 1)[1].strip()
                break
        
        # Default to issue file if not specified
        if not file_path:
            file_path = context.issue.file_path
        
        if not file_path:
            return None
        
        # Find ORIGINAL and FIXED sections
        original_start = None
        fixed_start = None
        
        for i, line in enumerate(lines):
            if "---ORIGINAL---" in line or "ORIGINAL:" in line:
                original_start = i + 1
            elif "---FIXED---" in line or "FIXED:" in line:
                fixed_start = i + 1
        
        if original_start is None or fixed_start is None:
            return None
        
        original_lines = lines[original_start:fixed_start - 1]
        fixed_lines = lines[fixed_start:]
        
        original_content = "\n".join(original_lines)
        fixed_content = "\n".join(fixed_lines)
        
        # Generate diff
        diff = self._generate_diff(original_content, fixed_content, file_path)
        
        return PatchData(
            id=hashlib.sha256(diff.encode()).hexdigest()[:16],
            file_path=file_path,
            original_content=original_content,
            patched_content=fixed_content,
            diff=diff,
            start_line=context.issue.line_number,
            end_line=context.issue.line_number,
        )
    
    def _parse_diff_block(
        self,
        block: str,
        context: FixContext,
    ) -> Optional[PatchData]:
        """Parse a diff block into a PatchData object."""
        # Extract file from diff header
        file_match = re.search(r"[+-]{3}\s+[ab]/(.+)", block)
        file_path = file_match.group(1) if file_match else context.issue.file_path
        
        if not file_path:
            return None
        
        # The block is already a diff
        return PatchData(
            id=hashlib.sha256(block.encode()).hexdigest()[:16],
            file_path=file_path,
            original_content="",  # Not available in diff format
            patched_content="",
            diff=block,
            start_line=context.issue.line_number,
        )
    
    def _generate_diff(
        self,
        original: str,
        fixed: str,
        file_path: str,
    ) -> str:
        """Generate a unified diff between original and fixed content."""
        original_lines = original.split("\n")
        fixed_lines = fixed.split("\n")
        
        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
        
        return "\n".join(diff)
    
    def _extract_explanation(self, response: str) -> str:
        """Extract explanation from LLM response."""
        # Remove code blocks
        clean = re.sub(r"```.*?```", "", response, flags=re.DOTALL)
        
        # Extract first few paragraphs
        paragraphs = [p.strip() for p in clean.split("\n\n") if p.strip()]
        
        if paragraphs:
            return " ".join(paragraphs[:2])
        
        return "Fix generated by autonomous remediation agent."
    
    # =========================================================================
    # CONFIDENCE CALCULATION
    # =========================================================================
    
    def _calculate_confidence(
        self,
        issue: RemediationIssue,
        patches: List[PatchData],
    ) -> float:
        """Calculate confidence score for a generated fix."""
        base = issue.fix_confidence
        
        # Adjust based on patch characteristics
        if len(patches) == 1:
            patch = patches[0]
            
            # Smaller patches = higher confidence
            lines_changed = len(patch.diff.split("\n"))
            if lines_changed <= 5:
                base += 0.1
            elif lines_changed <= 20:
                base += 0.05
            elif lines_changed > 50:
                base -= 0.1
        
        # Multiple patches = slightly lower confidence
        if len(patches) > 1:
            base -= 0.05 * (len(patches) - 1)
        
        return min(max(base, 0.0), 1.0)
    
    def _create_failed_fix(
        self,
        issue: RemediationIssue,
        reason: str,
    ) -> RemediationFix:
        """Create a failed fix object."""
        return RemediationFix(
            id=str(uuid.uuid4()),
            issue_id=issue.id,
            strategy=FixStrategy.DIRECT_PATCH,
            patches=[],
            explanation=f"Fix generation failed: {reason}",
            confidence=0.0,
            created_at=datetime.utcnow(),
            status=FixStatus.FAILED,
        )


# =============================================================================
# PATCH APPLICATOR
# =============================================================================


class PatchApplicator:
    """Applies patches to files."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    def apply_patch(
        self,
        patch: PatchData,
        dry_run: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Apply a patch to the target file.
        
        Args:
            patch: The patch to apply
            dry_run: If True, only validate without applying
        
        Returns:
            Tuple of (success, error_message)
        """
        file_path = self.project_root / patch.file_path
        
        if not file_path.exists():
            return False, f"File not found: {patch.file_path}"
        
        try:
            current_content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Failed to read file: {e}"
        
        # Find and replace original content
        if patch.original_content:
            if patch.original_content not in current_content:
                return False, "Original content not found in file (may have changed)"
            
            new_content = current_content.replace(
                patch.original_content,
                patch.patched_content,
                1  # Only replace first occurrence
            )
        else:
            # Apply diff if no original content
            return False, "Cannot apply patch without original content"
        
        if dry_run:
            return True, None
        
        # Write the patched content
        try:
            file_path.write_text(new_content, encoding="utf-8")
            logger.info(f"Applied patch to {patch.file_path}")
            return True, None
        except Exception as e:
            return False, f"Failed to write file: {e}"
    
    def create_backup(self, file_path: str) -> Optional[str]:
        """Create a backup of a file before patching."""
        full_path = self.project_root / file_path
        
        if not full_path.exists():
            return None
        
        try:
            content = full_path.read_text(encoding="utf-8")
            backup_id = hashlib.sha256(content.encode()).hexdigest()[:16]
            return content  # Return content for storing in DB
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None
    
    def revert_patch(
        self,
        file_path: str,
        original_content: str,
    ) -> Tuple[bool, Optional[str]]:
        """Revert a file to its original content."""
        full_path = self.project_root / file_path
        
        try:
            full_path.write_text(original_content, encoding="utf-8")
            logger.info(f"Reverted {file_path} to original state")
            return True, None
        except Exception as e:
            return False, f"Failed to revert file: {e}"
