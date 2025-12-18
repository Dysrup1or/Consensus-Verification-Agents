"""Unit tests for path security module.

Tests cover OWASP path traversal attack patterns:
- Basic traversal (../)
- URL encoding (%2e%2e%2f)
- Double encoding (%252e%252e)
- Windows paths (..\\)
- UNC paths (\\\\server\\share)
- Symlink escapes
- Null byte injection
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from modules.path_security import (
    PathValidator,
    PathValidationError,
    validate_path,
    is_safe_path,
)


class TestPathValidatorBasicTraversal:
    """Tests for basic directory traversal attacks."""
    
    @pytest.fixture
    def validator(self):
        """Create PathValidator with logging disabled for clean tests."""
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        """Create temporary root directory with test files."""
        # Create directory structure
        (tmp_path / "allowed").mkdir()
        (tmp_path / "allowed" / "subdir").mkdir()
        (tmp_path / "allowed" / "file.txt").write_text("test content")
        (tmp_path / "allowed" / "subdir" / "nested.txt").write_text("nested")
        return tmp_path
    
    def test_basic_traversal_blocked(self, validator, temp_root):
        """Basic ../ traversal should be blocked."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate_and_resolve("../../../etc/passwd", temp_root)
        assert exc_info.value.reason in ("traversal_pattern_raw", "traversal_pattern_decoded")
    
    def test_single_parent_traversal_blocked(self, validator, temp_root):
        """Single ../ should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("../secret", temp_root)
    
    def test_mid_path_traversal_blocked(self, validator, temp_root):
        """Traversal in middle of path should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("allowed/../../../secret", temp_root)
    
    def test_traversal_with_valid_prefix_blocked(self, validator, temp_root):
        """Traversal after valid prefix should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("allowed/subdir/../../../../../../etc/passwd", temp_root)
    
    def test_dot_only_path_allowed(self, validator, temp_root):
        """Single dot (current dir) should resolve to root."""
        result = validator.validate_and_resolve(".", temp_root)
        assert result == temp_root.resolve()
    
    def test_empty_path_resolves_to_root(self, validator, temp_root):
        """Empty path should resolve to root."""
        result = validator.validate_and_resolve("", temp_root)
        assert result == temp_root.resolve()


class TestPathValidatorURLEncoding:
    """Tests for URL-encoded traversal attacks."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        (tmp_path / "allowed").mkdir()
        return tmp_path
    
    def test_url_encoded_dot_dot_slash_blocked(self, validator, temp_root):
        """URL-encoded ../ (%2e%2e%2f) should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("%2e%2e%2fetc%2fpasswd", temp_root)
    
    def test_url_encoded_dots_only_blocked(self, validator, temp_root):
        """URL-encoded dots without slash should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("%2e%2e/secret", temp_root)
    
    def test_double_encoded_traversal_blocked(self, validator, temp_root):
        """Double URL-encoded traversal should be blocked."""
        # %252e = %2e (after first decode), then . (after second decode)
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("%252e%252e%252fetc", temp_root)
    
    def test_mixed_encoding_blocked(self, validator, temp_root):
        """Mixed encoded and plain traversal should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("..%2f..%2fetc", temp_root)
    
    def test_uppercase_encoded_blocked(self, validator, temp_root):
        """Uppercase URL encoding should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("%2E%2E%2Fetc", temp_root)
    
    def test_null_byte_injection_blocked(self, validator, temp_root):
        """Null byte injection should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("file.txt%00.jpg", temp_root)


class TestPathValidatorWindowsPaths:
    """Tests for Windows-specific path attacks."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        (tmp_path / "allowed").mkdir()
        return tmp_path
    
    def test_backslash_traversal_blocked(self, validator, temp_root):
        """Windows backslash traversal should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("..\\..\\windows\\system32", temp_root)
    
    def test_mixed_slash_traversal_blocked(self, validator, temp_root):
        """Mixed forward and backslash traversal should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("..\\../..\\etc", temp_root)
    
    def test_unc_path_blocked(self, validator, temp_root):
        """UNC paths (\\\\server\\share) should be blocked."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate_and_resolve("\\\\server\\share\\file.txt", temp_root)
        assert exc_info.value.reason == "dangerous_prefix"
    
    def test_extended_path_prefix_blocked(self, validator, temp_root):
        """Extended path prefix (\\\\?\\) should be blocked."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate_and_resolve("\\\\?\\C:\\secret", temp_root)
        assert exc_info.value.reason == "dangerous_prefix"
    
    def test_device_path_blocked(self, validator, temp_root):
        """Device path (\\\\.\\) should be blocked."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate_and_resolve("\\\\.\\PhysicalDrive0", temp_root)
        assert exc_info.value.reason == "dangerous_prefix"


class TestPathValidatorValidPaths:
    """Tests for valid paths that should be allowed."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# main")
        (tmp_path / "src" / "utils").mkdir()
        (tmp_path / "src" / "utils" / "helper.py").write_text("# helper")
        (tmp_path / "tests").mkdir()
        return tmp_path
    
    def test_simple_relative_path_allowed(self, validator, temp_root):
        """Simple relative path should be allowed."""
        result = validator.validate_and_resolve("src/main.py", temp_root)
        assert result.exists()
        assert result.is_relative_to(temp_root)
    
    def test_nested_path_allowed(self, validator, temp_root):
        """Nested relative path should be allowed."""
        result = validator.validate_and_resolve("src/utils/helper.py", temp_root)
        assert result.exists()
        assert result.name == "helper.py"
    
    def test_directory_path_allowed(self, validator, temp_root):
        """Directory path should be allowed."""
        result = validator.validate_and_resolve("src/utils", temp_root)
        assert result.is_dir()
    
    def test_path_with_spaces_allowed(self, validator, temp_root):
        """Path with spaces should be allowed."""
        (temp_root / "my files").mkdir()
        (temp_root / "my files" / "doc.txt").write_text("doc")
        result = validator.validate_and_resolve("my files/doc.txt", temp_root)
        assert result.exists()
    
    def test_url_encoded_spaces_decoded(self, validator, temp_root):
        """URL-encoded spaces should be decoded and allowed."""
        (temp_root / "my files").mkdir()
        result = validator.validate_and_resolve("my%20files", temp_root)
        assert result.name == "my files"
    
    def test_must_exist_with_existing_file(self, validator, temp_root):
        """must_exist=True with existing file should succeed."""
        result = validator.validate_and_resolve(
            "src/main.py", temp_root, must_exist=True
        )
        assert result.exists()
    
    def test_must_exist_with_nonexistent_file_raises(self, validator, temp_root):
        """must_exist=True with nonexistent file should raise."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate_and_resolve(
                "nonexistent.txt", temp_root, must_exist=True
            )
        assert exc_info.value.reason == "not_found"


class TestPathValidatorSymlinks:
    """Tests for symlink handling."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root_with_symlinks(self, tmp_path):
        """Create root with symlinks (skip on Windows if not supported)."""
        (tmp_path / "allowed").mkdir()
        (tmp_path / "allowed" / "file.txt").write_text("content")
        (tmp_path / "outside").mkdir()
        (tmp_path / "outside" / "secret.txt").write_text("secret")
        
        # Create symlinks if supported
        try:
            (tmp_path / "allowed" / "safe_link").symlink_to(
                tmp_path / "allowed" / "file.txt"
            )
            (tmp_path / "allowed" / "escape_link").symlink_to(
                tmp_path / "outside" / "secret.txt"
            )
            return tmp_path
        except OSError:
            pytest.skip("Symlinks not supported on this platform/permissions")
    
    def test_safe_symlink_allowed(self, validator, temp_root_with_symlinks):
        """Symlink within root should be allowed with allow_symlinks=True."""
        result = validator.validate_and_resolve(
            "allowed/safe_link",
            temp_root_with_symlinks / "allowed",
            allow_symlinks=True
        )
        assert result.exists()
    
    def test_escape_symlink_blocked_by_default(self, validator, temp_root_with_symlinks):
        """Symlink escaping root should be blocked by default."""
        with pytest.raises(PathValidationError) as exc_info:
            validator.validate_and_resolve(
                "allowed/escape_link",
                temp_root_with_symlinks / "allowed",
                allow_symlinks=False
            )
        assert exc_info.value.reason == "symlink_escape"


