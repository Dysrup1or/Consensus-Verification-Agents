from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .schemas import PatchSet


class SelfHealError(RuntimeError):
    pass


class SelfHealDisabledError(SelfHealError):
    pass


@dataclass(frozen=True)
class SelfHealConfig:
    enabled: bool = False
    max_iterations: int = 1
    max_files_per_iteration: int = 10
    max_file_bytes: int = 512 * 1024
    verify_timeout_seconds: int = 300


@dataclass(frozen=True)
class SelfHealIterationResult:
    iteration: int
    applied: bool
    reverted: bool
    verify_exit_code: int
    success: bool
    artifacts_dir: str


@dataclass(frozen=True)
class SelfHealResult:
    success: bool
    iterations: List[SelfHealIterationResult]


PatchProvider = Callable[[int], Optional[PatchSet]]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_repo_relative_path(rel_path: str) -> str:
    rp = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rp or rp.startswith("../") or "/../" in rp:
        raise SelfHealError(f"Invalid patch path: {rel_path}")
    # Hard deny obvious absolute/drive paths
    if ":/" in rp or rp.startswith("//"):
        raise SelfHealError(f"Invalid patch path: {rel_path}")
    return rp


def _resolve_under_root(project_root: Path, rel_path: str) -> Path:
    rp = _ensure_repo_relative_path(rel_path)
    abs_path = (project_root / rp).resolve()
    try:
        if not abs_path.is_relative_to(project_root.resolve()):
            raise SelfHealError(f"Patch path escapes project root: {rel_path}")
    except AttributeError:
        # Python < 3.9 fallback not needed; keep for safety
        pr = str(project_root.resolve())
        ap = str(abs_path)
        if not ap.startswith(pr):
            raise SelfHealError(f"Patch path escapes project root: {rel_path}")

    return abs_path


