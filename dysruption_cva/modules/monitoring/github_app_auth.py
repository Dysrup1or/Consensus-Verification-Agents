from __future__ import annotations

import asyncio
import base64
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger


class GitHubAppAuthError(RuntimeError):
    pass


def _github_app_id() -> int:
    raw = (os.getenv("CVA_GITHUB_APP_ID") or "").strip()
    if not raw:
        raise GitHubAppAuthError("CVA_GITHUB_APP_ID is required for GitHub App authentication")
    try:
        return int(raw)
    except Exception:
        raise GitHubAppAuthError("CVA_GITHUB_APP_ID must be an integer")


def _load_private_key_pem() -> str:
    b64 = (os.getenv("CVA_GITHUB_APP_PRIVATE_KEY_B64") or "").strip()
    if b64:
        try:
            return base64.b64decode(b64.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            raise GitHubAppAuthError(f"Failed to decode CVA_GITHUB_APP_PRIVATE_KEY_B64: {exc}")

    pem = (os.getenv("CVA_GITHUB_APP_PRIVATE_KEY") or "").strip()
    if not pem:
        raise GitHubAppAuthError(
            "Missing GitHub App private key. Set CVA_GITHUB_APP_PRIVATE_KEY (PEM) or CVA_GITHUB_APP_PRIVATE_KEY_B64."
        )
    return pem


def is_github_app_configured() -> bool:
    return bool((os.getenv("CVA_GITHUB_APP_ID") or "").strip()) and bool(
        (os.getenv("CVA_GITHUB_APP_PRIVATE_KEY") or "").strip() or (os.getenv("CVA_GITHUB_APP_PRIVATE_KEY_B64") or "").strip()
    )


def _mint_app_jwt(*, ttl_seconds: int = 540) -> str:
    """Mint GitHub App JWT used to create installation access tokens.

    GitHub requires an RS256 JWT with:
      - iss: GitHub App ID
      - iat: current time
      - exp: <= 10 minutes in the future
    """

    import jwt

    now = int(time.time())
    payload = {
        "iat": now - 30,
        "exp": now + int(ttl_seconds),
        "iss": _github_app_id(),
    }

    private_key = _load_private_key_pem()
    return jwt.encode(payload, private_key, algorithm="RS256")


@dataclass(frozen=True)
class _CachedInstallationToken:
    token: str
    expires_at_epoch: float


_cache_lock = asyncio.Lock()
_installation_token_cache: dict[int, _CachedInstallationToken] = {}


def _parse_expires_at(expires_at: str) -> float:
    if not expires_at:
        raise GitHubAppAuthError("GitHub returned empty expires_at")

    raw = expires_at.strip()
    # GitHub returns ISO8601 like 2025-12-15T00:00:00Z
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.timestamp()


async def get_installation_access_token(*, installation_id: int) -> str:
    """Return a short-lived installation token, cached until expiry."""

    if not isinstance(installation_id, int) or installation_id <= 0:
        raise GitHubAppAuthError("installation_id must be a positive integer")

    now = time.time()

    async with _cache_lock:
        cached = _installation_token_cache.get(installation_id)
        if cached and cached.expires_at_epoch > (now + 30):
            return cached.token

    app_jwt = _mint_app_jwt()
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cva-github-app/1.0",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.post(url, headers=headers)

    if resp.status_code >= 400:
        raise GitHubAppAuthError(f"GitHub installation token mint failed: {resp.status_code}: {resp.text[:500]}")

    payload = resp.json() if resp.content else {}
    token = (payload.get("token") or "").strip()
    expires_at = (payload.get("expires_at") or "").strip()
    if not token:
        raise GitHubAppAuthError("GitHub returned empty installation token")

    expires_at_epoch = _parse_expires_at(expires_at)

    async with _cache_lock:
        _installation_token_cache[installation_id] = _CachedInstallationToken(token=token, expires_at_epoch=expires_at_epoch)

    logger.info(f"Minted GitHub installation token (installation_id={installation_id}, exp={expires_at})")
    return token
