from pathlib import Path

from modules.file_manager import detect_changed_files


def test_detect_changed_files_mtime_fallback(tmp_path: Path):
    # No git repo => mtime detection
    project_root = tmp_path / "proj"
    project_root.mkdir()

    (project_root / "a.py").write_text("print('hi')\n", encoding="utf-8")

    res = detect_changed_files(project_root, "diff", mtime_window_seconds=3600)

    assert res.detection in {"mtime", "git"}
    assert "a.py" in res.changed_files