class TestPathValidatorSanitize:
    """Tests for sanitize_relative_path method."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    def test_sanitize_removes_parent_refs(self, validator):
        """Sanitize should remove parent directory references."""
        result = validator.sanitize_relative_path("../../../etc/passwd")
        assert ".." not in result
        assert result == "etc/passwd"
    
    def test_sanitize_removes_current_dir_refs(self, validator):
        """Sanitize should remove current directory references."""
        result = validator.sanitize_relative_path("./foo/./bar/./baz")
        assert result == "foo/bar/baz"
    
    def test_sanitize_handles_mixed_traversal(self, validator):
        """Sanitize should handle mixed traversal patterns."""
        result = validator.sanitize_relative_path("foo/../bar/../baz")
        # Note: sanitize removes .. but doesn't collapse paths
        assert ".." not in result
        assert "foo" in result
        assert "baz" in result
    
    def test_sanitize_normalizes_slashes(self, validator):
        """Sanitize should normalize backslashes to forward slashes."""
        result = validator.sanitize_relative_path("foo\\bar\\baz")
        assert "\\" not in result
        assert result == "foo/bar/baz"
    
    def test_sanitize_handles_url_encoding(self, validator):
        """Sanitize should decode URL encoding."""
        result = validator.sanitize_relative_path("foo%2fbar%2fbaz")
        assert result == "foo/bar/baz"
    
    def test_sanitize_empty_path(self, validator):
        """Sanitize should handle empty path."""
        result = validator.sanitize_relative_path("")
        assert result == ""
    
    def test_sanitize_removes_null_bytes(self, validator):
        """Sanitize should remove components with null bytes."""
        result = validator.sanitize_relative_path("foo/bar\x00.txt/baz")
        assert "\x00" not in result


class TestPathValidatorIsSafePath:
    """Tests for is_safe_path method."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        (tmp_path / "project1").mkdir()
        (tmp_path / "project2").mkdir()
        (tmp_path / "project1" / "file.txt").write_text("content")
        return tmp_path
    
    def test_is_safe_returns_true_for_valid_path(self, validator, temp_root):
        """is_safe_path should return True for valid paths."""
        assert validator.is_safe_path(
            "project1/file.txt",
            [temp_root]
        ) is True
    
    def test_is_safe_returns_false_for_traversal(self, validator, temp_root):
        """is_safe_path should return False for traversal attempts."""
        assert validator.is_safe_path(
            "../../../etc/passwd",
            [temp_root]
        ) is False
    
    def test_is_safe_checks_multiple_roots(self, validator, temp_root):
        """is_safe_path should check all provided roots."""
        project1 = temp_root / "project1"
        project2 = temp_root / "project2"
        
        # File exists in project1 but not project2
        assert validator.is_safe_path(
            "file.txt",
            [project1, project2]
        ) is True
    
    def test_is_safe_with_must_exist(self, validator, temp_root):
        """is_safe_path with must_exist should check existence."""
        assert validator.is_safe_path(
            "nonexistent.txt",
            [temp_root],
            must_exist=True
        ) is False
        
        assert validator.is_safe_path(
            "project1/file.txt",
            [temp_root],
            must_exist=True
        ) is True


