import os

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_apply_migrations_smoke():
    # This test is intentionally opt-in so local dev/CI without Postgres doesn't fail.
    if os.getenv("DATABASE_URL") is None:
        pytest.skip("DATABASE_URL not set; skipping Postgres migration smoke test")

    # Ensure we don't accidentally change local DB unless explicitly intended.
    if os.getenv("CVA_APPLY_MIGRATIONS", "false").lower() != "true":
        pytest.skip("CVA_APPLY_MIGRATIONS not true; skipping")

    from modules.persistence.migrations import apply_migrations
    from modules.persistence.db import ENGINE

    applied = await apply_migrations()
    assert applied >= 0

    async with ENGINE.begin() as conn:
        # Check that the migrations table exists and at least the initial schema is present.
        result = await conn.execute(
            text(
                "SELECT to_regclass('public.schema_migrations') IS NOT NULL AS ok"
            )
        )
        assert result.scalar() is True

        result = await conn.execute(text("SELECT to_regclass('public.runs') IS NOT NULL AS ok"))
        assert result.scalar() is True
