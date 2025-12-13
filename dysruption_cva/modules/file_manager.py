"""File and repository utilities for the Tribunal API.

Implements:
- diff/full file selection
- AST-based import resolution (depth-limited)
- LLM context assembly with token-budget truncation

This module is intentionally deterministic (no LLM calls).
"""

from __future__ import annotations

import ast
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from loguru import logger


_MAX_FILE_BYTES_DEFAULT = 512 * 1024  # 512KB safety cap for context building


@dataclass(frozen=True)
class DiffResult:
    mode: str  # "diff" | "full"
    changed_files: List[str]  # relative paths
    detection: str  # "git" | "mtime" | "full"


@dataclass(frozen=True)
class ImportResolutionResult:
    resolved_files: List[str]  # relative paths
    skipped_imports: List[str]  # import strings we could not resolve


@dataclass(frozen=True)
class ContextBuildResult:
    context: str
    token_count: int
    partial: bool
    truncated_files: List[str]
    included_changed_files: List[str]
    included_import_files: List[str]
    included_constitution: bool


def _safe_relative_to(path: Path, root: Path) -> Optional[str]:
    try:
        rel = path.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except Exception:
        return None


def get_project_root(upload_root: Path, project_id: str) -> Path:
    # Project IDs are treated as directory names; prevent path traversal.
    if not project_id or re.search(r"[\\/]|\.\.|^\s+$", project_id):
        raise ValueError("Invalid project_id")
    root = upload_root.resolve()
    candidate = (root / project_id).resolve()

    # Defend against symlink-based escapes (e.g., UPLOAD_ROOT/<id> -> /etc).
    try:
        candidate.relative_to(root)
    except Exception:
        raise ValueError("Invalid project_id")

    return candidate


def is_git_repo(project_root: Path) -> bool:
    return (project_root / ".git").exists() and (project_root / ".git").is_dir()


def detect_changed_files(
    project_root: Path,
    mode: str,
    *,
    mtime_window_seconds: int,
    exclude_dirs: Sequence[str] = (".git", "__pycache__", "node_modules", ".venv"),
) -> DiffResult:
    if mode not in {"diff", "full"}:
        raise ValueError("mode must be 'diff' or 'full'")

    if mode == "full":
        files = list(iter_project_files(project_root, exclude_dirs=exclude_dirs))
        return DiffResult(mode=mode, changed_files=files, detection="full")

    if is_git_repo(project_root):
        try:
            from git import Repo  # GitPython

            repo = Repo(str(project_root))
            changed: Set[str] = set()

            # Modified in working tree
            for diff in repo.index.diff(None):
                if diff.a_path:
                    changed.add(diff.a_path)

            # Untracked
            for p in repo.untracked_files:
                changed.add(p)

            # Staged vs HEAD (if HEAD exists)
            try:
                for diff in repo.index.diff("HEAD"):
                    if diff.a_path:
                        changed.add(diff.a_path)
            except Exception:
                pass

            changed_files = sorted({p.replace("\\", "/") for p in changed})
            return DiffResult(mode=mode, changed_files=changed_files, detection="git")
        except Exception as e:
            logger.warning(f"Git diff detection failed; falling back to mtime: {e}")

    changed_files = detect_mtime_changed_files(
        project_root,
        window_seconds=mtime_window_seconds,
        exclude_dirs=exclude_dirs,
    )
    return DiffResult(mode=mode, changed_files=changed_files, detection="mtime")


def iter_project_files(project_root: Path, *, exclude_dirs: Sequence[str]) -> Iterable[str]:
    root = project_root.resolve()
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        rel = _safe_relative_to(path, root)
        if not rel:
            continue
        parts = rel.split("/")
        if any(part in exclude_dirs for part in parts):
            continue
        yield rel


