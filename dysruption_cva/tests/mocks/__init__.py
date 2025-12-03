"""
Test mocks package for CVA v1.1

Provides deterministic JSON responses for testing without API calls.
"""

import json
from pathlib import Path
from typing import Any, Dict

MOCKS_DIR = Path(__file__).parent


def load_mock(filename: str) -> Dict[str, Any]:
    """Load a mock JSON file."""
    mock_path = MOCKS_DIR / filename
    if not mock_path.exists():
        raise FileNotFoundError(f"Mock file not found: {mock_path}")
    
    with open(mock_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_extraction_response() -> Dict[str, Any]:
    """Get mock extraction response with invariants."""
    data = load_mock("extraction_response.json")
    return data["extraction_response"]


def get_judge_verdict(judge: str, scenario: str = "pass") -> Dict[str, Any]:
    """
    Get mock judge verdict.
    
    Args:
        judge: "architect", "security", or "user_proxy"
        scenario: "pass", "fail", or "veto" (security only)
    
    Returns:
        Mock verdict dict
    """
    data = load_mock("judge_verdicts.json")
    
    if judge == "security" and scenario == "veto":
        return data["security_verdict_fail_veto"]
    elif judge == "security":
        return data["security_verdict_pass"]
    elif judge == "architect":
        return data["architect_verdict"]
    elif judge == "user_proxy":
        return data["user_proxy_verdict"]
    else:
        raise ValueError(f"Unknown judge: {judge}")


def get_remediation_response() -> Dict[str, Any]:
    """Get mock remediation response with fixes."""
    data = load_mock("remediation_response.json")
    return data["remediation_response"]


__all__ = [
    "load_mock",
    "get_extraction_response",
    "get_judge_verdict", 
    "get_remediation_response",
]
