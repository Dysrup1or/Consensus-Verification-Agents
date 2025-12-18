"""
Centralized Security Module for CVA.

This module provides a unified security interface that combines:
- Path security (path traversal prevention)
- Prompt security (LLM injection prevention)

Usage:
    from modules.security import (
        security_manager,
        validate_file_path,
        sanitize_user_content_for_llm,
        create_secure_prompt,
    )
    
    # Validate a file path
    safe_path = validate_file_path(user_path, project_root)
    
    # Check user content for injection threats
    threat = security_manager.analyze_prompt_threat(user_input)
    if not threat.is_safe:
        logger.warning(f"Threat detected: {threat.level}")
    
    # Create a secure prompt for LLM
    prompt = create_secure_prompt(
        system="You are a code reviewer",
        user_data=user_code
    )
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from .path_security import (
    PathValidator,
    PathValidationError,
    validate_path,
    is_safe_path,
)
from .prompt_security import (
    PromptSanitizer,
    ThreatLevel,
    ThreatAnalysis,
    analyze_prompt_threat,
    sanitize_user_input,
    create_safe_llm_prompt,
)


class SecurityManager:
    """
    Centralized security manager for CVA.
    
    Combines path and prompt security with consistent configuration.
    """
    
    def __init__(
        self,
        allowed_roots: Optional[List[Path]] = None,
        log_threats: bool = True,
        block_high_threat: bool = True,
    ):
        """
        Initialize security manager.
        
        Args:
            allowed_roots: List of allowed root directories for file access
            log_threats: Whether to log detected threats
            block_high_threat: Whether to block HIGH/CRITICAL threats
        """
        self.path_validator = PathValidator()
        self.prompt_sanitizer = PromptSanitizer(log_threats=log_threats)
        self.allowed_roots = allowed_roots or []
        self.log_threats = log_threats
        self.block_high_threat = block_high_threat
        
        # Statistics tracking
        self._stats = {
            "path_validations": 0,
            "path_blocks": 0,
            "prompt_scans": 0,
            "threat_detections": 0,
            "high_threat_blocks": 0,
        }
    
    # =========================================================================
    # PATH SECURITY
    # =========================================================================
    
    def validate_file_path(
        self,
        path: Union[str, Path],
        root: Union[str, Path],
        must_exist: bool = False,
    ) -> Path:
        """
        Validate a file path is safe to access.
        
        Args:
            path: The path to validate
            root: The allowed root directory
            must_exist: Whether the path must exist
            
        Returns:
            Validated absolute path
            
        Raises:
            PathValidationError: If path is not safe
        """
        self._stats["path_validations"] += 1
        try:
            return self.path_validator.validate_and_resolve(path, root, must_exist)
        except PathValidationError:
            self._stats["path_blocks"] += 1
            raise
    
    def is_path_safe(
        self,
        path: Union[str, Path],
        allowed_roots: Optional[List[Union[str, Path]]] = None,
    ) -> bool:
        """
        Check if a path is safe to access.
        
        Args:
            path: The path to check
            allowed_roots: Override allowed roots
            
        Returns:
            True if safe, False otherwise
        """
        roots = allowed_roots or self.allowed_roots
        if not roots:
            return False
        return self.path_validator.is_safe_path(path, roots)
    
    def sanitize_relative_path(self, path: str) -> str:
        """
        Sanitize a relative path from user input.
        
        Args:
            path: Potentially unsafe relative path
            
        Returns:
            Sanitized path safe for use
        """
        return self.path_validator.sanitize_relative_path(path)
    
    # =========================================================================
    # PROMPT SECURITY
    # =========================================================================
    
    def analyze_prompt_threat(self, text: str) -> ThreatAnalysis:
        """
        Analyze text for prompt injection threats.
        
        Args:
            text: User-provided text to analyze
            
        Returns:
            ThreatAnalysis with level, patterns, and recommendations
        """
        self._stats["prompt_scans"] += 1
        analysis = self.prompt_sanitizer.analyze_threat(text)
        
        if analysis.level >= ThreatLevel.MEDIUM:
            self._stats["threat_detections"] += 1
        
        if analysis.level >= ThreatLevel.HIGH:
            self._stats["high_threat_blocks"] += 1
            if self.log_threats:
                logger.warning(
                    f"[SECURITY] High threat detected: {analysis.level.name}, "
                    f"patterns: {[p[0] for p in analysis.patterns_found]}"
                )
        
        return analysis
    
    def sanitize_for_prompt(
        self,
        text: str,
        max_length: int = 10000,
        remove_patterns: bool = True,
    ) -> str:
        """
        Sanitize user input for safe inclusion in LLM prompts.
        
        Args:
            text: User input to sanitize
            max_length: Maximum length to allow
            remove_patterns: Whether to replace dangerous patterns
            
        Returns:
            Sanitized text safe for prompts
        """
        return self.prompt_sanitizer.sanitize_for_prompt(
            text, max_length=max_length, remove_patterns=remove_patterns
        )
    
    def create_safe_prompt(
        self,
        system_instructions: str,
        user_data: str,
        data_label: str = "USER_INPUT",
        include_security_rules: bool = True,
    ) -> str:
        """
        Create a safe prompt with proper structural separation.
        
        Args:
            system_instructions: System-level instructions
            user_data: User-provided content (code, text, etc.)
            data_label: Label for the user data section
            include_security_rules: Include security directives
            
        Returns:
            Structured prompt safe against injection
        """
        return self.prompt_sanitizer.create_safe_prompt(
            system_instructions=system_instructions,
            user_data=user_data,
            data_label=data_label,
            include_security_rules=include_security_rules,
        )
    
    def validate_llm_output(self, output: str) -> Tuple[bool, List[str]]:
        """
        Validate LLM output for potential prompt leakage.
        
        Args:
            output: LLM response to validate
            
        Returns:
            Tuple of (is_valid, list of issues found)
        """
        return self.prompt_sanitizer.validate_output(output)
    
    def should_block_request(self, user_input: str) -> Tuple[bool, str]:
        """
        Determine if a user request should be blocked.
        
        Args:
            user_input: User-provided text
            
        Returns:
            Tuple of (should_block, reason)
        """
        if not self.block_high_threat:
            return False, ""
        
        analysis = self.analyze_prompt_threat(user_input)
        
        if analysis.level >= ThreatLevel.HIGH:
            reason = f"Request blocked: {analysis.recommendations}"
            return True, reason
        
        return False, ""
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, int]:
        """Get security statistics."""
        return dict(self._stats)
    
    def reset_stats(self) -> None:
        """Reset security statistics."""
        for key in self._stats:
            self._stats[key] = 0


# Global singleton instance
_security_manager: Optional[SecurityManager] = None


def get_security_manager() -> SecurityManager:
    """Get or create the global security manager."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager(log_threats=True)
    return _security_manager


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_file_path(
    path: Union[str, Path],
    root: Union[str, Path],
    must_exist: bool = False,
) -> Path:
    """
    Validate a file path is safe to access.
    
    Args:
        path: The path to validate
        root: The allowed root directory
        must_exist: Whether the path must exist
        
    Returns:
        Validated absolute path
        
    Raises:
        PathValidationError: If path is not safe
    """
    return get_security_manager().validate_file_path(path, root, must_exist)


