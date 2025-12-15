from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select

from .db import db_session
from .models import ConstitutionVersion, RepoBranch, RepoConnection, User


SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


async def ensure_system_user() -> str:
    async with db_session() as session:
        existing = await session.get(User, SYSTEM_USER_ID)
        if existing is not None:
            return SYSTEM_USER_ID

        system = User(id=SYSTEM_USER_ID, email=None)
        session.add(system)
        await session.commit()
        return SYSTEM_USER_ID


@dataclass(frozen=True)
class CreateRepoConnectionInput:
    provider: str
    repo_full_name: str
    default_branch: str
    installation_id: Optional[int] = None
    user_id: Optional[str] = None


async def create_repo_connection(inp: CreateRepoConnectionInput) -> RepoConnection:
    user_id = inp.user_id or await ensure_system_user()

    async with db_session() as session:
        # Idempotent upsert behavior: if this user already connected this repo,
        # update its default_branch/installation_id instead of creating duplicates.
        existing_result = await session.execute(
            select(RepoConnection).where(
                RepoConnection.provider == inp.provider,
                RepoConnection.repo_full_name == inp.repo_full_name,
                RepoConnection.user_id == user_id,
            )
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            existing.default_branch = inp.default_branch
            existing.installation_id = inp.installation_id
            await session.commit()
            await session.refresh(existing)
            return existing

        conn = RepoConnection(
            id=str(uuid.uuid4()),
            user_id=user_id,
            provider=inp.provider,
            repo_full_name=inp.repo_full_name,
            default_branch=inp.default_branch,
            installation_id=inp.installation_id,
        )
        session.add(conn)
        await session.commit()
        await session.refresh(conn)
        return conn


async def list_repo_connections() -> list[RepoConnection]:
    async with db_session() as session:
        result = await session.execute(select(RepoConnection).order_by(RepoConnection.created_at.desc()))
        return list(result.scalars().all())


async def get_repo_connection_by_full_name(*, provider: str, repo_full_name: str) -> Optional[RepoConnection]:
    async with db_session() as session:
        result = await session.execute(
            select(RepoConnection).where(
                RepoConnection.provider == provider,
                RepoConnection.repo_full_name == repo_full_name,
            )
        )
        return result.scalars().first()


async def get_branch_by_name(*, repo_connection_id: str, branch: str) -> Optional[RepoBranch]:
    async with db_session() as session:
        result = await session.execute(
            select(RepoBranch).where(
                RepoBranch.repo_connection_id == repo_connection_id,
                RepoBranch.branch == branch,
            )
        )
        return result.scalars().first()


async def create_or_get_branch(*, repo_connection_id: str, branch: str, is_monitored: bool = True) -> RepoBranch:
    async with db_session() as session:
        result = await session.execute(
            select(RepoBranch).where(
                RepoBranch.repo_connection_id == repo_connection_id,
                RepoBranch.branch == branch,
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            return existing

        rb = RepoBranch(
            id=str(uuid.uuid4()),
            repo_connection_id=repo_connection_id,
            branch=branch,
            is_monitored=is_monitored,
        )
        session.add(rb)
        await session.commit()
        await session.refresh(rb)
        return rb


async def list_branches(repo_connection_id: str) -> list[RepoBranch]:
    async with db_session() as session:
        result = await session.execute(
            select(RepoBranch)
            .where(RepoBranch.repo_connection_id == repo_connection_id)
            .order_by(RepoBranch.created_at.desc())
        )
        return list(result.scalars().all())


async def set_branch_monitoring(repo_branch_id: str, is_monitored: bool) -> RepoBranch:
    async with db_session() as session:
        rb = await session.get(RepoBranch, repo_branch_id)
        if rb is None:
            raise KeyError("branch_not_found")
        rb.is_monitored = is_monitored
        await session.commit()
        await session.refresh(rb)
        return rb


async def create_constitution_version(repo_branch_id: str, content: str) -> ConstitutionVersion:
    async with db_session() as session:
        result = await session.execute(
            select(func.max(ConstitutionVersion.version)).where(ConstitutionVersion.repo_branch_id == repo_branch_id)
        )
        max_version = result.scalar_one_or_none() or 0

        cv = ConstitutionVersion(
            id=str(uuid.uuid4()),
            repo_branch_id=repo_branch_id,
            version=int(max_version) + 1,
            content=content,
        )
        session.add(cv)
        await session.commit()
        await session.refresh(cv)
        return cv


async def get_latest_constitution(repo_branch_id: str) -> Optional[ConstitutionVersion]:
    async with db_session() as session:
        result = await session.execute(
            select(ConstitutionVersion)
            .where(ConstitutionVersion.repo_branch_id == repo_branch_id)
            .order_by(ConstitutionVersion.version.desc())
            .limit(1)
        )
        return result.scalars().first()
