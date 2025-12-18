"""
Dysruption CVA - Parser Module (Module B: Constitution Parser / Extraction)
Reads spec.txt and extracts invariants as structured JSON using Gemini Flash.
Version: 1.1 - Enhanced with few-shot examples, category coverage enforcement,
               and Pydantic schema integration.

Key Features:
- Few-shot extraction prompts for better accuracy
- Category coverage enforcement: Security, Functionality, Style required
- Re-prompts specifically for missing categories
- Integration with schemas.py Pydantic models
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TypedDict

import yaml
from loguru import logger

from .schemas import (
    Invariant,
    InvariantCategory,
    InvariantSet,
    InvariantSeverity,
)

try:
    import litellm

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.error("LiteLLM not available. Install with: pip install litellm")


# Type definitions for better type safety (legacy compatibility)
class InvariantDict(TypedDict):
    id: int
    desc: str
    category: str
    severity: str


class InvariantsDict(TypedDict):
    security: List[InvariantDict]
    functionality: List[InvariantDict]
    style: List[InvariantDict]


# Required categories for coverage enforcement
REQUIRED_CATEGORIES: Set[str] = {"security", "functionality", "style"}


# Schema for invariants (v1.1 with categories)
INVARIANTS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["security", "functionality", "style"],
    "properties": {
        "security": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "desc", "severity"],
                "properties": {
                    "id": {"type": "integer"},
                    "desc": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                    },
                },
            },
        },
        "functionality": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "desc", "severity"],
                "properties": {
                    "id": {"type": "integer"},
                    "desc": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                    },
                },
            },
        },
        "style": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "desc", "severity"],
                "properties": {
                    "id": {"type": "integer"},
                    "desc": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                    },
                },
            },
        },
    },
}


# ============================================================================
# EXTRACTION SYSTEM PROMPT WITH FEW-SHOT EXAMPLES (v1.1 - Category Coverage)
# ============================================================================
EXTRACTION_SYSTEM_PROMPT: str = """You are an expert requirements analyst specializing in extracting requirements from project specifications.

Your task is to extract requirements into THREE REQUIRED categories: Security, Functionality, and Style.

## Output Schema (STRICT - ALL THREE CATEGORIES REQUIRED):
{
    "security": [
        {"id": 1, "desc": "Security requirement description", "severity": "critical|high|medium|low"}
    ],
    "functionality": [
        {"id": 1, "desc": "Functional requirement description", "severity": "critical|high|medium|low"}
    ],
    "style": [
        {"id": 1, "desc": "Code style requirement description", "severity": "critical|high|medium|low"}
    ]
}

## Category Definitions:

**Security Requirements** (MUST include at least 2):
- Authentication and authorization mechanisms
- Input validation and sanitization
- Encryption and data protection
- API security (rate limiting, CORS, HTTPS)
- Secrets management (environment variables, no hardcoded keys)
- Error handling that doesn't leak sensitive information
- Dependency security (known vulnerabilities)

**Functionality Requirements** (MUST include at least 3):
- Core feature implementations
- Business logic and rules
- Data handling and validation
- API endpoints and their behavior
- User-facing interactions
- Error handling and recovery
- Integration requirements

**Style Requirements** (MUST include at least 2):
- Code formatting (PEP 8, ESLint rules)
- Type annotations and hints
- Documentation (docstrings, comments)
- Naming conventions
- File organization
- Linting compliance (pylint, flake8, bandit)
- Testing requirements

## Severity Levels:
- **critical**: Must pass, failure triggers veto
- **high**: Strong weight in scoring
- **medium**: Standard weight
- **low**: Minor, advisory

## Few-Shot Examples:

### Example 1:
**Input Spec:** "Build a secure Python app with Firebase authentication and dark mode support."