def sanitize_user_content_for_llm(
    text: str,
    max_length: int = 10000,
) -> str:
    """
    Sanitize user content for safe LLM prompts.
    
    Args:
        text: User input to sanitize
        max_length: Maximum length
        
    Returns:
        Sanitized text
    """
    return get_security_manager().sanitize_for_prompt(text, max_length=max_length)


def create_secure_prompt(
    system: str,
    user_data: str,
    data_label: str = "USER_INPUT",
) -> str:
    """
    Create a secure prompt with structural separation.
    
    Args:
        system: System instructions
        user_data: User-provided content
        data_label: Label for user section
        
    Returns:
        Structured secure prompt
    """
    return get_security_manager().create_safe_prompt(
        system_instructions=system,
        user_data=user_data,
        data_label=data_label,
    )


def check_request_safety(user_input: str) -> Tuple[bool, str]:
    """
    Check if a user request is safe to process.
    
    Args:
        user_input: User-provided text
        
    Returns:
        Tuple of (is_safe, block_reason if not safe)
    """
    should_block, reason = get_security_manager().should_block_request(user_input)
    return not should_block, reason


__all__ = [
    # Main classes
    "SecurityManager",
    "get_security_manager",
    # Path security
    "PathValidator",
    "PathValidationError",
    "validate_file_path",
    "validate_path",
    "is_safe_path",
    # Prompt security
    "PromptSanitizer",
    "ThreatLevel",
    "ThreatAnalysis",
    "sanitize_user_content_for_llm",
    "create_secure_prompt",
    "check_request_safety",
    "analyze_prompt_threat",
]
