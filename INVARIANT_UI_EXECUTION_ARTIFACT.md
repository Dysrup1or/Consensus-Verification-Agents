# Invariant UI — Execution Artifact (Temporary Canonical)

> **Purpose:** This file is the temporary canonical “source of truth” for UI + UI-adjacent backend work in this repo.
>
> It reconciles aspirational UI plans with what actually exists in the codebase today, and turns the outcome into an agent-executable phased task list.
>
> **Scope:** `dysruption-ui/` (Next.js UI) + backend endpoints needed to support the UI in `dysruption_cva/`.
>
> **Status snapshot date:** 2025-12-18

---

## 0) Reality Snapshot (What Exists Today)

### UI: already implemented

- **Main dashboard (single page):** `dysruption-ui/app/page.tsx`
  - Orchestrated by `components/dashboard/useCvaRunController.ts`.
  - GitHub import + run initiation + status polling/WS updates.
- **Analytics page:** `dysruption-ui/app/analytics/page.tsx`
  - Uses `dysruption-ui/lib/analytics-api.ts` and `dysruption-ui/components/analytics/*`.
  - Judge performance UI exists (`components/analytics/JudgePerformance.tsx`).
- **Run diagnostics + coverage notes + cancel run:** implemented (per `dysruption-ui/docs/UI_IMPLEMENTATION_PROMPT.md`).
- **Theme provider:** `dysruption-ui/lib/theme.tsx`.
- **API proxy (“BFF”):** UI calls `API_BASE = '/api/cva'` (see `dysruption-ui/lib/api.ts`, `dysruption-ui/lib/analytics-api.ts`).

### Backend: already implemented

- **Judge Marketplace plugin system (real, not conceptual):** `dysruption_cva/modules/judge_marketplace/*`
  - Registry + discovery (`registry.py`), plugin interface (`plugin.py`), models (`models.py`).
  - Tribunal adapter exists (`tribunal_integration.py`).
  - Tests exist (see references in `dysruption_cva/CONSTITUTIONAL_COMPLIANCE_REPORT.md`).
- **Analytics endpoint for judges:** `GET /analytics/judges` implemented in `dysruption_cva/modules/persistence/analytics_api.py` and consumed by UI.

### Important nuance (truthful integration status)

- The **judge marketplace is implemented**, but it is **not wired in as the default judge execution path** in the main `dysruption_cva/modules/tribunal.py` flow.
  - There is a “try marketplace” path in `dysruption_cva/modules/workflows/predefined.py`, but it instantiates `JudgeRegistry()` without loading config/discovery by default.
  - This means: **core marketplace infrastructure exists**, but **runtime wiring + UI surfacing/config** remains.

---

## 1) Plan vs Reality — Gap Matrix

This consolidates the intent in:
- `dysruption_cva/docs/UI_DEVELOPMENT_PLAN.md`
- `dysruption_cva/docs/UI_ANALYSIS_AND_ROADMAP.md`
- `dysruption-ui/docs/UI_IMPLEMENTATION_PROMPT.md`

### A) Route structure

**Planned (docs):** route groups like `(onboarding)/`, `(dashboard)/projects/[projectId]/*`, `settings/*`.

**Reality:** no route groups today.
- Existing routes include:
  - `/` (dashboard): `dysruption-ui/app/page.tsx`
  - `/analytics`: `dysruption-ui/app/analytics/page.tsx`
  - `/login`: `dysruption-ui/app/login/page.tsx`
  - GitHub setup/callback routes under `dysruption-ui/app/github/*`.

**Integration approach:**
- Treat the current dashboard page as “Phase 0 shipping UI”.
- Introduce route groups only when onboarding + projects are implemented, and migrate incrementally.

### B) Design system / tokens

**Planned:** `styles/tokens.css` + Tailwind mapping to semantic CSS variables.

**Reality:**
- No `dysruption-ui/styles/` directory.
- Styling is primarily Tailwind + `dysruption-ui/app/globals.css` + extended colors in `dysruption-ui/tailwind.config.ts`.

**Integration approach:**
- Avoid a big-bang token migration.
- Introduce `styles/tokens.css` only when new onboarding pages/components would otherwise fork styling.

### C) Component architecture

**Planned:** `components/ui/*` (shadcn-style atoms) + `components/features/*`.

**Reality:**
- Feature-centric components exist (`components/dashboard/*`, `components/analytics/*`), but no `components/ui/*` atom library.

**Integration approach:**
- Only extract atoms when multiple screens need the same controls.
- Keep existing components stable; migrate opportunistically.

### D) State management

**Planned:** Zustand for UI state + TanStack Query for server state.

**Reality:**
- No Zustand/TanStack Query in `package.json`.
- State is handled via `useCvaRunController` + local component state; analytics uses manual `fetch`.

**Integration approach:**
- Don’t introduce Zustand/Query until you have:
  - multiple routes needing shared state, or
  - complicated cache/refresh semantics across screens.
