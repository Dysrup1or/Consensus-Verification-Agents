# Persistent Layered Verification System

## Overview

The **Layered Verification System** provides continuous, cost-effective code verification by using a tiered approach:

1. **Cheap first**: Local regex-based scanning runs constantly (FREE)
2. **Expensive only when needed**: LLM verification triggers only when issues exceed a threshold

This design minimizes API costs while maintaining strong security coverage.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PERSISTENT DAEMON                            │
│                   (runs every 5 seconds)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 0: Git Diff Detector                                      │
│  ─────────────────────────────                                   │
│  • Polls git status/diff                                         │
│  • Tracks last_verified_commit                                   │
│  • Detects both committed AND uncommitted changes                │
│  → Outputs: changed_files + diff_context                        │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: Quick Constitutional Scan (FREE - Local)              │
│  ───────────────────────────────────────────────────            │
│  • Regex patterns for security issues                           │
│  • Runs in ~10-30ms per file                                    │
│  • Smart false-positive filtering                               │
│  → Outputs: violations[], total_score                           │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 2: Issue Ranker + Threshold Check                        │
│  ───────────────────────────────────────────                    │
│  • Severity scoring: CRITICAL=25, HIGH=10, MEDIUM=5, LOW=1      │
│  • Escalation triggers:                                          │
│    - Any CRITICAL violation → immediate escalation               │
│    - More than 2 HIGH violations → escalation                   │
│    - Score > threshold (default 20) → escalation                │
│  → Outputs: should_escalate, reason                             │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 3: Full LLM Verification (EXPENSIVE - API)               │
│  ─────────────────────────────────────────────────              │
│  • Only triggered when threshold exceeded                       │
│  • Uses existing run_verification_pipeline                      │
│  • DeepSeek/GPT-4 for semantic intent verification              │
│  → Outputs: full verdict, suggested fixes                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Option 1: PowerShell Script

```powershell
# Basic usage (current directory)
.\start_persistent_verification.ps1

# Watch a specific repo
.\start_persistent_verification.ps1 -RepoPath "C:\path\to\repo"

# Quick scan only (no LLM, no API costs)
.\start_persistent_verification.ps1 -NoLLM

# Custom threshold
.\start_persistent_verification.ps1 -Threshold 30 -PollInterval 10
```

### Option 2: Python Module

```bash
cd dysruption_cva
python -m modules.monitoring.persistent_verification --repo /path/to/repo
```

### Option 3: Programmatic Usage

```python
from modules.monitoring.persistent_verification import start_persistent_verification

# Start in background
service = await start_persistent_verification(
    repo_path="/path/to/repo",
    constitution_path="constitution.md"
)

# Get status
status = service.get_status()
print(f"Violations found: {status['metrics']['violations_total']}")
print(f"Escalations: {status['metrics']['escalations_total']}")

# Stop when done
service.stop()
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CVA_POLL_INTERVAL` | `5.0` | Seconds between verification cycles |
| `CVA_ESCALATION_THRESHOLD` | `20` | Score threshold for LLM escalation |
| `CVA_ENABLE_LLM_ESCALATION` | `true` | Whether to call LLM when threshold exceeded |

### CLI Arguments

```
--repo, -r          Path to git repository (default: current directory)
--constitution, -c  Path to constitution file
--poll-interval, -p Poll interval in seconds
--threshold, -t     Escalation threshold score
--no-llm           Disable LLM escalation (quick scan only)
```

---

## Built-in Security Patterns

The quick scanner checks for these patterns by default:

| Rule ID | Severity | Description |
|---------|----------|-------------|
| SEC001 | Critical | Hardcoded secrets (API keys, passwords, tokens) |
| SEC002 | Critical | Use of `eval()` |
| SEC003 | High | Use of `exec()` |
| SEC004 | High | Private key material |
| SEC005 | Medium | `os.system()` calls |
| SEC006 | Medium | `subprocess` with `shell=True` |
| PATH001 | High | Path traversal (`../`) |
| SQL001 | Critical | SQL injection patterns |

---

## Scoring System

Violations are scored by severity:

| Severity | Score | Example |
|----------|-------|---------|
| Critical | 25 | Hardcoded API key, SQL injection |
| High | 10 | exec() usage, path traversal |
| Medium | 5 | os.system(), shell=True |
| Low | 1 | Minor style issues |

**Escalation triggers** (any one triggers LLM):
- Any CRITICAL violation (1+ critical)
- More than 2 HIGH violations
- Total score > threshold (default 20)

---

## Cost Analysis

### Without Layered System
- Every file change → full LLM verification
- ~$0.01-0.10 per verification (depending on file size)
- 100 saves/day = $1-10/day per developer

### With Layered System
- 100 saves/day → ~5-10 escalations (only when issues found)
- 95% reduction in API calls
- ~$0.05-0.50/day per developer

---

## Integration with Existing CVA

The layered system integrates seamlessly with your existing infrastructure:

| Existing Component | Integration Point |
|--------------------|-------------------|
| `watcher_v2.py` | Git diff detection replaces file system events |
| `monitoring/worker.py` | Layer 3 reuses `run_verification_pipeline` |
| `judge_engine.py` | Constitution regex rules loaded into Layer 1 |
| `monitoring/queue.py` | Could be extended for async escalation jobs |

---

## Files Created

| File | Description |
|------|-------------|
| `modules/monitoring/layered_verification.py` | Core layered verification engine |
| `modules/monitoring/persistent_verification.py` | Daemon service and CLI |
| `start_persistent_verification.ps1` | PowerShell launcher script |
| `docs/LAYERED_VERIFICATION.md` | This documentation |

---

## Example Output

```
╔═══════════════════════════════════════════════════════════════╗
║   PERSISTENT LAYERED VERIFICATION DAEMON                       ║
╚═══════════════════════════════════════════════════════════════╝
Configuration:
  Repository:    C:\Users\dev\my-project
  Poll Interval: 5s
  Threshold:     20
  LLM Enabled:   True

2025-12-17 02:00:00 | INFO | Layer 0: Detecting git changes...
2025-12-17 02:00:00 | INFO | 3 files changed since last commit
2025-12-17 02:00:00 | INFO | Layer 1: Quick scanning 3 files...
2025-12-17 02:00:00 | WARNING | Quick scan violation: [critical] SEC001 - Potential hardcoded secret detected in src/config.py:42
2025-12-17 02:00:00 | INFO | Layer 2: Evaluating escalation threshold...
2025-12-17 02:00:00 | WARNING | Escalating to LLM verification: Critical violation detected (1 critical issues)
2025-12-17 02:00:00 | INFO | Layer 3: Running full LLM verification...
2025-12-17 02:00:05 | INFO | Cycle complete: 3 files changed, quick_violations=1, escalated=True, time=5234ms
```

---

## Next Steps

1. **Start the daemon**: `.\start_persistent_verification.ps1`
2. **Monitor the output**: Watch for violations and escalations
3. **Tune the threshold**: Adjust based on your project's needs
4. **Add custom patterns**: Extend `QuickConstitutionalScanner.DEFAULT_PATTERNS`
5. **Integrate webhooks**: Connect to Slack/Teams for notifications
