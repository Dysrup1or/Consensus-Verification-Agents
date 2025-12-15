from __future__ import annotations

import io
import os
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger


class GitHubDownloadError(RuntimeError):
    pass


def _sanitize_repo_full_name(repo_full_name: str) -> str:
    repo_full_name = (repo_full_name or "").strip()
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo_full_name):
        raise GitHubDownloadError("Invalid repo_full_name")
    return repo_full_name


def _github_token() -> str:
    token = (os.getenv("CVA_GITHUB_TOKEN") or "").strip()
    if not token:
        raise GitHubDownloadError("CVA_GITHUB_TOKEN is required for continuous monitoring")
    return token


async def _resolve_github_bearer_token(*, installation_id: Optional[int]) -> str:
    """Resolve an auth token for GitHub API requests.

    Preference order:
      1) GitHub App installation token when installation_id is provided and App env is configured
      2) CVA_GITHUB_TOKEN (legacy/admin mode)
    """

    if installation_id is not None:
        try:
            from modules.monitoring.github_app_auth import get_installation_access_token, is_github_app_configured

            if is_github_app_configured():
                return await get_installation_access_token(installation_id=int(installation_id))
        except Exception as exc:
            logger.warning(f"GitHub App installation token unavailable; falling back to CVA_GITHUB_TOKEN. {exc}")

    return _github_token()


async def download_and_extract_zipball(
    *,
    repo_full_name: str,
    ref: str,
    dest_dir: Path,
    installation_id: Optional[int] = None,
    max_bytes: int = 150 * 1024 * 1024,
) -> None:
    """Download GitHub zipball and extract into dest_dir.

    Uses GitHub App installation tokens when installation_id is provided; otherwise falls back to CVA_GITHUB_TOKEN.
    """

    repo_full_name = _sanitize_repo_full_name(repo_full_name)
    ref = (ref or "").strip() or "HEAD"

    dest_dir.mkdir(parents=True, exist_ok=True)

    url = f"https://api.github.com/repos/{repo_full_name}/zipball/{ref}"

    bearer_token = await _resolve_github_bearer_token(installation_id=installation_id)
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "cva-monitor/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    logger.info(f"Downloading zipball {repo_full_name}@{ref}")

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise GitHubDownloadError(f"GitHub zipball fetch failed: {resp.status_code}: {resp.text[:500]}")

        content = resp.content
        if len(content) > max_bytes:
            raise GitHubDownloadError(f"Zipball too large ({len(content)} bytes)")

    # Zipball is a zip containing a single top-level folder.
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        members = zf.infolist()
        if not members:
            raise GitHubDownloadError("Empty zipball")

        top_prefix = members[0].filename.split("/")[0]
        for zi in members:
            name = zi.filename
            if not name or name.endswith("/"):
                continue
            if not name.startswith(top_prefix + "/"):
                # Unexpected; still extract conservatively.
                rel = name
            else:
                rel = name[len(top_prefix) + 1 :]

            rel = rel.strip().lstrip("/\\")
            if not rel or rel.startswith(".."):
                continue

            out_path = (dest_dir / rel).resolve()
            if not str(out_path).startswith(str(dest_dir.resolve())):
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(zi) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