**Output:**
```json
{
    "security": [
        {"id": 1, "desc": "Use Firebase OAuth2/JWT for secure authentication", "severity": "critical"},
        {"id": 2, "desc": "Store Firebase credentials in environment variables, never in code", "severity": "critical"},
        {"id": 3, "desc": "Use HTTPS for all API communications", "severity": "high"},
        {"id": 4, "desc": "Validate all user input before processing", "severity": "high"}
    ],
    "functionality": [
        {"id": 1, "desc": "Implement user login and registration via Firebase", "severity": "critical"},
        {"id": 2, "desc": "Implement dark mode theme toggle", "severity": "high"},
        {"id": 3, "desc": "Persist user theme preference across sessions", "severity": "medium"},
        {"id": 4, "desc": "Handle authentication errors with clear user feedback", "severity": "high"},
        {"id": 5, "desc": "Support session management with logout functionality", "severity": "medium"}
    ],
    "style": [
        {"id": 1, "desc": "Follow PEP 8 style guidelines for Python code", "severity": "medium"},
        {"id": 2, "desc": "Add type hints to all function signatures", "severity": "medium"},
        {"id": 3, "desc": "Include docstrings for all public functions and classes", "severity": "low"}
    ]
}
```

### Example 2:
**Input Spec:** "Create REST API for task management with PostgreSQL."

**Output:**
```json
{
    "security": [
        {"id": 1, "desc": "Implement API authentication (JWT or API keys)", "severity": "critical"},
        {"id": 2, "desc": "Use parameterized queries to prevent SQL injection", "severity": "critical"},
        {"id": 3, "desc": "Store database credentials in environment variables", "severity": "high"},
        {"id": 4, "desc": "Implement rate limiting on API endpoints", "severity": "medium"}
    ],
    "functionality": [
        {"id": 1, "desc": "Implement CRUD operations for tasks", "severity": "critical"},
        {"id": 2, "desc": "Support filtering and sorting tasks by status, date, priority", "severity": "high"},
        {"id": 3, "desc": "Return paginated results for task lists", "severity": "medium"},
        {"id": 4, "desc": "Use proper HTTP status codes (200, 201, 400, 401, 404, 500)", "severity": "high"},
        {"id": 5, "desc": "Validate task input data before database insertion", "severity": "high"}
    ],
    "style": [
        {"id": 1, "desc": "Follow REST API naming conventions for endpoints", "severity": "medium"},
        {"id": 2, "desc": "Use consistent JSON response format across all endpoints", "severity": "medium"},
        {"id": 3, "desc": "Include OpenAPI/Swagger documentation", "severity": "low"}
    ]
}
```

## CRITICAL Rules:
1. ALL THREE CATEGORIES (security, functionality, style) MUST have at least 2 items each
2. Each description should be specific, verifiable, and actionable
3. Infer security requirements even if not explicitly stated
4. Output ONLY valid JSON, no other text or explanation
5. Validate your JSON has all three categories before responding"""


# ============================================================================
# CATEGORY-SPECIFIC RE-PROMPT TEMPLATES
# ============================================================================
CATEGORY_REPROMPT_TEMPLATES: Dict[str, str] = {
    "security": """You are a security expert. The previous extraction is MISSING security requirements.

Analyze the specification and extract security requirements including:
- Authentication and authorization
- Input validation and sanitization
- Encryption and secrets management
- API security (HTTPS, rate limiting, CORS)
- Error handling that doesn't leak information
- Dependency vulnerability considerations

Output ONLY a JSON object with security requirements:
{"security": [{"id": 1, "desc": "...", "severity": "critical|high|medium|low"}]}

Specification:
---
{spec_content}
---""",
    "functionality": """You are a functional requirements expert. The previous extraction is MISSING functionality requirements.

Analyze the specification and extract functional requirements including:
- Core feature implementations
- Business logic and rules
- Data handling and validation
- API behavior and endpoints
- Error handling and recovery
- User interactions

Output ONLY a JSON object with functionality requirements:
{"functionality": [{"id": 1, "desc": "...", "severity": "critical|high|medium|low"}]}

Specification:
---
{spec_content}
---""",
    "style": """You are a code quality expert. The previous extraction is MISSING style requirements.

Analyze the specification and extract style requirements including:
- Code formatting standards (PEP 8, ESLint)
- Type annotations
- Documentation (docstrings, comments)
- Naming conventions
- File organization
- Linting compliance
- Testing requirements

Output ONLY a JSON object with style requirements:
{"style": [{"id": 1, "desc": "...", "severity": "critical|high|medium|low"}]}

