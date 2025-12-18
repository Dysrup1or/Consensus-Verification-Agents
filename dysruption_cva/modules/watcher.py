"""
Dysruption CVA - Watcher Module (Module A: Ingestion)
Monitors directories or Git repos for changes, builds file trees, triggers extraction and adjudication.
"""

import os
import json
import time
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Optional, Callable, List, Set
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from loguru import logger
import yaml

try:
    import git

    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    logger.warning("GitPython not available. Git repo support disabled.")


class DebounceHandler(FileSystemEventHandler):
    """
    File system event handler with debounce logic.
    Waits for 15 seconds of inactivity before triggering callbacks.
    """

    def __init__(
        self,
        debounce_seconds: float = 15.0,
        on_trigger: Optional[Callable[[], None]] = None,
        supported_extensions: Optional[List[str]] = None,
        ignore_patterns: Optional[List[str]] = None,
    ):
        super().__init__()
        self.debounce_seconds = debounce_seconds
        self.on_trigger = on_trigger
        self.supported_extensions = supported_extensions or [".py", ".js", ".ts", ".jsx", ".tsx"]
        self.ignore_patterns = ignore_patterns or ["__pycache__", "node_modules", ".git", ".venv", "venv"]
        self.last_event_time: Optional[float] = None
        self.pending_trigger = False
        self._changed_files: Set[str] = set()

    def _should_process(self, path: str) -> bool:
        """Check if file should be processed based on extension and ignore patterns."""
        path_obj = Path(path)

        # Check ignore patterns
        for pattern in self.ignore_patterns:
            if pattern in str(path_obj):
                return False

        # Check supported extensions
        if path_obj.suffix.lower() in self.supported_extensions:
            return True

        return False

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event with debouncing."""
        if event.is_directory:
            return

        src_path = str(event.src_path)

        if not self._should_process(src_path):
            return

        logger.debug(f"File event: {event.event_type} - {src_path}")
        self._changed_files.add(src_path)
        self.last_event_time = time.time()
        self.pending_trigger = True

    def check_and_trigger(self) -> bool:
        """Check if debounce period has passed and trigger if so. Returns True if triggered."""
        if not self.pending_trigger or self.last_event_time is None:
            return False

        elapsed = time.time() - self.last_event_time
        if elapsed >= self.debounce_seconds:
            logger.info(f"Debounce complete. {len(self._changed_files)} files changed. Triggering processing...")
            self.pending_trigger = False
            changed = list(self._changed_files)
            self._changed_files.clear()

            if self.on_trigger:
                self.on_trigger()
            return True
        return False


class DirectoryWatcher:
    """
    Watches a directory for code file changes.
    Supports both local directories and Git repositories.
    """

    def __init__(
        self,
        target_path: str,
        config_path: str = "config.yaml",
        on_change_callback: Optional[Callable[[], None]] = None,
    ):
        self.target_path = os.path.abspath(target_path)
        self.config = self._load_config(config_path)
        self.on_change_callback = on_change_callback
        self.observer: Optional[Observer] = None
        self.handler: Optional[DebounceHandler] = None
        self.is_git_repo = False
        self.temp_dir: Optional[str] = None
        self._file_hashes: Dict[str, str] = {}

        # Get watcher config
        watcher_config = self.config.get("watcher", {})
        self.debounce_seconds = watcher_config.get("debounce_seconds", 15)

        # Build supported extensions from config
        extensions_config = watcher_config.get("supported_extensions", {})
        self.supported_extensions: List[str] = []
        for lang_exts in extensions_config.values():
            self.supported_extensions.extend(lang_exts)
        if not self.supported_extensions:
            self.supported_extensions = [".py", ".js", ".ts", ".jsx", ".tsx"]

        self.ignore_patterns = watcher_config.get("ignore_patterns", [])

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

    def _is_git_url(self, path: str) -> bool:
        """Check if path is a Git URL."""
        return path.startswith(("http://", "https://", "git@", "git://"))

    def _clone_or_pull_repo(self, git_url: str) -> str:
        """Clone or pull a Git repository. Returns local path."""
        if not GIT_AVAILABLE:
            raise RuntimeError("GitPython is not available. Install with: pip install gitpython")

        # Create temp directory for the repo
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
        Returns the path being watched.
        
        Security:
        - Resolves path to absolute form
        - Validates path exists and is a directory
        - Prevents path traversal attacks
        """
        if git_url:
            self.target_path = self._clone_or_pull_repo(git_url)

        # Security: Convert to absolute path and resolve any .. components
        try:
            resolved_path = Path(self.target_path).resolve(strict=False)
            self.target_path = str(resolved_path)
        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid target path: {e}")
        
        # Security: Prevent path traversal - ensure resolved path doesn't escape expected bounds
        if ".." in self.target_path:
            raise ValueError("Path traversal detected: '..' not allowed in resolved path")
        
        # Validate path exists
        if not os.path.exists(self.target_path):
            raise FileNotFoundError(f"Target path does not exist: {self.target_path}")
        
        # Validate it's a directory
        if not os.path.isdir(self.target_path):
            raise ValueError(f"Target path is not a directory: {self.target_path}")

        logger.info(f"Watcher setup for: {self.target_path}")
        return self.target_path

    def detect_language(self) -> str:
        """Auto-detect primary project language based on file extensions."""
        extension_counts: Dict[str, int] = {}

        for root, _, files in os.walk(self.target_path):
            # Skip ignored directories
            skip = False
            for pattern in self.ignore_patterns:
                if pattern in root:
                    skip = True
                    break
            if skip:
                continue

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.supported_extensions:
                    extension_counts[ext] = extension_counts.get(ext, 0) + 1

        if not extension_counts:
            logger.warning("No supported code files found. Defaulting to Python.")
            return "python"

        # Determine language based on most common extension
        python_exts = {".py"}
        js_exts = {".js", ".ts", ".jsx", ".tsx"}

        python_count = sum(extension_counts.get(ext, 0) for ext in python_exts)
        js_count = sum(extension_counts.get(ext, 0) for ext in js_exts)

        if python_count >= js_count:
            logger.info(f"Detected language: Python ({python_count} files)")
            return "python"
        else:
            logger.info(f"Detected language: JavaScript/TypeScript ({js_count} files)")
            return "javascript"

    def build_file_tree(self) -> Dict[str, str]:
        """
        Build a JSON file tree with file contents.
        Returns: {file_path: content} dictionary
        """
        file_tree: Dict[str, str] = {}

        for root, _, files in os.walk(self.target_path):
            # Skip ignored directories
            skip = False
            for pattern in self.ignore_patterns:
                if pattern in root:
                    skip = True
                    break
            if skip:
                continue

            for file in files:
                file_path = os.path.join(root, file)
                ext = Path(file).suffix.lower()

                if ext not in self.supported_extensions:
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # Use relative path as key
                    rel_path = os.path.relpath(file_path, self.target_path)
                    file_tree[rel_path] = content
                    logger.debug(f"Added file: {rel_path} ({len(content)} chars)")

                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")

        logger.info(f"Built file tree with {len(file_tree)} files")
        return file_tree

    def _compute_hash(self, file_tree: Dict[str, str]) -> str:
        """Compute hash of file tree for idempotency check."""
        content = json.dumps(file_tree, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def has_changes(self, file_tree: Dict[str, str]) -> bool:
        """Check if file tree has changed since last check (for idempotency)."""
        current_hash = self._compute_hash(file_tree)

        # Check individual file hashes
        changed = False
        for path, content in file_tree.items():
            file_hash = hashlib.sha256(content.encode()).hexdigest()
            if self._file_hashes.get(path) != file_hash:
                changed = True
                self._file_hashes[path] = file_hash

        return changed

    def save_file_tree(self, file_tree: Dict[str, str], output_path: str = "file_tree.json") -> str:
        """Save file tree to JSON file."""
        output_file = Path(output_path)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(file_tree, f, indent=2)
        logger.info(f"Saved file tree to: {output_file}")
        return str(output_file)

    def start_watching(self) -> None:
        """Start watching the directory for changes."""
        self.handler = DebounceHandler(
            debounce_seconds=self.debounce_seconds,
            on_trigger=self.on_change_callback,
            supported_extensions=self.supported_extensions,
            ignore_patterns=self.ignore_patterns,
        )

        self.observer = Observer()
        self.observer.schedule(self.handler, self.target_path, recursive=True)
        self.observer.start()
        logger.info(f"Started watching: {self.target_path} (debounce: {self.debounce_seconds}s)")

    def stop_watching(self) -> None:
        """Stop watching the directory."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped directory watcher")

    def run_once(self) -> Dict[str, str]:
        """Run once without watching (for on-demand mode)."""
        file_tree = self.build_file_tree()
        return file_tree

    def watch_loop(self, extraction_fn: Callable, adjudication_fn: Callable) -> None:
        """
        Main watch loop. Runs extraction and adjudication when changes detected.
        """

        def on_trigger():
            logger.info("=" * 60)
            logger.info("CHANGE DETECTED - Starting CVA Pipeline")
            logger.info("=" * 60)

            try:
                # Build file tree
                file_tree = self.build_file_tree()

                if not file_tree:
                    logger.warning("No code files found. Skipping...")
                    return

                # Check for actual changes (idempotency)
                if not self.has_changes(file_tree):
                    logger.info("No actual content changes detected. Skipping...")
                    return

                # Save file tree
                self.save_file_tree(file_tree)

                # Detect language
                language = self.detect_language()

                # Run extraction
                logger.info("Running extraction...")
                extraction_fn(file_tree)

                # Run adjudication
                logger.info("Running adjudication...")
                adjudication_fn(file_tree, language)

                logger.info("=" * 60)
                logger.info("CVA Pipeline Complete")
                logger.info("=" * 60)

            except Exception as e:
                logger.error(f"Error in CVA pipeline: {e}")
                import traceback

                traceback.print_exc()

        self.handler = DebounceHandler(
            debounce_seconds=self.debounce_seconds,
            on_trigger=on_trigger,
            supported_extensions=self.supported_extensions,
            ignore_patterns=self.ignore_patterns,
        )

        self.observer = Observer()
        self.observer.schedule(self.handler, self.target_path, recursive=True)
        self.observer.start()

        logger.info(f"Watching {self.target_path} for changes (Ctrl+C to stop)...")

        try:
            while True:
                time.sleep(1)
                if self.handler:
                    self.handler.check_and_trigger()
        except KeyboardInterrupt:
            logger.info("Stopping watcher...")
            self.stop_watching()

    def cleanup(self) -> None:
        """Clean up temporary directories."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp directory: {self.temp_dir}")


