from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dysruption_cva.modules.schemas import Patch
from dysruption_cva.modules.schemas import PatchSet
from dysruption_cva.modules.self_heal import SelfHealConfig
from dysruption_cva.modules.self_heal import SelfHealDisabledError
from dysruption_cva.modules.self_heal import run_self_heal_patch_loop


def _patch_set(*, rel_path: str, before: str, after: str) -> PatchSet:
    p = Patch(
        file_path=rel_path,
        original_content=before,
        patched_content=after,
        unified_diff=f"--- a/{rel_path}\n+++ b/{rel_path}\n@@\n-{before}+{after}",
        issues_addressed=[],
        confidence=0.5,
        requires_review=True,
        generated_by="test",
        generation_time_ms=0,
    )
    return PatchSet(patches=[p], total_issues_addressed=1)


def test_p4_1_disabled_by_default(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()

    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    def provider(_i: int):
        return _patch_set(rel_path="a.txt", before="old\n", after="new\n")

    with pytest.raises(SelfHealDisabledError):
        run_self_heal_patch_loop(
            project_root=project_root,
            run_id="r1",
            artifacts_root=artifacts_root,
            patch_provider=provider,
            verify_command=[sys.executable, "-c", "import sys; sys.exit(0)"],
            config=SelfHealConfig(enabled=False),
        )


def test_p4_1_apply_and_verify_success(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()

    target = project_root / "a.txt"
    target.write_text("old\n", encoding="utf-8")

    artifacts_root = tmp_path / "artifacts"
    run_id = "r2"

    def provider(i: int):
        assert i == 1
        return _patch_set(rel_path="a.txt", before="old\n", after="new\n")

    res = run_self_heal_patch_loop(
        project_root=project_root,
        run_id=run_id,
        artifacts_root=artifacts_root,
        patch_provider=provider,
        verify_command=[
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; sys.exit(0 if Path('a.txt').read_text()=='new\\n' else 1)",
        ],
        config=SelfHealConfig(enabled=True, max_iterations=1, max_files_per_iteration=3),
    )

    assert res.success is True
    assert target.read_text(encoding="utf-8") == "new\n"

    iter_dir = artifacts_root / run_id / "self_heal" / "iter_01"
    assert (iter_dir / "proposed_patch_diff.txt").exists()
    assert (iter_dir / "pre_hashes.json").exists()
    assert (iter_dir / "post_hashes.json").exists()
    assert (iter_dir / "verify_exit_code.txt").read_text(encoding="utf-8").strip() == "0"


def test_p4_1_revert_on_verify_failure(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()

    target = project_root / "a.txt"
    target.write_text("old\n", encoding="utf-8")

    artifacts_root = tmp_path / "artifacts"
    run_id = "r3"

    def provider(i: int):
        assert i == 1
        return _patch_set(rel_path="a.txt", before="old\n", after="new\n")

    res = run_self_heal_patch_loop(
        project_root=project_root,
        run_id=run_id,
        artifacts_root=artifacts_root,
        patch_provider=provider,
        verify_command=[sys.executable, "-c", "import sys; sys.exit(1)"],
        config=SelfHealConfig(enabled=True, max_iterations=1, max_files_per_iteration=3),
    )

    assert res.success is False
    assert target.read_text(encoding="utf-8") == "old\n"

    iter_dir = artifacts_root / run_id / "self_heal" / "iter_01"
    assert (iter_dir / "result.json").exists()
    assert (iter_dir / "verify_exit_code.txt").read_text(encoding="utf-8").strip() == "1"
