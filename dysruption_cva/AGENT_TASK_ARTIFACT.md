# AGENT TASK ARTIFACT — CVA Phases 2–6

This artifact is the contract for Agent ChatGPT 5.2 (preview). No task may be marked **DONE** until its acceptance criteria are met and the listed verification steps pass.

Status values: **NOT_STARTED | IN_PROGRESS | DONE**

---

## Phase 2 — Harden Dependency Resolver + Integrate With Planner

### P2.1 — Dedicated dependency resolver module (polyglot)
- **Task ID:** P2.1
- **Title:** Extract polyglot dependency resolver module
- **Scope:**
  - Allowed: `dysruption_cva/modules/dependency_resolver.py`, `dysruption_cva/modules/file_manager.py`, new/updated tests under `dysruption_cva/tests/`
  - Not allowed: unrelated product features
- **Acceptance criteria:**
  - Create dedicated module with a single stable public API:
    - `resolve_dependencies(project_root: Path, entry_files: Sequence[str], *, depth: int, max_files: int, config: ResolverConfig) -> ResolutionResult`
  - `ResolutionResult` includes:
    - `resolved_files: list[str]` (repo-relative, normalized `/`)
    - `skipped_imports: list[str]` (raw import strings that could not resolve)
    - `diagnostics: dict` with reason buckets and counts (e.g. `skipped_external`, `skipped_missing`, `skipped_too_large`)
  - No caller needs language-specific rules.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Added module `dysruption_cva/modules/dependency_resolver.py`
  - Tests:
    - `dysruption_cva/tests/test_phase2_dependency_resolver_module.py`
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase2_dependency_resolver_module.py` (PASS)
- **Status:** DONE

### P2.2 — Remove “force by duplication” (explicit forcing only)
- **Task ID:** P2.2
- **Title:** Replace implicit forced-file convention with explicit parameter
- **Scope:**
  - Allowed: `dysruption_cva/modules/file_manager.py`, resolver module if needed, tests
- **Acceptance criteria:**
  - Add explicit mechanism (`forced_files: Sequence[str]` or structured inputs).
  - Coverage plan table includes reason `forced_*` for forced files.
  - Rollups/telemetry includes forced-file count.
  - Remove any inference from duplicates or ordering.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Planner signatures now accept `forced_files` explicitly (no duplicate/order inference)
  - Telemetry rollups include forced-file count (`forced_files_count`)
  - Test:
    - `dysruption_cva/tests/test_phase2_forced_files_explicit.py`
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase2_forced_files_explicit.py` (PASS)
- **Status:** DONE

### P2.3 — TS/JS resolution: tsconfig paths + conservative package.json workspaces
- **Task ID:** P2.3
- **Title:** Support tsconfig aliases and monorepo workspaces (repo-local only)
- **Scope:**
  - Allowed: resolver module + tests
- **Acceptance criteria:**
  - `tsconfig/jsconfig`:
    - supports `compilerOptions.baseUrl`
    - supports `compilerOptions.paths` with single `*` wildcard (deterministic priority)
    - remains repo-local (no escapes)
  - `package.json` workspaces:
    - detect `workspaces: []` or `workspaces: { packages: [] }`
    - resolve internal workspace packages conservatively to local entry
    - never resolve to external `node_modules`
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Tests:
    - `dysruption_cva/tests/test_phase2_dependency_resolver_tsconfig.py`
    - `dysruption_cva/tests/test_phase2_dependency_resolver_module.py` (workspaces)
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase2_dependency_resolver_tsconfig.py dysruption_cva/tests/test_phase2_dependency_resolver_module.py` (PASS)
- **Status:** DONE

### P2.4 — Integrate resolver with Phase 1 planner
- **Task ID:** P2.4
- **Title:** Planner uses dedicated resolver; risk centrality uses resolver graph
- **Scope:**
  - Allowed: `dysruption_cva/modules/file_manager.py`, resolver module, tests
- **Acceptance criteria:**
  - Planner calls resolver module.
  - Centrality/risk uses resolver edges (not ad-hoc parsing in multiple places).
  - Dependencies appear in manifest/coverage plan and are eligible for upgrades.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Planner calls `resolve_dependencies(...)` to expand repo-local dependencies and compute centrality.
  - Test:
    - `dysruption_cva/tests/test_phase2_planner_integration_resolver.py`
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase2_planner_integration_resolver.py` (PASS)
- **Status:** DONE

