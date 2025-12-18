# Autonomous Remediation Agent — Full Autonomy

## Executive Summary

The **Autonomous Remediation Agent** is an advanced system that automatically detects, diagnoses, and fixes code issues discovered during CVA verification runs without human intervention. Building upon the existing `self_heal.py` module, this agent elevates the system from a "suggest-and-apply" model to a fully autonomous "detect-plan-fix-verify" closed-loop system.

### Vision Statement

Transform CVA from a verification tool that **reports** problems into an autonomous agent that **resolves** problems while maintaining strict safety guardrails, full auditability, and human-overrideable controls.

---

## Research Summary — Best Practices

### Industry Patterns Applied

#### 1. **Agentic AI Systems (OpenAI Governance Framework)**
- **Bounded Autonomy**: Agent operates within defined safety boundaries
- **Transparency**: All decisions logged and explainable
- **Human Override**: Emergency stop and manual review triggers
- **Accountability**: Clear audit trail for all changes

#### 2. **Site Reliability Engineering (Google SRE)**
- **Error Budgets**: Limit autonomous changes per time window
- **Rollback-First Design**: Every change must be reversible
- **Canary Deployments**: Test fixes in isolation before full application
- **Incident Response Tiers**: Escalation based on severity

#### 3. **Self-Healing Systems (Distributed Systems Patterns)**
- **Heartbeat Monitoring**: Continuous health checks
- **State Watch**: Monitor for drift and anomalies
- **Idempotent Operations**: Safe to retry without side effects
- **Two-Phase Commit**: Prepare → Validate → Apply or Rollback

#### 4. **Automated Remediation (AIOps)**
- **Root Cause Analysis**: Identify underlying issue, not just symptoms
- **Fix Classification**: Categorize fixes by confidence and impact
- **Learning Loop**: Improve fix quality over time
- **Blast Radius Control**: Limit scope of autonomous changes

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     AUTONOMOUS REMEDIATION AGENT                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐         │
│  │  Issue Detector │───▶│ Root Cause Engine │───▶│ Fix Planner      │        │
│  │  (from verdict) │    │ (diagnosis)       │    │ (strategy)       │        │
│  └────────────────┘    └──────────────────┘    └────────┬─────────┘         │
│                                                          │                   │
│                                                          ▼                   │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                      SAFETY CONTROLLER                              │     │
│  │  ┌──────────┐  ┌───────────┐  ┌─────────────┐  ┌───────────────┐  │     │
│  │  │ Approval │  │ Blast     │  │ Rate        │  │ Kill Switch   │  │     │
│  │  │ Gateway  │  │ Radius    │  │ Limiter     │  │ (emergency)   │  │     │
│  │  └──────────┘  └───────────┘  └─────────────┘  └───────────────┘  │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                      │                                       │
│                                      ▼                                       │
│  ┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐         │
│  │  Fix Generator  │───▶│ Sandbox Validator │───▶│ Patch Applicator │        │
│  │  (LLM patches)  │    │ (isolated test)   │    │ (atomic apply)   │        │
│  └────────────────┘    └──────────────────┘    └────────┬─────────┘         │
│                                                          │                   │
│                                                          ▼                   │
│  ┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐         │
│  │  Verify Engine  │◀──│ Rollback Engine   │◀──│ Health Monitor   │        │
│  │  (re-run tests) │    │ (instant revert)  │    │ (post-apply)     │        │
│  └────────────────┘    └──────────────────┘    └──────────────────┘         │
│                                                          │                   │
│                                                          ▼                   │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                     LEARNING & TELEMETRY                            │     │
│  │  ┌──────────┐  ┌───────────┐  ┌─────────────┐  ┌───────────────┐  │     │
│  │  │ Feedback │  │ Pattern   │  │ Confidence  │  │ Audit Log     │  │     │
│  │  │ Loop     │  │ Library   │  │ Calibrator  │  │ (immutable)   │  │     │
│  │  └──────────┘  └───────────┘  └─────────────┘  └───────────────┘  │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Specification

