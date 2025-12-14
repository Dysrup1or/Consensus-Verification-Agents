from __future__ import annotations

import asyncio

import pytest

from dysruption_cva.modules.router import HealthResult
from dysruption_cva.modules.router import ProviderSpec
from dysruption_cva.modules.router import RouterError
from dysruption_cva.modules.router import RouterRequest
from dysruption_cva.modules.router import default_health_check
from dysruption_cva.modules.router import route


@pytest.mark.anyio
async def test_p3_1_lane2_selects_local_when_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hc(spec: ProviderSpec) -> HealthResult:
        return HealthResult(provider=spec.provider, model=spec.model, healthy=True, reason="ok")

    decision = await route(
        request=RouterRequest(lane="lane2", token_budget=8000, allow_escalation=True),
        lane2_candidates=[ProviderSpec(provider="local", model="local/llama", tier="lane2")],
        lane3_candidates=[ProviderSpec(provider="frontier", model="openai/gpt-4o-mini", tier="lane3")],
        health_check=hc,
    )

    assert decision.lane_used == "lane2"
    assert decision.provider == "local"


@pytest.mark.anyio
async def test_p3_1_escalates_to_lane3_when_lane2_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hc(spec: ProviderSpec) -> HealthResult:
        if spec.tier == "lane2":
            return HealthResult(provider=spec.provider, model=spec.model, healthy=False, reason="down")
        return HealthResult(provider=spec.provider, model=spec.model, healthy=True, reason="ok")

    decision = await route(
        request=RouterRequest(lane="lane2", token_budget=8000, allow_escalation=True),
        lane2_candidates=[ProviderSpec(provider="local", model="local/llama", tier="lane2")],
        lane3_candidates=[ProviderSpec(provider="frontier", model="openai/gpt-4o-mini", tier="lane3")],
        health_check=hc,
    )

    assert decision.lane_used == "lane3"
    assert decision.reason == "escalated_to_lane3"


@pytest.mark.anyio
async def test_p3_1_fails_without_escalation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hc(spec: ProviderSpec) -> HealthResult:
        return HealthResult(provider=spec.provider, model=spec.model, healthy=False, reason="down")

    with pytest.raises(RouterError):
        await route(
            request=RouterRequest(lane="lane2", token_budget=8000, allow_escalation=False),
            lane2_candidates=[ProviderSpec(provider="local", model="local/llama", tier="lane2")],
            lane3_candidates=[ProviderSpec(provider="frontier", model="openai/gpt-4o-mini", tier="lane3")],
            health_check=hc,
        )


@pytest.mark.anyio
async def test_p3_2_timeout_is_a_structured_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hc(spec: ProviderSpec) -> HealthResult:
        if spec.model == "openai/timeout":
            raise asyncio.TimeoutError()
        return HealthResult(provider=spec.provider, model=spec.model, healthy=True, reason="ok")

    decision = await route(
        request=RouterRequest(lane="lane3", token_budget=8000),
        lane2_candidates=[],
        lane3_candidates=[
            ProviderSpec(provider="frontier", model="openai/timeout", tier="lane3"),
            ProviderSpec(provider="frontier", model="openai/gpt-4o-mini", tier="lane3"),
        ],
        health_check=hc,
    )

    assert decision.lane_used == "lane3"
    assert decision.model == "openai/gpt-4o-mini"
    assert decision.fallback_chain[0]["reason"] == "timeout"


@pytest.mark.anyio
async def test_p3_2_auth_missing_is_detected_by_default_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    hr = await default_health_check(ProviderSpec(provider="frontier", model="openai/gpt-4o-mini", tier="lane3"))
    assert hr.healthy is False
    assert hr.reason.startswith("auth_missing:")


@pytest.mark.anyio
async def test_p3_2_model_missing_is_detected_by_default_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    hr = await default_health_check(ProviderSpec(provider="frontier", model="", tier="lane3"))
    assert hr.healthy is False
    assert hr.reason == "model_missing"
