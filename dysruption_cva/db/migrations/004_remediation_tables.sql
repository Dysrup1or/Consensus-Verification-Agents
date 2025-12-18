-- Migration 004: Autonomous Remediation Agent Tables
-- Created: 2025-12-17
-- Description: Adds tables for autonomous remediation tracking

-- Remediation runs (one per failed verification run)
CREATE TABLE IF NOT EXISTS remediation_runs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    total_issues_detected INTEGER DEFAULT 0,
    total_fixes_attempted INTEGER DEFAULT 0,
    total_fixes_applied INTEGER DEFAULT 0,
    total_fixes_reverted INTEGER DEFAULT 0,
    final_health_state TEXT,
    abort_reason TEXT,
    autonomy_level TEXT DEFAULT 'full',
    max_iterations INTEGER DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_remediation_runs_run_id ON remediation_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_remediation_runs_status ON remediation_runs(status);
CREATE INDEX IF NOT EXISTS idx_remediation_runs_started ON remediation_runs(started_at);

-- Individual issues detected from verdict
CREATE TABLE IF NOT EXISTS remediation_issues (
    id TEXT PRIMARY KEY,
    remediation_run_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    file_path TEXT,
    line_start INTEGER,
    line_end INTEGER,
    description TEXT NOT NULL,
    detailed_message TEXT,
    auto_fixable INTEGER DEFAULT 0,
    fix_confidence REAL DEFAULT 0.0,
    source_criterion_id INTEGER,
    source_judge TEXT,
    source_violation_id TEXT,
    root_cause_id TEXT,
    is_symptom INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (remediation_run_id) REFERENCES remediation_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_remediation_issues_run ON remediation_issues(remediation_run_id);
CREATE INDEX IF NOT EXISTS idx_remediation_issues_category ON remediation_issues(category);
CREATE INDEX IF NOT EXISTS idx_remediation_issues_severity ON remediation_issues(severity);
CREATE INDEX IF NOT EXISTS idx_remediation_issues_file ON remediation_issues(file_path);

-- Root cause analysis results
CREATE TABLE IF NOT EXISTS remediation_root_causes (
    id TEXT PRIMARY KEY,
    remediation_run_id TEXT NOT NULL,
    primary_issue_id TEXT NOT NULL,
    primary_description TEXT,
    symptom_issue_ids TEXT,  -- JSON array
    affected_files TEXT,     -- JSON array
    fix_order TEXT,          -- JSON array of issue IDs
    confidence REAL DEFAULT 0.5,
    analysis_method TEXT DEFAULT 'pattern_match',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (remediation_run_id) REFERENCES remediation_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (primary_issue_id) REFERENCES remediation_issues(id)
);
CREATE INDEX IF NOT EXISTS idx_remediation_root_causes_run ON remediation_root_causes(remediation_run_id);

-- Fix attempts
CREATE TABLE IF NOT EXISTS remediation_fixes (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    remediation_run_id TEXT,
    iteration INTEGER NOT NULL DEFAULT 1,
    strategy TEXT DEFAULT 'single_file',
    approval_level TEXT DEFAULT 'confirm',
    approved_by TEXT,
    approved_at TEXT,
    rejection_reason TEXT,
    patch_content TEXT,      -- JSON with patches
    confidence REAL DEFAULT 0.5,
    requires_review INTEGER DEFAULT 1,
    breaking_change INTEGER DEFAULT 0,
    llm_model TEXT,
    llm_tokens_used INTEGER,
    generation_time_ms INTEGER,
    sandbox_result TEXT,
    sandbox_output TEXT,
    status TEXT DEFAULT 'pending',
    applied INTEGER DEFAULT 0,
    applied_at TEXT,
    verified INTEGER DEFAULT 0,
    verification_result TEXT,
    verification_output TEXT,
    reverted INTEGER DEFAULT 0,
    reverted_at TEXT,
    revert_reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (issue_id) REFERENCES remediation_issues(id) ON DELETE CASCADE,
    FOREIGN KEY (remediation_run_id) REFERENCES remediation_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_remediation_fixes_issue ON remediation_fixes(issue_id);
CREATE INDEX IF NOT EXISTS idx_remediation_fixes_run ON remediation_fixes(remediation_run_id);
CREATE INDEX IF NOT EXISTS idx_remediation_fixes_status ON remediation_fixes(status);

-- Pattern library for learned fixes
CREATE TABLE IF NOT EXISTS remediation_patterns (
    id TEXT PRIMARY KEY,
    issue_signature TEXT NOT NULL UNIQUE,
    category TEXT,
    fix_template TEXT,
    example_diff TEXT,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_confidence REAL DEFAULT 0.5,
    last_used TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_remediation_patterns_sig ON remediation_patterns(issue_signature);
CREATE INDEX IF NOT EXISTS idx_remediation_patterns_category ON remediation_patterns(category);

-- Rate limiting state
CREATE TABLE IF NOT EXISTS remediation_rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_start TEXT NOT NULL,
    window_type TEXT NOT NULL,  -- 'hourly' or 'daily'
    fixes_count INTEGER DEFAULT 0,
    reverts_count INTEGER DEFAULT 0,
    cooldown_until TEXT,
    project_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_remediation_rate_window ON remediation_rate_limits(window_type, window_start);

-- Immutable audit log
CREATE TABLE IF NOT EXISTS remediation_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    remediation_run_id TEXT,
    action TEXT NOT NULL,
    details TEXT,  -- JSON with additional info
    actor TEXT DEFAULT 'agent',
    FOREIGN KEY (remediation_run_id) REFERENCES remediation_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_remediation_audit_ts ON remediation_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_remediation_audit_run ON remediation_audit_log(remediation_run_id);
CREATE INDEX IF NOT EXISTS idx_remediation_audit_action ON remediation_audit_log(action);

-- File backups for rollback
CREATE TABLE IF NOT EXISTS remediation_file_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fix_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    original_content BLOB,
    original_hash TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (fix_id) REFERENCES remediation_fixes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_remediation_backups_fix ON remediation_file_backups(fix_id);

-- Kill switch state (single row table)
CREATE TABLE IF NOT EXISTS remediation_kill_switch (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active INTEGER DEFAULT 0,
    activated_at TEXT,
    activated_by TEXT,
    reason TEXT
);
INSERT OR IGNORE INTO remediation_kill_switch (id, active) VALUES (1, 0);
