"""
Dysruption CVA - Parser Module (Module B: Constitution Parser / Extraction)
Reads spec.txt and extracts invariants as structured JSON using Gemini Flash.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from loguru import logger
import yaml

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.error("LiteLLM not available. Install with: pip install litellm")


# Schema for invariants
INVARIANTS_SCHEMA = {
    "type": "object",
    "required": ["technical", "functional"],
    "properties": {
        "technical": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "desc"],
                "properties": {
                    "id": {"type": "integer"},
                    "desc": {"type": "string"}
                }
            }
        },
        "functional": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "desc"],
                "properties": {
                    "id": {"type": "integer"},
                    "desc": {"type": "string"}
                }
            }
        }
    }
}


class ConstitutionParser:
    """
    Parses spec.txt (constitution) and extracts requirements as structured invariants.
    Uses Gemini 1.5 Flash for extraction.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.extraction_config = self.config.get('llms', {}).get('extraction', {})
        self.thresholds = self.config.get('thresholds', {})
        self.retry_config = self.config.get('retry', {})
        self.output_config = self.config.get('output', {})
        
        # LLM settings
        self.model = self.extraction_config.get('model', 'gemini/gemini-1.5-flash')
        self.max_tokens = self.extraction_config.get('max_tokens', 4096)
        self.temperature = self.extraction_config.get('temperature', 0.0)
        
        # Thresholds
        self.min_invariants = self.thresholds.get('min_invariants', 5)
        
        # Retry settings
        self.max_attempts = self.retry_config.get('max_attempts', 3)
        self.backoff_seconds = self.retry_config.get('backoff_seconds', 2)
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return {}
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def read_spec(self, spec_path: str = "spec.txt") -> str:
        """Read the specification file."""
        spec_file = Path(spec_path)
        
        if not spec_file.exists():
            raise FileNotFoundError(f"Specification file not found: {spec_path}")
        
        with open(spec_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        if not content:
            raise ValueError(f"Specification file is empty: {spec_path}")
        
        logger.info(f"Read spec file: {spec_path} ({len(content)} chars)")
        return content
    
    def _validate_invariants(self, invariants: Dict) -> bool:
        """Validate invariants against schema."""
        try:
            # Check required keys
            if 'technical' not in invariants or 'functional' not in invariants:
                logger.error("Missing required keys: 'technical' or 'functional'")
                return False
            
            # Check types
            if not isinstance(invariants['technical'], list):
                logger.error("'technical' must be a list")
                return False
                
            if not isinstance(invariants['functional'], list):
                logger.error("'functional' must be a list")
                return False
            
            # Check items structure
            for category in ['technical', 'functional']:
                for item in invariants[category]:
                    if not isinstance(item, dict):
                        logger.error(f"Invalid item in {category}: must be dict")
                        return False
                    if 'id' not in item or 'desc' not in item:
                        logger.error(f"Invalid item in {category}: missing 'id' or 'desc'")
                        return False
                    if not isinstance(item['id'], int):
                        logger.error(f"Invalid id in {category}: must be integer")
                        return False
                    if not isinstance(item['desc'], str):
                        logger.error(f"Invalid desc in {category}: must be string")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
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
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=self.max_tokens,
                    temperature=self.temperature
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
        # Try to find JSON in code blocks first
        import re
        
        # Pattern for JSON in code blocks
        json_pattern = r'```(?:json)?\s*([\s\S]*?)```'
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
        json_obj_pattern = r'\{[\s\S]*\}'
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
        Returns structured JSON with technical and functional requirements.
        """
        system_prompt = """You are an expert requirements analyst. Your task is to extract numbered lists of technical and functional requirements from a project specification.

Output ONLY valid JSON in this exact format:
{
    "technical": [
        {"id": 1, "desc": "Technical requirement description"},
        {"id": 2, "desc": "Another technical requirement"}
    ],
    "functional": [
        {"id": 1, "desc": "Functional requirement description"},
        {"id": 2, "desc": "Another functional requirement"}
    ]
}

Technical requirements include:
- Architecture decisions (frameworks, libraries, patterns)
- Infrastructure requirements (databases, APIs, services)
- Performance requirements
- Security requirements
- Code quality standards

Functional requirements include:
- User-facing features
- Business logic
- Data handling
- Error handling
- User experience requirements

Be EXHAUSTIVE - extract ALL requirements, both explicit and implied.
Each description should be specific and verifiable.
Output ONLY the JSON, no other text."""

        user_prompt = f"""Extract all technical and functional requirements from this specification:

---
{spec_content}
---

Remember: Output ONLY valid JSON with 'technical' and 'functional' arrays."""

        logger.info("Extracting invariants from specification...")
        
        response = self._call_llm(user_prompt, system_prompt)
        
        if not response:
            raise RuntimeError("Failed to get response from LLM")
        
        invariants = self._extract_json_from_response(response)
        
        if not invariants:
            raise ValueError("Failed to extract valid JSON from LLM response")
        
        if not self._validate_invariants(invariants):
            raise ValueError("Extracted invariants failed validation")
        
        total_count = len(invariants['technical']) + len(invariants['functional'])
        logger.info(f"Extracted {total_count} invariants ({len(invariants['technical'])} technical, {len(invariants['functional'])} functional)")
        
        return invariants
    
    def clarify_if_needed(self, invariants: Dict[str, List[Dict]], spec_content: str) -> Dict[str, List[Dict]]:
        """
        Re-prompt if too few invariants were extracted.
        """
        total_count = len(invariants['technical']) + len(invariants['functional'])
        
        if total_count >= self.min_invariants:
            return invariants
        
        logger.warning(f"Only {total_count} invariants extracted (minimum: {self.min_invariants}). Re-prompting...")
        
        system_prompt = """You are an expert requirements analyst. The previous extraction was too sparse.
Your task is to DEEPLY analyze the specification and extract MORE requirements.

Think about:
- Implied requirements (what must be true even if not stated?)
- Edge cases and error handling
- Security considerations
- Performance expectations
- Code quality standards
- User experience details

Output ONLY valid JSON in this exact format:
{
    "technical": [{"id": 1, "desc": "..."}],
    "functional": [{"id": 1, "desc": "..."}]
}

Be MORE EXHAUSTIVE this time."""

        user_prompt = f"""The specification below needs more thorough analysis. Extract AT LEAST {self.min_invariants} requirements total.

Previous extraction only found {total_count} requirements. Look deeper for:
- Implicit requirements
- Best practices that should apply
- Security considerations
- Error handling expectations
- Performance requirements

Specification:
---
{spec_content}
---

Output ONLY valid JSON with 'technical' and 'functional' arrays."""

        response = self._call_llm(user_prompt, system_prompt)
        
        if not response:
            logger.warning("Clarification call failed. Using original invariants.")
            return invariants
        
        new_invariants = self._extract_json_from_response(response)
        
        if new_invariants and self._validate_invariants(new_invariants):
            new_total = len(new_invariants['technical']) + len(new_invariants['functional'])
            logger.info(f"Clarification extracted {new_total} invariants")
            return new_invariants
        
        logger.warning("Clarification failed validation. Using original invariants.")
        return invariants
    
    def save_criteria(self, invariants: Dict[str, List[Dict]], output_path: Optional[str] = None) -> str:
        """Save extracted invariants to JSON file."""
        if output_path is None:
            output_path = self.output_config.get('criteria_file', 'criteria.json')
        
        output_file = Path(output_path)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(invariants, f, indent=2)
        
        logger.info(f"Saved criteria to: {output_file}")
        return str(output_file)
    
    def load_criteria(self, criteria_path: str = "criteria.json") -> Dict[str, List[Dict]]:
        """Load previously extracted criteria."""
        criteria_file = Path(criteria_path)
        
        if not criteria_file.exists():
            raise FileNotFoundError(f"Criteria file not found: {criteria_path}")
        
        with open(criteria_file, 'r', encoding='utf-8') as f:
            invariants = json.load(f)
        
        if not self._validate_invariants(invariants):
            raise ValueError("Loaded criteria failed validation")
        
        return invariants
    
    def run(self, spec_path: str = "spec.txt", output_path: Optional[str] = None) -> Dict[str, List[Dict]]:
        """
        Main extraction pipeline.
        
        Args:
            spec_path: Path to specification file
            output_path: Optional path for criteria output
            
        Returns:
            Extracted invariants dict
        """
        # Read specification
        spec_content = self.read_spec(spec_path)
        
        # Extract invariants
        invariants = self.extract_invariants(spec_content)
        
        # Clarify if needed
        invariants = self.clarify_if_needed(invariants, spec_content)
        
        # Save criteria
        self.save_criteria(invariants, output_path)
        
        return invariants


def run_extraction(
    spec_path: str = "spec.txt",
    config_path: str = "config.yaml",
    output_path: Optional[str] = None,
    file_tree: Optional[Dict[str, str]] = None  # Not used but accepted for interface consistency
) -> Dict[str, List[Dict]]:
    """
    Main entry point for the parser module.
    
    Args:
        spec_path: Path to specification file
        config_path: Path to config.yaml
        output_path: Optional path for criteria output
        file_tree: File tree (not used, for interface consistency)
        
    Returns:
        Extracted invariants dict
    """
    parser = ConstitutionParser(config_path)
    return parser.run(spec_path, output_path)


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
        print(json.dumps(invariants, indent=2))
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Create a spec.txt file with your project specification.")
