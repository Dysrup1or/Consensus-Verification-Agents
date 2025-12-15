-- Invariant Sentinel (CVA) - Monitor job queue (continuous monitoring)
-- Target: PostgreSQL

CREATE TABLE IF NOT EXISTS monitor_jobs (
  id UUID PRIMARY KEY,
  repo_branch_id UUID NOT NULL REFERENCES repo_branches(id) ON DELETE CASCADE,
  commit_sha TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','running','completed','failed')),
  run_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  locked_at TIMESTAMPTZ,
  locked_by TEXT,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_monitor_jobs_status_created_at ON monitor_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_monitor_jobs_repo_branch_created_at ON monitor_jobs(repo_branch_id, created_at DESC);