### 1. Issue Detector (`remediation/detector.py`)

**Purpose**: Extract actionable issues from tribunal verdicts

**Inputs**:
- `TribunalVerdict` with failed criteria
- Static analysis results
- Judge feedback (scores, issues, suggestions)

**Outputs**:
- `List[RemediationIssue]` with:
  - `issue_id`: Unique identifier
  - `category`: `security | correctness | style | performance | compatibility`
  - `severity`: `critical | high | medium | low`
  - `file_path`: Affected file
  - `line_range`: Start/end lines
  - `description`: Human-readable issue
  - `auto_fixable`: Boolean confidence assessment
  - `fix_confidence`: 0.0-1.0 probability of successful fix

### 2. Root Cause Engine (`remediation/root_cause.py`)

**Purpose**: Diagnose underlying issues, not just symptoms

**Features**:
- Pattern matching against known issue types
- Dependency chain analysis (what broke what)
- Historical correlation (has this pattern failed before?)
- Multi-file impact assessment

**Outputs**:
- `RootCause` object with:
  - `primary_issue`: The core problem
  - `related_issues`: Symptoms caused by primary
  - `affected_files`: Files that need changes
  - `fix_order`: Recommended fix sequence

### 3. Fix Planner (`remediation/planner.py`)

**Purpose**: Create execution strategy for fixes

**Strategies**:
```python
class FixStrategy(Enum):
    SINGLE_FILE = "single_file"     # One file fix
    MULTI_FILE = "multi_file"       # Coordinated changes
    STAGED = "staged"               # Apply incrementally
    DEPENDENCY_FIRST = "dep_first"  # Fix imports/deps first
```

**Planning Rules**:
1. Security fixes → highest priority
2. Breaking changes → staged deployment
3. Style fixes → batch together
4. Performance → validate with benchmarks

### 4. Safety Controller (`remediation/safety.py`)

**Purpose**: Enforce guardrails on autonomous operations

**Components**:

#### a) Approval Gateway
```python
class ApprovalLevel(Enum):
    AUTO = "auto"           # No approval needed
    REVIEW = "review"       # Logged but auto-applied
    CONFIRM = "confirm"     # Requires explicit confirmation
    MANUAL = "manual"       # Human must apply
```

**Rules**:
| Fix Type | Confidence ≥ 0.9 | Confidence 0.7-0.9 | Confidence < 0.7 |
|----------|------------------|--------------------|--------------------|
| Style | AUTO | AUTO | REVIEW |
| Correctness | REVIEW | CONFIRM | MANUAL |
| Security | CONFIRM | MANUAL | MANUAL |
| Breaking | MANUAL | MANUAL | MANUAL |

#### b) Blast Radius Controller
```python
@dataclass
class BlastRadiusLimits:
    max_files_per_run: int = 10
    max_lines_changed: int = 500
    max_functions_modified: int = 20
    forbidden_paths: List[str] = field(default_factory=lambda: [
        "*.env", "*.secret*", "**/credentials/**",
        "**/config/prod*", "docker-compose.prod.yml"
    ])
```

#### c) Rate Limiter
```python
@dataclass  
class RateLimits:
    max_fixes_per_hour: int = 50
    max_fixes_per_day: int = 200
    max_reverts_before_lockout: int = 5
    cooldown_after_revert_minutes: int = 30
```

#### d) Kill Switch
- Environment variable: `CVA_REMEDIATION_KILL_SWITCH=true`
- File-based trigger: `.cva-remediation-stop`
- API endpoint: `POST /api/remediation/stop`

### 5. Fix Generator (`remediation/generator.py`)

**Purpose**: Generate patches using LLM with specialized prompts

**Models by Fix Type**:
```yaml
llms:
  remediation:
    security_fix:
      model: "anthropic/claude-sonnet-4-20250514"
      temperature: 0.1
      max_tokens: 4096
    correctness_fix:
      model: "openai/gpt-4o"
      temperature: 0.2
    style_fix:
      model: "openai/gpt-4o-mini"
      temperature: 0.3
```

