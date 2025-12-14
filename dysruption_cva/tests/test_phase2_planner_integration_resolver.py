from __future__ import annotations

from pathlib import Path

from dysruption_cva.modules.file_manager import plan_context


def test_p2_4_planner_includes_repo_local_dependency_and_centrality(tmp_path: Path) -> None:
    root = tmp_path
    (root / "src").mkdir(parents=True, exist_ok=True)

    (root / "src" / "dep.py").write_text("def dep():\n    return 1\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("import src.dep\n\n# touch\n", encoding="utf-8")

    plan = plan_context(
        root,
        changed_files=["src/main.py"],
        import_files=[],
        forced_files=[],
        constitution_text="",
        token_budget=8_000,
    )

    paths = {i.rel_path for i in plan.items}
    assert "src/dep.py" in paths

    dep_item = next(i for i in plan.items if i.rel_path == "src/dep.py")
    # Dependency should at least be planned for header coverage.
    assert dep_item.planned_tier in {"header", "full", "slice"}
