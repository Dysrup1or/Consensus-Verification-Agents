from __future__ import annotations

from pathlib import Path

from dysruption_cva.modules.file_manager import plan_context


def test_p2_2_forced_files_are_explicit_and_auditable(tmp_path: Path) -> None:
    root = tmp_path
    (root / "src").mkdir(parents=True, exist_ok=True)

    (root / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")

    changed = ["src/a.py", "src/b.py"]

    plan_forced = plan_context(
        root,
        changed_files=changed,
        import_files=[],
        forced_files=["src/b.py"],
        constitution_text="",
        token_budget=8_000,
    )

    by_path = {i.rel_path: i for i in plan_forced.items}
    assert by_path["src/b.py"].planned_tier in {"full", "slice"}
    assert by_path["src/b.py"].planned_reason.startswith("forced_")

    plan_not_forced = plan_context(
        root,
        changed_files=changed,
        import_files=[],
        forced_files=[],
        constitution_text="",
        token_budget=8_000,
    )
    by_path2 = {i.rel_path: i for i in plan_not_forced.items}
    assert not by_path2["src/b.py"].planned_reason.startswith("forced_")
