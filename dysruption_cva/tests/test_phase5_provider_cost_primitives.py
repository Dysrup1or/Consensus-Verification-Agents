from __future__ import annotations

import json

import pytest

from dysruption_cva.modules.provider_adapter import acompletion_batch
from dysruption_cva.modules.provider_adapter import build_messages_with_stable_prefix


@pytest.mark.anyio
async def test_p5_1_stable_prefix_split_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    import dysruption_cva.modules.judge_engine as je

    if not je.LITELLM_AVAILABLE:
        pytest.skip("LiteLLM not available")

    captured = {}

    async def fake_acompletion(*, model, messages, temperature=0):
        captured["model"] = model
        captured["messages"] = messages
        return {"choices": [{"message": {"content": json.dumps({"violations": []})}}]}

    monkeypatch.setattr(je.litellm, "acompletion", fake_acompletion)

    verdicts, _ms = await je.run_intent_llm_checks(
        success_spec={"acceptance_criteria": ["works"]},
        context="# FILE: a.py\nprint('x')\n",
        model="openai/gpt-4o-mini",
        timeout_seconds=5,
    )

    assert verdicts == []
    msgs = captured["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "intent verification judge" in msgs[0]["content"].lower()
    assert "SUCCESS_SPEC:" not in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "SUCCESS_SPEC:" in msgs[1]["content"]
    assert "CODE_CONTEXT:" in msgs[1]["content"]


@pytest.mark.anyio
async def test_p5_2_batch_primitive_is_deterministic_order() -> None:
    async def provider_call(messages):
        # Encode the user content so we can assert stable order.
        user = next((m["content"] for m in messages if m.get("role") == "user"), "")
        return {"choices": [{"message": {"content": json.dumps({"echo": user})}}]}

    batch_messages = [
        build_messages_with_stable_prefix(stable_prefix="S", variable_suffix=f"U{i}")
        for i in range(5)
    ]

    resps, tel = await acompletion_batch(
        model="test/model",
        batch_messages=batch_messages,
        timeout_seconds=5,
        provider_call=provider_call,
        max_concurrency=3,
    )

    assert tel.batch_size == 5
    assert tel.mode in {"concurrent", "provider_batch", "sequential"}
    assert len(tel.per_item_latency_ms) == 5

    echoed = [json.loads(r["choices"][0]["message"]["content"]) for r in resps]
    assert [e["echo"] for e in echoed] == [f"U{i}" for i in range(5)]