**Prompt Template**:
```
You are an expert code remediation agent. Generate a MINIMAL, TARGETED fix.

## ISSUE
{issue_description}

## ROOT CAUSE
{root_cause_analysis}

## AFFECTED CODE
{relevant_code}

## CONSTRAINTS
- Change ONLY what is necessary
- Preserve existing behavior except for the bug
- Maintain code style consistency
- Add comments explaining non-obvious fixes

## OUTPUT FORMAT
Output valid JSON:
{
  "fix_id": "<uuid>",
  "patches": [
    {
      "file": "<path>",
      "description": "<what this fixes>",
      "diff": "<unified diff>",
      "test_hint": "<how to verify this fix>"
    }
  ],
  "confidence": <0.0-1.0>,
  "requires_review": <boolean>,
  "breaking_change": <boolean>
}
```

### 6. Sandbox Validator (`remediation/sandbox.py`)

**Purpose**: Test fixes in isolation before application

**Validation Steps**:
1. **Syntax Check**: Parse modified files
2. **Type Check**: Run mypy/pyright on changes
3. **Unit Tests**: Run tests touching modified code
4. **Static Analysis**: Re-run linters
5. **Integration Tests**: If configured, run integration suite

**Sandbox Modes**:
```python
class SandboxMode(Enum):
    IN_MEMORY = "memory"      # Virtual filesystem
    TEMP_DIR = "temp"         # Copy to temp directory
    DOCKER = "docker"         # Isolated container
    GIT_WORKTREE = "worktree" # Git worktree isolation
```

### 7. Patch Applicator (`remediation/applicator.py`)

**Purpose**: Atomic patch application with rollback support

**Features**:
- Two-phase commit (prepare → apply)
- File locking during application
- Checksum verification pre/post
- Automatic backup creation

**Application Protocol**:
```
1. PREPARE
   ├── Lock target files
   ├── Create backup snapshots
   ├── Validate patches apply cleanly
   └── Record pre-state checksums

2. APPLY
   ├── Write patched content
   ├── Record post-state checksums
   └── Update change manifest

3. VERIFY
   ├── Run verification command
   └── If PASS → COMMIT, else → ROLLBACK

4. COMMIT/ROLLBACK
   ├── Release locks
   └── Clean up or restore backups
```

### 8. Rollback Engine (`remediation/rollback.py`)

**Purpose**: Instant reversion on failure

**Rollback Levels**:
```python
class RollbackScope(Enum):
    PATCH = "patch"           # Single patch
    ITERATION = "iteration"   # All patches in iteration
    RUN = "run"               # Entire remediation run
    SESSION = "session"       # All runs in session
```

**Rollback Sources**:
1. **Memory backups**: Fast, in-process rollback
2. **File backups**: Stored in artifacts directory
3. **Git stash**: Automatic stash before changes
4. **Git reset**: Hard reset to known good commit

### 9. Health Monitor (`remediation/monitor.py`)

**Purpose**: Post-application health checking

**Checks**:
- Test suite still passes
- No new static analysis warnings
- Application starts successfully
- No performance regression (if benchmarks exist)
- No security vulnerabilities introduced

**Health States**:
```python
class HealthState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"       # Some issues but functional
    UNHEALTHY = "unhealthy"     # Requires rollback
    UNKNOWN = "unknown"         # Can't determine
```

### 10. Learning & Telemetry (`remediation/learning.py`)

**Purpose**: Improve over time

**Feedback Loop**:
```
Fix Applied → Verification → Result
     │                          │
     └──────────────────────────┘
                 │
                 ▼
         Pattern Library
         (successful patterns)
                 │
                 ▼
       Confidence Calibrator
       (adjust fix confidence)
```

**Stored Patterns**:
```python
@dataclass
class FixPattern:
    pattern_id: str
    issue_signature: str      # Hash of issue characteristics
    fix_template: str         # Generalized fix
    success_count: int
    failure_count: int
    avg_confidence: float
    last_used: datetime
```

---

## Database Schema

### New Tables

