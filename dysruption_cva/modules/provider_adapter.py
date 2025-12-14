from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple


def estimate_tokens(text: str) -> int:
    # Heuristic: ~4 chars/token.
    return max(0, int(len(text or "") / 4))


@dataclass(frozen=True)
class BatchTelemetry:
    batch_size: int
    mode: str  # provider_batch|concurrent|sequential|single
    per_item_latency_ms: List[int]


ProviderCall = Callable[[List[Dict[str, str]]], Awaitable[Any]]


def build_messages_with_stable_prefix(*, stable_prefix: str, variable_suffix: str) -> List[Dict[str, str]]:
    stable = (stable_prefix or "").strip()
    variable = variable_suffix or ""
    # Cache-friendly layout: stable instructions in system, variable in user.
    return [
        {"role": "system", "content": stable},
        {"role": "user", "content": variable},
    ]


async def acompletion_single(
    *,
    model: str,
    messages: List[Dict[str, str]],
    timeout_seconds: int,
    provider_call: Optional[ProviderCall] = None,
    temperature: int = 0,
) -> Tuple[Any, int]:
    """One completion with latency measurement.

    If provider_call is provided, it is used (for tests); otherwise expects LiteLLM-like call.
    """

    start = time.time()

    if provider_call is None:
        import litellm  # local import for testability

        async def _call() -> Any:
            return await litellm.acompletion(model=model, messages=messages, temperature=temperature)

        resp = await asyncio.wait_for(_call(), timeout=timeout_seconds)
    else:
        resp = await asyncio.wait_for(provider_call(messages), timeout=timeout_seconds)

    latency_ms = int((time.time() - start) * 1000)
    return resp, latency_ms


async def acompletion_batch(
    *,
    model: str,
    batch_messages: Sequence[List[Dict[str, str]]],
    timeout_seconds: int,
    provider_call: Optional[Callable[[List[Dict[str, str]]], Awaitable[Any]]] = None,
    max_concurrency: int = 8,
    prefer_batch: bool = False,
    temperature: int = 0,
) -> Tuple[List[Any], BatchTelemetry]:
    """Batch primitive.

    Deterministic mapping: output list order matches input batch_messages order.

    We default to concurrent fan-out (provider-agnostic). If prefer_batch=True and the
    underlying provider supports native batch in future, this can be upgraded.
    """

    n = len(batch_messages)
    if n == 0:
        return [], BatchTelemetry(batch_size=0, mode="single", per_item_latency_ms=[])

    if n == 1:
        resp, ms = await acompletion_single(
            model=model,
            messages=list(batch_messages[0]),
            timeout_seconds=timeout_seconds,
            provider_call=provider_call,
            temperature=temperature,
        )
        return [resp], BatchTelemetry(batch_size=1, mode="single", per_item_latency_ms=[ms])

    # Native provider batch not implemented (avoid assuming API support).
    _ = prefer_batch

    sem = asyncio.Semaphore(max(1, int(max_concurrency)))

    async def _one(idx: int, msgs: List[Dict[str, str]]) -> Tuple[int, Any, int]:
        async with sem:
            resp, ms = await acompletion_single(
                model=model,
                messages=msgs,
                timeout_seconds=timeout_seconds,
                provider_call=provider_call,
                temperature=temperature,
            )
            return idx, resp, ms

    tasks = [_one(i, list(m)) for i, m in enumerate(batch_messages)]
    done = await asyncio.gather(*tasks)
    done_sorted = sorted(done, key=lambda t: t[0])

    responses: List[Any] = [r for _, r, _ in done_sorted]
    per_item_ms: List[int] = [ms for _, _, ms in done_sorted]

    return responses, BatchTelemetry(batch_size=n, mode="concurrent", per_item_latency_ms=per_item_ms)
