from __future__ import annotations

from dysruption_cva.modules.ts_imports import extract_js_ts_details
from dysruption_cva.modules.ts_imports import get_tree_sitter_status


def test_tree_sitter_status_probe_is_explicit_and_consistent() -> None:
    status = get_tree_sitter_status()
    assert isinstance(status.available, bool)
    assert isinstance(status.reason, str)
    assert status.reason

    src = "export function add(a: number, b: number) { return a + b }\n"
    details = extract_js_ts_details("src/x.ts", src)

    # If Tree-sitter is available, extraction should report it.
    # If not, we must explicitly be in fallback mode with a warning.
    if status.available:
        assert details.used_tree_sitter is True
        assert details.warnings == []
    else:
        assert details.used_tree_sitter is False
        assert "tree_sitter_unavailable" in details.warnings
