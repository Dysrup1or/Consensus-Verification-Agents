"""SQLite-backed coverage tracking for Tribunal API.

Purpose:
- Track which files have been included in model-assisted (Lane 2/3) checks.
- Allow future runs to boost risk for previously-uncovered changed files.

This is intentionally lightweight and local (no network calls).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class CoverageRow:
    project_id: str
    rel_path: str
    coverage_kind: str  # full|header|slice
    last_covered_at: int
    last_run_id: str


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_coverage (
                project_id TEXT NOT NULL,
                rel_path TEXT NOT NULL,
                coverage_kind TEXT NOT NULL,
                last_covered_at INTEGER NOT NULL,
                last_run_id TEXT NOT NULL,
                PRIMARY KEY (project_id, rel_path)
            )
            """
        )
        conn.commit()


def get_coverage_map(db_path: Path, project_id: str) -> Dict[str, CoverageRow]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(
            "SELECT project_id, rel_path, coverage_kind, last_covered_at, last_run_id FROM file_coverage WHERE project_id = ?",
            (project_id,),
        )
        out: Dict[str, CoverageRow] = {}
        for row in cur.fetchall():
            r = CoverageRow(
                project_id=row[0],
                rel_path=row[1],
                coverage_kind=row[2],
                last_covered_at=int(row[3]),
                last_run_id=row[4],
            )
            out[r.rel_path] = r
        return out


def upsert_coverage(
    db_path: Path,
    *,
    project_id: str,
    run_id: str,
    rel_paths: Iterable[str],
    coverage_kind: str,
    now_ts: Optional[int] = None,
) -> None:
    init_db(db_path)
    ts = int(now_ts if now_ts is not None else time.time())
    with sqlite3.connect(str(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO file_coverage (project_id, rel_path, coverage_kind, last_covered_at, last_run_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, rel_path) DO UPDATE SET
                coverage_kind=excluded.coverage_kind,
                last_covered_at=excluded.last_covered_at,
                last_run_id=excluded.last_run_id
            """,
            [(project_id, rel, coverage_kind, ts, run_id) for rel in rel_paths],
        )
        conn.commit()
