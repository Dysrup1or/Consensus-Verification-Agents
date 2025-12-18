"""
Tests for SARIF Export Module (Phase 1)

Tests the SARIF 2.1.0 export functionality for GitHub Code Scanning integration.

NOTE: These tests use the tribunal's dataclass definitions (TribunalVerdict, CriterionResult,
JudgeScore, Verdict) rather than the Pydantic schemas.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

import pytest

from modules.sarif_export import (
    SarifExporter,
    SarifDocument,
    SarifLevel,
    SarifKind,
    generate_sarif,
    save_sarif,
    validate_sarif,
    map_criterion_type_to_sarif_level,
    map_verdict_to_sarif_kind,
    map_score_to_sarif_level,
)

# Import tribunal dataclasses (the actual types used by tribunal.py)
from modules.tribunal import (
    TribunalVerdict,
    CriterionResult,
    JudgeScore,
    Verdict,
    StaticAnalysisFileResult,
)
from modules.schemas import JudgeRole


# =============================================================================
# FIXTURES - Using Tribunal Dataclasses
# =============================================================================


@pytest.fixture
def sample_judge_score_pass() -> JudgeScore:
    """Create a passing judge score."""
    return JudgeScore(
        judge_name="Architect Judge",
        judge_role=JudgeRole.ARCHITECT,
        model="claude-sonnet-4",
        score=8,
        explanation="Good architecture with proper separation of concerns.",
        pass_verdict=True,
        confidence=0.92,
        issues=[],
        suggestions=["Consider adding more documentation"],
        is_veto_eligible=False,
    )


@pytest.fixture
def sample_judge_score_fail() -> JudgeScore:
    """Create a failing judge score."""
    return JudgeScore(
        judge_name="Security Judge",
        judge_role=JudgeRole.SECURITY,
        model="deepseek-v3",
        score=3,
        explanation="Critical security vulnerabilities detected.",
        pass_verdict=False,
        confidence=0.95,
        issues=["SQL injection in query builder", "Hardcoded API key"],
        suggestions=["Use parameterized queries", "Move secrets to env vars"],
        is_veto_eligible=True,
    )


@pytest.fixture
def sample_criterion_result_pass(sample_judge_score_pass) -> CriterionResult:
    """Create a passing criterion result."""
    return CriterionResult(
        criterion_id=1,
        criterion_type="security",
        criterion_desc="API keys must be loaded from environment variables",
        scores=[sample_judge_score_pass],
        average_score=8.5,
        consensus_verdict=Verdict.PASS,
        majority_ratio=1.0,
        final_explanation="Criterion passed with strong consensus.",
        relevant_files=["modules/provider_adapter.py"],
        veto_triggered=False,
        veto_reason=None,
    )


@pytest.fixture
def sample_criterion_result_fail(sample_judge_score_fail) -> CriterionResult:
    """Create a failing criterion result."""
    return CriterionResult(
        criterion_id=2,
        criterion_type="security",
        criterion_desc="No hardcoded secrets in codebase",
        scores=[sample_judge_score_fail],
        average_score=3.0,
        consensus_verdict=Verdict.FAIL,
        majority_ratio=1.0,
        final_explanation="Security violations found.",
        relevant_files=["config.py", "utils/db.py"],
        veto_triggered=True,
        veto_reason="Security Judge detected critical vulnerabilities",
    )


@pytest.fixture
def sample_criterion_result_functionality() -> CriterionResult:
    """Create a functionality criterion result with PARTIAL verdict."""
    judge_score = JudgeScore(
        judge_name="User Proxy Judge",
        judge_role=JudgeRole.USER_PROXY,
        model="gemini-2.0-flash",
        score=6,
        explanation="Partially implements the requirement.",
        pass_verdict=False,
        confidence=0.85,
        issues=["Missing pagination"],
        suggestions=["Add page parameter"],
        is_veto_eligible=False,
    )
    return CriterionResult(
        criterion_id=3,
        criterion_type="functionality",
        criterion_desc="Implement pagination for list endpoints",
        scores=[judge_score],
        average_score=6.0,
        consensus_verdict=Verdict.PARTIAL,
        majority_ratio=0.67,
        final_explanation="Partial implementation of pagination.",
        relevant_files=["api/routes.py"],
        veto_triggered=False,
        veto_reason=None,
    )


@pytest.fixture
def sample_tribunal_verdict(
    sample_criterion_result_pass,
    sample_criterion_result_fail,
    sample_criterion_result_functionality,
) -> TribunalVerdict:
    """Create a complete tribunal verdict with mixed results."""
    return TribunalVerdict(
        timestamp=datetime.now().isoformat(),
        overall_verdict=Verdict.VETO,
        overall_score=5.5,
        total_criteria=3,
        passed_criteria=1,
        failed_criteria=2,
        static_analysis_issues=0,
        criterion_results=[
            sample_criterion_result_pass,
            sample_criterion_result_fail,
            sample_criterion_result_functionality,
        ],
        static_analysis_results=[],
        remediation_suggestions=[],
        execution_time_seconds=120.5,
        veto_triggered=True,
        veto_reason="Security Judge veto triggered",
        veto_judge="Security Judge",
        static_analysis_aborted=False,
        abort_reason=None,
    )


@pytest.fixture
def sample_tribunal_verdict_passing() -> TribunalVerdict:
    """Create a passing tribunal verdict."""
    judge_score = JudgeScore(
        judge_name="Architect Judge",
        judge_role=JudgeRole.ARCHITECT,
        model="claude-sonnet-4",
        score=8,
        explanation="All requirements met.",
        pass_verdict=True,
        confidence=0.90,
        issues=[],
        suggestions=[],
        is_veto_eligible=False,
    )
    result = CriterionResult(
        criterion_id=1,
        criterion_type="security",
        criterion_desc="Secure configuration",
        scores=[judge_score],
        average_score=8.0,
        consensus_verdict=Verdict.PASS,
        majority_ratio=1.0,
        final_explanation="Secure configuration validated.",
        relevant_files=["config.py"],
        veto_triggered=False,
        veto_reason=None,
    )
    return TribunalVerdict(
        timestamp=datetime.now().isoformat(),
        overall_verdict=Verdict.PASS,
        overall_score=8.0,
        total_criteria=1,
        passed_criteria=1,
        failed_criteria=0,
        static_analysis_issues=0,
        criterion_results=[result],
        static_analysis_results=[],
        remediation_suggestions=[],
        execution_time_seconds=60.0,
        veto_triggered=False,
        veto_reason=None,
        veto_judge=None,
        static_analysis_aborted=False,
        abort_reason=None,
    )


# =============================================================================
# MAPPING TESTS
# =============================================================================


class TestCriterionTypeMapping:
    """Tests for criterion type to SARIF level mapping."""

    def test_security_maps_to_error(self):
        assert map_criterion_type_to_sarif_level("security") == SarifLevel.ERROR

    def test_functionality_maps_to_warning(self):
        assert map_criterion_type_to_sarif_level("functionality") == SarifLevel.WARNING

    def test_style_maps_to_note(self):
        assert map_criterion_type_to_sarif_level("style") == SarifLevel.NOTE

    def test_unknown_maps_to_warning(self):
        assert map_criterion_type_to_sarif_level("unknown") == SarifLevel.WARNING


class TestVerdictMapping:
    """Tests for verdict to SARIF kind mapping."""

    def test_pass_maps_to_pass(self):
        assert map_verdict_to_sarif_kind("PASS") == SarifKind.PASS
        assert map_verdict_to_sarif_kind("pass") == SarifKind.PASS

    def test_fail_maps_to_fail(self):
        assert map_verdict_to_sarif_kind("FAIL") == SarifKind.FAIL
        assert map_verdict_to_sarif_kind("fail") == SarifKind.FAIL

    def test_veto_maps_to_fail(self):
        assert map_verdict_to_sarif_kind("VETO") == SarifKind.FAIL
        assert map_verdict_to_sarif_kind("veto") == SarifKind.FAIL

    def test_partial_maps_to_review(self):
        assert map_verdict_to_sarif_kind("PARTIAL") == SarifKind.REVIEW
        assert map_verdict_to_sarif_kind("partial") == SarifKind.REVIEW

    def test_error_maps_to_review(self):
        # ERROR is treated as unknown, maps to review (fallback)
        assert map_verdict_to_sarif_kind("ERROR") == SarifKind.REVIEW


class TestScoreMapping:
    """Tests for score to SARIF level mapping."""

    def test_high_score_maps_to_none(self):
        assert map_score_to_sarif_level(8.0) == SarifLevel.NONE

    def test_passing_score_maps_to_none(self):
        assert map_score_to_sarif_level(7.0) == SarifLevel.NONE

    def test_medium_score_maps_to_warning(self):
        assert map_score_to_sarif_level(5.5) == SarifLevel.WARNING

    def test_low_score_maps_to_error(self):
        assert map_score_to_sarif_level(3.0) == SarifLevel.ERROR

    def test_very_low_score_maps_to_error(self):
        assert map_score_to_sarif_level(1.5) == SarifLevel.ERROR


# =============================================================================
# SARIF EXPORTER TESTS
# =============================================================================


class TestSarifExporter:
    """Tests for the SarifExporter class."""

    def test_exporter_initialization(self, sample_tribunal_verdict):
        """Test exporter initializes correctly."""
        exporter = SarifExporter(sample_tribunal_verdict)
        assert exporter.verdict == sample_tribunal_verdict
        assert exporter.include_passing is False

    def test_exporter_builds_document(self, sample_tribunal_verdict):
        """Test exporter builds valid SARIF document."""
        exporter = SarifExporter(sample_tribunal_verdict)
        document = exporter.build_document()
        
        assert document.version == "2.1.0"
        assert len(document.runs) == 1
        assert document.runs[0].tool.driver.name == "Dysruption CVA"

    def test_exporter_to_dict(self, sample_tribunal_verdict):
        """Test exporter converts to dictionary."""
        exporter = SarifExporter(sample_tribunal_verdict)
        sarif_dict = exporter.to_dict()
        
        assert "$schema" in sarif_dict
        assert sarif_dict["version"] == "2.1.0"
        assert "runs" in sarif_dict

    def test_exporter_to_json(self, sample_tribunal_verdict):
        """Test exporter converts to JSON string."""
        exporter = SarifExporter(sample_tribunal_verdict)
        sarif_json = exporter.to_json()
        
        assert isinstance(sarif_json, str)
        parsed = json.loads(sarif_json)
        assert parsed["version"] == "2.1.0"

    def test_exporter_excludes_passing_by_default(self, sample_tribunal_verdict):
        """Test that passing results are excluded by default."""
        exporter = SarifExporter(sample_tribunal_verdict, include_passing=False)
        sarif_dict = exporter.to_dict()
        
        results = sarif_dict["runs"][0]["results"]
        # Should only include failing and partial results
        # Criterion 1 passed (id=1 -> S1), should be excluded
        # Criterion 2 failed (id=2 -> S2), should be included
        # Criterion 3 partial (id=3 -> F3), should be included
        result_ids = [r["ruleId"] for r in results]
        assert "S1" not in result_ids  # Passed, excluded
        assert "S2" in result_ids  # Failed with veto
        assert "F3" in result_ids  # Partial

    def test_exporter_includes_passing_when_requested(self, sample_tribunal_verdict):
        """Test that passing results are included when requested."""
        exporter = SarifExporter(sample_tribunal_verdict, include_passing=True)
        sarif_dict = exporter.to_dict()
        
        results = sarif_dict["runs"][0]["results"]
        result_ids = [r["ruleId"] for r in results]
        assert "S1" in result_ids  # Should now be included

    def test_exporter_rules_match_results(self, sample_tribunal_verdict):
        """Test that rules are defined for all results."""
        exporter = SarifExporter(sample_tribunal_verdict)
        sarif_dict = exporter.to_dict()
        
        rules = sarif_dict["runs"][0]["tool"]["driver"]["rules"]
        results = sarif_dict["runs"][0]["results"]
        
        rule_ids = {r["id"] for r in rules}
        for result in results:
            assert result["ruleId"] in rule_ids

    def test_exporter_veto_marked_as_error(self, sample_tribunal_verdict):
        """Test that veto results are marked as errors."""
        exporter = SarifExporter(sample_tribunal_verdict)
        sarif_dict = exporter.to_dict()
        
        results = sarif_dict["runs"][0]["results"]
        veto_result = next((r for r in results if r["ruleId"] == "S2"), None)
        
        assert veto_result is not None
        assert veto_result["level"] == "error"

    def test_exporter_includes_locations(self, sample_tribunal_verdict):
        """Test that results include file locations."""
        exporter = SarifExporter(sample_tribunal_verdict)
        sarif_dict = exporter.to_dict()
        
        results = sarif_dict["runs"][0]["results"]
        for result in results:
            assert "locations" in result
            assert len(result["locations"]) > 0


class TestSarifExporterSave:
    """Tests for SARIF file saving."""

    def test_save_creates_file(self, sample_tribunal_verdict):
        """Test that save creates a SARIF file."""
        exporter = SarifExporter(sample_tribunal_verdict)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "verdict.sarif"
            saved_path = exporter.save(output_path)
            
            assert saved_path.exists()
            assert saved_path.suffix == ".sarif"

    def test_save_creates_valid_json(self, sample_tribunal_verdict):
        """Test that saved file contains valid JSON."""
        exporter = SarifExporter(sample_tribunal_verdict)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "verdict.sarif"
            saved_path = exporter.save(output_path)
            
            with open(saved_path) as f:
                content = json.load(f)
            
            assert content["version"] == "2.1.0"

    def test_save_creates_parent_directories(self, sample_tribunal_verdict):
        """Test that save creates parent directories if needed."""
        exporter = SarifExporter(sample_tribunal_verdict)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "deep" / "verdict.sarif"
            saved_path = exporter.save(output_path)
            
            assert saved_path.exists()


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestGenerateSarif:
    """Tests for the generate_sarif convenience function."""

    def test_generate_sarif_returns_dict(self, sample_tribunal_verdict):
        """Test that generate_sarif returns a dictionary."""
        result = generate_sarif(sample_tribunal_verdict)
        assert isinstance(result, dict)
        assert "version" in result

    def test_generate_sarif_with_working_directory(self, sample_tribunal_verdict):
        """Test generate_sarif with custom working directory."""
        result = generate_sarif(
            sample_tribunal_verdict,
            working_directory="/custom/path"
        )
        assert result["runs"][0]["invocations"][0]["workingDirectory"]["uri"] == "/custom/path"


class TestSaveSarif:
    """Tests for the save_sarif convenience function."""

    def test_save_sarif_creates_file(self, sample_tribunal_verdict):
        """Test that save_sarif creates a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.sarif"
            result = save_sarif(sample_tribunal_verdict, output_path)
            
            assert result.exists()


