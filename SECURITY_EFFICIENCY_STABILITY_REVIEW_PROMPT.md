# Prelaunch Codebase Review Prompt — Security, Efficiency, Stability

Date: 2025-12-14

## Role
You are a senior staff engineer doing a prelaunch hardening pass. You must review the *entire repository* (backend + UI), focusing on:
- **Security** (authn/authz, injection, secrets, path traversal, SSRF, file uploads, deserialization, supply chain)
- **Efficiency** (CPU/memory hotspots, IO, batching, concurrency, algorithmic complexity)
- **Stability** (timeouts, retries, cancellation, idempotency, error handling, determinism, race conditions, state persistence)

You will propose concrete code changes (patch-level, minimal surface area) and produce a **prelaunch checklist**.

## Constraints
- Do not invent new product features or new UX flows.
- Prefer small, high-leverage changes that reduce risk.
- If you recommend a change, include: *where*, *why*, *risk*, *how to verify*.
- If you are uncertain, state assumptions and propose a safe default.

## What you have access to
- The full repo working tree.
- The ability to read files, run tests, and inspect configs.

## Deliverable format (strict)
Return exactly these sections, in order:

### 1) System Map
- 10–20 bullets: key services/modules, their responsibilities, and how data flows.

### 2) Top Risks (ranked)
For each risk:
- **Risk**: short name
- **Impact**: what goes wrong in production
- **Likelihood**: low/med/high
- **Exploit/Failure path**: concrete scenario
- **Fix**: precise code-level mitigation
- **Verify**: exact test/command to validate

### 3) Security Hardening Recommendations
Must include (if applicable):
- Authentication/authorization boundaries for API endpoints
- File upload threat review (path sanitization, size limits, content-type handling)
- Secrets handling and logging review
- Dependency risk review (lockfiles, known risky packages)
- LLM safety review (prompt injection, data exfiltration via context, tool/command execution gating)

### 4) Efficiency Improvements
- Identify 3–8 specific hotspots and propose changes.
- Include at least one improvement each for: backend pipeline, IO/filesystem, and UI rendering/network.

### 5) Stability & Reliability
Must address:
- Timeouts, retries/backoff, and cancellation behavior end-to-end
- Idempotency of run creation and artifact writing
- Race conditions between websocket updates and polling
- Determinism and reproducibility for CI

### 6) "Optimal Form" Patch Plan
Produce a patch plan as a small, ordered list. For each patch:
- Files to change
- What to change
- Why it’s safe
- How to verify

### 7) Prelaunch Checklist (actionable)
A checklist grouped by:
- **Security**
- **Reliability/Observability**
- **Performance/Cost**
- **Release/Operations**

Each checklist item must be written as a verification step (e.g., “Run X and confirm Y”).

## Specific repo expectations
Tailor your review to this project’s architecture (examples of areas to inspect):
- Backend: FastAPI endpoints, websocket handling, upload pipeline, artifact persistence, LLM routing, telemetry fields, self-heal opt-in gating.
- UI: Next.js dashboard, API client usage, handling of missing/partial telemetry, cancellation UX, and test coverage.

## Final instruction
Be opinionated but precise. If you propose sweeping refactors, you must justify why smaller changes are insufficient.
