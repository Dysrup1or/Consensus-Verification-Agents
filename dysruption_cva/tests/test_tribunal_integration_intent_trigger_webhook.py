import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
import httpx

from modules.api import app
from modules.judge_engine import JudgeMetrics, JudgeOutput
from modules.router import RouterDecision


@pytest.mark.anyio
async def test_agent_intent_trigger_verdict_webhook_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Arrange project root under UPLOAD_ROOT
    import modules.api as api

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()

    project_id = "proj1"
    project_root = upload_root / project_id
    (project_root / ".tribunal").mkdir(parents=True)
    (project_root / ".tribunal" / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
    (project_root / "a.py").write_text("print('ok')\n", encoding="utf-8")

    api.UPLOAD_ROOT = upload_root
    api.RUN_ARTIFACTS_ROOT = tmp_path / "run_artifacts"
    api.API_TOKEN = "testtoken"

    # Stub router so tests don't depend on real provider env/auth.
    async def fake_route_llm(**kwargs):
        return RouterDecision(
            lane_requested="lane2",
            lane_used="lane2",
            provider="local",
            model="local/test-model",
            reason="lane2_selected",
            fallback_chain=[],
        )

    monkeypatch.setattr(api, "route_llm", fake_route_llm)

    # Stub judge_engine to avoid real LLM usage
    captured_kwargs = {}

    async def fake_judge_engine(**kwargs):
        captured_kwargs.update(kwargs)
        return JudgeOutput(
            verdicts=[],
            partial=False,
            skipped_imports=kwargs.get("skipped_imports", []),
            unevaluated_rules=[],
            metrics=JudgeMetrics(scan_time_ms=1, token_count=1, llm_latency_ms=1, violations_count=0),
        )

    monkeypatch.setattr(api, "judge_engine", fake_judge_engine)

    # Capture webhook payload
    event = asyncio.Event()
    captured = {}

    async def fake_webhook(*, callback_url, callback_bearer_token, payload):
        captured["callback_url"] = callback_url
        captured["payload"] = payload
        event.set()

    monkeypatch.setattr(api, "_emit_initiator_webhook", fake_webhook)

    run_id = str(uuid4())

    intent = {
        "run_id": run_id,
        "project_id": project_id,
        "initiator": {"callback_url": "https://example.test/webhook"},
        "success_spec": {"acceptance_criteria": ["It works"]},
    }

    headers = {"Authorization": "Bearer testtoken"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # POST intent
        r1 = await client.post("/api/intent", json=intent, headers=headers)
        assert r1.status_code == 202

        # Trigger scan
        r2 = await client.post("/api/trigger_scan", json={"run_id": run_id, "mode": "diff"}, headers=headers)
        assert r2.status_code == 202

        # Wait for webhook
        await asyncio.wait_for(event.wait(), timeout=5)

        assert captured["callback_url"] == "https://example.test/webhook"
        assert captured["payload"]["run_id"] == run_id
        assert captured["payload"]["status"] in {"complete", "failed"}

        # Persisted verdict artifact should exist and include telemetry.
        verdict_path = (api.RUN_ARTIFACTS_ROOT / run_id / "tribunal_verdicts.json").resolve()
        for _ in range(50):
            if verdict_path.exists():
                break
            await asyncio.sleep(0.05)

        assert verdict_path.exists()
        data = verdict_path.read_text(encoding="utf-8")
        assert "\"telemetry\"" in data

        # Verdicts endpoint should return persisted payload.
        r3 = await client.get(f"/api/verdicts/{run_id}")
        assert r3.status_code == 200
        payload = r3.json()
        assert "telemetry" in payload
        assert "coverage" in payload["telemetry"]

        # Phase 3: routed model is used + persisted.
        assert captured_kwargs.get("llm_model") == "local/test-model"
        assert payload["telemetry"].get("router", {}).get("model") == "local/test-model"