# =============================================================================
# VALIDATION TESTS
# =============================================================================


class TestValidateSarif:
    """Tests for SARIF validation."""

    def test_validate_sarif_accepts_valid_document(self, sample_tribunal_verdict):
        """Test that valid SARIF passes validation."""
        sarif_dict = generate_sarif(sample_tribunal_verdict)
        assert validate_sarif(sarif_dict) is True

    def test_validate_sarif_rejects_missing_version(self):
        """Test that missing version is rejected."""
        with pytest.raises(ValueError, match="missing 'version'"):
            validate_sarif({"runs": []})

    def test_validate_sarif_rejects_wrong_version(self):
        """Test that wrong version is rejected."""
        with pytest.raises(ValueError, match="Unsupported SARIF version"):
            validate_sarif({"version": "1.0.0", "runs": []})

    def test_validate_sarif_rejects_missing_runs(self):
        """Test that missing runs is rejected."""
        with pytest.raises(ValueError, match="missing or invalid 'runs'"):
            validate_sarif({"version": "2.1.0"})

    def test_validate_sarif_rejects_missing_tool(self):
        """Test that missing tool in run is rejected."""
        with pytest.raises(ValueError, match="missing 'tool'"):
            validate_sarif({"version": "2.1.0", "runs": [{}]})

    def test_validate_sarif_rejects_missing_driver(self):
        """Test that missing driver is rejected."""
        with pytest.raises(ValueError, match="missing 'driver'"):
            validate_sarif({"version": "2.1.0", "runs": [{"tool": {}}]})


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_results(self):
        """Test handling of verdict with no results."""
        verdict = TribunalVerdict(
            timestamp=datetime.now().isoformat(),
            overall_verdict=Verdict.PASS,
            overall_score=10.0,
            total_criteria=0,
            passed_criteria=0,
            failed_criteria=0,
            static_analysis_issues=0,
            criterion_results=[],
            static_analysis_results=[],
            remediation_suggestions=[],
            execution_time_seconds=0.0,
            veto_triggered=False,
            veto_reason=None,
            veto_judge=None,
            static_analysis_aborted=False,
            abort_reason=None,
        )
        
        sarif_dict = generate_sarif(verdict)
        assert sarif_dict["runs"][0]["results"] == []

    def test_long_message_truncation(self, sample_tribunal_verdict):
        """Test that long messages are truncated."""
        # Modify a result to have a very long description
        sample_tribunal_verdict.criterion_results[0].criterion_desc = "A" * 2000
        
        sarif_dict = generate_sarif(sample_tribunal_verdict, include_passing=True)
        results = sarif_dict["runs"][0]["results"]
        
        for result in results:
            # Text should be truncated to 1000 chars
            assert len(result["message"]["text"]) <= 1500

    def test_windows_path_normalization(self, sample_tribunal_verdict):
        """Test that Windows paths are normalized."""
        # Add a Windows-style path
        sample_tribunal_verdict.criterion_results[1].relevant_files = ["modules\\tribunal.py"]
        
        sarif_dict = generate_sarif(sample_tribunal_verdict)
        results = sarif_dict["runs"][0]["results"]
        
        for result in results:
            for location in result.get("locations", []):
                if "physicalLocation" in location:
                    uri = location["physicalLocation"]["artifactLocation"]["uri"]
                    assert "\\" not in uri  # Should use forward slashes

    def test_passing_verdict_empty_results_when_excluded(
        self, sample_tribunal_verdict_passing
    ):
        """Test that all-passing verdict produces empty results when passing excluded."""
        sarif_dict = generate_sarif(
            sample_tribunal_verdict_passing,
            include_passing=False
        )
        
        # Should have empty results since all passed
        assert sarif_dict["runs"][0]["results"] == []


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests for full SARIF workflow."""

    def test_full_workflow(self, sample_tribunal_verdict):
        """Test complete SARIF generation and validation workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate SARIF
            sarif_dict = generate_sarif(sample_tribunal_verdict)
            
            # Validate
            assert validate_sarif(sarif_dict) is True
            
            # Save
            output_path = Path(tmpdir) / "verdict.sarif"
            save_sarif(sample_tribunal_verdict, output_path)
            
            # Read back and validate
            with open(output_path) as f:
                loaded = json.load(f)
            
            assert validate_sarif(loaded) is True
            assert loaded["version"] == sarif_dict["version"]
            assert len(loaded["runs"]) == len(sarif_dict["runs"])

    def test_sarif_github_compatible_structure(self, sample_tribunal_verdict):
        """Test that SARIF structure is GitHub Code Scanning compatible."""
        sarif_dict = generate_sarif(sample_tribunal_verdict)
        
        # GitHub requires these fields
        assert "$schema" in sarif_dict
        assert sarif_dict["version"] == "2.1.0"
        
        run = sarif_dict["runs"][0]
        
        # Tool must have driver with name
        assert "tool" in run
        assert "driver" in run["tool"]
        assert "name" in run["tool"]["driver"]
        
        # Results must have ruleId and message
        for result in run.get("results", []):
            assert "ruleId" in result
            assert "message" in result
            assert "text" in result["message"]

    def test_invocation_properties(self, sample_tribunal_verdict):
        """Test that invocation includes proper metadata."""
        sarif_dict = generate_sarif(sample_tribunal_verdict)
        
        invocations = sarif_dict["runs"][0]["invocations"]
        assert len(invocations) == 1
        
        invocation = invocations[0]
        assert "executionSuccessful" in invocation
        assert "workingDirectory" in invocation
        
        # Properties should include verdict metadata
        props = invocation.get("properties", {})
        assert "overall_verdict" in props
        assert "overall_score" in props
        assert "veto_triggered" in props
