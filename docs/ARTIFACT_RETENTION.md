# Artifact retention & repository hygiene

This repo produces **high-churn, generated artifacts** during local development (uploads, run outputs, logs, test results, scans). Keeping all outputs forever makes the codebase harder to update, review, and ship.

## Local-only policy (not production)

This document and the provided cleanup tooling are intended for **local developer workstations** and **non-production sandboxes**.

- Do **not** apply these retention/deletion rules to production systems, production logs, or production audit trails.
- Production retention should be handled by a dedicated solution (centralized logging/observability, storage lifecycle policies, and explicit compliance retention requirements).
- For now, treat this repo’s cleanup as **local hygiene only**; we’ll define a separate production-grade retention approach later.

## Goals

- Keep the repository **lean** and **updatable**.
- Keep generated artifacts **out of source control**.
- Keep enough recent output to debug: **retain a small rolling window**.
- Make cleanup **user-driven** (explicit command), and optionally **automatic** (retention on start/end of a run).

## What should be treated as generated output

- Upload staging directories (e.g. `temp_uploads/`, `dysruption_cva/temp_uploads/`).
- Per-run artifacts (e.g. `dysruption_cva/run_artifacts/`).
- Local logs (e.g. `logs/`).
- Test outputs (e.g. Playwright `dysruption-ui/test-results/`).
- Coverage, caches, build output (`__pycache__/`, `.pytest_cache/`, `.next/`, `out/`, `*.tsbuildinfo`).
- Scan/report outputs that can be regenerated (e.g. `*.sarif`, `verification_report.*`, `pytest_results.txt`).

## Best-practice retention strategy

### 1) Default: don’t persist unless needed
- Prefer OS temp locations for transient uploads and intermediate files.
- Persist only what you must to support:
  - debugging,
  - reproducing an issue,
  - a short audit trail.

### 2) Rolling retention (keep N)
- Keep the newest **N** artifacts and delete older ones.
- N should be small and configurable (typical: 2–10).

### 3) Time-based retention (keep for D days)
- Delete artifacts older than **D** days.
- Useful for shared dev boxes / CI machines.

### 4) User-driven cleanup
- Provide an explicit command to prune artifacts.
- Avoid surprising deletions unless the user opted-in.

## Repo-local implementation in this workspace

### `.gitignore` protections
- Root, CVA, and UI `.gitignore` files are updated to ignore common generated artifacts and high-churn folders.

### Cleanup script
- Run (default keep 2): `./cleanup_artifacts.ps1`
- Dry-run: `./cleanup_artifacts.ps1 -WhatIf`
- Keep N instead of 2: `./cleanup_artifacts.ps1 -KeepCount N`
- Behavior:
  - Deletes caches/build outputs
  - Clears upload staging dirs (keeps `.gitkeep`)
  - Keeps newest 2 run folders in `dysruption_cva/run_artifacts/`
  - Keeps newest 2 files in `logs/`
  - Keeps newest 2 top-level report markdown files matching `*REPORT*`, `*READINESS*`, `CVA_RUN_ANALYSIS_*`

Important: Do not run this script on production hosts.

## Recommended next improvements (optional)

- Add a configurable retention setting in `dysruption_cva/config.yaml` (e.g. `artifact_retention_runs: 2`) and enforce it after each completed run.
- Store all generated artifacts under a single ignored root like `.invariant/` to isolate churn and make cleanup predictable.
- In UI, avoid writing large artifacts into the repo; keep them in `test-results/` and similar ignored folders.
