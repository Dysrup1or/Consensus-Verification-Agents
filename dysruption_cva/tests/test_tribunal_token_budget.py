from pathlib import Path

from modules.file_manager import build_llm_context


def test_token_budget_truncates_and_sets_partial(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()

    big = "A" * 50_000
    (root / "changed.py").write_text(big, encoding="utf-8")

    ctx = build_llm_context(
        root,
        changed_files=["changed.py"],
        import_files=[],
        constitution_text="B" * 50_000,
        token_budget=500,  # intentionally tiny
    )

    assert ctx.partial is True
    assert "changed.py" in ctx.truncated_files or "__constitution__" in ctx.truncated_files
    assert ctx.token_count <= 500
