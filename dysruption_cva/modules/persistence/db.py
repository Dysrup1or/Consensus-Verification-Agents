from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def _normalized_database_url(raw: str) -> str:
    """
    Normalize DATABASE_URL for SQLAlchemy async drivers.
    
    Behavior:
    - Production/Railway: REQUIRES DATABASE_URL, fails if missing
    - Local development: Falls back to SQLite with warning
    
    Raises:
        RuntimeError: If DATABASE_URL is missing in production/Railway
    """
    raw = (raw or "").strip()
    
    if not raw:
        # Check if we're in production or Railway
        is_production = os.getenv("CVA_PRODUCTION", "false").lower() == "true"
        is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT"))
        
        if is_production or is_railway:
            raise RuntimeError(
                "DATABASE_URL environment variable is required in production/Railway. "
                "Please link a PostgreSQL database to this service in Railway Dashboard, "
                "or set DATABASE_URL manually. "
                f"(CVA_PRODUCTION={is_production}, RAILWAY_ENVIRONMENT={os.getenv('RAILWAY_ENVIRONMENT', 'not_set')})"
            )
        
        # Local development: allow SQLite with warning
        logger.warning(
            "DATABASE_URL not set. Using SQLite for local development. "
            "This is NOT suitable for production - data will be lost on restart."
        )
        return "sqlite+aiosqlite:///./cva_dev.db"

    # Railway Postgres typically provides DATABASE_URL (postgresql://...).
    # For SQLAlchemy async driver we need postgresql+asyncpg://...
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    
    return raw


def _database_url_from_env() -> str:
    return _normalized_database_url(os.getenv("DATABASE_URL", ""))


_ENGINE: Optional[AsyncEngine] = None
_SESSIONMAKER: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_async_engine(
            _database_url_from_env(),
            echo=False,
            pool_pre_ping=True,
        )
    return _ENGINE


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _SESSIONMAKER
    if _SESSIONMAKER is None:
        _SESSIONMAKER = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SESSIONMAKER


async def reset_engine_for_tests(database_url: str) -> None:
    """Reset the global engine/sessionmaker.

    Useful for pytest where other tests may import modules.api early.
    """

    global _ENGINE, _SESSIONMAKER
    if _ENGINE is not None:
        await _ENGINE.dispose()
    _ENGINE = create_async_engine(
        _normalized_database_url(database_url),
        echo=False,
        pool_pre_ping=True,
    )
    _SESSIONMAKER = async_sessionmaker(bind=_ENGINE, expire_on_commit=False)


@asynccontextmanager
async def db_session() -> AsyncSession:
    async with get_sessionmaker()() as session:
        yield session
