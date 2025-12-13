"""Tribunal Judge Engine.

Implements constitution rule checks (deterministic) and intent verification (LLM).
Designed for use by the Tribunal API endpoints (/api/*).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


try:
    import litellm

    LITELLM_AVAILABLE = True
except Exception:
    LITELLM_AVAILABLE = False


@dataclass(frozen=True)
class JudgeMetrics:
    scan_time_ms: int
    token_count: int
    llm_latency_ms: Optional[int]
    violations_count: int


@dataclass(frozen=True)
class JudgeOutput:
    verdicts: List[Dict[str, Any]]
    partial: bool
    skipped_imports: List[str]
    unevaluated_rules: List[str]
    metrics: JudgeMetrics


_DEFAULT_MIN_CONSTITUTION = """# CVA Minimal Constitution\n\n- The project MUST NOT contain obvious secrets (API keys, private keys).\n- The project MUST NOT use `eval()` on untrusted input.\n"""


def default_min_constitution() -> str:
    return _DEFAULT_MIN_CONSTITUTION


def _sanitize_message(s: str, *, max_len: int = 2000) -> str:
    s2 = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s or "")
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2[:max_len]


def parse_constitution_rules(constitution_text: str) -> List[Dict[str, Any]]:
    """Parse deterministic rules from constitution.

    Assumption (documented in migration plan): a constitution may include a fenced JSON block:

    ```json
    {"tribunal_rules": [{"rule_id": "R1", "severity": "high", "type": "regex", "pattern": "...", "message": "..."}]}
    ```

    If no such block exists, returns an empty list.
    """

    if not constitution_text:
        return []

    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", constitution_text)
    if not m:
        return []

    try:
        payload = json.loads(m.group(1))
        rules = payload.get("tribunal_rules") or []
        if isinstance(rules, list):
            out: List[Dict[str, Any]] = []
            for r in rules:
                if not isinstance(r, dict):
                    continue
                if not r.get("rule_id") or not r.get("type"):
                    continue
                out.append(r)
            return out
    except Exception as e:
        logger.warning(f"Failed parsing constitution rule block: {e}")

    return []


def run_constitution_regex_checks(
    *,
    rules: List[Dict[str, Any]],
    file_texts: Dict[str, str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    verdicts: List[Dict[str, Any]] = []
    unevaluated: List[str] = []

    for rule in rules:
        rule_id = str(rule.get("rule_id"))
        rtype = str(rule.get("type"))
        if rtype != "regex":
            # Non-regex rules are treated as not evaluated by this deterministic engine.
            unevaluated.append(rule_id)
            continue

        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            unevaluated.append(rule_id)
            continue

        severity = str(rule.get("severity") or "medium").lower()
        message = _sanitize_message(str(rule.get("message") or "Rule violation"))
        suggested_fix = _sanitize_message(str(rule.get("suggested_fix") or "")) or None
        auto_fixable = bool(rule.get("auto_fixable", False))

        try:
            rx = re.compile(pattern)
        except re.error:
            unevaluated.append(rule_id)
            continue

        for rel_path, text in file_texts.items():
            for match in rx.finditer(text):
                # Best-effort line mapping
                start = match.start()
                line_start = text.count("\n", 0, start) + 1
                verdicts.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "constitution",
                        "rule_id": rule_id,
                        "severity": severity,
                        "file": rel_path,
                        "line_start": line_start,
                        "line_end": line_start,
                        "message": message,
                        "suggested_fix": suggested_fix,
                        "auto_fixable": auto_fixable,
                        "confidence": 0.99,
                    }
                )

    return verdicts, unevaluated


