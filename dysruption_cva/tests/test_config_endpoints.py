import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _dev_mode(monkeypatch):
    # Ensure auth gating doesn't block the test suite.
    monkeypatch.setenv("CVA_PRODUCTION", "false")


@pytest.fixture()
def client(tmp_path):
    # Force the persistence layer to a per-test sqlite file.
    # modules.api is imported by other tests, so we reset the engine explicitly.
    from modules.persistence.db import reset_engine_for_tests

    db_path = tmp_path / "cva_test.db"

    async def _reset():
        await reset_engine_for_tests(f"sqlite+aiosqlite:///{db_path.as_posix()}")

    import anyio

    anyio.run(_reset)

    # Ensure schema is created for sqlite before requests.
    from modules.persistence.init import ensure_sqlite_schema

    anyio.run(ensure_sqlite_schema)

    from modules.api import app

    with TestClient(app) as c:
        yield c


def test_config_crud_smoke(client: TestClient):
    # Create repo connection
    r = client.post(
        "/api/config/repo_connections",
        json={"provider": "github", "repo_full_name": "octo/demo", "default_branch": "main"},
    )
    assert r.status_code == 200, r.text
    repo_conn = r.json()
    assert repo_conn["id"]
    assert repo_conn["repo_full_name"] == "octo/demo"

    # List connections
    r = client.get("/api/config/repo_connections")
    assert r.status_code == 200
    assert any(x["id"] == repo_conn["id"] for x in r.json())

    # Create branch
    r = client.post(
        f"/api/config/repo_connections/{repo_conn['id']}/branches",
        json={"branch": "main", "is_monitored": True},
    )
    assert r.status_code == 200, r.text
    branch = r.json()
    assert branch["branch"] == "main"
    assert branch["is_monitored"] is True

    # Create constitution version
    r = client.post(
        f"/api/config/repo_branches/{branch['id']}/constitution",
        json={"content": "# Constitution\n\nDo the right thing."},
    )
    assert r.status_code == 200, r.text
    cv = r.json()
    assert cv["version"] == 1

    # Read latest constitution
    r = client.get(f"/api/config/repo_branches/{branch['id']}/constitution/latest")
    assert r.status_code == 200
    latest = r.json()
    assert latest["version"] == 1
    assert "Do the right thing" in latest["content"]

    # Toggle monitoring off
    r = client.patch(f"/api/config/repo_branches/{branch['id']}", json={"is_monitored": False})
    assert r.status_code == 200
    assert r.json()["is_monitored"] is False
