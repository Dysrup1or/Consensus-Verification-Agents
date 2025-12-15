import pytest

from modules.monitoring import github_app_auth
from modules.monitoring import github_zipball


def test_parse_expires_at_z() -> None:
    epoch = github_app_auth._parse_expires_at("2025-12-15T00:00:00Z")
    assert isinstance(epoch, float)
    assert epoch > 0


@pytest.mark.asyncio
async def test_installation_token_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    github_app_auth._installation_token_cache.clear()

    monkeypatch.setattr(github_app_auth, "_mint_app_jwt", lambda: "app.jwt")

    calls = {"post": 0}

    class FakeResp:
        status_code = 201
        content = b"1"

        @property
        def text(self) -> str:
            return "{\"token\": \"inst.token\", \"expires_at\": \"2099-01-01T00:00:00Z\"}"

        def json(self):
            return {"token": "inst.token", "expires_at": "2099-01-01T00:00:00Z"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None):
            calls["post"] += 1
            return FakeResp()

    monkeypatch.setattr(github_app_auth.httpx, "AsyncClient", FakeAsyncClient)

    t1 = await github_app_auth.get_installation_access_token(installation_id=123)
    t2 = await github_app_auth.get_installation_access_token(installation_id=123)

    assert t1 == "inst.token"
    assert t2 == "inst.token"
    assert calls["post"] == 1


@pytest.mark.asyncio
async def test_zipball_prefers_installation_token(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_installation_access_token(*, installation_id: int) -> str:
        return f"inst-{installation_id}"

    monkeypatch.setattr(github_app_auth, "is_github_app_configured", lambda: True)
    monkeypatch.setattr(github_app_auth, "get_installation_access_token", fake_get_installation_access_token)
    monkeypatch.setenv("CVA_GITHUB_TOKEN", "pat")

    token = await github_zipball._resolve_github_bearer_token(installation_id=456)
    assert token == "inst-456"


@pytest.mark.asyncio
async def test_zipball_falls_back_to_pat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_app_auth, "is_github_app_configured", lambda: False)
    monkeypatch.setenv("CVA_GITHUB_TOKEN", "pat")

    token = await github_zipball._resolve_github_bearer_token(installation_id=456)
    assert token == "pat"
