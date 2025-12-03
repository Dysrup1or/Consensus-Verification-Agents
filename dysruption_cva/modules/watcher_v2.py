"""
Dysruption CVA - Watcher Module v1.1 (Module A: Ingestion)

Enhanced directory watcher with:
- Smart 3-second debounce (reset on file save)
- dirty_files set tracking for incremental scans
- FileTree output with Pydantic schemas
- Git repository support

Author: Dysruption Enterprises
Version: 1.1
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import yaml
from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .schemas import (
    FileMetadata,
    FileNode,
    FileTree,
    PipelineStatus,
)

try:
    import git

    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    logger.warning("GitPython not available. Git repo support disabled.")


# =============================================================================
# SMART DEBOUNCE HANDLER
# =============================================================================


class SmartDebounceHandler(FileSystemEventHandler):
    """
    File system event handler with smart debounce logic.

    Implements a 3-second debounce that RESETS when a file is saved again.
    This ensures we wait for the developer to finish making changes.

    Maintains a `dirty_files` set to track which files changed since
    the last successful scan, enabling incremental processing.
    """

    def __init__(
        self,
        debounce_seconds: float = 3.0,
        on_trigger: Optional[Callable[[Set[str]], None]] = None,
        supported_extensions: Optional[List[str]] = None,
        ignore_patterns: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize the smart debounce handler.

        Args:
            debounce_seconds: Seconds to wait after last event before triggering
            on_trigger: Callback receiving set of dirty file paths
            supported_extensions: File extensions to monitor (e.g., ['.py', '.js'])
            ignore_patterns: Directory/file patterns to ignore
        """
        super().__init__()
        self.debounce_seconds = debounce_seconds
        self.on_trigger = on_trigger
        self.supported_extensions = supported_extensions or [
            ".py", ".js", ".ts", ".jsx", ".tsx", ".pyi"
        ]
        self.ignore_patterns = ignore_patterns or [
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".pytest_cache", ".mypy_cache", "__pypackages__", "dist",
            "build", ".eggs", "*.egg-info"
        ]

        # Debounce state
        self.last_event_time: Optional[float] = None
        self.pending_trigger: bool = False

        # Dirty files tracking - survives across debounce cycles
        self._dirty_files: Set[str] = set()
        self._current_batch: Set[str] = set()

    def _should_process(self, path: str) -> bool:
        """
        Check if file should be processed based on extension and ignore patterns.

        Args:
            path: File path to check

        Returns:
            True if file should be processed
        """
        path_obj = Path(path)
        path_str = str(path_obj)

        # Check ignore patterns
        for pattern in self.ignore_patterns:
            if pattern.startswith("*"):
                # Glob-like pattern
                if path_obj.match(pattern):
                    return False
            elif pattern in path_str:
                return False

        # Check supported extensions
        return path_obj.suffix.lower() in self.supported_extensions

    def on_any_event(self, event: FileSystemEvent) -> None:
        """
        Handle any file system event with smart debouncing.

        Key behavior: Each event RESETS the debounce timer, ensuring
        we wait for 3 seconds of inactivity before processing.

        Args:
            event: The file system event
        """
        if event.is_directory:
            return

        src_path = str(event.src_path)

        if not self._should_process(src_path):
            return

        logger.debug(f"File event: {event.event_type} - {src_path}")

        # Add to both dirty sets
        self._dirty_files.add(src_path)
        self._current_batch.add(src_path)

        # SMART DEBOUNCE: Reset timer on every event
        self.last_event_time = time.time()
        self.pending_trigger = True

    def check_and_trigger(self) -> bool:
        """
        Check if debounce period has passed and trigger callback if so.

        Returns:
            True if callback was triggered, False otherwise
        """
        if not self.pending_trigger or self.last_event_time is None:
            return False

        elapsed = time.time() - self.last_event_time
        if elapsed >= self.debounce_seconds:
            files_in_batch = len(self._current_batch)
            logger.info(
                f"Debounce complete ({self.debounce_seconds}s). "
                f"{files_in_batch} files in batch, {len(self._dirty_files)} total dirty."
            )

            self.pending_trigger = False
            batch = self._current_batch.copy()
            self._current_batch.clear()

            if self.on_trigger:
                self.on_trigger(batch)
            return True
        return False

    def get_dirty_files(self) -> Set[str]:
        """Get all files that changed since last successful scan."""
        return self._dirty_files.copy()

    def clear_dirty_files(self) -> None:
        """Clear dirty files set after successful processing."""
        self._dirty_files.clear()
        logger.debug("Cleared dirty files set")

    def mark_files_clean(self, files: Set[str]) -> None:
        """Mark specific files as clean (processed)."""
        self._dirty_files -= files