def detect_mtime_changed_files(
    project_root: Path,
    *,
    window_seconds: int,
    exclude_dirs: Sequence[str],
) -> List[str]:
    root = project_root.resolve()
    now = time.time()
    changed: List[str] = []
    for rel in iter_project_files(root, exclude_dirs=exclude_dirs):
        abs_path = (root / rel).resolve()
        try:
            if now - abs_path.stat().st_mtime <= window_seconds:
                changed.append(rel)
        except Exception:
            continue
    return sorted(changed)


def _module_to_candidate_paths(module: str) -> List[str]:
    # mypkg.sub -> [mypkg/sub.py, mypkg/sub/__init__.py]
    parts = module.split(".")
    base = "/".join(parts)
    return [f"{base}.py", f"{base}/__init__.py"]


def _parse_imports_from_source(source: str) -> Set[str]:
    imports: Set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Handle relative imports by ignoring leading dots here; resolver will adjust.
                prefix = "." * node.level
                imports.add(prefix + node.module)
                # Also include explicit imported names as potential submodules.
                for alias in node.names:
                    if alias.name and alias.name != "*":
                        imports.add(prefix + node.module + "." + alias.name)
            elif node.level:
                imports.add("." * node.level)
    return imports


def resolve_imports(
    project_root: Path,
    changed_files: Sequence[str],
    *,
    depth: int = 2,
    max_files: int = 200,
) -> ImportResolutionResult:
    root = project_root.resolve()

    resolved: Set[str] = set()
    skipped: Set[str] = set()

    def read(rel: str) -> Optional[str]:
        path = (root / rel).resolve()
        try:
            if not path.exists() or not path.is_file():
                return None
            if path.stat().st_size > _MAX_FILE_BYTES_DEFAULT:
                return None
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

    def resolve_module(module: str, base_rel: str) -> Optional[str]:
        # If module is relative (starts with dots), resolve relative to base file.
        dot_prefix = len(module) - len(module.lstrip("."))
        mod_name = module.lstrip(".")

        if dot_prefix:
            base_dir = Path(base_rel).parent
            for _ in range(dot_prefix - 1):
                base_dir = base_dir.parent
            if mod_name:
                candidate_base = (base_dir / mod_name.replace(".", "/")).as_posix()
                candidates = [f"{candidate_base}.py", f"{candidate_base}/__init__.py"]
            else:
                candidates = [base_dir.as_posix() + "/__init__.py"]
        else:
            candidates = _module_to_candidate_paths(mod_name)

        for cand in candidates:
            path = (root / cand).resolve()
            rel = _safe_relative_to(path, root)
            if rel and path.exists() and path.is_file():
                return rel
        return None

    frontier: List[Tuple[str, int]] = [(f, 0) for f in changed_files]
    seen: Set[str] = set(changed_files)

    while frontier:
        rel, d = frontier.pop(0)
        if d >= depth:
            continue

        src = read(rel)
        if src is None:
            continue

        for imp in _parse_imports_from_source(src):
            resolved_rel = resolve_module(imp, rel)
            if not resolved_rel:
                skipped.add(imp)
                continue
            if resolved_rel in seen:
                continue
            seen.add(resolved_rel)
            resolved.add(resolved_rel)
            frontier.append((resolved_rel, d + 1))
            if len(seen) >= max_files:
                break

    return ImportResolutionResult(
        resolved_files=sorted(resolved),
        skipped_imports=sorted(skipped),
    )