```sql
-- Remediation runs
CREATE TABLE remediation_runs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, aborted
    total_issues_detected INTEGER DEFAULT 0,
    total_fixes_attempted INTEGER DEFAULT 0,
    total_fixes_applied INTEGER DEFAULT 0,
    total_fixes_reverted INTEGER DEFAULT 0,
    final_health_state TEXT,
    abort_reason TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
CREATE INDEX idx_remediation_runs_run_id ON remediation_runs(run_id);

-- Individual issues detected
CREATE TABLE remediation_issues (
    id TEXT PRIMARY KEY,
    remediation_run_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    file_path TEXT,
    line_start INTEGER,
    line_end INTEGER,
    description TEXT,
    auto_fixable INTEGER DEFAULT 0,
    fix_confidence REAL,
    root_cause_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (remediation_run_id) REFERENCES remediation_runs(id)
);
CREATE INDEX idx_remediation_issues_run ON remediation_issues(remediation_run_id);

-- Fix attempts
CREATE TABLE remediation_fixes (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    strategy TEXT,
    approval_level TEXT,
    patch_content TEXT,
    sandbox_result TEXT,
    applied INTEGER DEFAULT 0,
    applied_at TEXT,
    verified INTEGER DEFAULT 0,
    verification_result TEXT,
    reverted INTEGER DEFAULT 0,
    reverted_at TEXT,
    revert_reason TEXT,
    confidence REAL,
    llm_model TEXT,
    llm_tokens_used INTEGER,
    generation_time_ms INTEGER,
    FOREIGN KEY (issue_id) REFERENCES remediation_issues(id)
);
CREATE INDEX idx_remediation_fixes_issue ON remediation_fixes(issue_id);

-- Pattern library
CREATE TABLE remediation_patterns (
    id TEXT PRIMARY KEY,
    issue_signature TEXT NOT NULL UNIQUE,
    fix_template TEXT,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_confidence REAL,
    last_used TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_remediation_patterns_sig ON remediation_patterns(issue_signature);

-- Rate limiting state
CREATE TABLE remediation_rate_limits (
    id INTEGER PRIMARY KEY,
    window_start TEXT NOT NULL,
    window_type TEXT NOT NULL,  -- hourly, daily
    fixes_count INTEGER DEFAULT 0,
    reverts_count INTEGER DEFAULT 0,
    cooldown_until TEXT
);

-- Audit log (immutable)
CREATE TABLE remediation_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    remediation_run_id TEXT,
    action TEXT NOT NULL,
    details TEXT,
    actor TEXT DEFAULT 'agent',
    FOREIGN KEY (remediation_run_id) REFERENCES remediation_runs(id)
);
CREATE INDEX idx_remediation_audit_ts ON remediation_audit_log(timestamp);
```

---

## API Endpoints

### Control Endpoints

```
POST   /api/remediation/start/{run_id}
       Start autonomous remediation for a failed run
       Body: { "strategy": "auto|staged|manual", "max_iterations": 5 }

POST   /api/remediation/stop/{remediation_run_id}
       Emergency stop of running remediation

POST   /api/remediation/rollback/{remediation_run_id}
       Rollback all changes from a remediation run

GET    /api/remediation/status/{remediation_run_id}
       Get current status and progress

POST   /api/remediation/approve/{fix_id}
       Manually approve a pending fix

POST   /api/remediation/reject/{fix_id}
       Reject a pending fix
```

### Query Endpoints

```
GET    /api/remediation/runs
       List all remediation runs
       Query: ?status=completed&days=7

GET    /api/remediation/issues/{remediation_run_id}
       List issues detected in a run

GET    /api/remediation/fixes/{remediation_run_id}
       List fixes attempted in a run

GET    /api/remediation/patterns
       List learned fix patterns

GET    /api/remediation/stats
       Aggregate statistics
       Response: { success_rate, avg_confidence, patterns_used, etc. }
```

### WebSocket Events

