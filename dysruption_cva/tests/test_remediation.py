"""
Unit tests for Autonomous Remediation Agent

Tests cover:
- Issue detection and classification
- Safety controller (kill switch, rate limits, blast radius)
- Fix generation
- Patch application and rollback
"""

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.remediation.models import (
    ApprovalLevel,
    FixStatus,
    FixStrategy,
    HealthState,
    IssueCategory,
    IssueSeverity,
    PatchData,
    RemediationFix,
    RemediationIssue,
    RemediationRun,
    RemediationStatus,
    RootCause,
)
from modules.remediation.safety import (
    BlastRadiusLimits,
    RateLimits,
    SafetyConfig,
    SafetyController,
    activate_kill_switch,
    deactivate_kill_switch,
    is_kill_switch_active,
)
from modules.remediation.detector import (
    IssueDetector,
    extract_file_location,
    extract_all_locations,
    FileLocation,
)
from modules.remediation.generator import (
    ContextBuilder,
    FixGenerator,
    PatchApplicator,
)
from modules.remediation.engine import (
    RemediationConfig,
    RemediationEngine,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    # Create some test files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        '''def hello():
    print("Hello, World!")
    return x  # undefined variable

def add(a, b):
    return a + b
'''
    )
    (tmp_path / "src" / "utils.py").write_text(
        '''import os
from typing import List

def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()
'''
    )
    return tmp_path


@pytest.fixture
def sample_verdict() -> Dict[str, Any]:
    """Sample tribunal verdict with issues."""
    return {
        "id": "verdict-123",
        "pass": False,
        "items": [
            {
                "file_path": "src/main.py",
                "pass": False,
                "criterion": "no-undefined-vars",
                "reason": "Undefined variable 'x' at line 3",
                "issues": [
                    {
                        "message": "NameError: name 'x' is not defined",
                        "file": "src/main.py",
                        "line": 3,
                        "column": 12,
                    }
                ],
            },
            {
                "file_path": "src/main.py",
                "pass": False,
                "criterion": "type-check",
                "reason": "Type error in function",
                "issues": [
                    {
                        "message": "Argument of type 'str' is not assignable to parameter of type 'int'",
                        "file": "src/main.py",
                        "line": 5,
                    }
                ],
            },
        ],
    }


@pytest.fixture
def safety_config() -> SafetyConfig:
    """Default safety configuration for tests."""
    return SafetyConfig(
        enabled=True,
        blast_radius=BlastRadiusLimits(
            max_files_per_run=5,
            max_lines_changed=100,
            forbidden_paths=["*.env", "**/secrets/**"],
        ),
        rate_limits=RateLimits(
            max_fixes_per_hour=10,
            max_fixes_per_day=50,
        ),
    )


# =============================================================================
# ISSUE DETECTION TESTS
# =============================================================================


class TestIssueDetector:
    """Tests for issue detection and classification."""
    
    def test_classify_type_error(self):
        """Test classification of type errors."""
        detector = IssueDetector()
        
        messages = [
            "Type 'string' is not assignable to type 'number'",
            "Argument of type 'str' cannot be assigned to parameter",
            "TypeScript error TS2345: incompatible types",
        ]
        
        for msg in messages:
            category = detector.classify_category(msg)
            assert category == IssueCategory.TYPE_ERROR, f"Failed for: {msg}"
    
    def test_classify_import_error(self):
        """Test classification of import errors."""
        detector = IssueDetector()
        
        messages = [
            "ModuleNotFoundError: No module named 'foo'",
            "Cannot find module 'react'",
            "ImportError: cannot import name 'bar'",
        ]
        
        for msg in messages:
            category = detector.classify_category(msg)
            assert category == IssueCategory.IMPORT_ERROR, f"Failed for: {msg}"
    
    def test_classify_lint_error(self):
        """Test classification of lint errors."""
        detector = IssueDetector()
        
        messages = [
            "eslint: Unexpected trailing whitespace",
            "pylint W0612: Unused variable 'foo'",
            "Line too long (120 > 100 characters)",
        ]
        
        for msg in messages:
            category = detector.classify_category(msg)
            assert category == IssueCategory.LINT_ERROR, f"Failed for: {msg}"
    
    def test_classify_severity(self):
        """Test severity classification."""
        detector = IssueDetector()
        
        # Critical
        assert detector.classify_severity(
            "CRITICAL: Data loss detected",
            IssueCategory.RUNTIME_ERROR
        ) == IssueSeverity.CRITICAL
        
        # High
        assert detector.classify_severity(
            "Error: Cannot read property of undefined",
            IssueCategory.RUNTIME_ERROR
        ) == IssueSeverity.HIGH
        
        # Low (style)
        assert detector.classify_severity(
            "Style suggestion: use const instead of let",
            IssueCategory.LINT_ERROR
        ) == IssueSeverity.LOW
    
    def test_extract_from_verdict(self, sample_verdict):
        """Test extraction of issues from verdict."""
        detector = IssueDetector()
        issues = detector.extract_from_verdict(sample_verdict, "run-123")
        
        assert len(issues) == 2
        assert all(isinstance(i, RemediationIssue) for i in issues)
        assert issues[0].file_path == "src/main.py"
        assert issues[0].line_number == 3
    
    def test_group_related_issues(self, sample_verdict):
        """Test grouping of related issues."""
        detector = IssueDetector()
        issues = detector.extract_from_verdict(sample_verdict)
        
        groups = detector.group_related_issues(issues)
        
        # Both issues are in same file, should be grouped
        assert len(groups) == 1
        assert len(groups[0]) == 2
    
    def test_identify_root_cause(self, sample_verdict):
        """Test root cause identification."""
        detector = IssueDetector()
        issues = detector.extract_from_verdict(sample_verdict)
        
        groups = detector.group_related_issues(issues)
        root_cause = detector.identify_root_cause(groups[0])
        
        assert root_cause is not None
        assert root_cause.primary_issue_id in [i.id for i in issues]


class TestFileLocationExtraction:
    """Tests for file location extraction from error messages."""
    
    def test_python_traceback_format(self):
        """Test extraction from Python traceback format."""
        message = 'File "src/app.py", line 42'
        loc = extract_file_location(message)
        
        assert loc is not None
        assert loc.file_path == "src/app.py"
        assert loc.line == 42
    
    def test_typescript_format(self):
        """Test extraction from TypeScript format."""
        message = "src/component.tsx(15,8): error TS2345"
        loc = extract_file_location(message)
        
        assert loc is not None
        assert loc.file_path == "src/component.tsx"
        assert loc.line == 15
        assert loc.column == 8
    
    def test_eslint_format(self):
        """Test extraction from ESLint format."""
        message = "src/utils.js:25:10 - Unexpected semicolon"
        loc = extract_file_location(message)
        
        assert loc is not None
        assert loc.file_path == "src/utils.js"
        assert loc.line == 25
        assert loc.column == 10
    
    def test_extract_all_locations(self):
        """Test extraction of multiple locations."""
        message = """
        Error in src/a.py:10:5
        Called from src/b.py:20
        Origin: File "src/c.py", line 30
        """
        locations = extract_all_locations(message)
        
        assert len(locations) >= 2  # May find more depending on patterns


# =============================================================================
# SAFETY CONTROLLER TESTS
# =============================================================================


class TestSafetyController:
    """Tests for safety controller."""
    
    def test_kill_switch_env_var(self, temp_project):
        """Test kill switch via environment variable."""
        with patch.dict(os.environ, {"CVA_REMEDIATION_KILL_SWITCH": "true"}):
            active, reason = is_kill_switch_active()
            assert active is True
            assert "Environment variable" in reason
    
    def test_kill_switch_file(self, temp_project):
        """Test kill switch via stop file."""
        stop_file = temp_project / ".cva-remediation-stop"
        stop_file.write_text("Emergency stop requested")
        
        active, reason = is_kill_switch_active(project_root=temp_project)
        
        assert active is True
        assert "Stop file" in reason
        
        # Cleanup
        stop_file.unlink()
    
    def test_activate_deactivate_kill_switch(self, temp_project):
        """Test activation and deactivation of kill switch."""
        # Activate
        activate_kill_switch("Test activation", "pytest", project_root=temp_project)
        
        active, _ = is_kill_switch_active(project_root=temp_project)
        assert active is True
        
        # Deactivate
        deactivate_kill_switch(project_root=temp_project)
        
        active, _ = is_kill_switch_active(project_root=temp_project)
        assert active is False
    
    def test_blast_radius_limits(self, safety_config):
        """Test blast radius checking."""
        controller = SafetyController(safety_config)
        
        # Within limits
        ok, reason = controller.check_blast_radius(
            files_to_modify=["a.py", "b.py"],
            lines_changed=50,
        )
        assert ok is True
        
        # Exceeds file limit
        ok, reason = controller.check_blast_radius(
            files_to_modify=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            lines_changed=10,
        )
        assert ok is False
        assert "Too many files" in reason
        
        # Exceeds line limit
        ok, reason = controller.check_blast_radius(
            files_to_modify=["a.py"],
            lines_changed=200,
        )
        assert ok is False
        assert "Too many lines" in reason
    
    def test_forbidden_paths(self, safety_config):
        """Test forbidden path checking."""
        controller = SafetyController(safety_config)
        
        # Check forbidden
        ok, reason = controller.check_blast_radius(
            files_to_modify=[".env"],
        )
        assert ok is False
        assert "forbidden" in reason.lower()
        
        # Check allowed
        ok, _ = controller.check_blast_radius(
            files_to_modify=["src/main.py"],
        )
        assert ok is True
    
    def test_rate_limiting(self, safety_config):
        """Test rate limiting."""
        controller = SafetyController(safety_config)
        
        # Should be allowed initially
        ok, _ = controller.check_rate_limit()
        assert ok is True
        
        # Record fixes up to limit
        for _ in range(10):
            controller.record_fix_applied()
        
        # Should be blocked
        ok, reason = controller.check_rate_limit()
        assert ok is False
        assert "limit" in reason.lower()
    
    def test_approval_classification(self, safety_config):
        """Test fix approval level classification."""
        controller = SafetyController(safety_config)
        
        # High confidence lint error -> AUTO
        issue = RemediationIssue(
            id="test-1",
            category=IssueCategory.LINT_ERROR,
            severity=IssueSeverity.LOW,
            message="Unused import",
        )
        level = controller.classify_approval_level(issue, fix_confidence=0.95)
        assert level == ApprovalLevel.AUTO
        
        # Security issue -> MANUAL (always)
        security_issue = RemediationIssue(
            id="test-2",
            category=IssueCategory.SECURITY,
            severity=IssueSeverity.HIGH,
            message="SQL injection vulnerability",
        )
        level = controller.classify_approval_level(security_issue, fix_confidence=0.95)
        assert level == ApprovalLevel.MANUAL
    
    def test_pre_flight_check(self, safety_config, temp_project):
        """Test pre-flight safety check."""
        controller = SafetyController(safety_config, project_root=temp_project)
        
        # Should pass
        ok, issues = controller.pre_flight_check(
            files_to_modify=["src/main.py"],
            lines_changed=10,
        )
        assert ok is True
        assert len(issues) == 0
        
        # Should fail (forbidden path)
        ok, issues = controller.pre_flight_check(
            files_to_modify=[".env"],
        )
        assert ok is False
        assert len(issues) > 0


# =============================================================================
# FIX GENERATOR TESTS
# =============================================================================


class TestContextBuilder:
    """Tests for context building."""
    
    def test_build_context(self, temp_project):
        """Test building fix context."""
        builder = ContextBuilder(temp_project)
        
        issue = RemediationIssue(
            id="test-1",
            category=IssueCategory.RUNTIME_ERROR,
            severity=IssueSeverity.HIGH,
            message="Undefined variable 'x'",
            file_path="src/main.py",
            line_number=3,
        )
        
        context = builder.build_context(issue)
        
        assert context is not None
        assert context.file_content is not None
        assert "def hello" in context.file_content
        assert context.file_language == "python"
    
    def test_detect_language(self, temp_project):
        """Test language detection."""
        builder = ContextBuilder(temp_project)
        
        assert builder._detect_language(Path("foo.py")) == "python"
        assert builder._detect_language(Path("foo.ts")) == "typescript"
        assert builder._detect_language(Path("foo.tsx")) == "typescript"
        assert builder._detect_language(Path("foo.js")) == "javascript"
        assert builder._detect_language(Path("foo.unknown")) == "text"


class TestPatchApplicator:
    """Tests for patch application."""
    
    def test_apply_patch(self, temp_project):
        """Test applying a patch."""
        applicator = PatchApplicator(temp_project)
        
        patch = PatchData(
            id="patch-1",
            file_path="src/main.py",
            original_content='return x  # undefined variable',
            patched_content='return None  # fixed undefined variable',
            diff="",
        )
        
        success, error = applicator.apply_patch(patch)
        
        assert success is True
        assert error is None
        
        # Verify file was modified
        content = (temp_project / "src" / "main.py").read_text()
        assert "return None" in content
    
    def test_apply_patch_dry_run(self, temp_project):
        """Test dry run doesn't modify file."""
        applicator = PatchApplicator(temp_project)
        
        original_content = (temp_project / "src" / "main.py").read_text()
        
        patch = PatchData(
            id="patch-1",
            file_path="src/main.py",
            original_content='return x',
            patched_content='return None',
            diff="",
        )
        
        success, _ = applicator.apply_patch(patch, dry_run=True)
        
        assert success is True
        
        # Verify file was NOT modified
        assert (temp_project / "src" / "main.py").read_text() == original_content
    
    def test_create_backup(self, temp_project):
        """Test backup creation."""
        applicator = PatchApplicator(temp_project)
        
        backup = applicator.create_backup("src/main.py")
        
        assert backup is not None
        assert "def hello" in backup
    
    def test_revert_patch(self, temp_project):
        """Test reverting a patch."""
        applicator = PatchApplicator(temp_project)
        
        # Get original
        original = (temp_project / "src" / "main.py").read_text()
        
        # Modify file
        (temp_project / "src" / "main.py").write_text("MODIFIED")
        
        # Revert
        success, _ = applicator.revert_patch("src/main.py", original)
        
        assert success is True
        assert (temp_project / "src" / "main.py").read_text() == original


# =============================================================================
# ENGINE TESTS
# =============================================================================


class TestRemediationEngine:
    """Tests for the main remediation engine."""
    
    @pytest.fixture
    def engine(self, temp_project, safety_config) -> RemediationEngine:
        """Create a test engine."""
        config = RemediationConfig(
            enabled=True,
            auto_apply=True,
            max_iterations=3,
            safety=safety_config,
        )
        return RemediationEngine(temp_project, config)
    
    @pytest.mark.asyncio
    async def test_remediate_detects_issues(self, engine, sample_verdict):
        """Test that remediation detects issues from verdict."""
        # Don't auto-apply for this test
        engine.config.auto_apply = False
        
        run = await engine.remediate(sample_verdict)
        
        assert run.status in (RemediationStatus.COMPLETED, RemediationStatus.IN_PROGRESS)
        assert len(run.issues) == 2
    
    @pytest.mark.asyncio
    async def test_remediate_respects_kill_switch(self, engine, sample_verdict, temp_project):
        """Test that remediation respects kill switch."""
        # Activate kill switch
        (temp_project / ".cva-remediation-stop").write_text("Test stop")
        
        run = await engine.remediate(sample_verdict)
        
        assert run.status == RemediationStatus.BLOCKED
        assert "kill switch" in run.error.lower()
        
        # Cleanup
        (temp_project / ".cva-remediation-stop").unlink()
    
    @pytest.mark.asyncio
    async def test_remediate_empty_verdict(self, engine):
        """Test handling of verdict with no issues."""
        verdict = {"id": "empty", "pass": True, "items": []}
        
        run = await engine.remediate(verdict)
        
        assert run.status == RemediationStatus.COMPLETED
        assert len(run.issues) == 0


# =============================================================================
# MODEL TESTS
# =============================================================================


class TestModels:
    """Tests for data models."""
    
    def test_remediation_issue_to_dict(self):
        """Test issue serialization."""
        issue = RemediationIssue(
            id="test-123",
            category=IssueCategory.TYPE_ERROR,
            severity=IssueSeverity.HIGH,
            message="Test error",
            file_path="src/main.py",
            line_number=10,
        )
        
        data = issue.to_db_dict()
        
        assert data["id"] == "test-123"
        assert data["category"] == "type_error"
        assert data["severity"] == "high"
        assert data["file_path"] == "src/main.py"
    
    def test_remediation_fix_to_dict(self):
        """Test fix serialization."""
        fix = RemediationFix(
            id="fix-123",
            issue_id="issue-123",
            strategy=FixStrategy.DIRECT_PATCH,
            patches=[
                PatchData(
                    id="patch-1",
                    file_path="src/main.py",
                    original_content="old",
                    patched_content="new",
                    diff="diff",
                )
            ],
            explanation="Fixed the bug",
            confidence=0.85,
            status=FixStatus.PENDING,
        )
        
        data = fix.to_db_dict()
        
        assert data["id"] == "fix-123"
        assert data["strategy"] == "direct_patch"
        assert data["confidence"] == 0.85
    
    def test_remediation_run_to_dict(self):
        """Test run serialization."""
        run = RemediationRun(
            id="run-123",
            verdict_id="verdict-456",
            status=RemediationStatus.COMPLETED,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            iterations=2,
            fixes_applied=1,
            fixes_reverted=0,
            health_state=HealthState.HEALTHY,
        )
        
        data = run.to_db_dict()
        
        assert data["id"] == "run-123"
        assert data["status"] == "completed"
        assert data["iterations"] == 2


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests for the full remediation flow."""
    
    @pytest.mark.asyncio
    async def test_full_remediation_flow(self, temp_project):
        """Test complete remediation flow with mock LLM."""
        # Setup
        config = RemediationConfig(
            enabled=True,
            auto_apply=True,
            max_iterations=2,
        )
        
        # Create engine with mock LLM
        engine = RemediationEngine(temp_project, config)
        
        # Create a simple verdict
        verdict = {
            "id": "test-verdict",
            "pass": False,
            "items": [
                {
                    "file_path": "src/main.py",
                    "pass": False,
                    "reason": "Undefined variable 'x' at line 3",
                }
            ],
        }
        
        # Run remediation
        run = await engine.remediate(verdict)
        
        # Verify
        assert run.id is not None
        assert run.status in (
            RemediationStatus.COMPLETED,
            RemediationStatus.IN_PROGRESS,
            RemediationStatus.PARTIAL,
        )
        assert len(run.issues) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