Specification:
---
{spec_content}
---""",
}


class ConstitutionParser:
    """
    Parses spec.txt (constitution) and extracts requirements as structured invariants.
    Uses Gemini 1.5 Flash for extraction with category coverage enforcement.

    v1.1 Features:
    - Three required categories: Security, Functionality, Style
    - Re-prompts specifically for missing categories
    - Converts to Pydantic InvariantSet for type safety
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.extraction_config = self.config.get("llms", {}).get("extraction", {})
        self.thresholds = self.config.get("thresholds", {})
        self.retry_config = self.config.get("retry", {})
        self.output_config = self.config.get("output", {})

        # LLM settings
        self.model = self.extraction_config.get("model", "gemini/gemini-1.5-flash")
        self.max_tokens = self.extraction_config.get("max_tokens", 4096)
        self.temperature = self.extraction_config.get("temperature", 0.0)

        # Thresholds
        self.min_invariants = self.thresholds.get("min_invariants", 5)
        self.min_per_category = self.thresholds.get("min_per_category", 2)

        # Retry settings
        self.max_attempts = self.retry_config.get("max_attempts", 3)
        self.backoff_seconds = self.retry_config.get("backoff_seconds", 2)

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return {}

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    # Security: Maximum spec file size (1MB) to prevent DoS
    MAX_SPEC_SIZE_BYTES = 1 * 1024 * 1024
    
    # Security: Patterns that could indicate code execution attempts
    DANGEROUS_PATTERNS = [
        "__import__",
        "eval(",
        "exec(",
        "compile(",
        "os.system",
        "subprocess",
        "<script",
        "javascript:",
    ]
    
    def read_spec(self, spec_path: str = "spec.txt") -> str:
        """Read and sanitize the specification file.
        
        Security:
        - Enforces size limits to prevent DoS
        - Validates UTF-8 encoding
        - Detects potential code execution patterns
        - Resolves path to prevent traversal
        """
        # Security: Resolve to absolute path to prevent traversal
        spec_file = Path(spec_path).resolve()
        
        # Security: Check for path traversal attempts
        if ".." in str(spec_file):
            raise ValueError("Path traversal detected in spec path")

        if not spec_file.exists():
            raise FileNotFoundError(f"Specification file not found: {spec_path}")
        
        # Security: Check file size before reading
        file_size = spec_file.stat().st_size
        if file_size > self.MAX_SPEC_SIZE_BYTES:
            raise ValueError(
                f"Specification file too large: {file_size} bytes "
                f"(max: {self.MAX_SPEC_SIZE_BYTES} bytes)"
            )
        
        if file_size == 0:
            raise ValueError(f"Specification file is empty: {spec_path}")

        # Security: Read with explicit UTF-8 encoding, fail on decode errors
        try:
            with open(spec_file, "r", encoding="utf-8", errors="strict") as f:
                content = f.read().strip()
        except UnicodeDecodeError as e:
            raise ValueError(f"Invalid encoding in spec file (must be UTF-8): {e}")
        
        # Security: Check for dangerous patterns that could indicate code injection
        content_lower = content.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in content_lower:
                logger.warning(
                    f"Potentially dangerous pattern '{pattern}' found in spec file - "
                    "spec content is used as text only, not executed"
                )

        logger.info(f"Read spec file: {spec_path} ({len(content)} chars)")
        return content

    def _compute_spec_hash(self, content: str) -> str:
        """Compute SHA256 hash of spec content for caching."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _validate_invariants(self, invariants: Dict) -> bool:
        """
        Validate invariants against v1.1 schema with three required categories.
        """
        try:
            # Check required category keys
            for category in REQUIRED_CATEGORIES:
                if category not in invariants:
                    logger.error(f"Missing required category: '{category}'")
                    return False

                if not isinstance(invariants[category], list):
                    logger.error(f"'{category}' must be a list")
                    return False

            # Check items structure in each category
            for category in REQUIRED_CATEGORIES:
                for item in invariants[category]:
                    if not isinstance(item, dict):
                        logger.error(f"Invalid item in {category}: must be dict")
                        return False
                    if "id" not in item or "desc" not in item:
                        logger.error(
                            f"Invalid item in {category}: missing 'id' or 'desc'"
                        )
                        return False
                    if not isinstance(item["id"], int):
                        logger.error(f"Invalid id in {category}: must be integer")
                        return False
                    if not isinstance(item["desc"], str):
                        logger.error(f"Invalid desc in {category}: must be string")
                        return False
                    # Validate severity if present
                    if "severity" in item:
                        valid_severities = {"critical", "high", "medium", "low"}
                        if item["severity"] not in valid_severities:
                            logger.warning(
                                f"Invalid severity '{item['severity']}' in {category}, defaulting to 'medium'"
                            )
                            item["severity"] = "medium"

            return True

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    def _get_missing_categories(self, invariants: Dict) -> List[str]:
        """
        Check which required categories are missing or have too few items.
        Returns list of category names that need more requirements.
        """
        missing = []
        for category in REQUIRED_CATEGORIES:
            count = len(invariants.get(category, []))
            if count < self.min_per_category:
                missing.append(category)
                logger.warning(
                    f"Category '{category}' has only {count} items "
                    f"(minimum: {self.min_per_category})"
                )
        return missing

    def _call_llm(self, prompt: str, system_prompt: str) -> Optional[str]:
        """Call LLM with retry logic."""
        if not LITELLM_AVAILABLE:
            raise RuntimeError("LiteLLM not available")

        for attempt in range(1, self.max_attempts + 1):
            try:
                logger.debug(f"LLM call attempt {attempt}/{self.max_attempts}")

                response = litellm.completion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )

                content = response.choices[0].message.content
                logger.debug(f"LLM response received ({len(content)} chars)")
                return content

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt}): {e}")
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    logger.error(f"All {self.max_attempts} attempts failed")
                    raise

        return None

    def _extract_json_from_response(self, response: str) -> Optional[Dict]:
        """Extract JSON from LLM response, handling markdown code blocks."""
        import re

        # Pattern for JSON in code blocks
        json_pattern = r"```(?:json)?\s*([\s\S]*?)```"
        matches = re.findall(json_pattern, response)

        if matches:
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

        # Try parsing the whole response as JSON
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Try finding JSON object pattern
        json_obj_pattern = r"\{[\s\S]*\}"
        matches = re.findall(json_obj_pattern, response)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        logger.error("Could not extract JSON from response")
        return None

    def extract_invariants(self, spec_content: str) -> Dict[str, List[Dict]]:
        """
        Extract invariants from specification using LLM.
        Returns structured JSON with security, functionality, and style categories.
        Uses enhanced prompts with few-shot examples for better extraction.
        """
        user_prompt = f"""Extract all requirements from this project specification into the THREE REQUIRED categories:
