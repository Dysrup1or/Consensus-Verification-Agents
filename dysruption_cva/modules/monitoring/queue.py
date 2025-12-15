from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select

from modules.persistence.db import db_session
from modules.persistence.models import MonitorJob, RepoBranch, RepoConnection


async def enqueue_job(*, repo_branch_id: str, commit_sha: str, event_type: str) -> MonitorJob:
    async with db_session() as session:
        job = MonitorJob(
            id=str(uuid.uuid4()),
            repo_branch_id=repo_branch_id,
            commit_sha=commit_sha,
            event_type=event_type,
            status="queued",
            attempts=0,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def claim_next_job(*, worker_id: str) -> Optional[MonitorJob]:
    """Best-effort job claim.

    SQLite doesn't support SKIP LOCKED; this is a simple "first queued" claim.
    """

    async with db_session() as session:
        result = await session.execute(
            select(MonitorJob)
            .where(MonitorJob.status == "queued")
            .order_by(MonitorJob.created_at.asc())
            .limit(1)
        )
        job = result.scalars().first()
        if job is None:
            return None

        job.status = "running"
        job.attempts = int(job.attempts or 0) + 1
        job.locked_at = datetime.utcnow()
        job.locked_by = worker_id

        await session.commit()
        await session.refresh(job)
        return job


async def mark_job_completed(job_id: str, *, run_id: Optional[str] = None) -> None:
    async with db_session() as session:
        job = await session.get(MonitorJob, job_id)
        if job is None:
            return
        job.status = "completed"
        if run_id:
            job.run_id = run_id
        await session.commit()


async def mark_job_failed(job_id: str, *, error: str) -> None:
    async with db_session() as session:
        job = await session.get(MonitorJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.last_error = (error or "")[:2000]
        await session.commit()


async def get_branch_context(repo_branch_id: str) -> tuple[RepoBranch, RepoConnection]:
    async with db_session() as session:
        branch = await session.get(RepoBranch, repo_branch_id)
        if branch is None:
            raise KeyError("branch_not_found")
        conn = await session.get(RepoConnection, branch.repo_connection_id)
        if conn is None:
            raise KeyError("repo_connection_not_found")
        return branch, conn