# =============================================================================
# DIRECTORY WATCHER
# =============================================================================


class DirectoryWatcher:
    """
    Enhanced directory watcher with smart debounce and dirty file tracking.

    Features:
    - 3-second smart debounce (resets on each file save)
    - Maintains dirty_files set for incremental scanning
    - Outputs structured FileTree with Pydantic schemas
    - Git repository support (clone/pull)
    """

    def __init__(
        self,
        target_path: str,
        config_path: str = "config.yaml",
        on_change_callback: Optional[Callable[[Set[str]], None]] = None,
    ) -> None:
        """
        Initialize the directory watcher.

        Args:
            target_path: Directory to watch
            config_path: Path to configuration YAML
            on_change_callback: Called with dirty files when changes detected
        """
        self.target_path = os.path.abspath(target_path)
        self.config = self._load_config(config_path)
        self.on_change_callback = on_change_callback
        self.observer: Optional[Observer] = None
        self.handler: Optional[SmartDebounceHandler] = None
        self.is_git_repo: bool = False
        self.temp_dir: Optional[str] = None

        # File tracking
        self._file_hashes: Dict[str, str] = {}
        self._last_scan_time: Optional[datetime] = None

        # Get watcher config
        watcher_config = self.config.get("watcher", {})
        self.debounce_seconds = watcher_config.get("debounce_seconds", 3.0)

        # Build supported extensions from config
        extensions_config = watcher_config.get("supported_extensions", {})
        self.supported_extensions: List[str] = []
        for lang_exts in extensions_config.values():
            self.supported_extensions.extend(lang_exts)
        if not self.supported_extensions:
            self.supported_extensions = [".py", ".js", ".ts", ".jsx", ".tsx"]

        self.ignore_patterns = watcher_config.get("ignore_patterns", [
            "__pycache__", "node_modules", ".git", ".venv", "venv"
        ])

    def _load_config(self, config_path: str) -> Dict[str, Any]:
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

    def _compute_file_hash(self, content: str) -> str:
        """Compute SHA256 hash of file content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
        }
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "unknown")

    def _is_git_url(self, path: str) -> bool:
        """Check if path is a Git URL."""
        return path.startswith(("http://", "https://", "git@", "git://"))

    def _clone_or_pull_repo(self, git_url: str) -> str:
        """Clone or pull a Git repository. Returns local path."""
        if not GIT_AVAILABLE:
            raise RuntimeError(
                "GitPython is not available. Install with: pip install gitpython"
            )

        repo_name = git_url.rstrip("/").split("/")[-1].replace(".git", "")
        self.temp_dir = tempfile.mkdtemp(prefix=f"cva_{repo_name}_")
        repo_path = os.path.join(self.temp_dir, repo_name)

        if os.path.exists(repo_path):
            logger.info(f"Pulling existing repo: {git_url}")
            try:
                repo = git.Repo(repo_path)
                repo.remotes.origin.pull()
            except Exception as e:
                logger.error(f"Error pulling repo: {e}. Re-cloning...")
                import shutil
                shutil.rmtree(repo_path, ignore_errors=True)
                git.Repo.clone_from(git_url, repo_path)
        else:
            logger.info(f"Cloning repo: {git_url}")
            git.Repo.clone_from(git_url, repo_path)

        self.is_git_repo = True
        return repo_path

    def setup(self, git_url: Optional[str] = None) -> str:
        """
        Setup the watcher. If git_url provided, clone/pull the repo.

        Args:
            git_url: Optional Git repository URL

        Returns:
            Path being watched
        """
        if git_url:
            self.target_path = self._clone_or_pull_repo(git_url)

        if not os.path.exists(self.target_path):
            raise FileNotFoundError(f"Target path does not exist: {self.target_path}")

        logger.info(f"Watcher setup for: {self.target_path}")
        return self.target_path

    def detect_primary_language(self) -> str:
        """Auto-detect primary project language based on file extensions."""
        extension_counts: Dict[str, int] = {}

        for root, _, files in os.walk(self.target_path):
            if any(pattern in root for pattern in self.ignore_patterns):
                continue

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.supported_extensions:
                    extension_counts[ext] = extension_counts.get(ext, 0) + 1

        if not extension_counts:
            logger.warning("No supported code files found. Defaulting to Python.")
            return "python"

        python_exts = {".py", ".pyi"}
        js_exts = {".js", ".ts", ".jsx", ".tsx"}

        python_count = sum(extension_counts.get(ext, 0) for ext in python_exts)
        js_count = sum(extension_counts.get(ext, 0) for ext in js_exts)

        if python_count >= js_count:
            logger.info(f"Detected language: Python ({python_count} files)")
            return "python"
        else:
            logger.info(f"Detected language: JavaScript/TypeScript ({js_count} files)")
            return "javascript"

    def build_file_tree(
        self,
        dirty_only: bool = False,
        dirty_files: Optional[Set[str]] = None,
    ) -> FileTree:
        """
        Build a structured file tree with content and metadata.

        Args:
            dirty_only: If True, only include files in dirty_files set
            dirty_files: Set of dirty file paths (absolute)

        Returns:
            FileTree Pydantic model
        """
        files: Dict[str, FileNode] = {}
        dirty_paths: List[str] = []
        total_lines = 0
        languages: Dict[str, int] = {}
        scan_time = datetime.now()

        for root, _, filenames in os.walk(self.target_path):
            if any(pattern in root for pattern in self.ignore_patterns):
                continue

            for filename in filenames:
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, self.target_path)
                ext = Path(filename).suffix.lower()

                if ext not in self.supported_extensions:
                    continue

                # Skip if dirty_only and file not in dirty set
                if dirty_only and dirty_files:
                    if file_path not in dirty_files and rel_path not in dirty_files:
                        continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    stat = os.stat(file_path)
                    line_count = content.count("\n") + 1
                    total_lines += line_count
                    content_hash = self._compute_file_hash(content)
                    language = self._detect_language(file_path)

                    # Track language distribution
                    languages[language] = languages.get(language, 0) + 1

                    # Check if file is dirty (changed since last scan)
                    is_dirty = self._file_hashes.get(rel_path) != content_hash
                    if is_dirty:
                        dirty_paths.append(rel_path)
                        self._file_hashes[rel_path] = content_hash

                    metadata = FileMetadata(
                        path=rel_path,
                        absolute_path=file_path,
                        size_bytes=stat.st_size,
                        lines=line_count,
                        language=language,
                        last_modified=datetime.fromtimestamp(stat.st_mtime),
                        hash=content_hash,
                        is_dirty=is_dirty,
                    )

                    files[rel_path] = FileNode(
                        metadata=metadata,
                        content=content,
                        syntax_valid=True,  # Will be validated by static analysis
                        static_issues=[],
                    )

                    logger.debug(f"Added file: {rel_path} ({line_count} lines)")

                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")

        self._last_scan_time = scan_time

        file_tree = FileTree(
            root_path=self.target_path,
            scan_timestamp=scan_time,
            files=files,
            dirty_files=dirty_paths,
            total_lines=total_lines,
            languages=languages,
        )

        logger.info(
            f"Built file tree: {len(files)} files, {len(dirty_paths)} dirty, "
            f"{total_lines} total lines"
        )
        return file_tree

    def save_file_tree(
        self,
        file_tree: FileTree,
        output_path: str = "filetree.json",
    ) -> str:
        """
        Save file tree to JSON file.

        Args:
            file_tree: FileTree to save
            output_path: Output file path

        Returns:
            Path to saved file
        """
        output_file = Path(output_path)

        # Convert to JSON-serializable format
        tree_dict = file_tree.model_dump(mode="json")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(tree_dict, f, indent=2, default=str)

        logger.info(f"Saved file tree to: {output_file}")
        return str(output_file)

    def start_watching(
        self,
        on_trigger: Optional[Callable[[Set[str]], None]] = None,
    ) -> None:
        """
        Start watching the directory for changes.

        Args:
            on_trigger: Callback when changes detected (receives dirty files set)
        """
        callback = on_trigger or self.on_change_callback

        self.handler = SmartDebounceHandler(
            debounce_seconds=self.debounce_seconds,
            on_trigger=callback,
            supported_extensions=self.supported_extensions,
            ignore_patterns=self.ignore_patterns,
        )

        self.observer = Observer()
        self.observer.schedule(self.handler, self.target_path, recursive=True)
        self.observer.start()

        logger.info(
            f"Started watching: {self.target_path} "
            f"(smart debounce: {self.debounce_seconds}s)"
        )

    def stop_watching(self) -> None:
        """Stop watching the directory."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("Stopped directory watcher")

    def run_once(self) -> FileTree:
        """
        Run a single scan without watching.

        Returns:
            FileTree with all files
        """
        return self.build_file_tree()

    def get_dirty_files(self) -> Set[str]:
        """Get current set of dirty files from handler."""
        if self.handler:
            return self.handler.get_dirty_files()
        return set()

    def clear_dirty_files(self) -> None:
        """Clear dirty files after successful processing."""
        if self.handler:
            self.handler.clear_dirty_files()
        self._file_hashes.clear()

    def watch_loop(
        self,
        on_scan: Callable[[FileTree], None],
        poll_interval: float = 0.5,
    ) -> None:
        """
        Main watch loop with smart debounce.

        Args:
            on_scan: Callback receiving FileTree when scan triggered
            poll_interval: How often to check debounce timer
        """

        def on_trigger(dirty_files: Set[str]) -> None:
            logger.info("=" * 60)
            logger.info("CHANGE DETECTED - Starting CVA Scan")
            logger.info("=" * 60)

            try:
                # Build file tree (only dirty files for efficiency)
                file_tree = self.build_file_tree(
                    dirty_only=bool(dirty_files),
                    dirty_files=dirty_files,
                )

                if not file_tree.files:
                    logger.warning("No files to process. Skipping...")
                    return

                # Save file tree
                self.save_file_tree(file_tree)

                # Call the scan callback
                on_scan(file_tree)

                # Mark processed files as clean
                if self.handler:
                    self.handler.mark_files_clean(dirty_files)

                logger.info("=" * 60)
                logger.info("CVA Scan Complete")
                logger.info("=" * 60)

            except Exception as e:
                logger.error(f"Error in scan pipeline: {e}")
                import traceback
                traceback.print_exc()

        self.start_watching(on_trigger)

        logger.info(f"Watching {self.target_path} for changes (Ctrl+C to stop)...")

        try:
            while True:
                time.sleep(poll_interval)
                if self.handler:
                    self.handler.check_and_trigger()
        except KeyboardInterrupt:
            logger.info("Stopping watcher...")
            self.stop_watching()

    def cleanup(self) -> None:
        """Clean up temporary directories and stop observer."""
        self.stop_watching()

        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp directory: {self.temp_dir}")


