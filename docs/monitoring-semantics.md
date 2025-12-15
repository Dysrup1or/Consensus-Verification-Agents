# Invariant Sentinel — Monitoring Semantics

This document defines the exact, testable semantics for continuous monitoring.

## 1) Triggers

A verification run MUST be scheduled when any of the following occur for a monitored repo/branch:

1. **GitHub push event** to the monitored branch.
2. **GitHub pull_request event** of type `opened`, `reopened`, or `synchronize` targeting the monitored branch.
3. **Polling detects SHA change** (fallback) for the monitored branch.

Non-triggers:
- Tag pushes do not trigger runs.
- Pushes to non-monitored branches do not trigger runs.

## 2) Unit of Work

A run is defined by the tuple:

- `repo_full_name` (e.g., `org/repo`)
- `branch` (e.g., `main`)
- `commit_sha` (40-hex)
- `constitution_version_id`

A run MUST always execute against a specific immutable `commit_sha`.

## 3) Idempotency

If the system receives the same change signal multiple times, it MUST NOT run duplicate work.

Idempotency key:

- `idempotency_key = repo_full_name + ":" + branch + ":" + commit_sha + ":" + constitution_version_id`

Behavior:
- If a run with the same idempotency key already exists in state `queued`, `running`, `completed`, or `failed`, the new request MUST be treated as a no-op.

## 4) Concurrency

Constraints:

- **Per repo/branch:** At most **one** run may be `running` at a time.
- **Global:** A configurable maximum number of concurrent runs MAY be enforced (e.g., `MAX_CONCURRENT_RUNS`).

If a run is already running for a repo/branch and a new change arrives, the new work MUST be queued and subject to coalescing rules.

## 5) Coalescing (Latest SHA Wins)

When multiple changes arrive for the same `repo_full_name + branch` while a run is already `queued` or `running`:

- The system MUST keep at most **one pending** queued job for that repo/branch.
- The pending job MUST always reference the **latest known commit_sha**.

Example:
- Running: `sha=A`
- Events arrive: `sha=B`, `sha=C`
- Result: only one queued job remains, for `sha=C`.

## 6) Failure and Retry

- A job that fails due to transient reasons (network, GitHub API 5xx/timeout) MUST be retried with exponential backoff.
- A job that fails due to permanent reasons (invalid repo, invalid auth, missing constitution) MUST NOT retry automatically.

Retry policy (defaults):
- Max retries: 5
- Backoff: 30s, 60s, 120s, 240s, 480s

## 7) Completion

A run is considered complete when:
- A final verdict is persisted (PASS/FAIL/VETO) and
- All findings are persisted and linked to the run.

## 8) Observability Requirements

For every trigger, the system MUST emit a structured log with:
- `event_type`, `repo_full_name`, `branch`, `commit_sha`, `constitution_version_id`, `idempotency_key`
- `job_id` and `run_id` if created

The system MUST expose enough information to answer:
- “Why did it run?”
- “Why did it not run?”
- “What is it doing right now?”
