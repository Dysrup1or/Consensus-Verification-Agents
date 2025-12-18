"""Path security validation module.

Provides centralized path validation to prevent directory traversal attacks.
Based on OWASP Path Traversal prevention guidelines:
https://owasp.org/www-community/attacks/Path_Traversal

Key attack patterns defended against:
- Basic traversal: ../../../etc/passwd
- URL encoding: %2e%2e%2f (decodes to ../)
- Double encoding: %252e%252e%252f
- Windows paths: ..\\..\\windows\\system32
- UNC paths: \\\\server\\share\\file
- Null bytes: file.txt%00.jpg
- Unicode encoding: %c0%af (overlong UTF-8)
"""

import logging
import urllib.parse
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import List, Optional, Union

logger = logging.getLogger(__name__)


class PathValidationError(Exception):
    """Raised when path validation fails due to security concerns."""
    
    def __init__(self, message: str, path: str = "", reason: str = ""):
        self.path = path
        self.reason = reason
        super().__init__(message)


class PathValidator:
    """Centralized path validation to prevent traversal attacks.
    
    This class provides secure path handling by:
    1. Decoding URL-encoded paths (including double encoding)
    2. Detecting traversal patterns before resolution
    3. Resolving paths and verifying containment
    4. Blocking symlink escapes
    5. Handling Windows and Unix paths uniformly
    
    Example:
        validator = PathValidator()
        project_root = Path("/home/user/project")
        
        # Safe path - returns resolved Path
        safe = validator.validate_and_resolve("src/main.py", project_root)
        
        # Unsafe path - raises PathValidationError
        validator.validate_and_resolve("../../../etc/passwd", project_root)
    """
    
    # Patterns that indicate traversal attempts (case-insensitive)
    TRAVERSAL_PATTERNS = [
        r"\.\.[\\/]",          # ../ or ..\
        r"\.\.%",              # URL-encoded following ..
        r"%2e%2e",             # URL encoded .. (%2e = .)
        r"%252e%252e",         # Double URL encoded ..
        r"%c0%ae",             # Overlong UTF-8 encoding of .
        r"%c0%af",             # Overlong UTF-8 encoding of /
        r"%00",                # Null byte injection
    ]
    
    # Dangerous path prefixes (Windows UNC, device paths)
    DANGEROUS_PREFIXES = [
        r"^\\\\",              # UNC path: \\server\share
        r"^\\\\\?\\",          # Extended path: \\?\
        r"^\\\\\.\\",          # Device path: \\.\
    ]
    
    def __init__(self, log_failures: bool = True, strict_mode: bool = True):
        """Initialize PathValidator.
        
        Args:
            log_failures: If True, log all validation failures
            strict_mode: If True, block all traversal patterns even if 
                        they would resolve within root
        """
        self.log_failures = log_failures
        self.strict_mode = strict_mode
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.TRAVERSAL_PATTERNS
        ]
        self._compiled_dangerous = [
            re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PREFIXES
        ]
    
    def validate_and_resolve(
        self,
        path: Union[str, Path],
        root: Union[str, Path],
        must_exist: bool = False,
        allow_symlinks: bool = False
    ) -> Path:
        """Validate path and resolve to absolute within root.
        
        This is the primary security method. It:
        1. Decodes URL encoding (recursively for double-encoding)
        2. Checks for traversal patterns
        3. Resolves to absolute path
        4. Verifies result is within root
        5. Optionally checks symlink destinations
        
        Args:
            path: Path to validate (relative or absolute string/Path)
            root: Root directory that path must be contained within
            must_exist: If True, raise error if path doesn't exist
            allow_symlinks: If True, allow symlinks (still verify destination)
            
        Returns:
            Resolved absolute Path guaranteed to be within root
            
        Raises:
            PathValidationError: If path is invalid, escapes root, or 
                                contains dangerous patterns
        """
        # Convert Path to string if needed for decoding
        path_str = str(path) if isinstance(path, Path) else path
        root = Path(root) if isinstance(root, str) else root
        
        if not path_str:
            # Empty path resolves to root
            return root.resolve()
        
        # Normalize root first
        root = root.resolve()
        
        # Step 1: Decode URL encoding (handles double encoding)
        decoded = self._decode_path(path_str)
        
        # Step 2: Check for dangerous prefixes (UNC, device paths)
        if self._has_dangerous_prefix(decoded):
            self._log_failure(f"Dangerous path prefix: {path_str}")
            raise PathValidationError(
                f"Path contains dangerous prefix: {path_str}",
                path=path_str,
                reason="dangerous_prefix"
            )
        
        # Step 3: Check for traversal patterns (strict mode)
        if self.strict_mode and self._has_traversal_pattern(path_str):
            self._log_failure(f"Traversal pattern in raw path: {path_str}")
            raise PathValidationError(
                f"Path contains traversal pattern: {path_str}",
                path=path_str,
                reason="traversal_pattern_raw"
            )
        
        if self._has_traversal_pattern(decoded):
            self._log_failure(f"Traversal pattern in decoded path: {decoded}")
            raise PathValidationError(
                f"Path contains traversal pattern after decoding: {path_str}",
                path=path_str,
                reason="traversal_pattern_decoded"
            )
        
        # Step 4: Resolve to absolute path
        try:
            # Handle both absolute and relative paths
            path_obj = Path(decoded)
            if path_obj.is_absolute():
                resolved = path_obj.resolve()
            else:
                resolved = (root / decoded).resolve()
        except (OSError, ValueError) as e:
            self._log_failure(f"Cannot resolve path '{path_str}': {e}")
            raise PathValidationError(
                f"Cannot resolve path: {path_str}",
                path=path_str,
                reason="resolution_failed"
            ) from e
        
        # Step 5: Verify containment within root
        if not self._is_contained(resolved, root):
            self._log_failure(f"Path escapes root: {path_str} -> {resolved}")
            raise PathValidationError(
                f"Path escapes root directory: {path_str}",
                path=path_str,
                reason="escapes_root"
            )
        
        # Step 6: Check symlinks if not allowed
        if not allow_symlinks and resolved.exists():
            if resolved.is_symlink():
                # Resolve symlink and check destination
                real_path = resolved.resolve()
                if not self._is_contained(real_path, root):
                    self._log_failure(f"Symlink escapes root: {path_str} -> {real_path}")
                    raise PathValidationError(
                        f"Symlink destination escapes root: {path_str}",
                        path=path_str,
                        reason="symlink_escape"
                    )
        
        # Step 7: Check existence if required
        if must_exist and not resolved.exists():
            raise PathValidationError(
                f"Path does not exist: {resolved}",
                path=path_str,
                reason="not_found"
            )
        
        return resolved
    
    def sanitize_relative_path(self, path: str) -> str:
        """Sanitize path by removing traversal sequences.
        
        This creates a safe relative path by:
        1. Decoding URL encoding
        2. Splitting into components
        3. Removing . and .. components
        4. Rejoining with forward slashes
        
        Args:
            path: Path string to sanitize
            
        Returns:
            Sanitized path string with traversal removed
            
        Example:
            >>> validator.sanitize_relative_path("../../../etc/passwd")
            'etc/passwd'
            >>> validator.sanitize_relative_path("foo/../bar/./baz")
            'foo/bar/baz'
        """
        if not path:
            return ""
        
        # Decode URL encoding
        decoded = self._decode_path(path)
        
        # Normalize slashes to forward slash
        normalized = decoded.replace("\\", "/")
        
        # Split and filter dangerous components
        parts = []
        for part in normalized.split("/"):
            # Skip empty, current dir, and parent dir references
            if not part or part == "." or part == "..":
                continue
            # Skip parts with null bytes or other dangerous chars
            if "\x00" in part:
                continue
            parts.append(part)
        
        return "/".join(parts)
    
    def is_safe_path(
        self,
        path: str,
        allowed_roots: List[Path],
        must_exist: bool = False
    ) -> bool:
        """Check if path is safe (contained in any allowed root).
        
        Non-throwing alternative to validate_and_resolve for use in
        conditional logic.
        
        Args:
            path: Path to check
            allowed_roots: List of allowed root directories
            must_exist: If True, path must also exist
            
        Returns:
            True if path is safe and within at least one allowed root
            
        Example:
            >>> validator.is_safe_path("src/main.py", [project_root])
            True
            >>> validator.is_safe_path("../../../etc/passwd", [project_root])
            False
        """
        for root in allowed_roots:
            try:
                resolved = self.validate_and_resolve(
                    path, root, must_exist=must_exist
                )
                return True
            except PathValidationError:
                continue
        return False
    
    def validate_paths_batch(
        self,
        paths: List[str],
        root: Path,
        must_exist: bool = False
    ) -> tuple[List[Path], List[tuple[str, str]]]:
        """Validate multiple paths, returning successes and failures.
        
        Useful for batch operations where some paths may be invalid.
        
        Args:
            paths: List of paths to validate
            root: Root directory for containment check
            must_exist: If True, paths must exist
            
        Returns:
            Tuple of (valid_paths, failures) where failures is list of
            (path, error_reason) tuples
        """
        valid = []
        failed = []
        
        for path in paths:
            try:
                resolved = self.validate_and_resolve(path, root, must_exist)
                valid.append(resolved)
            except PathValidationError as e:
                failed.append((path, e.reason))
        
        return valid, failed
    
    def _decode_path(self, path: str) -> str:
        """Recursively decode URL-encoded path.
        
        Handles double encoding by decoding until no change.
        """
        decoded = urllib.parse.unquote(path)
        # Handle double/triple encoding
        iterations = 0
        max_iterations = 5  # Prevent infinite loops
        while decoded != path and iterations < max_iterations:
            path = decoded
            decoded = urllib.parse.unquote(path)
            iterations += 1
        return decoded
    
    def _has_traversal_pattern(self, path: str) -> bool:
        """Check for traversal patterns in path string."""
        # Check compiled regex patterns
        for pattern in self._compiled_patterns:
            if pattern.search(path):
                return True
        
        # Also check for literal .. in path components
        # Normalize slashes first
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        return ".." in parts
    
    def _has_dangerous_prefix(self, path: str) -> bool:
        """Check for dangerous path prefixes."""
        for pattern in self._compiled_dangerous:
            if pattern.match(path):
                return True
        return False
    
    def _is_contained(self, path: Path, root: Path) -> bool:
        """Check if path is contained within root.
        
        Uses Path.is_relative_to() for Python 3.9+ compatibility.
        """
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
    
    def _log_failure(self, message: str) -> None:
        """Log validation failure if logging enabled."""
        if self.log_failures:
            logger.warning(f"[PATH SECURITY] {message}")


# Convenience function for simple validation
def validate_path(path: str, root: Path, must_exist: bool = False) -> Path:
    """Convenience function for one-off path validation.
    
    Args:
        path: Path to validate
        root: Root directory for containment
        must_exist: If True, path must exist
        
    Returns:
        Validated absolute Path
        
    Raises:
        PathValidationError: If validation fails
    """
    validator = PathValidator(log_failures=True)
    return validator.validate_and_resolve(path, root, must_exist)


def is_safe_path(path: str, root: Path) -> bool:
    """Convenience function to check if path is safe.
    
    Args:
        path: Path to check
        root: Root directory for containment
        
    Returns:
        True if path is safe, False otherwise
    """
    validator = PathValidator(log_failures=False)
    return validator.is_safe_path(path, [root])
