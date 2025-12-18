# Startup Script Development Report (Invariant)

Date: 2025-12-17

## Executive summary

A unified, local-development startup orchestrator was added to the repo to reliably start and validate the two primary services:

- **Backend**: FastAPI (`dysruption_cva`) on port `8001`
- **Frontend**: Next.js (`dysruption-ui`) on port `3000`

The script prioritizes **stability**, **fail-fast validation**, **repeatability**, and **clear operator feedback**.

This is explicitly **local-only tooling** and is not intended to be used in production.

## What we built

- New script: `startup.ps1` (repo root)
- Updated guide: `dysruption_cva/STARTUP.md` now recommends using `startup.ps1`

### Supported actions

- `-Action Start` (default): validate, start services, health check, optionally open browser
- `-Action Validate`: run preflight + dependency checks only
- `-Action Stop`: stop processes started by this script (PID file), fallback to port-based stop
- `-Action Status`: show PID file status and quick health probes

### Key options

- `-Detached`: starts services in background and writes `.invariant_pids`
- `-SkipBrowser`: don’t open the browser
- `-BackendOnly` / `-FrontendOnly`
- `-MockMode`: sets `NEXT_PUBLIC_USE_MOCK=true` for the UI process (local)
- `-NoAuth`: sets `CVA_REQUIRE_AUTH=false` for the UI process (local)
- `-NoPortCleanup`: avoids killing processes bound to ports
- `-RunGate`: runs `npm run gate` in `dysruption-ui` during validation

## Requirements (success criteria)

### Functional requirements

1. Starts backend and frontend with a single command on Windows PowerShell.
2. Performs preflight checks before starting (fail fast) unless explicitly skipped.
3. Creates and uses `logs/` for output capture.
4. Confirms service readiness with health checks and bounded timeouts.
5. Supports detached/background mode with a PID file and a stop command.

### Non-functional requirements

- **Stability**: predictable behavior across reruns; minimal operator surprise.
- **Efficiency**: avoid unnecessary installs; avoid full gate suite unless requested.
- **Safety**: do not delete files; do not override env vars; avoid killing ports unless allowed.
- **Clarity**: clear, actionable output with fix hints.

## Potential pitfalls

- **Port cleanup risks**: killing whatever is bound to 8001/3000 can terminate unrelated processes.
  - Mitigation: `-NoPortCleanup` and `ShouldProcess` prompts.
- **Quoting and shell interoperability**: mixing PowerShell + cmd + npm can be fragile.
  - Mitigation: the script uses `cmd.exe` directly for npm execution and env injection.
- **Auth expectations**: production requires NextAuth session; local workflows often don’t.
  - Mitigation: `-NoAuth` is local-only and explicit.
- **LLM keys / model validation**: preflight can be slow or fail if provider keys/models are missing.
  - Mitigation: preflight supports warnings; model validation remains optional.

## Validation performed

- Ran `startup.ps1 -Action Validate` successfully.
- Preflight confirmed: Python, Node, packages, required files, ports free.

## Challenges encountered and mitigations

1. **PowerShell parse error due to nested quoting**
   - Symptom: script failed to parse in the frontend start command.
   - Fix: removed nested `powershell -Command` quoting and used `cmd.exe` command construction.

2. **Ensuring local-only behavior**
   - Risk: operators might attempt to use local orchestration as a production process manager.
   - Mitigation: script header and docs explicitly state local-only intent.

## Evaluation criteria

A startup run is considered successful when:

- `startup.ps1 -Action Validate` exits with code 0.
- `startup.ps1` starts both services and:
  - Backend responds to `http://localhost:8001/` and `http://localhost:8001/docs`
  - Frontend responds to `http://localhost:3000/login`
- Detached mode writes `.invariant_pids` and `-Action Stop` terminates those processes.

## Recommendations for future improvements

- **Production-grade orchestration** (separate track):
  - Standardize on Railway service commands (already present) and add a production runbook.
  - Centralize logs and define compliance retention requirements.
- **Containerization for local parity**:
  - Add `docker compose` for local multi-service startup.
- **Health endpoint standardization**:
  - Add a dedicated backend `/healthz` endpoint (stable semantics).
  - Add a UI `/api/healthz` endpoint that checks proxy → backend.
- **CI alignment**:
  - Run `npm run gate` in CI and gate merges.

## Call to action (proposed deadlines)

- By **2025-12-18**: Team adopts `startup.ps1` as the canonical local boot path.
- By **2025-12-19**: Add a short “Production runbook” doc clarifying Railway startup commands and retention.
- By **2025-12-23**: Decide and implement the production-grade solution for retention/logging (separate from local cleanup scripts).
