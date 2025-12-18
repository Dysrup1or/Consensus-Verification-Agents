"""
Issue Detector for Autonomous Remediation Agent

Extracts actionable issues from TribunalVerdict and transforms them
into RemediationIssue objects for downstream processing.

Responsibilities:
- Parse tribunal verdict structure
- Classify issues by category and severity
- Determine auto-fixability
- Extract location information (file, line, column)
- Group related issues for root cause analysis
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from .models import (
    IssueCategory,
    IssueSeverity,
    RemediationIssue,
    RootCause,
)


# =============================================================================
# ISSUE CLASSIFICATION
# =============================================================================


# Patterns for classifying issues by category
CATEGORY_PATTERNS: Dict[IssueCategory, List[str]] = {
    IssueCategory.TYPE_ERROR: [
        r"type\s+error",
        r"type\s+mismatch",
        r"incompatible\s+type",
        r"cannot\s+assign\s+type",
        r"expected\s+.*\s+but\s+got",
        r"property.*does\s+not\s+exist",
        r"argument\s+of\s+type",
        r"type.*is\s+not\s+assignable",
        r"TypeScript\s+error",
    ],
    IssueCategory.RUNTIME_ERROR: [
        r"runtime\s+error",
        r"exception",
        r"crash",
        r"undefined\s+is\s+not",
        r"null\s+reference",
        r"attribute\s+error",
        r"name\s+error",
        r"reference\s+error",
        r"unhandled\s+rejection",
    ],
    IssueCategory.TEST_FAILURE: [
        r"test\s+fail",
        r"assertion\s+fail",
        r"expected\s+.*\s+to\s+(equal|be|match|have)",
        r"expect\s*\(",
        r"assert",
        r"should\s+(be|have|equal)",
        r"test\s+case",
        r"spec\s+fail",
    ],
    IssueCategory.LINT_ERROR: [
        r"lint",
        r"eslint",
        r"pylint",
        r"flake8",
        r"style\s+error",
        r"formatting",
        r"indentation",
        r"trailing\s+whitespace",
        r"line\s+too\s+long",
        r"unused\s+import",
        r"unused\s+variable",
    ],
    IssueCategory.SECURITY: [
        r"security",
        r"vulnerability",
        r"cve",
        r"injection",
        r"xss",
        r"csrf",
        r"sql\s+injection",
        r"auth(entication|orization)",
        r"credential",
        r"sensitive\s+data",
        r"encryption",
        r"unsafe",
    ],
    IssueCategory.IMPORT_ERROR: [
        r"import\s*error",
        r"importerror",
        r"module\s*not\s*found",
        r"cannot\s+find\s+module",
        r"no\s+module\s+named",
        r"could\s+not\s+resolve",
        r"dependency\s+(error|missing)",
        r"unresolved\s+import",
        r"cannot\s+import\s+name",
    ],
    IssueCategory.SYNTAX_ERROR: [
        r"syntax\s+error",
        r"parse\s+error",
        r"unexpected\s+token",
        r"invalid\s+syntax",
        r"unterminated\s+string",
        r"missing\s+semicolon",
        r"missing\s+bracket",
    ],
    IssueCategory.LOGIC_ERROR: [
        r"logic\s+error",
        r"infinite\s+loop",
        r"off\s+by\s+one",
        r"boundary",
        r"edge\s+case",
        r"race\s+condition",
        r"deadlock",
        r"incorrect\s+(result|output|behavior)",
    ],
    IssueCategory.PERFORMANCE: [
        r"performance",
        r"slow",
        r"timeout",
        r"memory\s+leak",
        r"n\+1\s+query",
        r"inefficient",
        r"bottleneck",
        r"latency",
    ],
    IssueCategory.DOCUMENTATION: [
        r"documentation",
        r"docstring",
        r"comment",
        r"jsdoc",
        r"type\s+annotation\s+missing",
        r"missing\s+documentation",
    ],
}

# Patterns for severity classification
SEVERITY_PATTERNS: Dict[IssueSeverity, List[str]] = {
    IssueSeverity.CRITICAL: [
        r"critical",
        r"crash",
        r"data\s+loss",
        r"security\s+vulnerability",
        r"production\s+down",
        r"breaking\s+change",
        r"cannot\s+start",
        r"fatal",
    ],
    IssueSeverity.HIGH: [
        r"error",
        r"fail",
        r"exception",
        r"broken",
        r"does\s+not\s+work",
        r"undefined",
        r"null\s+reference",
    ],
    IssueSeverity.MEDIUM: [
        r"warning",
        r"deprecated",
        r"inconsistent",
        r"may\s+cause",
        r"potential",
    ],
    IssueSeverity.LOW: [
        r"info",
        r"style",
        r"convention",
        r"suggestion",
        r"hint",
        r"nitpick",
    ],
}

# Issue categories that are typically auto-fixable
AUTO_FIXABLE_CATEGORIES: Set[IssueCategory] = {
    IssueCategory.LINT_ERROR,
    IssueCategory.IMPORT_ERROR,
    IssueCategory.SYNTAX_ERROR,
    IssueCategory.TYPE_ERROR,
    IssueCategory.DOCUMENTATION,
}

# Confidence scores by category (higher = more likely to be correctly fixed)
CATEGORY_CONFIDENCE: Dict[IssueCategory, float] = {
    IssueCategory.LINT_ERROR: 0.95,
    IssueCategory.SYNTAX_ERROR: 0.85,
    IssueCategory.IMPORT_ERROR: 0.80,
    IssueCategory.TYPE_ERROR: 0.75,
    IssueCategory.DOCUMENTATION: 0.90,
    IssueCategory.TEST_FAILURE: 0.60,
    IssueCategory.RUNTIME_ERROR: 0.50,
    IssueCategory.LOGIC_ERROR: 0.40,
    IssueCategory.SECURITY: 0.30,
    IssueCategory.PERFORMANCE: 0.35,
    IssueCategory.UNKNOWN: 0.25,
}


# =============================================================================
# LOCATION EXTRACTION
# =============================================================================


@dataclass
class FileLocation:
    """Represents a location in a file."""
    file_path: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None


# Patterns for extracting file locations from error messages
LOCATION_PATTERNS = [
    # TypeScript/JavaScript: file.ts(10,5): error TS1234
    r"(?P<file>[\w./\\-]+\.\w+)\((?P<line>\d+),(?P<col>\d+)\)",
    # Python: File "path/file.py", line 10
    r'File\s+"(?P<file>[^"]+)",\s+line\s+(?P<line>\d+)',
    # ESLint: path/file.ts:10:5
    r"(?P<file>[\w./\\-]+\.\w+):(?P<line>\d+):(?P<col>\d+)",
    # Generic: file.py:10
    r"(?P<file>[\w./\\-]+\.\w+):(?P<line>\d+)",
    # Just filename and line: at file.py line 10
    r"at\s+(?P<file>[\w./\\-]+\.\w+)\s+line\s+(?P<line>\d+)",
    # Stack trace: at function (file.js:10:5)
    r"at\s+\S+\s+\((?P<file>[^:)]+):(?P<line>\d+):(?P<col>\d+)\)",
]


def extract_file_location(text: str) -> Optional[FileLocation]:
    """Extract file location from error message or context."""
    for pattern in LOCATION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            groups = match.groupdict()
            return FileLocation(
                file_path=groups["file"],
                line=int(groups["line"]) if "line" in groups else None,
                column=int(groups.get("col")) if groups.get("col") else None,
            )
    return None


def extract_all_locations(text: str) -> List[FileLocation]:
    """Extract all file locations from text."""
    locations = []
    for pattern in LOCATION_PATTERNS:
        for match in re.finditer(pattern, text):
            groups = match.groupdict()
            loc = FileLocation(
                file_path=groups["file"],
                line=int(groups["line"]) if "line" in groups else None,
                column=int(groups.get("col")) if groups.get("col") else None,
            )
            # Avoid duplicates
            if loc not in locations:
                locations.append(loc)
    return locations


# =============================================================================
# ISSUE DETECTOR
# =============================================================================


class IssueDetector:
    """
    Detects and extracts issues from tribunal verdicts.
    
    Transforms raw verdict data into structured RemediationIssue objects
    with proper classification, severity, and location information.
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root
        self._compiled_category_patterns: Dict[IssueCategory, List[re.Pattern]] = {}
        self._compiled_severity_patterns: Dict[IssueSeverity, List[re.Pattern]] = {}
        
        # Pre-compile regex patterns
        for category, patterns in CATEGORY_PATTERNS.items():
            self._compiled_category_patterns[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
        
        for severity, patterns in SEVERITY_PATTERNS.items():
            self._compiled_severity_patterns[severity] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    
    def classify_category(self, message: str, context: str = "") -> IssueCategory:
        """Classify an issue into a category based on its message."""
        combined = f"{message} {context}".lower()
        
        # Count pattern matches per category
        scores: Dict[IssueCategory, int] = {}
        
        for category, patterns in self._compiled_category_patterns.items():
            score = sum(1 for p in patterns if p.search(combined))
            if score > 0:
                scores[category] = score
        
        if scores:
            return max(scores, key=scores.get)
        
        return IssueCategory.UNKNOWN
    
    def classify_severity(
        self,
        message: str,
        category: IssueCategory,
        context: str = "",
    ) -> IssueSeverity:
        """Classify issue severity based on message and category."""
        combined = f"{message} {context}".lower()
        
        # Check explicit severity patterns
        for severity, patterns in self._compiled_severity_patterns.items():
            for pattern in patterns:
                if pattern.search(combined):
                    return severity
        
        # Fall back to category-based defaults
        category_defaults = {
            IssueCategory.SECURITY: IssueSeverity.HIGH,
            IssueCategory.RUNTIME_ERROR: IssueSeverity.HIGH,
            IssueCategory.SYNTAX_ERROR: IssueSeverity.HIGH,
            IssueCategory.TEST_FAILURE: IssueSeverity.MEDIUM,
            IssueCategory.TYPE_ERROR: IssueSeverity.MEDIUM,
            IssueCategory.IMPORT_ERROR: IssueSeverity.MEDIUM,
            IssueCategory.LOGIC_ERROR: IssueSeverity.MEDIUM,
            IssueCategory.LINT_ERROR: IssueSeverity.LOW,
            IssueCategory.DOCUMENTATION: IssueSeverity.LOW,
            IssueCategory.PERFORMANCE: IssueSeverity.MEDIUM,
            IssueCategory.UNKNOWN: IssueSeverity.MEDIUM,
        }
        
        return category_defaults.get(category, IssueSeverity.MEDIUM)
    
    def estimate_fix_confidence(
        self,
        category: IssueCategory,
        severity: IssueSeverity,
        has_location: bool,
        has_expected_output: bool = False,
    ) -> float:
        """
        Estimate confidence that an issue can be auto-fixed.
        
        Returns a score from 0.0 to 1.0.
        """
        base = CATEGORY_CONFIDENCE.get(category, 0.25)
        
        # Adjust based on factors
        if has_location:
            base += 0.1
        
        if has_expected_output:
            base += 0.15
        
        # Lower confidence for higher severity
        if severity == IssueSeverity.CRITICAL:
            base *= 0.5
        elif severity == IssueSeverity.HIGH:
            base *= 0.7
        
        return min(max(base, 0.0), 1.0)
    
    def is_auto_fixable(
        self,
        category: IssueCategory,
        severity: IssueSeverity,
    ) -> bool:
        """Determine if an issue type is typically auto-fixable."""
        if severity == IssueSeverity.CRITICAL:
            return False
        
        return category in AUTO_FIXABLE_CATEGORIES
    
    # =========================================================================
    # VERDICT PARSING
    # =========================================================================
    
    def extract_from_verdict(
        self,
        verdict: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> List[RemediationIssue]:
        """
        Extract issues from a TribunalVerdict.
        
        Handles various verdict structures:
        - verdict.items[].issues[]
        - verdict.failures[]
        - verdict.errors[]
        """
        issues: List[RemediationIssue] = []
        
        # Method 1: items with issues
        items = verdict.get("items", [])
        for item in items:
            if not item.get("pass", True):
                item_issues = self._extract_from_verdict_item(item, run_id)
                issues.extend(item_issues)
        
        # Method 2: top-level failures
        failures = verdict.get("failures", [])
        for failure in failures:
            issue = self._create_issue_from_failure(failure, run_id)
            if issue:
                issues.append(issue)
        
        # Method 3: top-level errors
        errors = verdict.get("errors", [])
        for error in errors:
            issue = self._create_issue_from_error(error, run_id)
            if issue:
                issues.append(issue)
        
        # Method 4: check overall status
        if not verdict.get("pass", True) and not issues:
            # Create a generic issue if we couldn't extract specifics
            reason = verdict.get("reason", verdict.get("message", "Verification failed"))
            issues.append(self._create_generic_issue(reason, run_id))
        
        # Deduplicate issues
        issues = self._deduplicate_issues(issues)
        
        logger.info(f"Extracted {len(issues)} issues from verdict")
        return issues
    
    def _extract_from_verdict_item(
        self,
        item: Dict[str, Any],
        run_id: Optional[str],
    ) -> List[RemediationIssue]:
        """Extract issues from a single verdict item."""
        issues = []
        
        # Get item context
        file_path = item.get("file_path", item.get("filePath"))
        criterion = item.get("criterion", item.get("criterionId", ""))
        
        # Extract from nested issues
        item_issues = item.get("issues", [])
        for issue_data in item_issues:
            issue = self._create_issue_from_issue_data(
                issue_data, file_path, criterion, run_id
            )
            if issue:
                issues.append(issue)
        
        # If no nested issues, create from item itself
        if not item_issues:
            reason = item.get("reason", item.get("message", ""))
            if reason:
                issue = self._create_issue_from_reason(
                    reason, file_path, criterion, run_id
                )
                if issue:
                    issues.append(issue)
        
        return issues
    
    def _create_issue_from_issue_data(
        self,
        issue_data: Dict[str, Any],
        file_path: Optional[str],
        criterion: str,
        run_id: Optional[str],
    ) -> Optional[RemediationIssue]:
        """Create RemediationIssue from structured issue data."""
        message = issue_data.get("message", issue_data.get("description", ""))
        if not message:
            return None
        
        # Get or infer file location
        loc_file = issue_data.get("file", issue_data.get("filePath", file_path))
        loc_line = issue_data.get("line")
        loc_col = issue_data.get("column")
        
        # Try to extract location from message if not provided
        if not loc_file or not loc_line:
            extracted = extract_file_location(message)
            if extracted:
                loc_file = loc_file or extracted.file_path
                loc_line = loc_line or extracted.line
                loc_col = loc_col or extracted.column
        
        # Classify
        category = self.classify_category(message, criterion)
        severity = self.classify_severity(message, category, criterion)
        
        return RemediationIssue(
            id=self._generate_issue_id(message, loc_file, loc_line),
            remediation_run_id=run_id,
            category=category,
            severity=severity,
            message=message,
            file_path=loc_file,
            line_number=loc_line,
            column_number=loc_col,
            raw_output=issue_data.get("raw_output", ""),
            criterion_id=criterion,
            auto_fixable=self.is_auto_fixable(category, severity),
            fix_confidence=self.estimate_fix_confidence(
                category, severity, bool(loc_file and loc_line)
            ),
            detected_at=datetime.utcnow(),
        )
    
    def _create_issue_from_failure(
        self,
        failure: Dict[str, Any],
        run_id: Optional[str],
    ) -> Optional[RemediationIssue]:
        """Create issue from a failure object."""
        message = failure.get("message", failure.get("reason", str(failure)))
        if not message:
            return None
        
        file_path = failure.get("file", failure.get("filePath"))
        line = failure.get("line")
        
        # Extract location if not provided
        if not file_path or not line:
            extracted = extract_file_location(message)
            if extracted:
                file_path = file_path or extracted.file_path
                line = line or extracted.line
        
        category = self.classify_category(message)
        severity = self.classify_severity(message, category)
        
        return RemediationIssue(
            id=self._generate_issue_id(message, file_path, line),
            remediation_run_id=run_id,
            category=category,
            severity=severity,
            message=message,
            file_path=file_path,
            line_number=line,
            raw_output=failure.get("raw_output", failure.get("stack", "")),
            auto_fixable=self.is_auto_fixable(category, severity),
            fix_confidence=self.estimate_fix_confidence(
                category, severity, bool(file_path and line)
            ),
            detected_at=datetime.utcnow(),
        )
    
    def _create_issue_from_error(
        self,
        error: Dict[str, Any],
        run_id: Optional[str],
    ) -> Optional[RemediationIssue]:
        """Create issue from an error object."""
        # Errors are typically more severe
        message = error.get("message", str(error))
        if not message:
            return None
        
        file_path = error.get("file")
        line = error.get("line")
        
        extracted = extract_file_location(message)
        if extracted:
            file_path = file_path or extracted.file_path
            line = line or extracted.line
        
        category = self.classify_category(message)
        severity = IssueSeverity.HIGH  # Errors default to high
        
        return RemediationIssue(
            id=self._generate_issue_id(message, file_path, line),
            remediation_run_id=run_id,
            category=category,
            severity=severity,
            message=message,
            file_path=file_path,
            line_number=line,
            raw_output=error.get("stack", ""),
            auto_fixable=False,  # Errors usually need review
            fix_confidence=0.3,
            detected_at=datetime.utcnow(),
        )
    
    def _create_issue_from_reason(
        self,
        reason: str,
        file_path: Optional[str],
        criterion: str,
        run_id: Optional[str],
    ) -> Optional[RemediationIssue]:
        """Create issue from a simple reason string."""
        if not reason:
            return None
        
        category = self.classify_category(reason, criterion)
        severity = self.classify_severity(reason, category, criterion)
        
        # Try to extract location
        line = None
        col = None
        extracted = extract_file_location(reason)
        if extracted:
            file_path = file_path or extracted.file_path
            line = extracted.line
            col = extracted.column
        
        return RemediationIssue(
            id=self._generate_issue_id(reason, file_path, line),
            remediation_run_id=run_id,
            category=category,
            severity=severity,
            message=reason,
            file_path=file_path,
            line_number=line,
            column_number=col,
            criterion_id=criterion,
            auto_fixable=self.is_auto_fixable(category, severity),
            fix_confidence=self.estimate_fix_confidence(
                category, severity, bool(file_path and line)
            ),
            detected_at=datetime.utcnow(),
        )
    
    def _create_generic_issue(
        self,
        message: str,
        run_id: Optional[str],
    ) -> RemediationIssue:
        """Create a generic issue when we can't extract specifics."""
        category = self.classify_category(message)
        severity = self.classify_severity(message, category)
        
        return RemediationIssue(
            id=self._generate_issue_id(message, None, None),
            remediation_run_id=run_id,
            category=category,
            severity=severity,
            message=message,
            auto_fixable=False,
            fix_confidence=0.1,
            detected_at=datetime.utcnow(),
        )
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def _generate_issue_id(
        self,
        message: str,
        file_path: Optional[str],
        line: Optional[int],
    ) -> str:
        """Generate a unique ID for an issue."""
        content = f"{message}:{file_path or ''}:{line or ''}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _deduplicate_issues(
        self,
        issues: List[RemediationIssue],
    ) -> List[RemediationIssue]:
        """Remove duplicate issues based on ID."""
        seen: Set[str] = set()
        unique: List[RemediationIssue] = []
        
        for issue in issues:
            if issue.id not in seen:
                seen.add(issue.id)
                unique.append(issue)
        
        return unique
    
    # =========================================================================
    # ROOT CAUSE ANALYSIS
    # =========================================================================
    
    def group_related_issues(
        self,
        issues: List[RemediationIssue],
    ) -> List[List[RemediationIssue]]:
        """
        Group issues that might have a common root cause.
        
        Groups by:
        - Same file
        - Same error pattern
        - Import chain
        """
        groups: List[List[RemediationIssue]] = []
        used: Set[str] = set()
        
        for issue in issues:
            if issue.id in used:
                continue
            
            group = [issue]
            used.add(issue.id)
            
            # Find related issues
            for other in issues:
                if other.id in used:
                    continue
                
                if self._are_issues_related(issue, other):
                    group.append(other)
                    used.add(other.id)
            
            groups.append(group)
        
        return groups
    
    def _are_issues_related(
        self,
        issue1: RemediationIssue,
        issue2: RemediationIssue,
    ) -> bool:
        """Determine if two issues might be related."""
        # Same file
        if issue1.file_path and issue1.file_path == issue2.file_path:
            return True
        
        # Same category and similar message
        if issue1.category == issue2.category:
            # Check for common substrings
            msg1_words = set(issue1.message.lower().split())
            msg2_words = set(issue2.message.lower().split())
            common = msg1_words & msg2_words
            
            if len(common) > 3:
                return True
        
        # Import-related cascade
        if issue1.category == IssueCategory.IMPORT_ERROR:
            if issue1.file_path and issue2.file_path:
                # Check if one imports the other (simplified)
                path1 = Path(issue1.file_path).stem
                path2 = Path(issue2.file_path).stem
                
                if path1 in issue2.message or path2 in issue1.message:
                    return True
        
        return False
    
    def identify_root_cause(
        self,
        group: List[RemediationIssue],
    ) -> Optional[RootCause]:
        """
        Identify the root cause for a group of related issues.
        
        Returns the issue most likely to be the root cause.
        """
        if not group:
            return None
        
        if len(group) == 1:
            issue = group[0]
            return RootCause(
                id=f"rc_{issue.id}",
                primary_issue_id=issue.id,
                symptom_issue_ids=[],
                description=issue.message,
                confidence=0.9,
            )
        
        # Sort by likelihood of being root cause:
        # 1. Import errors (cause downstream issues)
        # 2. Syntax errors (cause parse failures)
        # 3. Earlier line numbers (cascade down)
        # 4. Higher severity
        
        def root_score(issue: RemediationIssue) -> Tuple:
            category_priority = {
                IssueCategory.IMPORT_ERROR: 0,
                IssueCategory.SYNTAX_ERROR: 1,
                IssueCategory.TYPE_ERROR: 2,
            }
            
            severity_priority = {
                IssueSeverity.CRITICAL: 0,
                IssueSeverity.HIGH: 1,
                IssueSeverity.MEDIUM: 2,
                IssueSeverity.LOW: 3,
            }
            
            return (
                category_priority.get(issue.category, 10),
                severity_priority.get(issue.severity, 10),
                issue.line_number or 999999,
            )
        
        sorted_issues = sorted(group, key=root_score)
        root_issue = sorted_issues[0]
        symptoms = [i.id for i in sorted_issues[1:]]
        
        return RootCause(
            id=f"rc_{root_issue.id}",
            primary_issue_id=root_issue.id,
            symptom_issue_ids=symptoms,
            description=f"Root cause: {root_issue.message}",
            confidence=0.7 if len(symptoms) > 0 else 0.9,
        )