# =============================================================================
# MODULE ENTRY POINT
# =============================================================================


def run_watcher(
    target_path: str,
    config_path: str = "config.yaml",
    git_url: Optional[str] = None,
    watch_mode: bool = False,
    on_scan: Optional[Callable[[FileTree], None]] = None,
) -> Optional[FileTree]:
    """
    Main entry point for the watcher module.

    Args:
        target_path: Local directory to watch
        config_path: Path to config.yaml
        git_url: Optional Git repository URL to clone
        watch_mode: If True, watch continuously. If False, run once.
        on_scan: Callback for watch mode (receives FileTree)

    Returns:
        FileTree if run once, None if watching
    """
    watcher = DirectoryWatcher(target_path, config_path)

    try:
        watcher.setup(git_url)

        if watch_mode:
            if on_scan is None:
                raise ValueError("on_scan callback required for watch mode")
            watcher.watch_loop(on_scan)
            return None
        else:
            file_tree = watcher.run_once()
            watcher.save_file_tree(file_tree)
            return file_tree
    finally:
        watcher.cleanup()


if __name__ == "__main__":
    import sys

    logger.add(sys.stderr, level="DEBUG")

    test_path = "."
    if len(sys.argv) > 1:
        test_path = sys.argv[1]

    watcher = DirectoryWatcher(test_path)
    watcher.setup()

    print(f"Language: {watcher.detect_primary_language()}")
    file_tree = watcher.run_once()
    print(f"Files: {list(file_tree.files.keys())}")
    print(f"Total lines: {file_tree.total_lines}")
