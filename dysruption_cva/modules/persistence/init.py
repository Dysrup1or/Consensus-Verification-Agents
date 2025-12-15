from __future__ import annotations

from loguru import logger

from .db import get_engine
from .models import Base


async def ensure_sqlite_schema() -> None:
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SQLite schema ensured")
