-- Invariant Sentinel (CVA) - Initial schema
-- Target: PostgreSQL

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repo_connections (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider IN ('github')),
  repo_full_name TEXT NOT NULL,
  default_branch TEXT NOT NULL,
  installation_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(provider, repo_full_name)
);

CREATE TABLE IF NOT EXISTS repo_branches (
  id UUID PRIMARY KEY,
  repo_connection_id UUID NOT NULL REFERENCES repo_connections(id) ON DELETE CASCADE,
  branch TEXT NOT NULL,
  is_monitored BOOLEAN NOT NULL DEFAULT TRUE,
  last_seen_sha TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(repo_connection_id, branch)
);

CREATE TABLE IF NOT EXISTS constitution_versions (
  id UUID PRIMARY KEY,
  repo_branch_id UUID NOT NULL REFERENCES repo_branches(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(repo_branch_id, version)
);

CREATE TABLE IF NOT EXISTS runs (
  id UUID PRIMARY KEY,
  repo_branch_id UUID NOT NULL REFERENCES repo_branches(id) ON DELETE CASCADE,
  constitution_version_id UUID NOT NULL REFERENCES constitution_versions(id) ON DELETE RESTRICT,
  commit_sha TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','running','completed','failed')),
  verdict TEXT CHECK (verdict IN ('PASS','FAIL','VETO')),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(repo_branch_id, constitution_version_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS findings (
  id UUID PRIMARY KEY,
  repo_branch_id UUID NOT NULL REFERENCES repo_branches(id) ON DELETE CASCADE,
  run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  severity TEXT NOT NULL,
  invariant_id TEXT,
  file_path TEXT,
  message TEXT NOT NULL,
  suggested_fix TEXT,
  fingerprint TEXT NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL,
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(repo_branch_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_runs_repo_branch_created_at ON runs(repo_branch_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_repo_branch_resolved ON findings(repo_branch_id, resolved_at);