```typescript
// Emitted during remediation
interface RemediationEvent {
  type: 
    | 'remediation_started'
    | 'issue_detected'
    | 'fix_generated'
    | 'fix_pending_approval'
    | 'fix_applied'
    | 'fix_verified'
    | 'fix_reverted'
    | 'remediation_completed'
    | 'remediation_failed'
    | 'emergency_stop';
  
  remediation_run_id: string;
  timestamp: string;
  data: Record<string, any>;
}
```

---

## Configuration

### Environment Variables

```bash
# Master enable/disable
CVA_REMEDIATION_ENABLED=true

# Autonomy level
CVA_REMEDIATION_AUTONOMY=full  # full|supervised|suggest_only

# Safety limits
CVA_REMEDIATION_MAX_FILES=10
CVA_REMEDIATION_MAX_ITERATIONS=5
CVA_REMEDIATION_MAX_FIXES_PER_HOUR=50
CVA_REMEDIATION_FORBIDDEN_PATHS=".env,*.secret*,**/prod/**"

# Sandbox
CVA_REMEDIATION_SANDBOX_MODE=temp  # memory|temp|docker|worktree

# Approval thresholds
CVA_REMEDIATION_AUTO_APPROVE_THRESHOLD=0.9
CVA_REMEDIATION_SECURITY_REQUIRES_MANUAL=true

# Kill switch
CVA_REMEDIATION_KILL_SWITCH=false
```

### Config YAML Section

```yaml
remediation:
  enabled: true
  autonomy: full  # full | supervised | suggest_only
  
  safety:
    max_files_per_run: 10
    max_lines_changed: 500
    max_iterations: 5
    forbidden_paths:
      - "*.env"
      - "*.secret*"
      - "**/config/prod*"
      - "**/credentials/**"
    
    rate_limits:
      max_fixes_per_hour: 50
      max_fixes_per_day: 200
      max_reverts_before_lockout: 5
      cooldown_after_revert_minutes: 30
    
    approval:
      auto_threshold: 0.9
      review_threshold: 0.7
      security_requires_manual: true
      breaking_changes_require_manual: true
  
  sandbox:
    mode: temp  # memory | temp | docker | worktree
    timeout_seconds: 300
    run_tests: true
    run_linters: true
    run_type_check: true
  
  learning:
    enabled: true
    min_samples_for_pattern: 5
    confidence_decay_days: 30
  
  llms:
    security_fix:
      model: "anthropic/claude-sonnet-4-20250514"
      temperature: 0.1
    correctness_fix:
      model: "openai/gpt-4o"
      temperature: 0.2
    style_fix:
      model: "openai/gpt-4o-mini"
      temperature: 0.3
```

---

## Implementation Tasks

### Phase 1: Foundation (Priority: Critical)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-1.1 | Create remediation module structure | Set up `modules/remediation/` with `__init__.py` and base classes | `import modules.remediation` succeeds |
| ARA-1.2 | Define data models | Create Pydantic models for issues, fixes, patterns | Schema validation tests pass |
| ARA-1.3 | Database migration | Add remediation tables to SQLite | Migration applies without errors |
| ARA-1.4 | Config schema extension | Add remediation config to config.yaml schema | Config loads with remediation section |
| ARA-1.5 | Safety controller base | Implement kill switch and basic rate limiting | Kill switch stops all operations |

### Phase 2: Detection & Planning (Priority: High)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-2.1 | Issue detector | Extract issues from TribunalVerdict | Extracts all failed criteria as issues |
| ARA-2.2 | Root cause analyzer | Implement basic root cause detection | Groups related issues correctly |
| ARA-2.3 | Fix planner | Create fix strategies and ordering | Plans execute in correct order |
| ARA-2.4 | Approval gateway | Implement approval level classification | Security fixes require CONFIRM |

### Phase 3: Fix Generation (Priority: High)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-3.1 | Fix generator base | LLM-based patch generation | Generates valid unified diffs |
| ARA-3.2 | Specialized prompts | Per-category fix prompts | Security vs style fixes differ |
| ARA-3.3 | Pattern matching | Check pattern library before LLM | Known patterns used when available |
| ARA-3.4 | Confidence scoring | Calibrate fix confidence | Confidence correlates with success |

