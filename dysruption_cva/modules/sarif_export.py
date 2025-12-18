"""
Dysruption CVA - SARIF Export Module
Version: 1.0

Generates SARIF (Static Analysis Results Interchange Format) 2.1.0 output
for native GitHub Code Scanning integration.

SARIF Specification: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
GitHub SARIF Support: https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning

Usage:
    from modules.sarif_export import generate_sarif, SarifExporter
    
    sarif_output = generate_sarif(tribunal_verdict)
    # or
    exporter = SarifExporter(tribunal_verdict)
    sarif_json = exporter.to_dict()
    exporter.save("verdict.sarif")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, Field

# Import from tribunal to use the same dataclasses
# Using TYPE_CHECKING to avoid circular imports during static analysis
if TYPE_CHECKING:
    from .tribunal import TribunalVerdict, CriterionResult, Verdict


# =============================================================================
# SARIF 2.1.0 SCHEMA MODELS
# =============================================================================


class SarifLevel(str, Enum):
    """SARIF result level (severity mapping)."""
    NONE = "none"
    NOTE = "note"
    WARNING = "warning"
    ERROR = "error"


class SarifKind(str, Enum):
    """SARIF result kind."""
    NOT_APPLICABLE = "notApplicable"
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"
    OPEN = "open"
    INFORMATIONAL = "informational"


class SarifMessage(BaseModel):
    """SARIF message object."""
    text: str
    markdown: Optional[str] = None


class SarifArtifactLocation(BaseModel):
    """SARIF artifact location (file reference)."""
    uri: str
    uriBaseId: Optional[str] = None
    index: Optional[int] = None


class SarifRegion(BaseModel):
    """SARIF region (line/column location)."""
    startLine: int = Field(..., ge=1)
    startColumn: Optional[int] = Field(default=1, ge=1)
    endLine: Optional[int] = Field(default=None, ge=1)
    endColumn: Optional[int] = Field(default=None, ge=1)
    snippet: Optional[SarifMessage] = None


class SarifPhysicalLocation(BaseModel):
    """SARIF physical location in a file."""
    artifactLocation: SarifArtifactLocation
    region: Optional[SarifRegion] = None


class SarifLocation(BaseModel):
    """SARIF location wrapper."""
    physicalLocation: Optional[SarifPhysicalLocation] = None
    message: Optional[SarifMessage] = None


class SarifFix(BaseModel):
    """SARIF fix suggestion."""
    description: SarifMessage
    artifactChanges: List[Dict[str, Any]] = Field(default_factory=list)


class SarifResult(BaseModel):
    """SARIF result (individual finding)."""
    ruleId: str
    ruleIndex: Optional[int] = None
    kind: SarifKind = SarifKind.FAIL
    level: SarifLevel = SarifLevel.WARNING
    message: SarifMessage
    locations: List[SarifLocation] = Field(default_factory=list)
    fixes: List[SarifFix] = Field(default_factory=list)
    partialFingerprints: Optional[Dict[str, str]] = None
    properties: Optional[Dict[str, Any]] = None


class SarifReportingDescriptor(BaseModel):
    """SARIF rule definition."""
    id: str
    name: Optional[str] = None
    shortDescription: Optional[SarifMessage] = None
    fullDescription: Optional[SarifMessage] = None
    helpUri: Optional[str] = None
    help: Optional[SarifMessage] = None
    defaultConfiguration: Optional[Dict[str, Any]] = None
    properties: Optional[Dict[str, Any]] = None


class SarifToolDriver(BaseModel):
    """SARIF tool driver (the analysis tool)."""
    name: str
    version: str
    informationUri: Optional[str] = None
    rules: List[SarifReportingDescriptor] = Field(default_factory=list)
    properties: Optional[Dict[str, Any]] = None


class SarifTool(BaseModel):
    """SARIF tool wrapper."""
    driver: SarifToolDriver


class SarifInvocation(BaseModel):
    """SARIF invocation (run metadata)."""
    executionSuccessful: bool
    startTimeUtc: Optional[str] = None
    endTimeUtc: Optional[str] = None
    workingDirectory: Optional[SarifArtifactLocation] = None
    properties: Optional[Dict[str, Any]] = None


class SarifRun(BaseModel):
    """SARIF run (single analysis execution)."""
    tool: SarifTool
    invocations: List[SarifInvocation] = Field(default_factory=list)
    results: List[SarifResult] = Field(default_factory=list)
    properties: Optional[Dict[str, Any]] = None


class SarifDocument(BaseModel):
    """SARIF 2.1.0 root document."""
    version: str = "2.1.0"
    schema_url: str = Field(
        default="https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        alias="$schema"
    )
    runs: List[SarifRun] = Field(default_factory=list)

    class Config:
        populate_by_name = True


# =============================================================================
# SEVERITY AND STATUS MAPPING
# =============================================================================


def map_criterion_type_to_sarif_level(criterion_type: str) -> SarifLevel:
    """Map CVA criterion type to SARIF level."""
    mapping = {
        "security": SarifLevel.ERROR,
        "functionality": SarifLevel.WARNING,
        "style": SarifLevel.NOTE,
        "performance": SarifLevel.WARNING,
        "architecture": SarifLevel.WARNING,
        "documentation": SarifLevel.NOTE,
    }
    return mapping.get(criterion_type.lower(), SarifLevel.WARNING)


def map_verdict_to_sarif_kind(verdict_value: str) -> SarifKind:
    """Map CVA verdict status to SARIF kind."""
    # Verdict enum values from tribunal: PASS, FAIL, PARTIAL, VETO
    verdict_lower = verdict_value.lower() if isinstance(verdict_value, str) else str(verdict_value).lower()
    if "pass" in verdict_lower:
        return SarifKind.PASS
    elif "fail" in verdict_lower:
        return SarifKind.FAIL
    elif "veto" in verdict_lower:
        return SarifKind.FAIL
    elif "partial" in verdict_lower:
        return SarifKind.REVIEW
    else:
        return SarifKind.REVIEW


def map_score_to_sarif_level(score: float) -> SarifLevel:
    """Map CVA score (1-10) to SARIF level."""
    if score >= 7.0:
        return SarifLevel.NONE  # Passing, no issue
    elif score >= 5.0:
        return SarifLevel.WARNING
    elif score >= 3.0:
        return SarifLevel.ERROR
    else:
        return SarifLevel.ERROR


# =============================================================================
# SARIF EXPORTER CLASS
# =============================================================================


class SarifExporter:
    """
    Converts TribunalVerdict to SARIF 2.1.0 format.
    
    Works with the tribunal's dataclass TribunalVerdict, not the Pydantic schemas.
    
    Usage:
        exporter = SarifExporter(verdict)
        sarif_dict = exporter.to_dict()
        exporter.save("verdict.sarif")
    """

    TOOL_NAME = "Dysruption CVA"
    TOOL_VERSION = "1.2"
    TOOL_INFO_URI = "https://github.com/dysruption/cva"
    HELP_BASE_URI = "https://github.com/dysruption/cva/blob/main/docs/rules/"

    def __init__(
        self,
        verdict: Any,  # TribunalVerdict dataclass from tribunal.py
        working_directory: Optional[str] = None,
        include_passing: bool = False,
    ):
        """
        Initialize SARIF exporter.
        
        Args:
            verdict: TribunalVerdict dataclass from tribunal evaluation
            working_directory: Project root directory for relative paths
            include_passing: Whether to include passing criteria (default: False)
        """
        self.verdict = verdict
        self.working_directory = working_directory or os.getcwd()
        self.include_passing = include_passing
        self._rule_index_map: Dict[str, int] = {}

    def _get_criterion_id_str(self, result: Any) -> str:
        """Get criterion ID as string (handles both int and str)."""
        cid = result.criterion_id
        ctype = result.criterion_type.lower() if hasattr(result, 'criterion_type') else "f"
        
        if isinstance(cid, int):
            # Map type to prefix
            prefix_map = {"security": "S", "functionality": "F", "style": "ST"}
            prefix = prefix_map.get(ctype, "F")
            return f"{prefix}{cid}"
        return str(cid)

    def _is_passing(self, result: Any) -> bool:
        """Check if a criterion result is passing."""
        verdict = result.consensus_verdict
        verdict_str = str(verdict).lower() if hasattr(verdict, '__str__') else "fail"
        if hasattr(verdict, 'value'):
            verdict_str = str(verdict.value).lower()
        return "pass" in verdict_str

    def _build_rules(self) -> List[SarifReportingDescriptor]:
        """Build SARIF rule definitions from criteria."""
        rules = []
        
        # Use criterion_results from tribunal's TribunalVerdict
        criterion_results = getattr(self.verdict, 'criterion_results', [])
        
        for idx, result in enumerate(criterion_results):
            rule_id = self._get_criterion_id_str(result)
            self._rule_index_map[rule_id] = idx
            
            # Determine category from type
            category = result.criterion_type.lower() if hasattr(result, 'criterion_type') else "functionality"
            
            rule = SarifReportingDescriptor(
                id=rule_id,
                name=f"CVA-{rule_id}",
                shortDescription=SarifMessage(
                    text=result.criterion_desc[:100] if result.criterion_desc else rule_id
                ),
                fullDescription=SarifMessage(
                    text=result.criterion_desc or ""
                ),
                helpUri=f"{self.HELP_BASE_URI}{rule_id.lower()}.md",
                help=SarifMessage(
                    text=f"CVA verification rule for {category} requirements."
                ),
                defaultConfiguration={
                    "level": map_criterion_type_to_sarif_level(category).value
                },
                properties={
                    "category": category,
                    "precision": "high" if result.majority_ratio >= 0.67 else "medium",
                    "security-severity": "8.0" if category == "security" else "5.0",
                }
            )
            rules.append(rule)
        
        return rules

    def _build_results(self) -> List[SarifResult]:
        """Build SARIF results from verdict."""
        results = []
        
        criterion_results = getattr(self.verdict, 'criterion_results', [])
        
        for result in criterion_results:
            rule_id = self._get_criterion_id_str(result)
            
            # Skip passing results unless explicitly requested
            if not self.include_passing and self._is_passing(result):
                continue
            
            # Determine level based on verdict and score
            if result.veto_triggered:
                level = SarifLevel.ERROR
            elif result.average_score < 5.0:
                level = SarifLevel.ERROR
            elif result.average_score < 7.0:
                level = SarifLevel.WARNING
            else:
                level = SarifLevel.NOTE
            
            # Build message with judge feedback
            message_parts = [f"**{result.criterion_desc}**"]
            message_parts.append(f"\n\nScore: {result.average_score:.1f}/10")
            message_parts.append(f"\nConsensus: {result.majority_ratio*100:.0f}%")
            
            if result.veto_triggered and result.veto_reason:
                message_parts.append(f"\n\n🚫 **VETO**: {result.veto_reason}")
            
            # Add judge scores summary
            scores = getattr(result, 'scores', [])
            if scores:
                message_parts.append("\n\n**Judge Scores:**")
                for js in scores:
                    emoji = "✅" if js.pass_verdict else "❌"
                    judge_name = getattr(js, 'judge_name', 'Judge')
                    message_parts.append(f"\n- {judge_name}: {emoji} {js.score}/10")
            
            message_text = "".join(message_parts)
            
            # Build locations from relevant files
            locations = []
            relevant_files = getattr(result, 'relevant_files', []) or []
            for file_path in relevant_files[:5]:  # Limit to 5 files
                # Normalize path
                normalized_path = str(file_path).replace("\\", "/")
                locations.append(
                    SarifLocation(
                        physicalLocation=SarifPhysicalLocation(
                            artifactLocation=SarifArtifactLocation(
                                uri=normalized_path,
                                uriBaseId="%SRCROOT%"
                            ),
                            region=SarifRegion(
                                startLine=1,  # Default to file start if no specific line
                                startColumn=1
                            )
                        ),
                        message=SarifMessage(
                            text=f"Relevant file for criterion {rule_id}"
                        )
                    )
                )
            
            # If no files, add a placeholder location
            if not locations:
                locations.append(
                    SarifLocation(
                        message=SarifMessage(
                            text="No specific file location identified"
                        )
                    )
                )
            
            # Build fingerprint for deduplication
            overall_verdict = getattr(self.verdict, 'overall_verdict', 'UNKNOWN')
            verdict_str = str(overall_verdict.value) if hasattr(overall_verdict, 'value') else str(overall_verdict)
            fingerprint = f"{rule_id}:{verdict_str}"
            
            # Get consensus verdict string
            consensus = result.consensus_verdict
            consensus_str = str(consensus.value) if hasattr(consensus, 'value') else str(consensus)
            
            sarif_result = SarifResult(
                ruleId=rule_id,
                ruleIndex=self._rule_index_map.get(rule_id),
                kind=map_verdict_to_sarif_kind(consensus_str),
                level=level,
                message=SarifMessage(
                    text=message_text[:1000],  # Limit message length
                    markdown=message_text
                ),
                locations=locations,
                partialFingerprints={
                    "primaryLocationLineHash": fingerprint
                },
                properties={
                    "score": result.average_score,
                    "majority_ratio": result.majority_ratio,
                    "veto_triggered": result.veto_triggered,
                    "criterion_type": result.criterion_type,
                }
            )
            results.append(sarif_result)
        
        return results

    def _build_invocation(self) -> SarifInvocation:
        """Build SARIF invocation metadata."""
        # Determine success based on verdict
        overall_verdict = getattr(self.verdict, 'overall_verdict', None)
        verdict_str = str(overall_verdict.value) if hasattr(overall_verdict, 'value') else str(overall_verdict)
        execution_successful = verdict_str.lower() not in ["error", "veto"]
        
        return SarifInvocation(
            executionSuccessful=execution_successful,
            startTimeUtc=None,  # Tribunal dataclass doesn't have start time
            endTimeUtc=None,
            workingDirectory=SarifArtifactLocation(
                uri=self.working_directory.replace("\\", "/")
            ),
            properties={
                "overall_verdict": verdict_str,
                "overall_score": getattr(self.verdict, 'overall_score', 0.0),
                "passed_count": getattr(self.verdict, 'passed_criteria', 0),
                "failed_count": getattr(self.verdict, 'failed_criteria', 0),
                "veto_triggered": getattr(self.verdict, 'veto_triggered', False),
                "execution_time_seconds": getattr(self.verdict, 'execution_time_seconds', 0.0),
            }
        )

    def build_document(self) -> SarifDocument:
        """Build complete SARIF document."""
        rules = self._build_rules()
        results = self._build_results()
        invocation = self._build_invocation()
        
        tool = SarifTool(
            driver=SarifToolDriver(
                name=self.TOOL_NAME,
                version=self.TOOL_VERSION,
                informationUri=self.TOOL_INFO_URI,
                rules=rules,
                properties={
                    "models": {
                        "architect": "claude-sonnet-4",
                        "security": "deepseek-v3",
                        "user_proxy": "gemini-2.0-flash",
                        "remediation": "gpt-4o-mini",
                    }
                }
            )
        )
        
        run = SarifRun(
            tool=tool,
            invocations=[invocation],
            results=results,
            properties={
                "cva_version": self.TOOL_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        
        return SarifDocument(runs=[run])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        document = self.build_document()
        # Use model_dump with by_alias to get $schema correctly
        return document.model_dump(by_alias=True, exclude_none=True)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Union[str, Path]) -> Path:
        """
        Save SARIF document to file.
        
        Args:
            path: Output file path (should end in .sarif)
            
        Returns:
            Path to saved file
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        
        return path


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def generate_sarif(
    verdict: Any,  # TribunalVerdict dataclass from tribunal.py
    working_directory: Optional[str] = None,
    include_passing: bool = False,
) -> Dict[str, Any]:
    """
    Generate SARIF output from TribunalVerdict.
    
    Args:
        verdict: TribunalVerdict dataclass from tribunal evaluation
        working_directory: Project root for relative paths
        include_passing: Include passing criteria in output
        
    Returns:
        SARIF document as dictionary
    """
    exporter = SarifExporter(
        verdict=verdict,
        working_directory=working_directory,
        include_passing=include_passing,
    )
    return exporter.to_dict()


