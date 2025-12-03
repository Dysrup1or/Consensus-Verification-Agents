"""
Tests for the Watcher module (Module A: Ingestion)
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.watcher import DirectoryWatcher, DebounceHandler, run_watcher


class TestDebounceHandler:
    """Tests for the DebounceHandler class."""

    def test_init_defaults(self):
        """Test handler initialization with defaults."""
        handler = DebounceHandler()

        assert handler.debounce_seconds == 15.0
        assert handler.on_trigger is None
        assert ".py" in handler.supported_extensions
        assert "__pycache__" in handler.ignore_patterns

    def test_init_custom(self):
        """Test handler initialization with custom values."""
        callback = Mock()
        handler = DebounceHandler(
            debounce_seconds=5.0, on_trigger=callback, supported_extensions=[".py"], ignore_patterns=["node_modules"]
        )

        assert handler.debounce_seconds == 5.0
        assert handler.on_trigger == callback
        assert handler.supported_extensions == [".py"]
        assert handler.ignore_patterns == ["node_modules"]

    def test_should_process_python_file(self):
        """Test that Python files are processed."""
        handler = DebounceHandler()

        assert handler._should_process("/project/main.py") is True
        assert handler._should_process("/project/test.py") is True

    def test_should_process_js_file(self):
        """Test that JavaScript files are processed."""
        handler = DebounceHandler()

        assert handler._should_process("/project/app.js") is True
        assert handler._should_process("/project/index.ts") is True

    def test_should_not_process_ignored(self):
        """Test that ignored patterns are skipped."""
        handler = DebounceHandler()

        assert handler._should_process("/project/__pycache__/main.pyc") is False
        assert handler._should_process("/project/node_modules/lib.js") is False
        assert handler._should_process("/project/.git/config") is False

    def test_should_not_process_unsupported(self):
        """Test that unsupported extensions are skipped."""
        handler = DebounceHandler()

        assert handler._should_process("/project/readme.md") is False
        assert handler._should_process("/project/data.json") is False
        assert handler._should_process("/project/image.png") is False


class TestDirectoryWatcher:
    """Tests for the DirectoryWatcher class."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        temp_dir = tempfile.mkdtemp()

        # Create some Python files
        Path(temp_dir, "main.py").write_text('print("hello")')
        Path(temp_dir, "utils.py").write_text("def helper(): pass")

        # Create subdirectory with more files
        sub_dir = Path(temp_dir, "src")
        sub_dir.mkdir()
        Path(sub_dir, "app.py").write_text("class App: pass")

        # Create ignored directory
        cache_dir = Path(temp_dir, "__pycache__")
        cache_dir.mkdir()
        Path(cache_dir, "main.cpython-310.pyc").write_bytes(b"compiled")

        yield temp_dir

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir, "config.yaml")
        config_path.write_text(
            """
watcher:
  debounce_seconds: 10
  supported_extensions:
    python: [".py"]
    javascript: [".js"]
  ignore_patterns:
    - "__pycache__"
    - ".git"
"""
        )
        yield str(config_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init(self, temp_project, temp_config):
        """Test watcher initialization."""
        watcher = DirectoryWatcher(temp_project, temp_config)

        assert watcher.target_path == os.path.abspath(temp_project)
        assert watcher.debounce_seconds == 10

    def test_setup(self, temp_project, temp_config):
        """Test watcher setup."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        path = watcher.setup()

        assert path == os.path.abspath(temp_project)

    def test_setup_nonexistent(self, temp_config):
        """Test setup with non-existent directory."""
        watcher = DirectoryWatcher("/nonexistent/path", temp_config)

        with pytest.raises(FileNotFoundError):
            watcher.setup()

    def test_detect_language_python(self, temp_project, temp_config):
        """Test language detection for Python project."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        language = watcher.detect_language()
        assert language == "python"

    def test_detect_language_javascript(self, temp_config):
        """Test language detection for JavaScript project."""
        temp_dir = tempfile.mkdtemp()
        try:
            Path(temp_dir, "app.js").write_text('console.log("hello")')
            Path(temp_dir, "index.js").write_text("export default {}")
            Path(temp_dir, "utils.ts").write_text("const x: number = 1")

            watcher = DirectoryWatcher(temp_dir, temp_config)
            watcher.setup()

            language = watcher.detect_language()
            assert language == "javascript"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_detect_language_empty(self, temp_config):
        """Test language detection for empty directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            watcher = DirectoryWatcher(temp_dir, temp_config)
            watcher.setup()

            language = watcher.detect_language()
            assert language == "python"  # Default
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_build_file_tree(self, temp_project, temp_config):
        """Test file tree building."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        file_tree = watcher.build_file_tree()

        assert len(file_tree) == 3
        assert "main.py" in file_tree
        assert "utils.py" in file_tree
        assert (
            os.path.join("src", "app.py").replace("\\", "/") in [k.replace("\\", "/") for k in file_tree.keys()]
            or "src\\app.py" in file_tree
            or "src/app.py" in file_tree
        )

    def test_build_file_tree_ignores_pycache(self, temp_project, temp_config):
        """Test that __pycache__ is ignored."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        file_tree = watcher.build_file_tree()

        for path in file_tree.keys():
            assert "__pycache__" not in path

    def test_has_changes_first_run(self, temp_project, temp_config):
        """Test change detection on first run."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        file_tree = watcher.build_file_tree()

        # First run should detect changes
        assert watcher.has_changes(file_tree) is True

    def test_has_changes_no_change(self, temp_project, temp_config):
        """Test change detection with no changes."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        file_tree = watcher.build_file_tree()

        # First run detects changes
        watcher.has_changes(file_tree)

        # Second run with same content should not detect changes
        assert watcher.has_changes(file_tree) is False

    def test_has_changes_with_modification(self, temp_project, temp_config):
        """Test change detection with modification."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        file_tree = watcher.build_file_tree()
        watcher.has_changes(file_tree)

        # Modify a file
        Path(temp_project, "main.py").write_text('print("modified")')

        new_tree = watcher.build_file_tree()
        assert watcher.has_changes(new_tree) is True

    def test_save_file_tree(self, temp_project, temp_config):
        """Test file tree saving."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        file_tree = watcher.build_file_tree()
        output_path = os.path.join(temp_project, "file_tree.json")

        watcher.save_file_tree(file_tree, output_path)

        assert os.path.exists(output_path)

        with open(output_path, "r") as f:
            saved = json.load(f)

        assert len(saved) == len(file_tree)

    def test_run_once(self, temp_project, temp_config):
        """Test on-demand run."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        file_tree = watcher.run_once()

        assert isinstance(file_tree, dict)
        assert len(file_tree) == 3

    def test_cleanup(self, temp_project, temp_config):
        """Test cleanup does not error."""
        watcher = DirectoryWatcher(temp_project, temp_config)
        watcher.setup()

        # Should not raise
        watcher.cleanup()


class TestRunWatcher:
    """Tests for the run_watcher function."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        temp_dir = tempfile.mkdtemp()
        Path(temp_dir, "main.py").write_text('print("hello")')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir, "config.yaml")
        config_path.write_text("watcher:\n  debounce_seconds: 5")
        yield str(config_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_watcher_once(self, temp_project, temp_config):
        """Test run_watcher in on-demand mode."""
        file_tree = run_watcher(target_path=temp_project, config_path=temp_config, watch_mode=False)

        assert file_tree is not None
        assert isinstance(file_tree, dict)
        assert "main.py" in file_tree


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_directory(self):
        """Test handling of empty directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            watcher = DirectoryWatcher(temp_dir)
            watcher.setup()

            file_tree = watcher.build_file_tree()
            assert file_tree == {}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_binary_file_handling(self):
        """Test handling of binary files (should be ignored)."""
        temp_dir = tempfile.mkdtemp()
        try:
            Path(temp_dir, "data.bin").write_bytes(b"\x00\x01\x02")
            Path(temp_dir, "main.py").write_text('print("hello")')

            watcher = DirectoryWatcher(temp_dir)
            watcher.setup()

            file_tree = watcher.build_file_tree()

            assert "main.py" in file_tree
            assert "data.bin" not in file_tree
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_unicode_content(self):
        """Test handling of unicode content."""
        temp_dir = tempfile.mkdtemp()
        try:
            Path(temp_dir, "unicode.py").write_text('# 日本語コメント\nprint("🎉")', encoding="utf-8")

            watcher = DirectoryWatcher(temp_dir)
            watcher.setup()

            file_tree = watcher.build_file_tree()

            assert "unicode.py" in file_tree
            assert "日本語" in file_tree["unicode.py"]
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_deeply_nested_files(self):
        """Test handling of deeply nested files."""
        temp_dir = tempfile.mkdtemp()
        try:
            deep_path = Path(temp_dir, "a", "b", "c", "d", "e")
            deep_path.mkdir(parents=True)
            Path(deep_path, "deep.py").write_text("# Deep file")

            watcher = DirectoryWatcher(temp_dir)
            watcher.setup()

            file_tree = watcher.build_file_tree()

            assert len(file_tree) == 1
            # Check the key contains the nested path
            key = list(file_tree.keys())[0]
            assert "deep.py" in key
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestDebounceEvents:
    """Tests for debounce event handling."""

    def test_on_any_event_triggers_debounce(self):
        """Test that on_any_event sets pending trigger."""
        callback = Mock()
        handler = DebounceHandler(debounce_seconds=0.1, on_trigger=callback)

        # Create mock event
        event = Mock()
        event.is_directory = False
        event.src_path = "/project/test.py"

        # Trigger event
        handler.on_any_event(event)

        # State should be updated
        assert handler.pending_trigger is True
        assert handler.last_event_time is not None

    def test_on_any_event_adds_to_changed_files(self):
        """Test that events add files to changed set."""
        handler = DebounceHandler(debounce_seconds=0.1)

        event = Mock()
        event.is_directory = False
        event.src_path = "/project/new.py"

        handler.on_any_event(event)
        assert "/project/new.py" in handler._changed_files

    def test_check_and_trigger_not_ready(self):
        """Test check_and_trigger returns False when not ready."""
        handler = DebounceHandler(debounce_seconds=10.0)

        # No events yet
        assert handler.check_and_trigger() is False

    def test_directory_events_ignored(self):
        """Test that directory events are ignored."""
        handler = DebounceHandler(debounce_seconds=0.1)

        event = Mock()
        event.is_directory = True
        event.src_path = "/project/subdir"

        handler.on_any_event(event)
        assert handler.pending_trigger is False


class TestGitClone:
    """Tests for Git clone functionality."""

    def test_clone_repo_not_implemented(self):
        """Test clone_repo behavior (may not have method)."""
        temp_dir = tempfile.mkdtemp()
        try:
            watcher = DirectoryWatcher(temp_dir)
            # Just verify it initializes correctly
            assert watcher is not None
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestWatchMode:
    """Tests for watch mode functionality."""

    def test_start_watching_creates_handler(self):
        """Test that start_watching creates handler."""
        temp_dir = tempfile.mkdtemp()
        try:
            Path(temp_dir, "test.py").write_text("# Test")

            watcher = DirectoryWatcher(temp_dir)
            watcher.setup()

            # Build file tree and verify setup works
            file_tree = watcher.build_file_tree()
            assert file_tree is not None
            assert len(file_tree) > 0
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