- security (authentication, validation, encryption, secrets management)
- functionality (features, business logic, data handling, APIs)
- style (formatting, types, documentation, linting, testing)

IMPORTANT: Each category MUST have at least 2 requirements. Include severity for each.

---
{spec_content}
---

Output ONLY valid JSON with all three categories."""

        logger.info(
            "Extracting invariants with category coverage enforcement..."
        )

        response = self._call_llm(user_prompt, EXTRACTION_SYSTEM_PROMPT)

        if not response:
            raise RuntimeError("Failed to get response from LLM")

        invariants = self._extract_json_from_response(response)

        if not invariants:
            raise ValueError("Failed to extract valid JSON from LLM response")

        # Ensure all required categories exist (even if empty)
        for category in REQUIRED_CATEGORIES:
            if category not in invariants:
                invariants[category] = []

        if not self._validate_invariants(invariants):
            raise ValueError("Extracted invariants failed validation")

        total_count = sum(len(invariants[cat]) for cat in REQUIRED_CATEGORIES)
        logger.info(
            f"Extracted {total_count} invariants "
            f"(security: {len(invariants['security'])}, "
            f"functionality: {len(invariants['functionality'])}, "
            f"style: {len(invariants['style'])})"
        )

        return invariants

    def _fill_missing_category(
        self, category: str, spec_content: str
    ) -> List[Dict]:
        """
        Re-prompt specifically for a missing category.
        Returns list of requirements for that category.
        """
        if category not in CATEGORY_REPROMPT_TEMPLATES:
            logger.warning(f"No re-prompt template for category: {category}")
            return []

        prompt = CATEGORY_REPROMPT_TEMPLATES[category].format(
            spec_content=spec_content
        )

        logger.info(f"Re-prompting specifically for '{category}' category...")

        response = self._call_llm(
            prompt, f"You are an expert in {category} requirements."
        )

        if not response:
            logger.warning(f"Failed to get {category} requirements from LLM")
            return []

        result = self._extract_json_from_response(response)

        if result and category in result and isinstance(result[category], list):
            logger.info(
                f"Extracted {len(result[category])} additional {category} requirements"
            )
            return result[category]

        logger.warning(f"Could not extract {category} requirements from response")
        return []

    def enforce_category_coverage(
        self, invariants: Dict[str, List[Dict]], spec_content: str
    ) -> Dict[str, List[Dict]]:
        """
        Enforce that all three required categories have adequate coverage.
        Re-prompts specifically for missing categories.

        v1.1 Feature: If a category is missing or has < min_per_category items,
        we re-prompt specifically for that category.
        """
        missing_categories = self._get_missing_categories(invariants)

        if not missing_categories:
            logger.info("All required categories have adequate coverage")
            return invariants

        logger.warning(
            f"Categories needing more requirements: {missing_categories}"
        )

        # Re-prompt for each missing category
        for category in missing_categories:
            additional_items = self._fill_missing_category(category, spec_content)

            if additional_items:
                # Renumber IDs to continue from existing
                start_id = len(invariants.get(category, [])) + 1
                for i, item in enumerate(additional_items):
                    item["id"] = start_id + i
                    # Ensure severity is set
                    if "severity" not in item:
                        item["severity"] = "medium"

                # Append to existing category
                if category not in invariants:
                    invariants[category] = []
                invariants[category].extend(additional_items)

                logger.info(
                    f"Category '{category}' now has {len(invariants[category])} items"
                )

        # Final check
        still_missing = self._get_missing_categories(invariants)
        if still_missing:
            logger.warning(
                f"After re-prompts, still missing coverage for: {still_missing}"
            )
        else:
            logger.info("Category coverage enforcement complete - all categories satisfied")

        return invariants

    def clarify_if_needed(
        self, invariants: Dict[str, List[Dict]], spec_content: str
    ) -> Dict[str, List[Dict]]:
        """
        Enhanced clarification with category coverage enforcement.
        First checks total count, then enforces category coverage.
        """
        total_count = sum(len(invariants[cat]) for cat in REQUIRED_CATEGORIES)

        if total_count < self.min_invariants:
            logger.warning(
                f"Only {total_count} invariants extracted "
                f"(minimum: {self.min_invariants}). Re-prompting..."
            )

            # Use original extraction prompt with emphasis on being thorough
            user_prompt = f"""The specification below needs more thorough analysis.
