"""Offline cost simulation for an Invariant (Tribunal API) scan.

This simulates what a *real* Invariant run does at the point it is called:
- Detect changed files (git diff if available, else mtime window)
- Resolve imports (depth-limited)
- Build a token-budgeted context (changed > imports > constitution)
- Estimate the single LLM call used for intent checking (judge_engine)

No network calls are made.

Usage examples:
  python simulate_invariant_costs.py --project-root "C:\\Users\\alexe\\CatalyzeUnified" --mode diff
  python simulate_invariant_costs.py --project-root "C:\\Users\\alexe\\CatalyzeUnified" --mode full --token-budget 20000

Notes:
- Token counting uses the repo's deterministic heuristic (~4 chars/token).
- Pricing comes from dysruption_cva/config.yaml (llms.remediation cost fields).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def _load_file_manager() -> Any:
    """Load modules/file_manager.py without importing the modules package.

    Importing the package executes modules/__init__.py which pulls in tribunal and
    LiteLLM cache wiring (and may log Redis errors). This simulator is intentionally
    deterministic and offline, so we bypass package import side effects.
    """

    path = (Path(__file__).parent / "modules" / "file_manager.py").resolve()
    spec = importlib.util.spec_from_file_location("_cva_file_manager", str(path))
    if not spec or not spec.loader:
        raise RuntimeError("Failed to load file_manager module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_FILE_MANAGER = _load_file_manager()
ContextBuildResult = _FILE_MANAGER.ContextBuildResult
build_llm_context = _FILE_MANAGER.build_llm_context
detect_changed_files = _FILE_MANAGER.detect_changed_files
estimate_tokens = _FILE_MANAGER.estimate_tokens
iter_project_files = _FILE_MANAGER.iter_project_files
resolve_imports = _FILE_MANAGER.resolve_imports


DEFAULT_TOKEN_BUDGET = 8000
# Match Tribunal API default (api.py) for diff mode; override via CLI as needed.
DEFAULT_MTIME_WINDOW_SECONDS = 300
DEFAULT_MODEL = "openai/gpt-4o-mini"  # matches api.py default


def _find_constitution_text(project_root: Path) -> str:
    # Match modules/api.py::_find_constitution_path behavior.
    tribunal_md = project_root / ".tribunal" / "constitution.md"
    tribunal_txt = project_root / ".tribunal" / "constitution.txt"
    if tribunal_md.exists():
        return tribunal_md.read_text(encoding="utf-8", errors="replace")
    if tribunal_txt.exists():
        return tribunal_txt.read_text(encoding="utf-8", errors="replace")

    # Back-compat for workspaces using PROGRAM_CONSTITUTION.md.
    legacy = project_root / "PROGRAM_CONSTITUTION.md"
    if legacy.exists():
        return legacy.read_text(encoding="utf-8", errors="replace")

    return ""


def _load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        return {}
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _get_model_pricing(config: Dict[str, Any], model: str) -> Tuple[float, float]:
    llms = config.get("llms") or {}

    # The Tribunal API intent judge uses CVA_TRIBUNAL_INTENT_MODEL which defaults to openai/gpt-4o-mini.
    # In config.yaml, this aligns with llms.remediation.
    remediation = llms.get("remediation") or {}

    if str(remediation.get("model")) == model:
        return float(remediation.get("cost_per_1k_input", 0.0)), float(remediation.get("cost_per_1k_output", 0.0))

    # Fallback: scan known entries for matching model string
    for entry in llms.values():
        if isinstance(entry, dict) and str(entry.get("model")) == model:
            return float(entry.get("cost_per_1k_input", 0.0)), float(entry.get("cost_per_1k_output", 0.0))

    return 0.0, 0.0


def _read_text_file(root: Path, rel: str, *, max_bytes: int = 512 * 1024) -> str:
    try:
        data = (root / rel).read_bytes()
    except Exception:
        return ""

    if len(data) > max_bytes:
        data = data[:max_bytes]

    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _load_success_spec(spec_path: Path | None) -> Dict[str, Any]:
    if spec_path and spec_path.exists():
        return json.loads(spec_path.read_text(encoding="utf-8"))

    # Small default success spec
    return {
        "intent_summary": "Verify the project matches the requested behavior.",
        "key_constraints": ["No hardcoded secrets", "Reasonable defaults", "Clear error handling"],
        "expected_behavior": "Implementation matches the user intent and constraints.",
    }


def _build_prompt(success_spec: Dict[str, Any], context: str) -> str:
    # Mirror modules/judge_engine.py::run_intent_llm_checks prompt template.
    return (
        "You are an intent verification judge.\n"
        "Given the SUCCESS_SPEC JSON and the CODE CONTEXT, identify any mismatches.\n"
        "Output STRICT JSON: {\"violations\": [{\"rule_id\":...,\"severity\":...,\"file\":...,\"line_start\":...,\"line_end\":...,\"message\":...,\"suggested_fix\":...,\"auto_fixable\":false,\"confidence\":0.0-1.0}]}\n"
        "Do not include extra keys.\n\n"
        f"SUCCESS_SPEC:\n{json.dumps(success_spec, ensure_ascii=False)[:131072]}\n\n"
        f"CODE_CONTEXT:\n{context}\n"
    )


def _estimate_cost_usd(input_tokens: int, output_tokens: int, *, cost_in: float, cost_out: float) -> float:
    return (input_tokens / 1000.0) * cost_in + (output_tokens / 1000.0) * cost_out


def simulate(
    *,
    project_root: Path,
    mode: str,
    token_budget: int,
    mtime_window_seconds: int,
    model: str,
    assumed_output_tokens: int,
    success_spec: Dict[str, Any],
) -> Dict[str, Any]:
    config_path = (Path(__file__).parent / "config.yaml").resolve()
    config = _load_config(config_path)
    cost_in, cost_out = _get_model_pricing(config, model)

    constitution_text = _find_constitution_text(project_root)

    diff_result = detect_changed_files(project_root, mode, mtime_window_seconds=mtime_window_seconds)
    import_res = resolve_imports(project_root, diff_result.changed_files, depth=2)

    ctx: ContextBuildResult = build_llm_context(
        project_root,
        changed_files=diff_result.changed_files,
        import_files=import_res.resolved_files,
        constitution_text=constitution_text,
        token_budget=token_budget,
        spec_text=constitution_text,
        enable_semantic_boost=True,
    )

    prompt = _build_prompt(success_spec, ctx.context)
    prompt_tokens = estimate_tokens(prompt)

    est_cost = _estimate_cost_usd(
        prompt_tokens,
        assumed_output_tokens,
        cost_in=cost_in,
        cost_out=cost_out,
    )

    return {
        "project_root": str(project_root),
        "mode": mode,
        "diff_detection": {
            "detection": diff_result.detection,
            "changed_files_count": len(diff_result.changed_files),
            "changed_files_preview": diff_result.changed_files[:10],
        },
        "import_resolution": {
            "import_files_count": len(import_res.resolved_files),
            "skipped_imports_count": len(import_res.skipped_imports),
        },
        "token_budget": {
            "budget": token_budget,
            "ctx_token_count": ctx.token_count,
            "partial": ctx.partial,
            "included_changed_files": len(ctx.included_changed_files),
            "included_import_files": len(ctx.included_import_files),
            "truncated_files_count": len(ctx.truncated_files),
            "included_constitution": ctx.included_constitution,
            "included_snippets": len(getattr(ctx, "file_snippets", {}) or {}),
        },
        "llm_call": {
            "model": model,
            "pricing_per_1k": {"input": cost_in, "output": cost_out},
            "estimated_prompt_tokens": prompt_tokens,
            "assumed_output_tokens": assumed_output_tokens,
            "estimated_cost_usd": round(est_cost, 6),
        },
    }


def _override_changed_files(project_root: Path, base_changed: List[str], target_count: int) -> List[str]:
    if target_count <= 0:
        return base_changed

    root = project_root.resolve()
    out: List[str] = []
    seen = set()

    for rel in base_changed:
        if rel in seen:
            continue
        out.append(rel)
        seen.add(rel)
        if len(out) >= target_count:
            return out

    for rel in iter_project_files(root, exclude_dirs=(".git", "__pycache__", "node_modules", ".venv")):
        if rel in seen:
            continue
        out.append(rel)
        seen.add(rel)
        if len(out) >= target_count:
            break

    return out


def estimate_full_coverage_runs(
    *,
    project_root: Path,
    changed_files: List[str],
    constitution_text: str,
    token_budget: int,
    success_spec: Dict[str, Any],
    model: str,
    cost_in: float,
    cost_out: float,
    assumed_output_tokens: int,
) -> Dict[str, Any]:
    """Estimate how many Tribunal API *runs* you'd need to fully cover changed files.

    Real Tribunal API does NOT currently auto-batch; a single run will go partial/truncate.
    This function estimates the lower bound on number of runs if you manually batch the
    changed files into separate scans so each scan can include its batch without truncation.
    """

    # Very rough budgeting: reserve constitution tokens if present; if constitution is huge,
    # it may be truncated or excluded, but we still reserve a small cushion.
    constitution_tokens = estimate_tokens(constitution_text) if constitution_text else 0
    reserve = min(constitution_tokens, max(0, token_budget // 3))
    available_for_files = max(0, token_budget - reserve)

    per_file_tokens: List[Tuple[str, int]] = []
    for rel in changed_files:
        content = _read_text_file(project_root, rel)
        section = f"\n# FILE: {rel}\n{content}"
        per_file_tokens.append((rel, estimate_tokens(section)))

    # Greedy sequential packing preserves "newbie just generated files" ordering roughly.
    batches: List[List[str]] = []
    batch: List[str] = []
    batch_tokens = 0
    for rel, tok in per_file_tokens:
        if tok > available_for_files and not batch:
            # One file alone exceeds budget; it will force a partial run.
            batches.append([rel])
            continue
        if batch_tokens + tok > available_for_files and batch:
            batches.append(batch)
            batch = [rel]
            batch_tokens = tok
            continue
        batch.append(rel)
        batch_tokens += tok
    if batch:
        batches.append(batch)

    # Estimate per-run cost using a context roughly at the token budget ceiling.
    # The prompt includes SUCCESS_SPEC + CODE_CONTEXT.
    success_spec_tokens = estimate_tokens(json.dumps(success_spec, ensure_ascii=False)[:131072])
    approx_prompt_tokens = success_spec_tokens + min(token_budget, token_budget) + 200
    est_cost_per_run = _estimate_cost_usd(
        approx_prompt_tokens,
        assumed_output_tokens,
        cost_in=cost_in,
        cost_out=cost_out,
    )

    return {
        "changed_files_count": len(changed_files),
        "token_budget": token_budget,
        "reserved_for_constitution_tokens": reserve,
        "available_for_files_tokens": available_for_files,
        "estimated_runs_to_cover_all_changed_files": len(batches),
        "estimated_cost_per_run_usd": round(est_cost_per_run, 6),
        "estimated_total_cost_usd": round(est_cost_per_run * len(batches), 6),
        "first_batch_preview": batches[0][:10] if batches else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline simulation of Invariant (Tribunal API) run costs")
    parser.add_argument("--project-root", required=True, help="Path to project root to simulate")
    parser.add_argument("--mode", choices=["diff", "full"], default="diff")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--mtime-window-seconds", type=int, default=DEFAULT_MTIME_WINDOW_SECONDS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--assumed-output-tokens", type=int, default=450)
    parser.add_argument("--success-spec-json", default=None, help="Optional path to a SUCCESS_SPEC JSON")
    parser.add_argument(
        "--override-changed-files-count",
        type=int,
        default=0,
        help="If >0, treat the project as having this many changed files (pads from all files).",
    )
    parser.add_argument(
        "--estimate-full-coverage",
        action="store_true",
        help="Estimate number of manual runs needed to cover all changed files without truncation.",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise SystemExit("project-root must be an existing directory")

    success_spec = _load_success_spec(Path(args.success_spec_json).resolve() if args.success_spec_json else None)

    # First simulate with detected changed files.
    config = _load_config((Path(__file__).parent / "config.yaml").resolve())
    cost_in, cost_out = _get_model_pricing(config, args.model)
    constitution_text = _find_constitution_text(project_root)

    diff_result = detect_changed_files(project_root, args.mode, mtime_window_seconds=args.mtime_window_seconds)
    changed_files = _override_changed_files(project_root, diff_result.changed_files, args.override_changed_files_count)

    import_res = resolve_imports(project_root, changed_files, depth=2)
    ctx: ContextBuildResult = build_llm_context(
        project_root,
        changed_files=changed_files,
        import_files=import_res.resolved_files,
        constitution_text=constitution_text,
        token_budget=args.token_budget,
        spec_text=constitution_text,
        enable_semantic_boost=True,
    )

    prompt = _build_prompt(success_spec, ctx.context)
    prompt_tokens = estimate_tokens(prompt)
    est_cost = _estimate_cost_usd(
        prompt_tokens,
        args.assumed_output_tokens,
        cost_in=cost_in,
        cost_out=cost_out,
    )

    out: Dict[str, Any] = {
        "project_root": str(project_root),
        "mode": args.mode,
        "diff_detection": {
            "detection": diff_result.detection,
            "changed_files_count": len(changed_files),
            "changed_files_preview": changed_files[:10],
            "override_changed_files_count": args.override_changed_files_count,
        },
        "import_resolution": {
            "import_files_count": len(import_res.resolved_files),
            "skipped_imports_count": len(import_res.skipped_imports),
        },
        "token_budget": {
            "budget": args.token_budget,
            "ctx_token_count": ctx.token_count,
            "partial": ctx.partial,
            "included_changed_files": len(ctx.included_changed_files),
            "included_import_files": len(ctx.included_import_files),
            "truncated_files_count": len(ctx.truncated_files),
            "included_constitution": ctx.included_constitution,
        },
        "llm_call": {
            "model": args.model,
            "pricing_per_1k": {"input": cost_in, "output": cost_out},
            "estimated_prompt_tokens": prompt_tokens,
            "assumed_output_tokens": args.assumed_output_tokens,
            "estimated_cost_usd": round(est_cost, 6),
        },
    }

    if args.estimate_full_coverage:
        out["full_coverage_estimate"] = estimate_full_coverage_runs(
            project_root=project_root,
            changed_files=changed_files,
            constitution_text=constitution_text,
            token_budget=args.token_budget,
            success_spec=success_spec,
            model=args.model,
            cost_in=cost_in,
            cost_out=cost_out,
            assumed_output_tokens=args.assumed_output_tokens,
        )

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    # Pretty summary
    dd = out["diff_detection"]
    tb = out["token_budget"]
    llm = out["llm_call"]

    print("Invariant run simulation (offline)\n")
    print(f"Project: {out['project_root']}")
    print(f"Mode: {out['mode']} (detection={dd['detection']})")
    print(f"Changed files: {dd['changed_files_count']} (preview={dd['changed_files_preview']})")
    print(f"Token budget: {tb['budget']} | ctx tokens={tb['ctx_token_count']} | partial={tb['partial']}")
    print(f"Included files: changed={tb['included_changed_files']} import={tb['included_import_files']} | truncated={tb['truncated_files_count']}")
    print(f"Included constitution: {tb['included_constitution']}")
    print(
        f"LLM: {llm['model']} | prompt≈{llm['estimated_prompt_tokens']} tok | output≈{llm['assumed_output_tokens']} tok | cost≈${llm['estimated_cost_usd']:.6f}"
    )

    if "full_coverage_estimate" in out:
        fc = out["full_coverage_estimate"]
        print("\nFull coverage estimate (manual batching)")
        print(
            f"Runs to cover all changed files: {fc['estimated_runs_to_cover_all_changed_files']} | total cost≈${fc['estimated_total_cost_usd']:.6f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