- When you do introduce them, start with **analytics** (pure server-state) first.

### E) “Projects dashboard” + `/api/projects`

**Planned:** backend `/api/projects` endpoints + multi-project UI.

**Reality:**
- No backend `/projects` endpoints found outside the docs.
- The UI’s primary unit of work today is a **run**, not a long-lived “project” entity.

**Integration approach:**
- Decide whether a “project” is:
  1) a persisted entity (DB-backed), or
  2) a derived view over `repo + branch + spec`.
- Implement the backend model first; then implement UI.

---

## 2) Canonical Decisions (So We Don’t Thrash)

These are the decisions this artifact treats as canonical until explicitly changed.

1. **Keep the `/api/cva/*` UI proxy**. It is the right place for secrets and future auth.
2. **Keep the current dashboard UX stable** while onboarding/projects are built.
3. **Judge Marketplace is real**. Treat it as an implemented backend subsystem that needs:
   - default runtime wiring (registry load + activation), and
   - UI exposure (inspect/configure/enable).
4. Prefer **incremental refactors** over reorganizing the entire UI folder tree at once.

---

## 3) Execution Phases (Agent-Executable)

### Phase 0 — Documentation alignment (low risk, immediate)

**Goal:** remove contradictions, make docs match reality, and point contributors to this artifact.

**Tasks:**
- Update `dysruption_cva/INVARIANT_VISION.md` to mark Judge Marketplace as implemented, but clarify what remains.
- Add short “this doc is superseded by…” banners to the older UI plan docs.

**Done criteria:**
- No doc claims Judge Marketplace is “missing a plugin system” (it exists).
- Contributors have one canonical starting point.

### Phase 1 — Judge Marketplace: runtime wiring (backend)

**Goal:** the marketplace registry is actually loaded/used at runtime (not only “available”).

**Tasks:**
- Decide authoritative config source (likely `dysruption_cva/config.yaml`).
- Ensure startup loads judge marketplace config, discovers plugins, and activates judges.
- Provide safe failure modes:
  - if plugins fail to load, fall back to current judge execution without crashing.

**Done criteria:**
- A run can execute with marketplace judges enabled without manual per-run registry setup.

### Phase 2 — Judge Marketplace: UI surfacing (minimal viable)

**Goal:** users can see what judges exist and what is active.

**Tasks (UI-first, no extra UX):**
- Add a read-only “Judges” section in the existing analytics page showing:
  - configured judges vs observed performance metrics.
- Add backend endpoint(s) to list configured/available judges and their metadata.

**Done criteria:**
- UI can answer “what judges are installed?” and “which are active?”

### Phase 3 — Onboarding (product UX)

**Goal:** get vibecoders to first successful run faster.

**Tasks:**
- Introduce `(onboarding)/` route group with a minimal wizard.
- Persist onboarding progress.
- Provide spec templates.

**Done criteria:**
- A new user can go from zero → first run without reading docs.

### Phase 4 — Projects (data model + UI)

**Goal:** durable “project” concept with history and settings.

**Tasks:**
- Implement backend project model and `/projects` endpoints.
- Implement `(dashboard)/projects` UI.

**Done criteria:**
- User can manage multiple repos/specs as projects.

### Phase 5 — One-click remediation

**Goal:** safely apply fixes.

**Tasks:**
- Backend: apply patch with guardrails + audit trail.
- UI: preview + apply + rollback affordances.

**Done criteria:**
- User can apply a suggested fix with clear visibility and rollback path.

---

## 4) Research Anchors (Why these choices)

- Next.js App Router supports both server and client data fetching, and explicitly acknowledges community libraries like SWR / React Query for client-component fetching and caching.
  - https://nextjs.org/docs/app/getting-started/fetching-data
- TanStack Query is purpose-built for **server-state** concerns like caching, dedupe, and background refetch.
  - https://tanstack.com/query/latest/docs/framework/react/overview
- Zustand positions itself as a small, fast, hook-based global state solution without provider boilerplate.
  - https://zustand.docs.pmnd.rs/getting-started/introduction

---

## 5) Non-goals (until phases that require them)

- No rewrite of the current dashboard purely for folder structure aesthetics.
- No introduction of a component-atom library until multiple pages force reuse.
- No new “projects” UX until a backend project model exists.

---

## 6) “Next Agent” Prompt (Copy/Paste)

You are an implementation agent working in this repository.

1) Treat this file as canonical.
2) Start with **Phase 0**, then implement **Phase 1**.
3) Maintain backwards compatibility for current `/` dashboard and `/analytics`.
4) Do not introduce new pages unless the phase explicitly calls for it.
5) When you add backend endpoints, also add:
   - minimal tests,
   - schema validation,
   - and documentation updates.

Output requirements:
- For each task, report:
  - what changed,
  - where (file links),
  - how to verify.