---

## Phase 3 — Router (Lane 2 local/open → Lane 3 frontier)

### P3.1 — Router policy + interface
- **Task ID:** P3.1
- **Title:** Deterministic router selects provider/model per lane with fallback chain
- **Scope:**
  - Allowed: new `dysruption_cva/modules/router.py`, tests, minimal wiring changes
- **Acceptance criteria:**
  - Structured request/response contract.
  - Lane 2 selects local/open class; Lane 3 selects frontier class.
  - Deterministic selection with reasons and fallback chain.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Implementation:
    - `dysruption_cva/modules/router.py`
  - Tests:
    - `dysruption_cva/tests/test_phase3_router.py` (lane2 selection + lane3 escalation + no-escalation failure)
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase3_router.py` (PASS)
- **Status:** DONE

### P3.2 — Provider health checks / capability probing
- **Task ID:** P3.2
- **Title:** Health checks drive routing; structured failures
- **Scope:**
  - Allowed: router module + tests + telemetry schema wiring
- **Acceptance criteria:**
  - Health checks support: missing model, auth failure, timeout.
  - Telemetry includes chosen lane/provider/model and fallback used.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Implementation:
    - `dysruption_cva/modules/router.py` (`default_health_check` + timeout/error normalization)
  - Tests:
    - `dysruption_cva/tests/test_phase3_router.py` (missing model, auth missing, timeout normalization)
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase3_router.py` (PASS)
- **Status:** DONE

### P3.3 — Wire router into LLM lane execution
- **Task ID:** P3.3
- **Title:** LLM lane uses router output; artifacts include routing details
- **Scope:**
  - Allowed: `dysruption_cva/modules/api.py`, `dysruption_cva/modules/judge_engine.py`, router module, tests
- **Acceptance criteria:**
  - Lane 2 first where configured; escalate to Lane 3 only when allowed.
  - Artifacts record lane/model/reason.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Wiring:
    - `dysruption_cva/modules/api.py` (routes model selection and persists routing in verdict + telemetry)
    - `dysruption_cva/modules/schemas.py` (adds optional `RunTelemetry.router`)
  - Tests:
    - `dysruption_cva/tests/test_tribunal_integration_intent_trigger_webhook.py` (stubs router; asserts routed model used + persisted)
  - Verification run:
    - `python -m pytest -q` (PASS)
- **Status:** DONE

---

## Phase 4 — Self-healing patch loop (opt-in)

### P4.1 — Strict opt-in patch loop controller
- **Task ID:** P4.1
- **Title:** Patch loop with verify/revert; disabled by default
- **Scope:**
  - Allowed: new controller module + tests + minimal API wiring
- **Acceptance criteria:**
  - Disabled by default; hard limits (iterations/files/paths).
  - Apply patch → run tests/lints → revert on failure.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Implementation:
    - `dysruption_cva/modules/self_heal.py` (`run_self_heal_patch_loop`, strict opt-in + revert-on-failure)
  - Minimal wiring:
    - `dysruption_cva/modules/api.py` (opt-in hook; no-op unless enabled + patches + verify cmd)
  - Tests:
    - `dysruption_cva/tests/test_phase4_self_heal_patch_loop.py` (disabled-by-default, success, revert)
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase4_self_heal_patch_loop.py` (PASS)
    - `python -m pytest -q` (PASS)
- **Status:** DONE

### P4.2 — Audit artifacts per iteration
- **Task ID:** P4.2
- **Title:** Persist diffs, hashes, commands, exit codes per iteration
- **Scope:**
  - Allowed: artifact writer + tests
- **Acceptance criteria:**
  - Persist proposed diff, applied diff hash, test cmd + exit code, final status under run-id.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Per-iteration artifacts under `{RUN_ARTIFACTS_ROOT}/{run_id}/self_heal/iter_{NN}/`:
    - `proposed_patch_diff.txt` + `proposed_patch_diff_sha256.txt`
    - `patched_files.json`
    - `pre_hashes.json` + `post_hashes.json`
    - `verify_command.json`, `verify_stdout.txt`, `verify_stderr.txt`, `verify_exit_code.txt`
    - `result.json` (timestamp, success, reverted)
  - Test asserts artifact existence:
    - `dysruption_cva/tests/test_phase4_self_heal_patch_loop.py`
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase4_self_heal_patch_loop.py` (PASS)
    - `python -m pytest -q` (PASS)
