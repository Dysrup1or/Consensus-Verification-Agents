# Invariant Vision Document

> **The Canonical Reference for Dysruption CVA Development**
>
> Last Updated: December 17, 2025

---

## Table of Contents

1. [Mission](#mission)
2. [Core Principles](#core-principles)
3. [Current System Status](#current-system-status)
4. [Architecture](#architecture)
5. [Implementation Roadmap](#implementation-roadmap)
6. [Technical Specifications](#technical-specifications)
7. [Success Metrics](#success-metrics)
8. [UI Direction (Canonical)](#ui-direction-canonical)
9. [UI Testing Plan (Canonical)](#ui-testing-plan-canonical)
10. [Canonical Docs Index](#canonical-docs-index)

---

## Mission

The Dysruption Consensus Verifier Agent (CVA) is the foundation for **autonomous self-improving software systems**.

It is not a linter. It is not a test runner. It is not a static analyzer.

**Invariant is the first step toward programs that build and fix themselves.**

---

## Core Principles

### 1. Universal Verification
CVA works on **any codebase**, against **any specification**.
- Not limited to specific languages or frameworks
- Spec-driven, not hardcoded rules
- Adaptable to any domain

### 2. Self-Verification is Validation
If CVA cannot analyze its own codebase, it cannot be trusted.
- CVA regularly verifies itself against its own spec
- Self-verification is a feature, not a bug

### 3. Persistent Vigilance
CVA is designed for continuous operation.
- Runs on every commit, PR, or scheduled interval
- Catches regressions before production
- **Goal: Persistent error detection and notification**

### 4. Multi-Model Consensus
No single AI model dominates verification decisions.
- Multiple independent LLM judges (Claude, DeepSeek, Gemini)
- Consensus or majority voting prevents bias
- Security judge has veto authority

### 5. Transparent Reasoning
All judgments must be explainable.
- Every score includes justification
- Issues identified with line numbers
- Actionable suggestions guide remediation

### 6. Fidelity Over Leniency
When in doubt, be honest about what you see.
- False positives are recoverable
- False negatives cause production incidents
- Evidence-based scoring only

### 7. Collaborative Self-Improvement
CVA helps developers fix issues, not just flag them.
- Actionable remediation guidance
- Generates patches when possible
- Iterative refinement until passing

---

## Current System Status

### ✅ Implemented Features (Production Ready)

| Component | Status | Details |
|-----------|--------|---------|
| **Multi-Judge Tribunal** | ✅ Complete | 3 judges: Architect (Claude), Security (DeepSeek), User Proxy (Gemini) |
| **Veto Protocol** | ✅ Complete | Security FAIL with >80% confidence = final FAIL |
| **Static Analysis** | ✅ Complete | Pylint + Bandit with fail-fast on critical issues |
| **FastAPI Backend** | ✅ Complete | 32 endpoints including REST + WebSocket |
| **CLI Mode** | ✅ Complete | `python cva.py --dir . --spec spec.txt` |
| **Watch Mode** | ✅ Complete | Smart 3-second debounce, incremental verification |
| **API Mode** | ✅ Complete | `/run`, `/status`, `/verdict`, `/prompt`, `/ws` |
| **File Watcher v2** | ✅ Complete | Dirty file tracking, FileTree Pydantic models |
| **Dependency Resolution** | ✅ Complete | Python AST + TypeScript import resolution |
| **Security Modules** | ✅ Complete | Path validation, prompt sanitization, rate limiting |
| **SARIF Export** | ✅ Complete | Standard format for IDE/CI integration |
| **RAG Integration** | ✅ Complete | Semantic file selection via embeddings |
| **Self-Heal Loop** | ✅ Complete | Patch generation with rollback support |
| **GitHub Webhooks** | ✅ Complete | Push/PR event handling with signature verification |
| **Telemetry** | ✅ Complete | Coverage, cost, latency, cache tracking |
| **Test Suite** | ✅ Complete | 410 tests, 99.5% pass rate |

### 📊 System Metrics (as of December 17, 2025)

| Metric | Value |
|--------|-------|
| Total Python Modules | 29 |
| Lines of Code | ~24,606 |
| Test Count | 410 |
| Test Pass Rate | 99.5% (407/410) |
| API Endpoints | 32 |
| Security Vulnerabilities (HIGH) | 0 |
| Security Vulnerabilities (MEDIUM) | 1 (intentional) |

### 🟡 Partially Implemented

| Component | Status | Remaining Work |
|-----------|--------|----------------|
| **Judge Marketplace** | 🟡 Partial | Core plugin system + tests exist; remaining: default runtime wiring + UI surfacing/config |
| **Custom Workflows** | 🟡 Partial | Predefined workflows work, user-defined pending |
| **IDE Integration** | 🟡 Partial | SARIF export works, VS Code extension pending |

### 🔴 Not Yet Implemented

| Component | Priority | Description |
|-----------|----------|-------------|
| **Workflow Composition** | P1 | Chain multiple workflows (lint → security → full) |
| **VS Code Extension** | P2 | Real-time diagnostics in editor |
| **RLHF Feedback Loop** | P3 | Learn from human corrections |
| **Autonomous Self-Healing** | P3 | Fully automated fix application |

---

## Architecture

### Multi-Judge Tribunal Flow

```
┌─────────────────┐
│  Specification  │
│  (Any Format)   │
└────────┬────────┘
         │
┌────────▼────────┐
│     Parser      │
│ (Gemini Flash)  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐ ┌───────────┐
│Claude │ │DeepSeek│ │  Gemini   │
│Sonnet │ │  V3   │ │ 2.5 Pro   │
│       │ │(VETO) │ │           │
└───┬───┘ └───┬───┘ └─────┬─────┘
    │         │           │
    └────┬────┴───────────┘
         │
┌────────▼────────┐
│    Consensus    │
│   (2/3 + Veto)  │
└────────┬────────┘
         │
┌────────▼────────┐
│     Verdict     │
│ PASS/FAIL/VETO  │
└─────────────────┘
```

### API Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
├─────────────────────────────────────────────────────────────┤
│  Core Endpoints           │  Tribunal API                   │
│  ─────────────            │  ────────────                   │
│  POST /run                │  POST /api/intent               │
│  GET  /status/{id}        │  POST /api/trigger_scan         │
│  GET  /verdict/{id}       │  GET  /api/verdicts/{id}        │
│  GET  /prompt/{id}        │  POST /api/retry/{id}           │
│  WS   /ws/{id}            │                                 │
├─────────────────────────────────────────────────────────────┤
│  Config API               │  Monitor API                    │
│  ──────────               │  ───────────                    │
│  GET/POST repo_connections│  POST /api/monitor/enqueue      │
│  GET/POST branches        │  GET  /api/monitor/runs         │
│  GET/POST constitution    │  POST /api/webhooks/github      │
├─────────────────────────────────────────────────────────────┤
│  Health                   │  Upload                         │
│  ───────                  │  ───────                        │
│  GET /health (200 always) │  POST /upload (multipart)       │
│  GET /ready  (503 if not) │                                 │
└─────────────────────────────────────────────────────────────┘
```

### Watch Mode Flow (Core Vision)

```
┌─────────────────────────────────────────────────────────────┐
│                DEVELOPER / AI AGENT                          │
│              (Creating/editing files)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼ File changes detected
┌─────────────────────────────────────────────────────────────┐
│               FILE WATCHER (watcher_v2.py)                   │
│  • Smart 3-second debounce (resets on each save)            │
│  • Dirty file tracking for incremental scans                │
│  • Respects .gitignore and ignore patterns                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼ Triggers workflow
┌─────────────────────────────────────────────────────────────┐
│                   WORKFLOW SELECTOR                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ PREDEFINED   │ │ CANONICAL    │ │ CUSTOM (Future)      │ │
│  │              │ │ DOC VERIFY   │ │                      │ │
│  │ • security   │ │ • spec.txt   │ │ • User-defined       │ │
│  │ • style      │ │ • openapi    │ │ • Project-specific   │ │
│  │ • coverage   │ │ • ARCH.md    │ │                      │ │
│  │ • lint       │ │              │ │                      │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  TRIBUNAL ENGINE                             │
│  Static Analysis → RAG Selection → Multi-Judge → Consensus  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FEEDBACK LOOP                             │
│  • REPORT.md generation     • SARIF export                  │
│  • WebSocket notifications  • CI/CD status checks           │
│  • Self-heal suggestions    • IDE diagnostics (future)      │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Foundation ✅ COMPLETE

- [x] Multi-judge tribunal with 3 LLM judges
- [x] Veto protocol (Security FAIL >80% = final FAIL)
- [x] Static analysis integration (pylint + bandit)
- [x] FastAPI backend with 32 endpoints
- [x] WebSocket real-time streaming
- [x] Watch mode with smart debounce
- [x] Security modules (path validation, prompt sanitization)
- [x] SARIF export for standard tooling
- [x] RAG-powered file selection
- [x] Self-heal patch generation
- [x] GitHub webhook integration
- [x] 410+ tests with 99.5% pass rate

### Phase 2: Enhanced Workflows (Current Focus)

- [ ] **P1: Workflow Composition** - Chain workflows (lint → security → full)
- [ ] **P1: Judge Marketplace (Wiring + UI)** - Pluggable custom judges (core implemented; needs default wiring + UI surfacing)
- [ ] **P2: Custom Workflow DSL** - User-defined verification workflows
- [ ] **P2: Incremental Verification** - Only re-verify affected criteria

### Phase 3: Developer Experience

- [ ] **P2: VS Code Extension** - Real-time diagnostics in editor
- [ ] **P2: GitHub App** - Native PR integration with status checks
- [ ] **P3: Dashboard UI** - Web-based run monitoring and configuration

### Phase 4: Autonomous Operations

- [ ] **P3: RLHF Feedback Loop** - Learn from human corrections
- [ ] **P3: Autonomous Self-Healing** - Auto-apply verified patches
- [ ] **P3: Specification Drift Detection** - Alert when code diverges from spec

### Vision State: Self-Improving Programs

```
Today (Implemented):
  1. CVA verifies code against spec
  2. CVA identifies issues and suggests fixes
  3. Human implements fixes
  4. CVA re-verifies until passing

Tomorrow (Phase 2-3):
  1. CVA verifies code against spec
  2. CVA generates patches automatically
  3. AI agent applies patches (with human approval)
  4. CVA re-verifies in a loop
  5. Human reviews final changes

Future (Phase 4):
  1. CVA monitors codebase continuously
  2. CVA detects specification drift
  3. CVA generates and applies fixes autonomously
  4. CVA verifies its own fixes
  5. Human reviews at milestones only
  6. Programs that maintain themselves
```

---

## Technical Specifications

### Models Configuration

| Role | Model | Purpose |
|------|-------|---------|
| Extraction | `gemini/gemini-2.0-flash` | Parse spec into invariants |
| Architect | `anthropic/claude-sonnet-4-20250514` | Design, patterns, logic |
| Security | `deepseek/deepseek-chat` | Vulnerabilities, VETO authority |
| User Proxy | `gemini/gemini-2.5-pro-preview-06-05` | Spec alignment, UX |
| Remediation | `openai/gpt-4o-mini` | Patch generation |

### Environment Variables

```bash
# Required
GOOGLE_API_KEY         # Gemini (extraction + user proxy)
ANTHROPIC_API_KEY      # Claude (architect judge)
DEEPSEEK_API_KEY       # DeepSeek (security judge)
OPENAI_API_KEY         # GPT-4o-mini (remediation)

# Production
CVA_API_TOKEN          # Auth token for API mode
CVA_PRODUCTION=true    # Enable production security
DATABASE_URL           # PostgreSQL for Railway

# Optional
CVA_ALLOWED_ORIGINS    # CORS origins (comma-separated)
CVA_RATE_LIMIT         # Requests per minute (default: 30)
CVA_UPLOAD_ROOT        # File upload directory
CVA_SELF_HEAL_ENABLED  # Enable autonomous patching
```

### Thresholds

| Parameter | Value | Description |
|-----------|-------|-------------|
| `pass_score` | 7 | Minimum score (1-10) for PASS |
| `veto_confidence` | 0.8 | Security veto threshold |
| `consensus_ratio` | 0.67 | 2/3 majority required |
| `chunk_size_tokens` | 8000 | Max tokens per LLM call |
| `debounce_seconds` | 3.0 | Watch mode debounce |

### Output Artifacts

| File | Format | Purpose |
|------|--------|---------|
| `verdict.json` | JSON | Machine-readable for CI/CD |
| `REPORT.md` | Markdown | Human-readable detailed report |
| `verdict.sarif` | SARIF | IDE/tooling integration |
| `run_artifacts/` | Directory | Per-run patches, logs |

---

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| False Positive Rate | <10% | Measuring |
| False Negative Rate | <1% | Measuring |
| Verification Time | <5min/100 files | ✅ Met |
| Judge Agreement | >80% | ✅ Met |
| Fix Success Rate | >70% | Measuring |
| Self-Verification | PASS | ✅ Met |
| Test Pass Rate | >95% | ✅ 99.5% |
| Security Vulnerabilities | 0 HIGH | ✅ 0 |

---

## The End State

A world where:

1. **Specifications are living documents** - not PDFs gathering dust, but active contracts continuously verified

2. **Code quality is autonomous** - not dependent on developer discipline or reviewer availability

3. **Regressions are impossible** - caught instantly, fixed automatically, never reach production

4. **AI assists at every layer** - from writing specs, to verifying code, to fixing issues

5. **Human expertise is amplified** - developers focus on creativity and architecture, not bug hunting

**Invariant is the foundation. The rest is building upward.**

---

*"The best code is code that maintains itself."*

— Dysruption Vision Document, December 2025

---

## UI Direction (Canonical)

Invariant’s UI exists to get users to a fast, trustworthy answer:

- “Does my code work as I described?”
- “What’s broken and what should I do next?”

Current UI status (consolidated from prior UI analysis/roadmap docs):

- The UI is functional and developer-oriented today (real-time updates, artifacts download, analytics).
- The next major product leap is **vibecoder-first onboarding and guided workflows** (reduce setup friction, reach “aha moment” quickly).
- The UI must remain **honest and evidence-based** (see Core Principles: Fidelity, Transparent Reasoning).

Non-negotiable UI quality gate:

- The UI must be testable, stable under mocking, and protected by an executable gate suite (`npm run gate`).

---

## UI Testing Plan (Canonical)

This is the systematic testing plan for the Invariant UI (`dysruption-ui`). It is designed to be **easy to execute**, **unambiguous**, and aligned with the repo’s existing tooling.

### Testing environment context

- UI stack: Next.js 14 (App Router), React 18, TypeScript.
- Unit/integration: Jest + React Testing Library + MSW (request mocking).
- E2E smoke: Playwright.
- Gate suite: `dysruption-ui/package.json` script `gate` runs lint/typecheck/unit/circular-deps/build/e2e.

Format requirements (code review expectations for UI components):

- TypeScript components should be functional components with explicit prop types.
- Client components must declare `"use client"` at the top when they use hooks/events.
- Interactions must be accessible:
  - Buttons have accessible names (`aria-label` or readable text).
  - Inputs/selects have labels or `aria-label`.
  - Expand/collapse controls use `aria-expanded`.
- Side effects belong in hooks (`useEffect`), not in render.
- API boundaries go through the API layer (`lib/api.ts`, `lib/analytics-api.ts`); tests should mock network via MSW rather than manual global fetch stubs.

### Step 1 — Identify interactable components (inventory)

Interactable UI surfaces currently present (based on repo structure and code search):

Pages:

- Dashboard page: `dysruption-ui/app/page.tsx`
- Login page: `dysruption-ui/app/login/page.tsx`
- Analytics page: `dysruption-ui/app/analytics/page.tsx`

Dashboard interactables:

- Header actions: `dysruption-ui/components/dashboard/DashboardHeader.tsx` (Sign out, History toggle)
- Run history: `dysruption-ui/components/dashboard/RunHistoryDropdown.tsx` (select prior run)
- Primary action panel: `dysruption-ui/components/dashboard/PrimaryActionPanel.tsx`
  - Verify button
  - Auto-fix toggle
  - GitHub connect
  - Repo select
  - Branch select
  - GitHub App install link
  - Constitution input examples + textarea
- Progress & results panel: `dysruption-ui/components/dashboard/ProgressResultsPanel.tsx`
  - Cancel run
  - Download report
  - Download patches
- Results section: `dysruption-ui/components/dashboard/ResultsSection.tsx`
  - Download report
  - Start new analysis
  - Patch list actions via PatchDiff
  - Prompt tabs + copy actions via PromptRecommendation

Shared interactables:

- Toast dismiss: `dysruption-ui/components/Toast.tsx`
- Judge card expand/collapse + copy actions: `dysruption-ui/components/Verdict.tsx` and `dysruption-ui/components/CopyButton.tsx`
- Patch copy/download: `dysruption-ui/components/PatchDiff.tsx`
- Constitution examples + textarea: `dysruption-ui/components/ConstitutionInput.tsx`

### Step 2 — Component code review checklist (correct format & correctness)

For each interactable component above, verify:

- Props are typed and the component is deterministic for a given set of props/state.
- Disabled states are respected (e.g., while a run is active):
  - buttons disable correctly
  - selects disable correctly
  - toggles reflect state with `aria-pressed`
- Error paths:
  - API failures surface a user-visible message (Toast or inline error)
  - no unhandled promise rejections
- Accessibility:
  - controls are reachable by keyboard
  - expandable cards have `role="button"` (if not a `<button>`) and respond to Enter/Space
- Browser APIs are guarded or testable:
  - clipboard usage (`navigator.clipboard`) has a fallback or is mockable
  - download uses Blob/URL without throwing in SSR contexts

### Step 3 — Automated tests (what to test, how)

Testing methods to use (standardized):

- Unit/component tests: Jest + React Testing Library.
- Network mocking: MSW for HTTP calls (avoid ad-hoc `global.fetch` mocks).
- Minimal E2E: Playwright smoke tests (do not try to cover all logic end-to-end).

Automation matrix (expected outputs & verification criteria):

1) Dashboard page (`dysruption-ui/app/page.tsx`)

- Expected output:
  - “Verify Invariant” button renders and is disabled until prerequisites are met.
  - Repo and branch selectors render with correct enabled/disabled behavior.
  - Clicking verify triggers a run start path and transitions to “Running Verification…” state.
  - While running, Cancel is visible and functional.
  - After cancel, a toast message indicates cancellation.
- Automated verification:
  - Existing test baseline: `dysruption-ui/__tests__/DashboardCancel.test.tsx`.
  - Add/extend tests to cover:
    - repo selection enables verify
    - missing repo shows a toast
    - cancel failure shows a toast

2) DashboardHeader (`dysruption-ui/components/dashboard/DashboardHeader.tsx`)

- Expected output:
  - Status pill reflects `status` + `isRunning`.
  - History button toggles visual active state.
  - Sign out button visible only when `hasSession=true`.
- Automated verification:
  - Unit test with mocked props:
    - verify conditional rendering
    - verify `onToggleHistory` and `onSignOut` are called

3) PrimaryActionPanel (`dysruption-ui/components/dashboard/PrimaryActionPanel.tsx`)

- Expected output:
  - Verify button disabled when `canStart=false` and enabled when `canStart=true`.
  - When `isRunning=true`, verify button shows “Running Verification…” and other controls are disabled.
  - Auto-fix toggle updates via `onToggleAutoFix` and reflects state via `aria-pressed`.
  - When GitHub is not connected:
    - “Connect GitHub” button shows and triggers `onConnectGitHub`.
  - When GitHub is connected:
    - repo select changes call `onSelectRepo`
    - branch select changes call `onSelectRef`
    - install link appears only when `githubInstallUrl` is available and not already installed.
- Automated verification:
  - Unit tests for all major prop-driven states (connected vs not, running vs idle, install status).

4) ProgressResultsPanel (`dysruption-ui/components/dashboard/ProgressResultsPanel.tsx`)

- Expected output:
  - If `isRunning=true` and `currentRunId` exists, Cancel button renders and triggers `onCancelRun`.
  - Download buttons are disabled unless `reportMarkdown`/`patchDiff` are present.
- Automated verification:
  - Unit test with props (no network).

5) ResultsSection (`dysruption-ui/components/dashboard/ResultsSection.tsx`)

- Expected output:
  - Score/invariant/files/duration cards render correct values.
  - Security veto badge shows when `consensus.veto_triggered=true`.
  - “Download Report” appears only when `reportMarkdown` exists.
  - “Start New Analysis” always triggers `onStartNewAnalysis`.
- Automated verification:
  - Unit test with minimal `consensus` fixture.

6) Verdict (`dysruption-ui/components/Verdict.tsx`)

- Expected output:
  - Renders three judge cards if verdicts are present.
  - Card expands/collapses by click and Enter/Space.
  - Copy buttons exist for verdict/explanation/issues and do not expand the card when clicked.
- Automated verification:
  - Existing test baseline: `dysruption-ui/__tests__/Verdict.test.tsx`.
  - Extend to assert:
    - `aria-expanded` toggles
    - keyboard interaction works

7) PatchDiff (`dysruption-ui/components/PatchDiff.tsx`)

- Expected output:
  - Copy triggers clipboard write and shows “Copied!” feedback.
  - Download creates a `.patch` file name derived from `file_path`.
- Automated verification:
  - Unit tests should mock `navigator.clipboard` and `URL.createObjectURL`.

8) Toast (`dysruption-ui/components/Toast.tsx`)

- Expected output:
  - Appears when message is set, auto-dismisses after `duration`.
  - Dismiss button hides toast immediately and calls `onDismiss`.
  - Uses role `alert` for error/veto and `status` otherwise.
- Automated verification:
  - Use Jest fake timers to test auto-dismiss deterministically.

9) Analytics page (`dysruption-ui/app/analytics/page.tsx`) and analytics components

- Expected output:
  - Period buttons change the selected period and trigger refetch.
  - Refresh button triggers refetch and shows disabled/spinning state while loading.
  - KPI cards render placeholders when data is missing.
  - Charts/tables render without crashing for empty datasets.
- Automated verification:
  - Component-level tests for `KPICard`, `RepoTable`, and the page skeleton.
  - Prefer MSW handlers for analytics endpoints.

### Step 4 — Manual tests (operator checklist)

Manual testing is required for interaction surfaces that are difficult to fully validate in unit tests:

- Login:
  - `http://localhost:3000/login` renders and shows provider buttons.
- Dashboard flow:
  - Connect GitHub → repo list loads → select repo/branch → run starts.
  - Cancel run works and surfaces a toast.
  - Download report/patches produces files.
- Results:
  - Expand/collapse judge cards; copy actions place content on clipboard.
- Analytics:
  - Period switching works and does not break layout.

### Step 5 — Pitfalls and how we prevent them

- Flaky tests due to timers/intervals:
  - Use Jest fake timers for Toast and polling logic.
- Brittle selectors:
  - Use `getByRole` + accessible names; avoid class selectors.
- Network mock drift:
  - Centralize handlers (MSW) and reuse fixtures.
- WebSocket behavior:
  - Unit tests should not rely on real WS; mock the WS client.
- Clipboard/download APIs:
  - Mock `navigator.clipboard` and URL Blob APIs in tests.

### Call to action + deadlines

- By **2025-12-19**: ensure every interactable component listed above has at least one unit test covering its primary interaction and disabled state.
- By **2025-12-23**: extend Playwright smoke tests to cover one authenticated happy-path (if/when a stable auth bypass exists for E2E).
- Ongoing: `npm run gate` must be green for merges.

---

## Canonical Docs Index

This file is the canonical reference. Supporting documents (details, history, and deep dives):

- UI plan and implementation phases: `dysruption_cva/docs/UI_DEVELOPMENT_PLAN.md`
- UI analysis and roadmap: `dysruption_cva/docs/UI_ANALYSIS_AND_ROADMAP.md`
- UI runtime/deploy guidance (Railway): `RAILWAY_INVARIANT_IDIOT_PROOF_GUIDE.md`
- Local startup orchestration: `startup.ps1` and `dysruption_cva/STARTUP.md`
- Local artifact retention (not production): `docs/ARTIFACT_RETENTION.md`
