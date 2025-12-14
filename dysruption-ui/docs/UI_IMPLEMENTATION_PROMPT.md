# Dysruption UI — Implementation Prompt (Single-screen Vibecoder Dashboard)

You are implementing UI changes in the existing Next.js (App Router) + Tailwind project under `dysruption-ui/`.

## Hard constraints (do not violate)
- Single screen only: modify the existing dashboard in `app/page.tsx`.
- No new pages/routes, modals, multi-step wizards, filters, or extra navigation.
- Use existing styling approach and tokens already present in the repo (Tailwind classes + the theme colors defined in `tailwind.config.ts`).
- Do not change backend behavior.

## Repo map (use these existing modules)
- Page: `dysruption-ui/app/page.tsx`
- API client: `dysruption-ui/lib/api.ts`
- Types: `dysruption-ui/lib/types.ts`
- Existing components to reuse:
  - `components/StatusBadge.tsx`
  - `components/Verdict.tsx`
  - `components/PatchDiff.tsx`
  - `components/PromptRecommendation.tsx`
  - `components/Toast.tsx`

## Goal
Add read-only “run diagnostics” to the existing results section so users can understand:
- Coverage quality (how much of the changed code was actually analyzed).
- Whether routing escalated (lane/provider/model and fallback chain).
- Cache/batch signals (stable-prefix intent, cached vs uncached, batch size/mode).

Also add a safe “Cancel” control while a run is in progress.

## Data source: tribunal verdict payload
The backend exposes `GET /api/verdicts/{run_id}` returning a JSON payload (or file-backed payload) that includes `telemetry` matching the backend Pydantic schema:
- `telemetry.coverage.*`
- `telemetry.router.*` (optional)
- `telemetry.cache.*`
- `telemetry.latency.*`

This endpoint does not require special headers.

### Required minimal TypeScript shapes
In `lib/types.ts`, add minimal interfaces (only what the UI needs) such as:
- `TelemetryCoverage`:
  - `fully_covered_percent_of_changed: number`
  - `changed_files_total: number`
  - `changed_files_fully_covered_count: number`
  - `header_covered_count: number`
  - `forced_files_count: number`
  - `skip_reasons: Record<string, string>`
- `TelemetryRouter` (optional):
  - `lane_used: string`
  - `provider: string`
  - `model: string`
  - `fallback_chain: Array<Record<string, string>>`
- `TelemetryCache`:
  - `cached_vs_uncached: 'unknown' | 'cached' | 'uncached' | string`
  - `intent?: string | null`
  - `provider_cache_signal?: string | null`
- `TelemetryLatency`:
  - `lane2_llm_batch_size?: number | null`
  - `lane2_llm_batch_mode?: string | null`
  - `lane2_llm_per_item_latency_ms?: number[] | null`
- `RunTelemetry`:
  - `coverage: TelemetryCoverage`
  - `router?: TelemetryRouter | null`
  - `cache: TelemetryCache`
  - `latency: TelemetryLatency`

The enclosing payload shape varies across runs; model it loosely:
- `type VerdictsPayload = { telemetry?: RunTelemetry | null; [key: string]: any }`

### Fetch function
In `lib/api.ts`, add:
- `fetchVerdictsPayload(runId: string): Promise<VerdictsPayload>` calling `GET ${API_BASE}/api/verdicts/${runId}`.
- It must be resilient:
  - If request fails (404/500), return an empty object (or `null`) and let the UI render “Diagnostics unavailable”.
  - Do not throw from UI data fetch for diagnostics.

## UI changes: new results panels (no new screen)
Implement 2 additions inside the existing results section in `app/page.tsx`:

### 1) “Run Diagnostics” section
Create a new component `components/RunDiagnostics.tsx` with props:
- `telemetry: RunTelemetry | null`

Behavior:
- If `telemetry` is null/undefined: render a compact placeholder (“Diagnostics unavailable for this run”).
- Otherwise render a 2×2 (responsive) grid of small cards:
  1. Coverage card:
     - Show `fully_covered_percent_of_changed` (rounded) and `changed_files_fully_covered_count/changed_files_total`.
     - Show `header_covered_count` and `forced_files_count` in small text.
  2. Routing card:
     - If `router` exists: show `lane_used`, `provider`, `model`.
     - Show a small indicator if `fallback_chain.length > 0`.
     - If missing: show “Router: unavailable”.
  3. Cache card:
     - Show `cached_vs_uncached`.
     - Show `intent` and `provider_cache_signal` if present; otherwise show “—”.
  4. Batch card:
     - If `lane2_llm_batch_size` present and > 0: show size and mode.
     - If per-item latencies present: show min/median/max in ms (compute client-side).
     - Otherwise show “Batch: single/unknown”.

Styling:
- Use existing tokens/classes (e.g. `bg-surface`, `border-border`, `text-textMuted`, `text-primary`, `text-success`, `text-warning`, `text-danger`).

### 2) “Coverage Notes” strip (informational)
If coverage is incomplete:
- condition example: `telemetry.coverage.fully_covered_percent_of_changed < 100` OR `Object.keys(skip_reasons).length > 0`

Render a small strip titled “Coverage Notes” that:
- groups `skip_reasons` by reason code and shows counts per reason (e.g. `skipped_external: 12`)
- does not list all file paths unless the total is very small (<= 5)

## Cancel run control
In `app/page.tsx`:
- When `isRunning` and `currentRunId` exists, show a “Cancel” button near the status/progress UI.
- On click:
  - Call `cancelRun(currentRunId)` from `lib/api.ts`.
  - Stop websocket (`wsRef.current?.stop()`), and ensure polling fallback stops naturally by transitioning state.
  - Set a toast message confirming cancellation.
  - Keep UI consistent (do not leave the spinner running).

If cancel fails:
- do not stop the websocket; keep the run running.
- show an error toast.

## Where to fetch telemetry in the page
In `app/page.tsx`, when a run completes (or when loading a historical run):
- After `fetchVerdict(runId)` succeeds, call `fetchVerdictsPayload(runId)` in parallel.
- Store `diagnosticsTelemetry` in state and pass it into `RunDiagnostics`.

## Tests (Jest + RTL)
Add tests under `dysruption-ui/__tests__/`:
- `RunDiagnostics.test.tsx`:
  - renders placeholder when telemetry missing
  - renders key fields when telemetry present
  - renders batch min/median/max correctly for a known list
- `DashboardCancel.test.tsx` (or similar):
  - mock `cancelRun` and assert button appears only while running
  - assert toast updates on success/failure

Run verification:
- `cd dysruption-ui; npm test`

## Done criteria
- No new pages.
- Diagnostics renders on the existing results page, never crashes if data missing.
- Cancel control works end-to-end against the existing backend endpoint.
- Tests pass.
