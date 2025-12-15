from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from datetime import datetime
import json

from loguru import logger

from modules.judge_engine import default_min_constitution
from modules.monitoring.github_zipball import download_and_extract_zipball
from modules.monitoring.queue import claim_next_job, get_branch_context, mark_job_completed, mark_job_failed
from modules.persistence.config_store import create_constitution_version, get_latest_constitution
from modules.persistence.run_store import create_run_record


def _worker_id() -> str:
    return os.getenv("CVA_WORKER_ID") or f"worker-{uuid.uuid4().hex[:8]}"


def _monitor_root() -> Path:
    upload_root = Path(os.getenv("CVA_UPLOAD_ROOT", str(Path(os.getcwd()) / "temp_uploads")))
    return Path(os.getenv("CVA_MONITOR_ROOT", str(upload_root / "monitor")))


async def _prepare_snapshot(*, repo_full_name: str, commit_sha: str, constitution_text: str, installation_id: int | None) -> Path:
    dest = (_monitor_root() / repo_full_name.replace("/", "__") / commit_sha[:12]).resolve()
    if dest.exists():
        return dest

    await download_and_extract_zipball(
        repo_full_name=repo_full_name,
        ref=commit_sha,
        dest_dir=dest,
        installation_id=installation_id,
    )

    tribunal_dir = (dest / ".tribunal").resolve()
    tribunal_dir.mkdir(parents=True, exist_ok=True)
    (tribunal_dir / "constitution.md").write_text(constitution_text, encoding="utf-8")

    return dest


async def run_monitor_worker_loop() -> None:
    if os.getenv("CVA_MONITOR_WORKER", "false").lower() != "true":
        logger.info("Monitor worker disabled (set CVA_MONITOR_WORKER=true to enable)")
        return

    poll_seconds = float(os.getenv("CVA_MONITOR_POLL_SECONDS", "2"))
    worker_id = _worker_id()

    logger.info(f"Monitor worker starting (id={worker_id}, poll={poll_seconds}s)")

    while True:
        try:
            job = await claim_next_job(worker_id=worker_id)
            if job is None:
                await asyncio.sleep(poll_seconds)
                continue

            try:
                branch, conn = await get_branch_context(job.repo_branch_id)
                if not branch.is_monitored:
                    await mark_job_completed(job.id, run_id=None)
                    continue

                latest_const = await get_latest_constitution(branch.id)
                if latest_const is None:
                    latest_const = await create_constitution_version(branch.id, default_min_constitution())

                constitution_text = latest_const.content

                snapshot_dir = await _prepare_snapshot(
                    repo_full_name=conn.repo_full_name,
                    commit_sha=job.commit_sha,
                    constitution_text=constitution_text,
                    installation_id=conn.installation_id,
                )

                # Start a regular /run-style pipeline against the snapshot.
                from modules.api import RunConfig, RunState, _runs, run_verification_pipeline

                run_id = str(uuid.uuid4())[:8]
                started_at = datetime.utcnow()
                config = RunConfig(
                    target_dir=str(snapshot_dir),
                    spec_path="spec.txt",
                    spec_content=constitution_text,
                    config_path="config.yaml",
                    generate_patches=False,
                    watch_mode=False,
                )
                _runs[run_id] = RunState(run_id, config)

                await run_verification_pipeline(run_id)
                finished_at = datetime.utcnow()

                # Best-effort verdict extraction from artifacts.
                verdict_value = None
                error_value = None
                try:
                    verdict_path = getattr(_runs.get(run_id), "verdict_path", None)
                    if verdict_path and Path(verdict_path).exists():
                        data = json.loads(Path(verdict_path).read_text(encoding="utf-8"))
                        verdict_value = data.get("overall_verdict") or data.get("verdict")
                except Exception as exc:
                    error_value = f"verdict_parse_error:{exc}"

                await create_run_record(
                    repo_branch_id=branch.id,
                    constitution_version_id=latest_const.id,
                    commit_sha=job.commit_sha,
                    event_type=job.event_type,
                    status="completed",
                    verdict=str(verdict_value) if verdict_value is not None else None,
                    error=error_value,
                    started_at=started_at,
                    finished_at=finished_at,
                )
                await mark_job_completed(job.id, run_id=run_id)

            except Exception as exc:
                logger.exception("Monitor job failed")
                await mark_job_failed(job.id, error=str(exc))

        except Exception:
            logger.exception("Monitor worker loop error")
            await asyncio.sleep(max(1.0, poll_seconds))
