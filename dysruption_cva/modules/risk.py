"""Risk scoring signals for Invariant (deterministic).

This module provides lightweight, best-effort signals used to prioritize
which files to include in the LLM context:
- new-file detection via `git status --porcelain`
- churn via `git diff --numstat` (working tree + staged)
- recent-touch frequency via `git log --name-only`

All functions must be safe to call outside git repos and should fail closed
(returning empty results) rather than raising.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class GitSignals:
    new_files: Set[str]
    churn_lines: Dict[str, int]
    recent_touches: Dict[str, int]


def _run_git(project_root: Path, args: List[str], *, timeout_s: float = 2.0) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    return proc.stdout or ""


def _parse_porcelain_status(output: str) -> Set[str]:
    new_files: Set[str] = set()
    for line in (output or "").splitlines():
        if not line.strip():
            continue
        # Format: XY <path> (or rename: XY <old> -> <new>)
        if line.startswith("?? "):
            path = line[3:].strip()
            if path:
                new_files.add(path.replace("\\", "/"))
            continue

        if len(line) < 4:
            continue

        xy = line[:2]
        rest = line[3:].strip()

        # rename: "R  old -> new" or "RM old -> new"
        if "->" in rest:
            rest = rest.split("->", 1)[1].strip()

        path = rest
        if not path:
            continue

        if "A" in xy:
            new_files.add(path.replace("\\", "/"))

    return new_files


def _parse_numstat(output: str) -> Dict[str, int]:
    churn: Dict[str, int] = {}
    for line in (output or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_s, del_s, path = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if ins_s == "-" or del_s == "-":
            continue
        try:
            ins_n = int(ins_s)
            del_n = int(del_s)
        except Exception:
            continue
        rel = path.replace("\\", "/")
        churn[rel] = churn.get(rel, 0) + ins_n + del_n
    return churn


def _parse_log_name_only(output: str) -> Dict[str, int]:
    touches: Dict[str, int] = {}
    for line in (output or "").splitlines():
        rel = line.strip()
        if not rel:
            continue
        rel = rel.replace("\\", "/")
        touches[rel] = touches.get(rel, 0) + 1
    return touches


def collect_git_signals(project_root: Path, rel_paths: Iterable[str]) -> GitSignals:
    """Collect git-backed signals for a set of paths.

    This intentionally does not error if git is unavailable or the folder
    isn't a repo.
    """

    root = project_root.resolve()
    rel_set = {p.replace("\\", "/") for p in rel_paths if p}

    status_out = _run_git(root, ["status", "--porcelain=v1"], timeout_s=2.0)
    new_files = _parse_porcelain_status(status_out or "") if status_out is not None else set()

    diff_out = _run_git(root, ["diff", "--numstat"], timeout_s=2.0)
    diff_cached_out = _run_git(root, ["diff", "--cached", "--numstat"], timeout_s=2.0)
    churn = _parse_numstat(diff_out or "")
    cached = _parse_numstat(diff_cached_out or "")
    for k, v in cached.items():
        churn[k] = churn.get(k, 0) + v

    log_out = _run_git(root, ["log", "-n", "60", "--name-only", "--pretty=format:"], timeout_s=2.5)
    touches = _parse_log_name_only(log_out or "") if log_out is not None else {}

    # Filter down to the requested paths only.
    new_files = {p for p in new_files if p in rel_set}
    churn = {p: churn.get(p, 0) for p in rel_set if p in churn}
    touches = {p: touches.get(p, 0) for p in rel_set if p in touches}

    return GitSignals(new_files=new_files, churn_lines=churn, recent_touches=touches)
