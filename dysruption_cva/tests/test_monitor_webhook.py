import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient


def _sig(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


@pytest.fixture(autouse=True)
def _dev_mode(monkeypatch):
    monkeypatch.setenv("CVA_PRODUCTION", "false")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from modules.persistence.db import reset_engine_for_tests
    import anyio

    db_path = tmp_path / "cva_test.db"

    anyio.run(lambda: reset_engine_for_tests(f"sqlite+aiosqlite:///{db_path.as_posix()}"))

    from modules.persistence.init import ensure_sqlite_schema

    anyio.run(ensure_sqlite_schema)

    from modules.api import app

    with TestClient(app) as c:
        yield c


def test_github_webhook_enqueues_job_when_monitored(client: TestClient, monkeypatch):
    secret = "topsecret"
    monkeypatch.setenv("CVA_GITHUB_WEBHOOK_SECRET", secret)

    # Create repo connection + branch
    r = client.post(
        "/api/config/repo_connections",
        json={"provider": "github", "repo_full_name": "octo/demo", "default_branch": "main"},
    )
    repo_conn_id = r.json()["id"]

    r = client.post(
        f"/api/config/repo_connections/{repo_conn_id}/branches",
        json={"branch": "main", "is_monitored": True},
    )
    assert r.status_code == 200

    body = {
        "ref": "refs/heads/main",
        "after": "a" * 40,
        "repository": {"full_name": "octo/demo"},
    }
    raw = json.dumps(body).encode("utf-8")

    r = client.post(
        "/api/webhooks/github",
        data=raw,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sig(secret, raw),
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out.get("job_id")


def test_list_runs_empty(client: TestClient):
    # Create repo connection + branch
    r = client.post(
        "/api/config/repo_connections",
        json={"provider": "github", "repo_full_name": "octo/demo", "default_branch": "main"},
    )
    repo_conn_id = r.json()["id"]
    r = client.post(
        f"/api/config/repo_connections/{repo_conn_id}/branches",
        json={"branch": "main", "is_monitored": True},
    )
    branch_id = r.json()["id"]

    r = client.get(f"/api/monitor/runs?repo_branch_id={branch_id}")
    assert r.status_code == 200
    assert r.json() == []


def test_github_webhook_rejects_bad_signature(client: TestClient, monkeypatch):
    secret = "topsecret"
    monkeypatch.setenv("CVA_GITHUB_WEBHOOK_SECRET", secret)

    raw = json.dumps({"hello": "world"}).encode("utf-8")

    r = client.post(
        "/api/webhooks/github",
        data=raw,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401
