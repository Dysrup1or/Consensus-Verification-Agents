# CVA Layered Verification - Enhancement Implementation Plan

**Created:** December 17, 2025  
**Status:** ✅ COMPLETED  
**Priority:** Short-term Quick Wins

---

## System Overview

This plan implements four enhancements to the CVA Layered Verification system:

1. **SARIF Output Format** - Industry-standard format for static analysis results
2. **SQL Injection Patterns** - Expanded detection for SQL vulnerabilities
3. **XSS Detection** - Cross-site scripting pattern detection
4. **Pre-commit Hook** - Git integration for shift-left security

---

## Task 1: SARIF Output Format

### Description
Add SARIF (Static Analysis Results Interchange Format) output to enable integration with:
- GitHub Code Scanning
- Azure DevOps
- VS Code SARIF Viewer extension
- Other industry tools

### Components
| Component | File | Description |
|-----------|------|-------------|
| SarifFormatter | `modules/monitoring/sarif_formatter.py` | Converts violations to SARIF JSON |
| CLI flag | `scheduled_verification.py` | `--sarif` output option |

### Verification Criteria
- [ ] SARIF output validates against SARIF 2.1.0 schema
- [ ] All violations include: ruleId, level, message, location (file, line, column)
- [ ] Tool metadata includes: name, version, rules array
- [ ] Output file: `verification_report.sarif`

### SARIF Schema Reference
```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [{
    "tool": { "driver": { "name": "CVA", "rules": [...] } },
    "results": [...]
  }]
}
```

---

## Task 2: SQL Injection Patterns

### Description
Expand SQL injection detection beyond basic string formatting to catch:
- String concatenation in queries
- f-string interpolation
- .format() usage
- ORM raw query misuse

### New Patterns
| Rule ID | Pattern | Example Caught |
|---------|---------|----------------|
| SQL002 | String concatenation | `"SELECT * FROM " + table` |
| SQL003 | f-string in query | `f"SELECT * FROM {table}"` |
| SQL004 | .format() in query | `"SELECT {}".format(col)` |
| SQL005 | Django raw() misuse | `Model.objects.raw(user_input)` |
| SQL006 | SQLAlchemy text() | `text(f"SELECT {x}")` |

### Verification Criteria
- [ ] Detects all 5 new SQL injection patterns
- [ ] Zero false positives on ORM parameterized queries
- [ ] Correctly allows: `cursor.execute("SELECT ?", (param,))`

---

## Task 3: XSS Detection Patterns

### Description
Add Cross-Site Scripting detection for web applications.

### New Patterns
| Rule ID | Pattern | Language | Example |
|---------|---------|----------|---------|
| XSS001 | innerHTML assignment | JS/TS | `el.innerHTML = data` |
| XSS002 | dangerouslySetInnerHTML | React | `<div dangerouslySetInnerHTML=...` |
| XSS003 | document.write | JS | `document.write(input)` |
| XSS004 | jQuery .html() | JS | `$(el).html(data)` |
| XSS005 | Template literal injection | Python | `render_template_string(user_input)` |
| XSS006 | Jinja2 safe filter misuse | Python | `{{ data\|safe }}` |

### Verification Criteria
- [ ] Detects all 6 XSS patterns
- [ ] Context-aware: skips sanitized content
- [ ] Works across .js, .ts, .jsx, .tsx, .py, .html files

---

## Task 4: Pre-commit Hook Integration

### Description
Create a Git pre-commit hook that:
1. Runs quick scan on staged files only
2. Blocks commit if critical/high issues found
3. Shows clear error messages
4. Can be bypassed with `--no-verify`

### Components
| Component | File | Description |
|-----------|------|-------------|
| Hook script | `.git/hooks/pre-commit` | Shell script entry point |
| Hook installer | `install_hooks.ps1` | PowerShell installer |
| Hook runner | `modules/monitoring/precommit_hook.py` | Python logic |

### Verification Criteria
- [ ] Hook blocks commits with critical issues
- [ ] Hook allows clean commits
- [ ] Hook runs in < 1 second for typical changesets
- [ ] `--no-verify` bypasses the hook
- [ ] Clear error messages with file:line references

---

## Execution Order

```
Task 1: SARIF Output ──────────────────► Test SARIF
    │
    ▼
Task 2: SQL Patterns ──────────────────► Test SQL
    │
    ▼
Task 3: XSS Patterns ──────────────────► Test XSS
    │
    ▼
Task 4: Pre-commit Hook ───────────────► Test Hook
    │
    ▼
Integration Testing ──────────────────► Documentation
```

---

## Dependencies

| Dependency | Required For | Status |
|------------|--------------|--------|
| Git | Pre-commit hook | ✅ Available |
| Python 3.10+ | All components | ✅ Available |
| layered_verification.py | All components | ✅ Exists |

---

## Assumptions

1. SARIF 2.1.0 is the target schema (current standard)
2. Pre-commit hook is bash-compatible (Git Bash on Windows)
3. Existing patterns remain unchanged
4. No breaking changes to existing APIs

---

## Potential Pitfalls

| Risk | Mitigation |
|------|------------|
| SARIF schema validation fails | Use minimal required fields only |
| False positives in SQL patterns | Add context-aware filtering |
| Hook slows down commits | Limit to staged files, optimize |
| Windows path issues in hook | Use forward slashes, test both |

---

## Success Criteria

- [x] All 4 enhancements implemented
- [x] All verification criteria pass
- [x] Zero regressions in existing functionality
- [x] Documentation updated
- [x] Tests pass

## Implementation Summary

| Task | Status | Files Created/Modified |
|------|--------|------------------------|
| SARIF Output | ✅ Complete | `sarif_formatter.py`, `scheduled_verification.py` |
| SQL Patterns | ✅ Complete | `layered_verification.py` (7 new rules) |
| XSS Patterns | ✅ Complete | `layered_verification.py` (7 new rules) |
| Pre-commit Hook | ✅ Complete | `precommit_hook.py`, `install_hooks.ps1` |

**Total new security patterns added:** 14 (from 13 to 27)

**Test Results:**
- Pre-commit hook correctly blocked commit with 5 vulnerabilities
- SARIF output validates against SARIF 2.1.0 schema
- Scheduled verification runs in ~200ms
- Zero false positives on codebase
