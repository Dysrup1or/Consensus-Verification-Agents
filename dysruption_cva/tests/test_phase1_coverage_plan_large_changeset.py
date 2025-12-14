from __future__ import annotations

from pathlib import Path

from dysruption_cva.modules.file_manager import build_llm_context


def test_phase1_large_changeset_keeps_broad_header_coverage(tmp_path: Path) -> None:
    # Build a tiny repo-ish tree with many changed files so we can catch regressions
    # where the LLM context collapses to only a handful of files under budget.
    root = tmp_path

    changed_files: list[str] = []
    for i in range(150):
        rel = f"src/file_{i:03d}.py"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(
            "\n".join(
                [
                    f"\"\"\"file {i}\"\"\"",
                    "import os",
                    "import sys",
                    "",
                    f"def f_{i}():",
                    f"    return {i}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        changed_files.append(rel)

    # Keep imports empty; Phase 1 should at least include headers for most changed files.
    ctx = build_llm_context(
        root,
        changed_files=changed_files,
        import_files=[],
        token_budget=8_000,
        max_file_bytes=256 * 1024,
        constitution_text="",
    )

    assert ctx.changed_files_total == 150
    # Guardrail: at least 90% of changed files should be represented in some form.
    covered = sum(
        1
        for rel in changed_files
        if ctx.coverage_kinds.get(rel) in {"header", "slice", "full"}
    )
    assert covered / len(changed_files) >= 0.90

    # If anything isn't covered, we should have an explicit reason.
    for rel in changed_files:
        if rel not in ctx.coverage_kinds:
            assert rel in ctx.skip_reasons