def run_watcher(
    target_path: str,
    config_path: str = "config.yaml",
    git_url: Optional[str] = None,
    watch_mode: bool = True,
    extraction_fn: Optional[Callable] = None,
    adjudication_fn: Optional[Callable] = None,
) -> Optional[Dict[str, str]]:
    """
    Main entry point for the watcher module.

    Args:
        target_path: Local directory to watch
        config_path: Path to config.yaml
        git_url: Optional Git repository URL to clone
        watch_mode: If True, watch continuously. If False, run once.
        extraction_fn: Function to call for extraction
        adjudication_fn: Function to call for adjudication

    Returns:
        File tree dict if run once, None if watching
    """
    watcher = DirectoryWatcher(target_path, config_path)

    try:
        actual_path = watcher.setup(git_url)

        if watch_mode:
            if extraction_fn is None or adjudication_fn is None:
                raise ValueError("extraction_fn and adjudication_fn required for watch mode")
            watcher.watch_loop(extraction_fn, adjudication_fn)
            return None
        else:
            return watcher.run_once()
    finally:
        watcher.cleanup()


if __name__ == "__main__":
    # Test the watcher module
    import sys

    logger.add(sys.stderr, level="DEBUG")

    test_path = "."
    if len(sys.argv) > 1:
        test_path = sys.argv[1]

    watcher = DirectoryWatcher(test_path)
    watcher.setup()

    print(f"Language: {watcher.detect_language()}")
    file_tree = watcher.build_file_tree()
    print(f"Files: {list(file_tree.keys())}")