### Phase 4: Validation & Application (Priority: High)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-4.1 | Sandbox validator | In-memory + temp dir validation | Invalid fixes rejected pre-apply |
| ARA-4.2 | Patch applicator | Two-phase commit with locks | Atomic application or clean failure |
| ARA-4.3 | Rollback engine | Multi-level rollback support | Rollback restores exact prior state |
| ARA-4.4 | Health monitor | Post-apply verification | Unhealthy triggers rollback |

### Phase 5: Integration (Priority: High)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-5.1 | API endpoints | REST endpoints for control/query | All endpoints respond correctly |
| ARA-5.2 | WebSocket events | Real-time remediation events | UI receives all event types |
| ARA-5.3 | Pipeline integration | Hook into verification pipeline | Auto-triggers on failed runs |
| ARA-5.4 | CLI commands | `cva remediate` command | CLI initiates remediation |

### Phase 6: Learning & Telemetry (Priority: Medium)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-6.1 | Feedback loop | Record fix outcomes | Outcomes stored in DB |
| ARA-6.2 | Pattern extraction | Extract patterns from successful fixes | Patterns created and stored |
| ARA-6.3 | Confidence calibration | Adjust confidence based on outcomes | Confidence improves over time |
| ARA-6.4 | Analytics integration | Connect to analytics dashboard | Remediation metrics visible |

### Phase 7: Advanced Features (Priority: Medium)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-7.1 | Docker sandbox | Isolated container validation | Fixes validated in Docker |
| ARA-7.2 | Git worktree sandbox | Git worktree isolation | Changes isolated in worktree |
| ARA-7.3 | Multi-file coordination | Coordinated multi-file fixes | Related files fixed atomically |
| ARA-7.4 | Staged deployment | Incremental fix application | Staged fixes apply in order |

### Phase 8: Testing & Hardening (Priority: Critical)

| Task ID | Title | Description | Verification |
|---------|-------|-------------|--------------|
| ARA-8.1 | Unit tests | Test all components in isolation | 90%+ coverage on remediation modules |
| ARA-8.2 | Integration tests | End-to-end remediation flows | Full flows pass |
| ARA-8.3 | Chaos testing | Test failure modes | Graceful degradation verified |
| ARA-8.4 | Security audit | Review for vulnerabilities | No path traversal, injection, etc. |

---

## Dependencies

### Python Packages

```
# Already present
pydantic>=2.0
loguru
litellm
PyYAML
httpx

# May need to add
filelock>=3.0       # File locking for atomic operations
GitPython>=3.0      # Git operations for rollback
watchdog>=3.0       # File system monitoring
tenacity>=8.0       # Retry logic
```

### Internal Dependencies

- `modules/tribunal.py` - Verdict data source
- `modules/self_heal.py` - Existing patch application (to be extended)
- `modules/schemas.py` - Patch/PatchSet models
- `modules/api.py` - Pipeline integration point
- `modules/persistence/` - Database layer

---

## Potential Pitfalls

### Technical Risks

1. **Race Conditions**: Multiple remediation attempts on same files
   - **Mitigation**: File locking, single-threaded remediation per project

2. **Infinite Fix Loops**: Fix introduces new issues, causing loop
   - **Mitigation**: Max iterations, issue signature tracking

3. **Catastrophic Rollback Failure**: Can't restore original state
   - **Mitigation**: Git stash backup, immutable file copies

4. **LLM Hallucinations**: Generated fix is nonsensical
   - **Mitigation**: Syntax validation, sandbox testing

5. **Performance Impact**: Remediation slows verification
   - **Mitigation**: Background processing, async operations

### Operational Risks

1. **Over-trust in Automation**: Users accept bad fixes
   - **Mitigation**: Clear confidence indicators, review prompts

2. **Silent Breaking Changes**: Fix passes tests but breaks production
   - **Mitigation**: Conservative defaults, staged deployment option

3. **Audit Trail Gaps**: Can't trace what changed and why
   - **Mitigation**: Immutable audit log, detailed artifacts

