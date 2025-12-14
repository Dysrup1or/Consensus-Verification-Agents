from __future__ import annotations

import json
from pathlib import Path

from dysruption_cva.modules.dependency_resolver import ResolverConfig
from dysruption_cva.modules.dependency_resolver import resolve_dependencies


def test_p2_1_python_relative_and_absolute_imports(tmp_path: Path) -> None:
    root = tmp_path
    (root / "pkg").mkdir(parents=True, exist_ok=True)

    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "util.py").write_text("def u():\n    return 1\n", encoding="utf-8")
    (root / "main.py").write_text("from pkg import util\nfrom .pkg import util as u2\n", encoding="utf-8")

    res = resolve_dependencies(
        root,
        ["main.py"],
        depth=2,
        max_files=50,
        config=ResolverConfig(max_file_bytes=256 * 1024),
    )

    assert "pkg/util.py" in res.resolved_files
    assert isinstance(res.diagnostics, dict)
    assert res.diagnostics.get("imports_seen", 0) >= 1


def test_p2_1_js_ts_relative_imports(tmp_path: Path) -> None:
    root = tmp_path
    (root / "src").mkdir(parents=True, exist_ok=True)

    (root / "src" / "dep.ts").write_text("export const x = 1\n", encoding="utf-8")
    (root / "src" / "main.ts").write_text("import { x } from './dep'\nexport { x }\n", encoding="utf-8")

    res = resolve_dependencies(
        root,
        ["src/main.ts"],
        depth=2,
        max_files=50,
        config=ResolverConfig(max_file_bytes=256 * 1024),
    )

    assert "src/dep.ts" in res.resolved_files


def test_p2_1_repo_root_safety(tmp_path: Path) -> None:
    root = tmp_path
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "main.ts").write_text("import x from '../secrets'\n", encoding="utf-8")

    res = resolve_dependencies(
        root,
        ["src/main.ts"],
        depth=1,
        max_files=20,
        config=ResolverConfig(max_file_bytes=256 * 1024),
    )

    # Must not resolve outside the repo; should be treated as missing.
    assert res.resolved_files == []
    assert "../secrets" in res.skipped_imports


def test_p2_3_workspaces_resolve_internal_package(tmp_path: Path) -> None:
    root = tmp_path

    (root / "package.json").write_text(
        json.dumps({"workspaces": ["packages/*"]}),
        encoding="utf-8",
    )

    (root / "packages" / "pkg-a" / "src").mkdir(parents=True, exist_ok=True)
    (root / "packages" / "pkg-a" / "package.json").write_text(
        json.dumps({"name": "pkg-a", "main": "src/index.ts"}),
        encoding="utf-8",
    )
    (root / "packages" / "pkg-a" / "src" / "index.ts").write_text("export const a = 1\n", encoding="utf-8")

    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "main.ts").write_text("import { a } from 'pkg-a'\nexport { a }\n", encoding="utf-8")

    res = resolve_dependencies(
        root,
        ["src/main.ts"],
        depth=2,
        max_files=50,
        config=ResolverConfig(max_file_bytes=256 * 1024, enable_workspaces=True),
    )

    assert "packages/pkg-a/src/index.ts" in res.resolved_files
