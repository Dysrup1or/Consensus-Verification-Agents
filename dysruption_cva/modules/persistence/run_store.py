from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from modules.persistence.db import db_session
from modules.persistence.models import ConstitutionVersion, Run


async def create_run_record(
    *,
    repo_branch_id: str,
    constitution_version_id: str,
    commit_sha: str,
    event_type: str,
    status: str,
    verdict: Optional[str],
    error: Optional[str],
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> Run:
    async with db_session() as session:
        run = Run(
            id=str(uuid.uuid4()),
            repo_branch_id=repo_branch_id,
            constitution_version_id=constitution_version_id,
            commit_sha=commit_sha,
            event_type=event_type,
            status=status,
            verdict=verdict,
            started_at=started_at,
            finished_at=finished_at,
            error=error,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def list_runs_for_branch(repo_branch_id: str, limit: int = 50) -> list[Run]:
    async with db_session() as session:
        result = await session.execute(
            select(Run)
            .where(Run.repo_branch_id == repo_branch_id)
            .order_by(Run.created_at.desc())
            .limit(int(limit))
        )
        return list(result.scalars().all())