### Security Risks

1. **Path Traversal**: Malicious patch targets system files
   - **Mitigation**: Strict path validation, sandbox isolation

2. **Code Injection**: LLM-generated code contains malicious content
   - **Mitigation**: Static analysis post-generation, sandboxing

3. **Privilege Escalation**: Remediation runs with elevated permissions
   - **Mitigation**: Principle of least privilege, drop capabilities

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Fix Success Rate | > 70% | Fixes that pass verification |
| Auto-Apply Rate | > 50% | Fixes applied without manual review |
| Rollback Rate | < 10% | Fixes that require rollback |
| Time to Fix | < 5 min | From detection to applied fix |
| False Positive Rate | < 5% | Fixes for non-issues |
| Pattern Reuse | > 30% | Fixes using learned patterns |

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Foundation | 2 days | None |
| Phase 2: Detection | 2 days | Phase 1 |
| Phase 3: Generation | 2 days | Phase 2 |
| Phase 4: Validation | 2 days | Phase 3 |
| Phase 5: Integration | 2 days | Phase 4 |
| Phase 6: Learning | 1 day | Phase 5 |
| Phase 7: Advanced | 2 days | Phase 5 |
| Phase 8: Testing | 2 days | All phases |

**Total Estimated Duration**: 15 working days

---

## Appendix A: Example Remediation Flow

```
1. Verification run fails with 3 issues:
   - Security: SQL injection in user_handler.py:45
   - Correctness: Null reference in data_processor.py:120
   - Style: Missing docstring in utils.py:30

2. Issue Detector classifies:
   - SQL injection → severity=critical, auto_fixable=true, confidence=0.85
   - Null reference → severity=high, auto_fixable=true, confidence=0.75
   - Missing docstring → severity=low, auto_fixable=true, confidence=0.95

3. Root Cause Engine analyzes:
   - SQL injection: Unparameterized query (no related issues)
   - Null reference: Missing null check (no related issues)
   - Missing docstring: Documentation gap (no related issues)

4. Fix Planner creates strategy:
   - Order: SQL injection → Null reference → Docstring
   - Strategy: SINGLE_FILE for all (independent issues)

5. Safety Controller evaluates:
   - SQL injection: confidence=0.85 + security → CONFIRM level
   - Null reference: confidence=0.75 + correctness → CONFIRM level
   - Docstring: confidence=0.95 + style → AUTO level

6. Fix Generator produces patches:
   - Patch 1: Parameterized query for SQL injection
   - Patch 2: Null check before reference
   - Patch 3: Added docstring

7. Sandbox Validator tests:
   - All patches apply cleanly
   - Syntax check: PASS
   - Type check: PASS
   - Unit tests: PASS

8. Patch Applicator applies:
   - Docstring fix: AUTO → applied immediately
   - SQL injection: CONFIRM → waits for approval (or auto if configured)
   - Null reference: CONFIRM → waits for approval

9. User approves SQL injection fix

10. Verify Engine re-runs:
    - SQL injection: PASS
    - Null reference: Still failing (not yet approved)
    - Docstring: PASS

11. User approves null reference fix

12. Final verification: ALL PASS

13. Remediation complete:
    - 3 issues detected
    - 3 fixes generated
    - 3 fixes applied
    - 0 rollbacks
    - Time: 4m 32s
```

---

## Appendix B: Kill Switch Behavior

When kill switch is activated:

1. **Immediate**:
   - All pending fixes are cancelled
   - Running fix generation is aborted
   - No new fixes are applied

2. **In Progress Operations**:
   - Current patch application completes or rolls back
   - Verification continues to completion
   - Results are recorded

3. **State**:
   - `remediation_runs.status = 'aborted'`
   - `remediation_runs.abort_reason = 'kill_switch_activated'`
   - Audit log entry created

4. **Recovery**:
   - Manual review of partial state
   - Option to rollback all changes
   - Kill switch must be explicitly reset

---

*Document Version: 1.0*  
*Created: 2025-12-17*  
*Status: PLANNING*
