from __future__ import annotations

import json
from pathlib import Path

from dysruption_cva.modules.dependency_resolver import ResolverConfig
from dysruption_cva.modules.dependency_resolver import resolve_dependencies


def test_phase2_tsconfig_paths_alias_resolves_repo_local_imports(tmp_path: Path) -> None:
    root = tmp_path

    (root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "baseUrl": ".",
                    "paths": {"@/*": ["src/*"]},
                }
            }
        ),
        encoding="utf-8",
    )

    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "foo.ts").write_text("export const foo = 1;\n", encoding="utf-8")
    (root / "src" / "main.ts").write_text(
        "import { foo } from \"@/foo\";\nexport const x = foo;\n",
        encoding="utf-8",
    )

    res = resolve_dependencies(root, ["src/main.ts"], depth=1, max_files=50, config=ResolverConfig(max_file_bytes=256 * 1024))
    assert "src/foo.ts" in res.resolved_files


def test_phase2_tsconfig_baseurl_resolves_bare_specifiers(tmp_path: Path) -> None:
    root = tmp_path

    (root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "baseUrl": "src",
                }
            }
        ),
        encoding="utf-8",
    )

    (root / "src" / "lib").mkdir(parents=True, exist_ok=True)
    (root / "src" / "lib" / "util.ts").write_text("export const util = 1;\n", encoding="utf-8")
    (root / "src" / "main.ts").write_text(
        "import { util } from \"lib/util\";\nexport const x = util;\n",
        encoding="utf-8",
    )

    res = resolve_dependencies(root, ["src/main.ts"], depth=1, max_files=50, config=ResolverConfig(max_file_bytes=256 * 1024))
    assert "src/lib/util.ts" in res.resolved_files
