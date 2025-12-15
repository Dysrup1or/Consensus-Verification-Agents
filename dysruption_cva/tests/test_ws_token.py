import os

import jwt
import pytest
from fastapi.testclient import TestClient


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

    monkeypatch.setenv("CVA_WS_JWT_SECRET", "unit-test-secret")

    from modules.api import app

    with TestClient(app) as c:
        yield c


def test_ws_token_mints_run_scoped_jwt(client: TestClient):
    run_id = "run123"
    r = client.get(f"/api/ws_token/{run_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["run_id"] == run_id
    assert data.get("ws_token")

    payload = jwt.decode(data["ws_token"], "unit-test-secret", algorithms=["HS256"])
    assert payload["typ"] == "cva_ws"
    assert payload["run_id"] == run_id