def estimate_tokens(text: str) -> int:
    # Deterministic heuristic (rough): ~4 chars/token average.
    return max(1, (len(text) + 3) // 4)


def _read_text_file(root: Path, rel: str, *, max_bytes: int) -> str:
    path = (root / rel).resolve()
    try:
        data = path.read_bytes()
    except Exception:
        return ""

    if len(data) > max_bytes:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def build_llm_context(
    project_root: Path,
    *,
    changed_files: Sequence[str],
    import_files: Sequence[str],
    constitution_text: str,
    token_budget: int,
    max_file_bytes: int = _MAX_FILE_BYTES_DEFAULT,
) -> ContextBuildResult:
    root = project_root.resolve()

    truncated: List[str] = []
    parts: List[str] = []

    def add_section(title: str, body: str) -> None:
        parts.append(f"\n\n## {title}\n{body}")

    def truncate_to_budget(text: str, remaining_tokens: int) -> str:
        # Deterministic truncation. We do not attempt semantic summarization here.
        remaining_chars = max(0, remaining_tokens * 4)
        if remaining_chars <= 0:
            return ""
        if len(text) <= remaining_chars:
            return text
        return text[: max(0, remaining_chars - 40)] + "\n...<truncated>"

    def add_fitted_section(title: str, rel: str, content: str, remaining_tokens: int) -> Tuple[bool, int, str]:
        """Add a section, truncating content until it fits remaining_tokens.

        Returns (added, tokens_used, final_content).
        """
        if remaining_tokens <= 0:
            return False, 0, ""

        snippet = truncate_to_budget(content, remaining_tokens)
        if not snippet:
            return False, 0, ""

        # Iteratively shrink to guarantee the full rendered section fits.
        rendered = f"\n\n## {title}: {rel}\n{snippet}"
        while estimate_tokens(rendered) > remaining_tokens and len(snippet) > 200:
            snippet = snippet[: max(0, len(snippet) - 200)]
            rendered = f"\n\n## {title}: {rel}\n{snippet}\n...<truncated>"

        if estimate_tokens(rendered) > remaining_tokens:
            return False, 0, ""

        parts.append(rendered)
        used = estimate_tokens(rendered)
        return True, used, snippet

    included_changed: List[str] = []
    included_imports: List[str] = []

    running_tokens = 0

    # 1) Changed files (highest priority)
    for rel in changed_files:
        content = _read_text_file(root, rel, max_bytes=max_file_bytes)
        section = f"\n# FILE: {rel}\n{content}"
        section_tokens = estimate_tokens(section)
        if running_tokens + section_tokens > token_budget:
            remaining = token_budget - running_tokens
            added, used, _ = add_fitted_section("Changed", rel, content, remaining)
            if added:
                included_changed.append(rel)
                running_tokens += used
            truncated.append(rel)
            continue
        add_section(f"Changed: {rel}", content)
        included_changed.append(rel)
        running_tokens += section_tokens

    # 2) Resolved imports (medium priority)
    for rel in import_files:
        content = _read_text_file(root, rel, max_bytes=max_file_bytes)
        section = f"\n# FILE: {rel}\n{content}"
        section_tokens = estimate_tokens(section)
        if running_tokens + section_tokens > token_budget:
            remaining = token_budget - running_tokens
            added, used, _ = add_fitted_section("Import", rel, content, remaining)
            if added:
                included_imports.append(rel)
                running_tokens += used
            truncated.append(rel)
            continue
        add_section(f"Import: {rel}", content)
        included_imports.append(rel)
        running_tokens += section_tokens

    # 3) Constitution (lowest priority)
    included_constitution = False
    constitution_tokens = estimate_tokens(constitution_text)
    if running_tokens + constitution_tokens <= token_budget:
        add_section("Constitution", constitution_text)
        included_constitution = True
        running_tokens += constitution_tokens
    else:
        remaining = token_budget - running_tokens
        # Constitution is not a file; fit it as a special section
        added, used, _ = add_fitted_section("Constitution", "constitution", constitution_text, remaining)
        if added:
            included_constitution = True
            running_tokens += used
            truncated.append("__constitution__")

    partial = (len(truncated) > 0) or (not included_constitution)
    context = "".join(parts).strip()

    return ContextBuildResult(
        context=context,
        token_count=running_tokens,
        partial=partial,
        truncated_files=truncated,
        included_changed_files=included_changed,
        included_import_files=included_imports,
        included_constitution=included_constitution,
    )
