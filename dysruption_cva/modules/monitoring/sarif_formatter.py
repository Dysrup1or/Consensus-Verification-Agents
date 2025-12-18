"""
SARIF (Static Analysis Results Interchange Format) Formatter

Converts CVA Layered Verification results to SARIF 2.1.0 format for:
- GitHub Code Scanning integration
- Azure DevOps integration
- VS Code SARIF Viewer extension
- Other industry-standard tools

SARIF Specification: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import hashlib

# SARIF Schema version
SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"

# CVA Tool metadata
CVA_TOOL_NAME = "CVA Layered Verification"
CVA_TOOL_VERSION = "1.0.0"
CVA_TOOL_INFORMATION_URI = "https://github.com/dysruption/cva"


@dataclass
class SarifLocation:
    """Represents a location in source code."""
    file_path: str
    start_line: int
    start_column: int = 1
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    
    def to_sarif(self, base_path: str = "") -> Dict[str, Any]:
        """Convert to SARIF location object."""
        # Normalize path to forward slashes for SARIF
        relative_path = self.file_path
        if base_path:
            try:
                relative_path = str(Path(self.file_path).relative_to(base_path))
            except ValueError:
                pass
        relative_path = relative_path.replace("\\", "/")
        
        region = {
            "startLine": self.start_line,
            "startColumn": self.start_column,
        }
        if self.end_line:
            region["endLine"] = self.end_line
        if self.end_column:
            region["endColumn"] = self.end_column
            
        return {
            "physicalLocation": {
                "artifactLocation": {
                    "uri": relative_path,
                    "uriBaseId": "%SRCROOT%"
                },
                "region": region
            }
        }


@dataclass
class SarifRule:
    """Represents a SARIF rule (detection pattern)."""
    rule_id: str
    name: str
    short_description: str
    full_description: str = ""
    severity: str = "warning"  # error, warning, note, none
    help_uri: str = ""
    tags: List[str] = field(default_factory=list)
    
    @property
    def sarif_level(self) -> str:
        """Convert severity to SARIF level."""
        mapping = {
            "critical": "error",
            "high": "error",
            "medium": "warning",
            "low": "note",
            "info": "none"
        }
        return mapping.get(self.severity.lower(), "warning")
    
    def to_sarif(self) -> Dict[str, Any]:
        """Convert to SARIF rule object."""
        rule = {
            "id": self.rule_id,
            "name": self.name,
            "shortDescription": {
                "text": self.short_description
            },
            "fullDescription": {
                "text": self.full_description or self.short_description
            },
            "defaultConfiguration": {
                "level": self.sarif_level
            },
            "properties": {
                "tags": self.tags or ["security"]
            }
        }
        if self.help_uri:
            rule["helpUri"] = self.help_uri
        return rule


@dataclass
class SarifResult:
    """Represents a single finding/violation."""
    rule_id: str
    message: str
    location: SarifLocation
    severity: str = "warning"
    fingerprint: str = ""
    
    def to_sarif(self, base_path: str = "") -> Dict[str, Any]:
        """Convert to SARIF result object."""
        # Generate fingerprint for deduplication
        if not self.fingerprint:
            fp_data = f"{self.rule_id}:{self.location.file_path}:{self.location.start_line}"
            self.fingerprint = hashlib.sha256(fp_data.encode()).hexdigest()[:16]
        
        level_mapping = {
            "critical": "error",
            "high": "error", 
            "medium": "warning",
            "low": "note",
            "info": "none"
        }
        
        return {
            "ruleId": self.rule_id,
            "level": level_mapping.get(self.severity.lower(), "warning"),
            "message": {
                "text": self.message
            },
            "locations": [self.location.to_sarif(base_path)],
            "fingerprints": {
                "primaryLocationLineHash": self.fingerprint
            }
        }


class SarifFormatter:
    """
    Formats CVA verification results as SARIF 2.1.0 JSON.
    
    Usage:
        formatter = SarifFormatter()
        formatter.add_rule(SarifRule(...))
        formatter.add_result(SarifResult(...))
        sarif_json = formatter.to_sarif()
        formatter.write_file("results.sarif")
    """
    
    def __init__(
        self,
        tool_name: str = CVA_TOOL_NAME,
        tool_version: str = CVA_TOOL_VERSION,
        base_path: str = ""
    ):
        self.tool_name = tool_name
        self.tool_version = tool_version
        self.base_path = base_path
        self.rules: Dict[str, SarifRule] = {}
        self.results: List[SarifResult] = []
        self.invocation_start: datetime = datetime.utcnow()
        self.invocation_end: Optional[datetime] = None
        self.invocation_success: bool = True
        
    def add_rule(self, rule: SarifRule) -> None:
        """Add a detection rule."""
        self.rules[rule.rule_id] = rule
        
    def add_result(self, result: SarifResult) -> None:
        """Add a finding/violation."""
        self.results.append(result)
        
        # Auto-create rule if not exists
        if result.rule_id not in self.rules:
            self.rules[result.rule_id] = SarifRule(
                rule_id=result.rule_id,
                name=result.rule_id,
                short_description=result.message,
                severity=result.severity
            )
    
    def add_rules_from_patterns(self, patterns: List[Dict[str, Any]]) -> None:
        """Add rules from CVA pattern definitions."""
        for pattern in patterns:
            rule = SarifRule(
                rule_id=pattern.get("rule_id", "UNKNOWN"),
                name=pattern.get("rule_id", "Unknown Rule"),
                short_description=pattern.get("message", "Security issue detected"),
                severity=pattern.get("severity", "medium"),
                tags=["security", pattern.get("severity", "medium")]
            )
            self.add_rule(rule)
    
    def add_results_from_violations(
        self,
        violations: List[Dict[str, Any]],
        default_severity: str = "medium"
    ) -> None:
        """Add results from CVA violation dictionaries."""
        for v in violations:
            location = SarifLocation(
                file_path=v.get("file", v.get("file_path", "unknown")),
                start_line=v.get("line", v.get("line_number", 1)),
                start_column=v.get("column", 1)
            )
            result = SarifResult(
                rule_id=v.get("rule_id", "UNKNOWN"),
                message=v.get("message", "Violation detected"),
                location=location,
                severity=v.get("severity", default_severity)
            )
            self.add_result(result)
    
    def set_invocation_complete(self, success: bool = True) -> None:
        """Mark the invocation as complete."""
        self.invocation_end = datetime.utcnow()
        self.invocation_success = success
        
    def to_sarif(self) -> Dict[str, Any]:
        """Generate complete SARIF document."""
        if not self.invocation_end:
            self.invocation_end = datetime.utcnow()
            
        # Build tool driver with rules
        driver = {
            "name": self.tool_name,
            "version": self.tool_version,
            "informationUri": CVA_TOOL_INFORMATION_URI,
            "rules": [rule.to_sarif() for rule in self.rules.values()]
        }
        
        # Build invocation
        invocation = {
            "executionSuccessful": self.invocation_success,
            "startTimeUtc": self.invocation_start.isoformat() + "Z",
            "endTimeUtc": self.invocation_end.isoformat() + "Z"
        }
        
        # Build results
        results = [r.to_sarif(self.base_path) for r in self.results]
        
        # Build complete SARIF document
        sarif = {
            "$schema": SARIF_SCHEMA,
            "version": SARIF_VERSION,
            "runs": [{
                "tool": {
                    "driver": driver
                },
                "invocations": [invocation],
                "results": results
            }]
        }
        
        return sarif
    
    def to_json(self, indent: int = 2) -> str:
        """Generate SARIF as JSON string."""
        return json.dumps(self.to_sarif(), indent=indent)
    
    def write_file(self, filepath: str) -> None:
        """Write SARIF to file."""
        Path(filepath).write_text(self.to_json(), encoding="utf-8")
        
    @classmethod
    def from_verification_result(
        cls,
        result: Dict[str, Any],
        patterns: List[Dict[str, Any]],
        base_path: str = ""
    ) -> "SarifFormatter":
        """
        Create formatter from CVA verification result.
        
        Args:
            result: The verification result dict (from scheduled_verification)
            patterns: The pattern definitions from QuickConstitutionalScanner
            base_path: Repository root path for relative paths
            
        Returns:
            Populated SarifFormatter ready to output
        """
        formatter = cls(base_path=base_path)
        
        # Add all defined rules
        formatter.add_rules_from_patterns(patterns)
        
        # Add violations as results
        quick_scan = result.get("quick_scan", {})
        violations = quick_scan.get("violations", [])
        formatter.add_results_from_violations(violations)
        
        # Set timing from result
        formatter.invocation_success = result.get("status") != "error"
        
        return formatter


def convert_to_sarif(
    verification_report_path: str,
    patterns: List[Dict[str, Any]],
    output_path: Optional[str] = None,
    base_path: str = ""
) -> str:
    """
    Convenience function to convert a verification report to SARIF.
    
    Args:
        verification_report_path: Path to verification_report.json
        patterns: Pattern definitions from QuickConstitutionalScanner
        output_path: Output path (defaults to same dir with .sarif extension)
        base_path: Repository root for relative paths
        
    Returns:
        Path to the generated SARIF file
    """
    import json
    
    # Load verification report
    report = json.loads(Path(verification_report_path).read_text(encoding="utf-8"))
    
    # Get latest run
    recent_runs = report.get("recent_runs", [])
    if not recent_runs:
        result = {"quick_scan": {"violations": []}, "status": "clean"}
    else:
        result = recent_runs[-1]
    
    # Create formatter
    formatter = SarifFormatter.from_verification_result(result, patterns, base_path)
    
    # Determine output path
    if not output_path:
        output_path = str(Path(verification_report_path).with_suffix(".sarif"))
    
    # Write file
    formatter.write_file(output_path)
    
    return output_path


if __name__ == "__main__":
    # Demo usage
    formatter = SarifFormatter(base_path="/repo")
    
    # Add a rule
    formatter.add_rule(SarifRule(
        rule_id="SEC001",
        name="Hardcoded Secret",
        short_description="Potential hardcoded secret detected",
        severity="critical",
        tags=["security", "secrets"]
    ))
    
    # Add a finding
    formatter.add_result(SarifResult(
        rule_id="SEC001",
        message="Hardcoded API key detected: API_KEY = 'sk-...'",
        location=SarifLocation(
            file_path="/repo/src/config.py",
            start_line=42,
            start_column=1
        ),
        severity="critical"
    ))
    
    formatter.set_invocation_complete(success=True)
    
    print(formatter.to_json())