async def run_intent_llm_checks(
    *,
    success_spec: Dict[str, Any],
    context: str,
    model: str,
    timeout_seconds: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Run LLM-based checks for intent verification.

    Returns (verdicts, llm_latency_ms).

    If LiteLLM is unavailable, raises RuntimeError.
    """

    if not LITELLM_AVAILABLE:
        raise RuntimeError("LiteLLM is not available")

    prompt = (
        "You are an intent verification judge.\n"
        "Given the SUCCESS_SPEC JSON and the CODE CONTEXT, identify any mismatches.\n"
        "Output STRICT JSON: {\"violations\": [{\"rule_id\":...,\"severity\":...,\"file\":...,\"line_start\":...,\"line_end\":...,\"message\":...,\"suggested_fix\":...,\"auto_fixable\":false,\"confidence\":0.0-1.0}]}\n"
        "Do not include extra keys.\n\n"
        f"SUCCESS_SPEC:\n{json.dumps(success_spec, ensure_ascii=False)[:131072]}\n\n"
        f"CODE_CONTEXT:\n{context}\n"
    )

    start = time.time()

    async def _call() -> Any:
        return await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

    try:
        resp = await asyncio.wait_for(_call(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise

    latency_ms = int((time.time() - start) * 1000)

    content = ""
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        content = str(resp)

    try:
        data = json.loads(content)
    except Exception as e:
        raise RuntimeError(f"Invalid LLM JSON output: {e}")

    violations = data.get("violations")
    if not isinstance(violations, list):
        raise RuntimeError("Invalid LLM JSON output: missing violations list")

    verdicts: List[Dict[str, Any]] = []
    for v in violations:
        if not isinstance(v, dict):
            continue
        verdicts.append(
            {
                "id": str(uuid.uuid4()),
                "type": "intent",
                "rule_id": _sanitize_message(str(v.get("rule_id") or "intent"), max_len=128),
                "severity": _sanitize_message(str(v.get("severity") or "medium"), max_len=32).lower(),
                "file": _sanitize_message(str(v.get("file") or ""), max_len=512) or None,
                "line_start": int(v.get("line_start") or 1),
                "line_end": int(v.get("line_end") or int(v.get("line_start") or 1)),
                "message": _sanitize_message(str(v.get("message") or "Intent mismatch")),
                "suggested_fix": _sanitize_message(str(v.get("suggested_fix") or "")) or None,
                "auto_fixable": bool(v.get("auto_fixable", False)),
                "confidence": float(v.get("confidence") or 0.5),
            }
        )

    return verdicts, latency_ms


async def judge_engine(
    *,
    file_texts: Dict[str, str],
    constitution_text: str,
    skipped_imports: List[str],
    token_count: int,
    token_budget_partial: bool,
    success_spec: Dict[str, Any],
    llm_model: str,
    llm_timeout_seconds: int,
    llm_enabled: bool = True,
) -> JudgeOutput:
    """Run deterministic constitution checks + optional LLM intent checks."""

    start = time.time()
    rules = parse_constitution_rules(constitution_text)

    const_verdicts, unevaluated = run_constitution_regex_checks(rules=rules, file_texts=file_texts)

    intent_verdicts: List[Dict[str, Any]] = []
    llm_latency_ms: Optional[int] = None

    if llm_enabled:
        # Note: token_budget_partial may mean constitution/context was truncated.
        # We still attempt intent checks unless asked to disable.
        context_for_llm = "\n".join([f"# FILE: {p}\n{t}" for p, t in file_texts.items()])
        try:
            intent_verdicts, llm_latency_ms = await run_intent_llm_checks(
                success_spec=success_spec,
                context=context_for_llm,
                model=llm_model,
                timeout_seconds=llm_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise

    verdicts = const_verdicts + intent_verdicts

    elapsed_ms = int((time.time() - start) * 1000)

    partial = bool(token_budget_partial)
    # Requirement: if token budget prevents constitution checks, list rules not evaluated.
    # We interpret this as: if constitution/context was truncated, mark any non-regex rules as unevaluated.
    if token_budget_partial and rules:
        for r in rules:
            rid = str(r.get("rule_id"))
            if rid not in unevaluated:
                # Only mark as unevaluated if it is not a regex (needs more context/LLM)
                if str(r.get("type")) != "regex":
                    unevaluated.append(rid)

    metrics = JudgeMetrics(
        scan_time_ms=elapsed_ms,
        token_count=token_count,
        llm_latency_ms=llm_latency_ms,
        violations_count=len(verdicts),
    )

    return JudgeOutput(
        verdicts=verdicts,
        partial=partial,
        skipped_imports=skipped_imports,
        unevaluated_rules=sorted(set(unevaluated)),
        metrics=metrics,
    )