def save_sarif(
    verdict: Any,  # TribunalVerdict dataclass from tribunal.py
    path: Union[str, Path] = "verdict.sarif",
    working_directory: Optional[str] = None,
    include_passing: bool = False,
) -> Path:
    """
    Generate and save SARIF output from TribunalVerdict.
    
    Args:
        verdict: TribunalVerdict dataclass from tribunal evaluation
        path: Output file path
        working_directory: Project root for relative paths
        include_passing: Include passing criteria in output
        
    Returns:
        Path to saved file
    """
    exporter = SarifExporter(
        verdict=verdict,
        working_directory=working_directory,
        include_passing=include_passing,
    )
    return exporter.save(path)


def validate_sarif(sarif_dict: Dict[str, Any]) -> bool:
    """
    Validate SARIF document against schema.
    
    Note: For full validation, use sarif-om or jsonschema with the official schema.
    This is a basic structural validation.
    
    Args:
        sarif_dict: SARIF document as dictionary
        
    Returns:
        True if valid, raises ValueError if invalid
    """
    # Check required top-level fields
    if "version" not in sarif_dict:
        raise ValueError("SARIF document missing 'version' field")
    
    if sarif_dict.get("version") != "2.1.0":
        raise ValueError(f"Unsupported SARIF version: {sarif_dict.get('version')}")
    
    if "runs" not in sarif_dict or not isinstance(sarif_dict["runs"], list):
        raise ValueError("SARIF document missing or invalid 'runs' field")
    
    for run_idx, run in enumerate(sarif_dict["runs"]):
        if "tool" not in run:
            raise ValueError(f"Run {run_idx} missing 'tool' field")
        
        if "driver" not in run["tool"]:
            raise ValueError(f"Run {run_idx} tool missing 'driver' field")
        
        driver = run["tool"]["driver"]
        if "name" not in driver:
            raise ValueError(f"Run {run_idx} driver missing 'name' field")
        
        if "results" in run:
            for result_idx, result in enumerate(run["results"]):
                if "ruleId" not in result:
                    raise ValueError(f"Run {run_idx} result {result_idx} missing 'ruleId'")
                if "message" not in result:
                    raise ValueError(f"Run {run_idx} result {result_idx} missing 'message'")
    
    return True
