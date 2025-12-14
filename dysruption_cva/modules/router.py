"""Phase 3: Deterministic router for lane2 (local/open) → lane3 (frontier).

Design goals:
- Deterministic: given config + health results, selection is stable.
- Explicit: returns a decision with reasons + fallback chain.
- Testable: health checks are injectable/mocked.

NOTE: Real provider probing (network calls) is intentionally minimal here. By default,
health checks validate configuration and required environment credentials only.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class ProviderSpec:
    provider: str  # e.g. "local", "openai", "anthropic", "legacy"
    model: str
    tier: str  # "lane2" | "lane3"


@dataclass(frozen=True)
class HealthResult:
    provider: str
    model: str
    healthy: bool
    reason: str


@dataclass(frozen=True)
class RouterRequest:
    lane: str  # "lane2" | "lane3"
    token_budget: int
    allow_escalation: bool = True
    preferred_providers: Sequence[str] = ()


@dataclass(frozen=True)
class RouterDecision:
    lane_requested: str
    lane_used: str
    provider: str
    model: str
    reason: str
    fallback_chain: List[Dict[str, str]]


class RouterError(RuntimeError):
    pass


HealthChecker = Callable[[ProviderSpec], Awaitable[HealthResult]]


def _required_env_for_model(model: str) -> Optional[str]:
    model = (model or "").strip().lower()
    if model.startswith("openai/"):
        return "OPENAI_API_KEY"
    if model.startswith("anthropic/"):
        return "ANTHROPIC_API_KEY"
    if model.startswith("azure/"):
        return "AZURE_API_KEY"
    # Local providers may not require env keys.
    return None


async def default_health_check(spec: ProviderSpec) -> HealthResult:
    """Default health check: validates model string + required env credential.

    This is intentionally conservative and local-only (no network).
    """

    if not (spec.model or "").strip():
        return HealthResult(provider=spec.provider, model=spec.model, healthy=False, reason="model_missing")

    required = _required_env_for_model(spec.model)
    if required and not os.getenv(required):
        return HealthResult(provider=spec.provider, model=spec.model, healthy=False, reason=f"auth_missing:{required}")

    return HealthResult(provider=spec.provider, model=spec.model, healthy=True, reason="ok")


def load_router_config_from_env(*, legacy_model: str) -> Dict[str, List[ProviderSpec]]:
    """Build lane candidate lists from env.

    - Lane 2: CVA_LANE2_MODEL (optional)
    - Lane 3: falls back to the existing legacy model
    """

    lane2_model = os.getenv("CVA_LANE2_MODEL", "").strip()
    lane3_model = os.getenv("CVA_LANE3_MODEL", "").strip() or (legacy_model or "").strip()

    lane2: List[ProviderSpec] = []
    if lane2_model:
        lane2.append(ProviderSpec(provider=os.getenv("CVA_LANE2_PROVIDER", "local"), model=lane2_model, tier="lane2"))

    lane3: List[ProviderSpec] = []
    if lane3_model:
        lane3.append(ProviderSpec(provider=os.getenv("CVA_LANE3_PROVIDER", "frontier"), model=lane3_model, tier="lane3"))

    return {"lane2": lane2, "lane3": lane3}


async def route(
    *,
    request: RouterRequest,
    lane2_candidates: Sequence[ProviderSpec],
    lane3_candidates: Sequence[ProviderSpec],
    health_check: HealthChecker = default_health_check,
) -> RouterDecision:
    """Select a provider/model for the requested lane with explicit fallback."""

    lane_requested = request.lane
    fallback_chain: List[Dict[str, str]] = []

    async def _first_healthy(cands: Sequence[ProviderSpec]) -> Optional[ProviderSpec]:
        ordered = list(cands)
        if request.preferred_providers:
            pref = [c for c in ordered if c.provider in set(request.preferred_providers)]
            rest = [c for c in ordered if c.provider not in set(request.preferred_providers)]
            ordered = pref + rest

        for c in ordered:
            try:
                hr = await health_check(c)
            except asyncio.TimeoutError:
                hr = HealthResult(provider=c.provider, model=c.model, healthy=False, reason="timeout")
            except Exception as e:
                hr = HealthResult(provider=c.provider, model=c.model, healthy=False, reason=f"error:{type(e).__name__}")

            fallback_chain.append({"provider": c.provider, "model": c.model, "healthy": str(hr.healthy).lower(), "reason": hr.reason})
            if hr.healthy:
                return c

        return None

    if lane_requested == "lane2":
        picked = await _first_healthy(lane2_candidates)
        if picked:
            return RouterDecision(
                lane_requested="lane2",
                lane_used="lane2",
                provider=picked.provider,
                model=picked.model,
                reason="lane2_selected",
                fallback_chain=fallback_chain,
            )

        if request.allow_escalation:
            picked3 = await _first_healthy(lane3_candidates)
            if picked3:
                return RouterDecision(
                    lane_requested="lane2",
                    lane_used="lane3",
                    provider=picked3.provider,
                    model=picked3.model,
                    reason="escalated_to_lane3",
                    fallback_chain=fallback_chain,
                )

        raise RouterError("No healthy providers for lane2 (and escalation not possible)")

    if lane_requested == "lane3":
        picked = await _first_healthy(lane3_candidates)
        if picked:
            return RouterDecision(
                lane_requested="lane3",
                lane_used="lane3",
                provider=picked.provider,
                model=picked.model,
                reason="lane3_selected",
                fallback_chain=fallback_chain,
            )
        raise RouterError("No healthy providers for lane3")

    raise RouterError(f"Unknown lane: {lane_requested}")