def _combine_patch_diff(patch_set: PatchSet) -> str:
    if not patch_set.patches:
        return ""
    parts: List[str] = []
    for p in patch_set.patches:
        parts.append(f"# {p.file_path}\n{p.unified_diff}".rstrip())
    return "\n\n".join(parts).strip() + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _capture_hashes(project_root: Path, rel_paths: Iterable[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for rel in rel_paths:
        abs_path = _resolve_under_root(project_root, rel)
        if abs_path.exists() and abs_path.is_file():
            out[rel] = _sha256_bytes(abs_path.read_bytes())
        else:
            out[rel] = "<missing>"
    return out


def apply_patch_set(
    *,
    project_root: Path,
    patch_set: PatchSet,
    config: SelfHealConfig,
) -> Tuple[Dict[str, Optional[bytes]], List[str]]:
    """Apply PatchSet by writing Patch.patched_content.

    Returns a backup map of original file bytes (None if file was missing) and list of touched rel paths.
    """

    if len(patch_set.patches) > config.max_files_per_iteration:
        raise SelfHealError("Too many patched files in a single iteration")

    backups: Dict[str, Optional[bytes]] = {}
    touched: List[str] = []

    for p in patch_set.patches:
        rel = _ensure_repo_relative_path(p.file_path)
        abs_path = _resolve_under_root(project_root, rel)

        if abs_path.exists() and abs_path.is_file():
            raw = abs_path.read_bytes()
            backups[rel] = raw
        else:
            backups[rel] = None

        patched_raw = (p.patched_content or "").encode("utf-8", errors="replace")
        if len(patched_raw) > config.max_file_bytes:
            raise SelfHealError(f"Patched content too large: {rel}")

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(patched_raw)
        touched.append(rel)

    return backups, touched


def revert_patch_set(*, project_root: Path, backups: Dict[str, Optional[bytes]]) -> None:
    for rel, raw in backups.items():
        abs_path = _resolve_under_root(project_root, rel)
        if raw is None:
            try:
                if abs_path.exists():
                    abs_path.unlink()
            except Exception:
                pass
        else:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(raw)


def run_verify_command(
    *,
    project_root: Path,
    command: Sequence[str],
    timeout_seconds: int,
) -> Tuple[int, str, str]:
    if not command:
        raise SelfHealError("verify command is required")

    proc = subprocess.run(
        list(command),
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        shell=False,
    )
    return int(proc.returncode), proc.stdout or "", proc.stderr or ""


def run_self_heal_patch_loop(
    *,
    project_root: Path,
    run_id: str,
    artifacts_root: Path,
    patch_provider: PatchProvider,
    verify_command: Sequence[str],
    config: SelfHealConfig,
) -> SelfHealResult:
    """Strict opt-in self-healing loop.

    For each iteration:
    - fetch PatchSet
    - apply
    - run verify command
    - on failure: revert

    Writes per-iteration audit artifacts under:
      {artifacts_root}/{run_id}/self_heal/iter_{NN}/...
    """

    if not config.enabled:
        raise SelfHealDisabledError("Self-heal patch loop is disabled")

    if config.max_iterations <= 0:
        raise SelfHealError("max_iterations must be >= 1")

    project_root = project_root.resolve()
    base_dir = (artifacts_root / run_id / "self_heal").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    results: List[SelfHealIterationResult] = []

    for iteration in range(1, config.max_iterations + 1):
        patch_set = patch_provider(iteration)
        if patch_set is None or not patch_set.patches:
            break

        iter_dir = base_dir / f"iter_{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)

        proposed_diff = _combine_patch_diff(patch_set)
        _write_text(iter_dir / "proposed_patch_diff.txt", proposed_diff)
        _write_text(iter_dir / "proposed_patch_diff_sha256.txt", _sha256_text(proposed_diff))

        patched_files = [_ensure_repo_relative_path(p.file_path) for p in patch_set.patches]
        _write_json(iter_dir / "patched_files.json", patched_files)

        pre_hashes = _capture_hashes(project_root, patched_files)
        _write_json(iter_dir / "pre_hashes.json", pre_hashes)

        backups: Dict[str, Optional[bytes]] = {}
        applied = False
        reverted = False
        verify_exit_code = 1

        try:
            backups, touched = apply_patch_set(project_root=project_root, patch_set=patch_set, config=config)
            applied = True

            post_hashes = _capture_hashes(project_root, touched)
            _write_json(iter_dir / "post_hashes.json", post_hashes)

            _write_json(iter_dir / "verify_command.json", {"argv": list(verify_command)})
            verify_exit_code, stdout, stderr = run_verify_command(
                project_root=project_root,
                command=verify_command,
                timeout_seconds=config.verify_timeout_seconds,
            )
            _write_text(iter_dir / "verify_stdout.txt", stdout)
            _write_text(iter_dir / "verify_stderr.txt", stderr)
            _write_text(iter_dir / "verify_exit_code.txt", str(verify_exit_code))

            success = verify_exit_code == 0
            if not success:
                revert_patch_set(project_root=project_root, backups=backups)
                reverted = True

        except subprocess.TimeoutExpired:
            _write_text(iter_dir / "verify_exit_code.txt", "timeout")
            if applied:
                revert_patch_set(project_root=project_root, backups=backups)
                reverted = True
            success = False
            verify_exit_code = 124

        except Exception as e:
            _write_text(iter_dir / "error.txt", f"{type(e).__name__}: {e}\n")
            if applied:
                revert_patch_set(project_root=project_root, backups=backups)
                reverted = True
            success = False
            verify_exit_code = 2

        _write_json(
            iter_dir / "result.json",
            {
                "iteration": iteration,
                "applied": applied,
                "reverted": reverted,
                "verify_exit_code": verify_exit_code,
                "success": success,
                "timestamp": datetime.now().isoformat(),
            },
        )

        results.append(
            SelfHealIterationResult(
                iteration=iteration,
                applied=applied,
                reverted=reverted,
                verify_exit_code=verify_exit_code,
                success=success,
                artifacts_dir=str(iter_dir),
            )
        )

        if success:
            return SelfHealResult(success=True, iterations=results)

    return SelfHealResult(success=False, iterations=results)


def config_from_env() -> SelfHealConfig:
    enabled = os.getenv("CVA_SELF_HEAL_ENABLED", "false").lower() == "true"
    max_iterations = int(os.getenv("CVA_SELF_HEAL_MAX_ITERATIONS", "1"))
    max_files = int(os.getenv("CVA_SELF_HEAL_MAX_FILES", "10"))
    timeout = int(os.getenv("CVA_SELF_HEAL_VERIFY_TIMEOUT_SECONDS", "300"))
    return SelfHealConfig(
        enabled=enabled,
        max_iterations=max_iterations,
        max_files_per_iteration=max_files,
        verify_timeout_seconds=timeout,
    )


def default_verify_command_from_env() -> List[str]:
    cmd = (os.getenv("CVA_SELF_HEAL_VERIFY_CMD", "") or "").strip()
    if not cmd:
        return []
    # Very small parser: split on whitespace; users can pass argv-style via JSON in future.
    return cmd.split()
