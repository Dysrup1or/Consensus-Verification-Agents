from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from loguru import logger
from sqlalchemy import text

from .db import get_engine


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def _project_root() -> Path:
    # NOTE:
    # - Local dev path often looks like: <repo>/dysruption_cva/modules/persistence/migrations.py
    # - Railway may set the service root to dysruption_cva, so the path is: /app/modules/persistence/migrations.py
    # A fixed parents[N] assumption breaks in the Railway layout.
    return Path(__file__).resolve().parent


def _migrations_dir() -> Path:
    configured = (os.getenv("CVA_MIGRATIONS_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    here = Path(__file__).resolve()

    # Prefer migrations shipped alongside the backend service (works when Railway root is dysruption_cva).
    # <service-root>/modules/persistence/migrations.py -> <service-root>/db/migrations
    service_root = here.parents[2] if len(here.parents) >= 3 else here.parent
    candidate = (service_root / "db" / "migrations").resolve()
    if candidate.exists():
        return candidate

    # Fallback: search upwards for a repo-root db/migrations.
    for parent in here.parents:
        candidate = (parent / "db" / "migrations").resolve()
        if candidate.exists():
            return candidate

    # Last resort: return the service-root candidate path (will log as missing).
    return (service_root / "db" / "migrations").resolve()


_FILENAME_RE = re.compile(r"^(?P<version>\d{3,})_(?P<name>.+)\.sql$")


def _list_migrations() -> List[Migration]:
    migrations_dir = _migrations_dir()
    if not migrations_dir.exists():
        return []

    migrations: List[Migration] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _FILENAME_RE.match(path.name)
        if not match:
            continue
        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=match.group("name"),
                path=path,
            )
        )

    migrations.sort(key=lambda m: m.version)
    return migrations


def _split_sql(sql: str) -> Iterable[str]:
    # Minimal splitter good enough for simple migration scripts.
    # Avoids executing empty statements and strips leading comments/whitespace.
    parts = [p.strip() for p in sql.split(";")]
    for part in parts:
        if not part:
            continue
        yield part


async def apply_migrations() -> int:
    migrations = _list_migrations()
    if not migrations:
        logger.info(f"No migrations found (dir={_migrations_dir()})")
        return 0

    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  name TEXT NOT NULL,
                  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        result = await conn.execute(text("SELECT version FROM schema_migrations"))
        applied_versions = {int(row[0]) for row in result.fetchall()}

        applied_count = 0
        for migration in migrations:
            if migration.version in applied_versions:
                continue

            sql = migration.path.read_text(encoding="utf-8")
            logger.info(f"Applying migration {migration.version}_{migration.name}")

            for statement in _split_sql(sql):
                await conn.execute(text(statement))

            await conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, name) VALUES (:v, :n)"
                ),
                {"v": migration.version, "n": migration.name},
            )
            applied_count += 1

        return applied_count


async def apply_migrations_if_configured() -> None:
    if os.getenv("CVA_APPLY_MIGRATIONS", "false").lower() != "true":
        return

    try:
        applied = await apply_migrations()
        logger.info(f"Migrations applied: {applied}")
    except Exception as exc:
        # Fail fast; better to crash at boot than run with unknown schema.
        logger.exception("Failed applying migrations")
        raise