- **Status:** DONE

---

## Phase 5 — Provider cost primitives (caching + batch)

### P5.1 — Stable prefix caching primitive
- **Task ID:** P5.1
- **Title:** Explicit stable prefix; cache intent + observed status in telemetry
- **Scope:**
  - Allowed: provider adapter layer + telemetry schema + tests
- **Acceptance criteria:**
  - Stable prefix defined and sent cache-friendly where supported.
  - Telemetry records cache intent/status.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Implementation:
    - `dysruption_cva/modules/judge_engine.py` (stable-prefix split: system=stable, user=variable)
    - `dysruption_cva/modules/provider_adapter.py` (`build_messages_with_stable_prefix`)
    - `dysruption_cva/modules/schemas.py` (telemetry cache intent fields)
    - `dysruption_cva/modules/api.py` (telemetry: cache intent/status)
  - Tests:
    - `dysruption_cva/tests/test_phase5_provider_cost_primitives.py` (asserts stable-prefix split message structure)
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase5_provider_cost_primitives.py` (PASS)
    - `python -m pytest -q` (PASS)
- **Status:** DONE

### P5.2 — Batch request primitive
- **Task ID:** P5.2
- **Title:** Batch prompts where supported; fallback to single-call
- **Scope:**
  - Allowed: provider adapter layer + telemetry schema + tests
- **Acceptance criteria:**
  - Deterministic mapping of N prompts to N responses.
  - Telemetry records batch size/mode/per-item latency.
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Implementation:
    - `dysruption_cva/modules/provider_adapter.py` (`acompletion_batch` with deterministic mapping)
    - `dysruption_cva/modules/schemas.py` (telemetry: batch size/mode/per-item latency optional fields)
    - `dysruption_cva/modules/api.py` (telemetry: best-effort batch rollups)
  - Tests:
    - `dysruption_cva/tests/test_phase5_provider_cost_primitives.py` (batch deterministic order)
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_phase5_provider_cost_primitives.py` (PASS)
    - `python -m pytest -q` (PASS)
- **Status:** DONE

---

## Phase 6 — Vibecoder UI (Next.js/Tailwind) — Single-screen dashboard

### P6.1 — Fetch + model tribunal telemetry (read-only)
- **Task ID:** P6.1
- **Title:** Add diagnostics fetch to UI (telemetry/routing/cache/batch)
- **Scope:**
  - Allowed: `dysruption-ui/lib/api.ts`, `dysruption-ui/lib/types.ts`, new tests under `dysruption-ui/__tests__/`
  - Not allowed: new pages/routes, backend behavior changes, auth changes
- **Acceptance criteria:**
  - Add a new read-only UI fetch that retrieves per-run tribunal payload from `GET /api/verdicts/{run_id}`.
  - Define minimal TS types for the subset the UI needs (at least `telemetry.coverage`, `telemetry.router`, `telemetry.cache`, `telemetry.latency`).
  - Must be resilient to missing fields/older payloads (treat as `unknown` / `null` without throwing).
  - The fetch must not require any tokens/headers.
- **Verification steps:**
  - `cd dysruption-ui; npm test`
- **Evidence:**
- **Evidence:**
  - Added minimal telemetry + payload types:
    - `dysruption-ui/lib/types.ts`
  - Added best-effort diagnostics fetch:
    - `dysruption-ui/lib/api.ts` (`fetchVerdictsPayload`)
  - Verification run:
    - `cd dysruption-ui; npm test` (PASS)
- **Status:** DONE

### P6.2 — Diagnostics panel (telemetry → badges)
- **Task ID:** P6.2
- **Title:** Render run diagnostics (coverage/routing/cache/batch) on the existing dashboard
- **Scope:**
  - Allowed: `dysruption-ui/app/page.tsx`, new component(s) in `dysruption-ui/components/`
  - Not allowed: new screens, modals, filters, or additional navigation
- **Acceptance criteria:**
  - Add a single new section within the existing results area (same page) titled “Run Diagnostics”.
  - Map at minimum these backend fields to visible UI values:
    - Coverage: `fully_covered_percent_of_changed`, `changed_files_total`, `changed_files_fully_covered_count`, `header_covered_count`, `forced_files_count`.
    - Routing: `router.lane_used`, `router.provider`, `router.model`, and whether `fallback_chain` is non-empty.
    - Cache: `cache.cached_vs_uncached`, `cache.intent`, `cache.provider_cache_signal`.
    - Batch: `latency.lane2_llm_batch_size`, `latency.lane2_llm_batch_mode` (and per-item latency if present).
  - If telemetry is unavailable, show a compact “Diagnostics unavailable” placeholder (no errors/toasts).
  - UI must use existing Tailwind tokens/colors already present in the project.