class TestPathValidatorBatch:
    """Tests for batch validation."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        (tmp_path / "valid1.txt").write_text("1")
        (tmp_path / "valid2.txt").write_text("2")
        return tmp_path
    
    def test_batch_validation_mixed_paths(self, validator, temp_root):
        """Batch validation should separate valid and invalid paths."""
        paths = [
            "valid1.txt",
            "../../../etc/passwd",
            "valid2.txt",
            "\\\\server\\share",
        ]
        
        valid, failed = validator.validate_paths_batch(paths, temp_root)
        
        assert len(valid) == 2
        assert len(failed) == 2
        assert all(p.exists() for p in valid)
        assert failed[0][0] == "../../../etc/passwd"
        assert failed[1][0] == "\\\\server\\share"


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")
        return tmp_path
    
    def test_validate_path_function(self, temp_root):
        """validate_path convenience function should work."""
        result = validate_path("file.txt", temp_root)
        assert result.exists()
    
    def test_validate_path_raises_on_traversal(self, temp_root):
        """validate_path should raise on traversal."""
        with pytest.raises(PathValidationError):
            validate_path("../secret", temp_root)
    
    def test_is_safe_path_function_true(self, temp_root):
        """is_safe_path convenience function should return True for safe paths."""
        assert is_safe_path("file.txt", temp_root) is True
    
    def test_is_safe_path_function_false(self, temp_root):
        """is_safe_path convenience function should return False for unsafe paths."""
        assert is_safe_path("../../../etc/passwd", temp_root) is False


class TestPathValidatorEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def validator(self):
        return PathValidator(log_failures=False)
    
    @pytest.fixture
    def temp_root(self, tmp_path):
        return tmp_path
    
    def test_very_long_path(self, validator, temp_root):
        """Very long paths should be handled gracefully."""
        long_path = "a" * 1000 + "/" + "b" * 1000
        # Should not raise, just validate
        try:
            result = validator.validate_and_resolve(long_path, temp_root)
            assert result.is_relative_to(temp_root)
        except PathValidationError:
            # Also acceptable - validation failed cleanly
            pass
    
    def test_unicode_path(self, validator, temp_root):
        """Unicode paths should be handled."""
        (temp_root / "文件").mkdir()
        result = validator.validate_and_resolve("文件", temp_root)
        assert result.name == "文件"
    
    def test_special_characters_in_path(self, validator, temp_root):
        """Special characters (except traversal) should be allowed."""
        (temp_root / "file-name_123").mkdir()
        result = validator.validate_and_resolve("file-name_123", temp_root)
        assert result.exists()
    
    def test_strict_mode_off(self, temp_root):
        """With strict_mode=False, some patterns may be allowed if safe."""
        validator = PathValidator(log_failures=False, strict_mode=False)
        
        # Create a path that has .. but resolves within root
        (temp_root / "a" / "b").mkdir(parents=True)
        
        # This should still be blocked because it escapes
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("../../../etc/passwd", temp_root)
    
    def test_absolute_path_outside_root_blocked(self, validator, temp_root):
        """Absolute path outside root should be blocked."""
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("/etc/passwd", temp_root)
    
    def test_logging_enabled(self, temp_root, caplog):
        """Validator should log failures when log_failures=True."""
        import logging
        caplog.set_level(logging.WARNING)
        
        validator = PathValidator(log_failures=True)
        
        with pytest.raises(PathValidationError):
            validator.validate_and_resolve("../secret", temp_root)
        
        assert "PATH SECURITY" in caplog.text