Extract AT LEAST {self.min_invariants} requirements total across all three categories.

Previous extraction only found {total_count} requirements. Analyze deeper.

Specification:
---
{spec_content}
---

Output ONLY valid JSON with 'security', 'functionality', and 'style' arrays."""

            response = self._call_llm(user_prompt, EXTRACTION_SYSTEM_PROMPT)

            if response:
                new_invariants = self._extract_json_from_response(response)
                if new_invariants and self._validate_invariants(new_invariants):
                    new_total = sum(
                        len(new_invariants[cat]) for cat in REQUIRED_CATEGORIES
                    )
                    if new_total > total_count:
                        logger.info(
                            f"Clarification improved extraction: {new_total} invariants"
                        )
                        invariants = new_invariants

        # Now enforce category coverage
        invariants = self.enforce_category_coverage(invariants, spec_content)

        return invariants

    def save_criteria(
        self, invariants: Dict[str, List[Dict]], output_path: Optional[str] = None
    ) -> str:
        """Save extracted invariants to JSON file."""
        if output_path is None:
            output_path = self.output_config.get("criteria_file", "criteria.json")

        output_file = Path(output_path)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(invariants, f, indent=2)

        logger.info(f"Saved criteria to: {output_file}")
        return str(output_file)

    def load_criteria(
        self, criteria_path: str = "criteria.json"
    ) -> Dict[str, List[Dict]]:
        """Load previously extracted criteria."""
        criteria_file = Path(criteria_path)

        if not criteria_file.exists():
            raise FileNotFoundError(f"Criteria file not found: {criteria_path}")

        with open(criteria_file, "r", encoding="utf-8") as f:
            invariants = json.load(f)

        if not self._validate_invariants(invariants):
            raise ValueError("Loaded criteria failed validation")

        return invariants

    def to_pydantic(
        self, invariants: Dict[str, List[Dict]], spec_content: str
    ) -> InvariantSet:
        """
        Convert raw invariants dict to Pydantic InvariantSet.
        Provides type safety and validation.
        """
        pydantic_invariants: List[Invariant] = []
        categories_covered: Dict[str, int] = {}
        global_id = 1

        # Map category strings to enum values
        category_map = {
            "security": InvariantCategory.SECURITY,
            "functionality": InvariantCategory.FUNCTIONALITY,
            "style": InvariantCategory.STYLE,
        }

        severity_map = {
            "critical": InvariantSeverity.CRITICAL,
            "high": InvariantSeverity.HIGH,
            "medium": InvariantSeverity.MEDIUM,
            "low": InvariantSeverity.LOW,
        }

        for cat_name, cat_enum in category_map.items():
            items = invariants.get(cat_name, [])
            categories_covered[cat_name] = len(items)

            for item in items:
                severity_str = item.get("severity", "medium").lower()
                severity = severity_map.get(severity_str, InvariantSeverity.MEDIUM)

                inv = Invariant(
                    id=global_id,
                    description=item["desc"],
                    category=cat_enum,
                    severity=severity,
                    keywords=[],  # Could extract keywords from description
                    source_line=None,
                )
                pydantic_invariants.append(inv)
                global_id += 1

        return InvariantSet(
            invariants=pydantic_invariants,
            extraction_timestamp=datetime.now(),
            spec_hash=self._compute_spec_hash(spec_content),
            categories_covered=categories_covered,
        )

    def run(
        self,
        spec_path: str = "spec.txt",
        output_path: Optional[str] = None,
        return_pydantic: bool = False,
    ) -> Dict[str, List[Dict]] | InvariantSet:
        """
        Main extraction pipeline.

        Args:
            spec_path: Path to specification file
            output_path: Optional path for criteria output
            return_pydantic: If True, return InvariantSet instead of dict

        Returns:
            Extracted invariants (dict or InvariantSet)
        """
        # Read specification
        spec_content = self.read_spec(spec_path)

        # Extract invariants
        invariants = self.extract_invariants(spec_content)

        # Clarify and enforce category coverage
        invariants = self.clarify_if_needed(invariants, spec_content)

        # Save criteria
        self.save_criteria(invariants, output_path)

        if return_pydantic:
            return self.to_pydantic(invariants, spec_content)

        return invariants


def run_extraction(
    spec_path: str = "spec.txt",
    config_path: str = "config.yaml",
    output_path: Optional[str] = None,
    file_tree: Optional[Dict[str, str]] = None,
    return_pydantic: bool = False,
) -> Dict[str, List[Dict]] | InvariantSet:
    """
    Main entry point for the parser module.

    Args:
        spec_path: Path to specification file
        config_path: Path to config.yaml
        output_path: Optional path for criteria output
        file_tree: File tree (not used, for interface consistency)
        return_pydantic: If True, return Pydantic InvariantSet

    Returns:
        Extracted invariants (dict with security/functionality/style keys,
        or InvariantSet if return_pydantic=True)
    """
    parser = ConstitutionParser(config_path)
    return parser.run(spec_path, output_path, return_pydantic)


if __name__ == "__main__":
    # Test the parser module
    import sys

    logger.add(sys.stderr, level="DEBUG")

    spec_path = "spec.txt"
    if len(sys.argv) > 1:
        spec_path = sys.argv[1]

    try:
        parser = ConstitutionParser()
        invariants = parser.run(spec_path)
        print("\n=== Extracted Invariants (v1.1 - Category Coverage) ===")
        print(json.dumps(invariants, indent=2))

        # Show category coverage
        print("\n=== Category Coverage ===")
        for category in REQUIRED_CATEGORIES:
            count = len(invariants.get(category, []))
            status = "✓" if count >= 2 else "✗"
            print(f"  {status} {category}: {count} requirements")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Create a spec.txt file with your project specification.")