- **Verification steps:**
  - `cd dysruption-ui; npm test`
- **Evidence:**
- **Evidence:**
  - New components:
    - `dysruption-ui/components/RunDiagnostics.tsx`
    - `dysruption-ui/components/CoverageNotesStrip.tsx`
  - Dashboard wiring:
    - `dysruption-ui/app/page.tsx` (renders “Run Diagnostics” and “Coverage Notes” in results)
  - Tests:
    - `dysruption-ui/__tests__/RunDiagnostics.test.tsx`
    - `dysruption-ui/__tests__/CoverageNotesStrip.test.tsx`
  - Verification run:
    - `cd dysruption-ui; npm test` (PASS)
- **Status:** DONE

### P6.3 — Cancel run (safe stop)
- **Task ID:** P6.3
- **Title:** Add Cancel control while a run is in progress
- **Scope:**
  - Allowed: `dysruption-ui/app/page.tsx`, `dysruption-ui/lib/api.ts`, small component additions
  - Not allowed: backend changes
- **Acceptance criteria:**
  - When `isRunning` is true and `currentRunId` exists, show a “Cancel” button.
  - On cancel: call `cancelRun(runId)`, stop websocket, stop polling, transition to a non-running UI state, and display a toast confirming cancellation.
  - If cancel fails: keep run running and show a toast with the error.
- **Verification steps:**
  - `cd dysruption-ui; npm test`
- **Evidence:**
- **Evidence:**
  - UI wiring:
    - `dysruption-ui/app/page.tsx` (Cancel button shown only while running; stops WS/polling; toast on success/failure)
  - API:
    - `dysruption-ui/lib/api.ts` (`cancelRun` used)
  - Test:
    - `dysruption-ui/__tests__/DashboardCancel.test.tsx`
  - Verification run:
    - `cd dysruption-ui; npm test` (PASS)
- **Status:** DONE

### P6.4 — Partial/skipped explanation strip (no new workflow)
- **Task ID:** P6.4
- **Title:** Explain partial coverage/skips using telemetry (read-only)
- **Scope:**
  - Allowed: `dysruption-ui/app/page.tsx`, new component(s)
  - Not allowed: new pages, new “fix flows”, or backend changes
- **Acceptance criteria:**
  - When telemetry indicates incomplete coverage (e.g., `skip_reasons` non-empty or `fully_covered_percent_of_changed` < 100), show a small “Coverage Notes” strip in results.
  - Render a short, readable summary (counts by reason code), without listing every file unless the list is very small.
  - No new user actions required; this is informational only.
- **Verification steps:**
  - `cd dysruption-ui; npm test`
- **Evidence:**
- **Evidence:**
  - UI:
    - `dysruption-ui/components/CoverageNotesStrip.tsx` (groups `skip_reasons` by reason code; avoids long file lists)
    - `dysruption-ui/app/page.tsx` (shows strip when telemetry indicates incomplete coverage)
  - Test:
    - `dysruption-ui/__tests__/CoverageNotesStrip.test.tsx`
  - Verification run:
    - `cd dysruption-ui; npm test` (PASS)
- **Status:** DONE

---

## Tree-sitter operational requirement

### TS.1 — Detect Tree-sitter active vs fallback
- **Task ID:** TS.1
- **Title:** Tree-sitter mode detection with explicit test
- **Scope:**
  - Allowed: `dysruption_cva/modules/ts_imports.py` and tests
- **Acceptance criteria:**
  - Provide a programmatic check that reports whether Tree-sitter is active.
  - Add a test that proves detection works (even if the environment is fallback).
- **Verification steps:**
  - `python -m pytest -q`
- **Evidence:**
  - Added `get_tree_sitter_status()` in `dysruption_cva/modules/ts_imports.py`
  - Test:
    - `dysruption_cva/tests/test_treesitter_status.py`
  - Verification run:
    - `python -m pytest -q dysruption_cva/tests/test_treesitter_status.py` (PASS)
- **Status:** DONE
