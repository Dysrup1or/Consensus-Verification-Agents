from pathlib import Path

from modules.file_manager import resolve_imports


def test_resolve_imports_depth_2(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)

    (root / "main.py").write_text("import pkg.mod\n", encoding="utf-8")
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "mod.py").write_text("from pkg import sub\n", encoding="utf-8")
    (root / "pkg" / "sub.py").write_text("VALUE = 1\n", encoding="utf-8")

    res = resolve_imports(root, ["main.py"], depth=2)

    assert "pkg/mod.py" in res.resolved_files
    # depth=2 should reach sub.py (main -> mod -> sub)
    assert "pkg/sub.py" in res.resolved_files
