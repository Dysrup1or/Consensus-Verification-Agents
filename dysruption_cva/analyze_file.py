"""Generic test script for code analysis"""

import sys
from modules.monitoring.context_windowing import (
    ASTWindowAnalyzer, RelevanceScorer, ContextPruner, ScoredWindow
)
from pathlib import Path
import re

# Get file from argument or default
file_path = sys.argv[1] if len(sys.argv) > 1 else 'modules/key_manager.py'
criterion = sys.argv[2] if len(sys.argv) > 2 else 'security'

content = Path(file_path).read_text(encoding='utf-8')

# Analyze
analyzer = ASTWindowAnalyzer(context_lines=3)
scorer = RelevanceScorer(inclusion_threshold=0.1)

lines = content.splitlines()
windows = analyzer.analyze_file(file_path, content, [(1, len(lines))])

# Score with criterion
criterion_text = {
    'security': 'Check for hardcoded secrets, injection vulnerabilities, insecure auth, credential exposure',
    'logic': 'Check for race conditions, error handling, edge cases, null checks, and logic flaws',
    'performance': 'Check for N+1 queries, blocking calls, memory leaks, inefficient algorithms',
}.get(criterion, criterion)

scored = scorer.score_windows(
    windows.windows,
    criterion_type=criterion,
    criterion_text=criterion_text
)

print('='*70)
print(f'ANALYSIS: {file_path}')
print(f'Criterion: {criterion}')
print('='*70)
print(f'Total windows: {len(scored)}')
print()

# Pattern-based scanning
PATTERNS = {
    'security': {
        'hardcoded_secret': r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
        'sql_injection': r'(?:execute|query)\s*\([^)]*(?:\+|%|\.format|f["\'])',
        'command_injection': r'(?:subprocess|os\.system|os\.popen)\s*\([^)]*(?:\+|%|\.format|f["\'])',
        'path_traversal': r'(?:open|Path)\s*\([^)]*(?:\+|%|\.format|f["\'])',
        'unsafe_eval': r'\beval\s*\(',
        'unsafe_exec': r'\bexec\s*\(',
        'pickle_load': r'pickle\.loads?\s*\(',
        'yaml_unsafe': r'yaml\.(?:load|unsafe_load)\s*\(',
        'weak_crypto': r'(?:md5|sha1)\s*\(',
    },
    'logic': {
        'bare_except': r'except\s*:',
        'pass_in_except': r'except.*:\s*\n\s*pass',
        'missing_await': r'async\s+def.*\n(?:(?!await).*\n)*return',
        'mutable_default': r'def\s+\w+\([^)]*(?:\[\]|\{\})\s*(?:,|\))',
        'global_state': r'^[A-Z_]+\s*=\s*(?:\[\]|\{\}|None)',
        'no_return_type': r'def\s+\w+\([^)]*\)\s*:(?!\s*->)',
    },
    'performance': {
        'sync_in_async': r'async\s+def.*\n.*(?:requests\.|urllib|open\()',
        'n_plus_one': r'for\s+\w+\s+in.*:\s*\n.*(?:\.query|\.get|await\s)',
        'unbounded_loop': r'while\s+True\s*:',
    }
}

patterns = PATTERNS.get(criterion, PATTERNS['security'])

print(f'PATTERN-BASED SCAN ({criterion}):')
print('-'*70)
issues_found = []
for pattern_name, pattern in patterns.items():
    matches = list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE))
    for m in matches:
        line_num = content[:m.start()].count('\n') + 1
        issues_found.append({
            'type': pattern_name,
            'line': line_num,
            'severity': 'HIGH' if 'injection' in pattern_name or 'unsafe' in pattern_name else 'MEDIUM',
            'match': m.group()[:80]
        })
        print(f'[{issues_found[-1]["severity"]}] Line {line_num}: {pattern_name}')
        print(f'  {m.group()[:80]}')
        print()

# Manual review based on criterion
print('STRUCTURAL REVIEW:')
print('-'*70)

if criterion == 'logic':
    # Check for error handling
    if 'try:' not in content:
        print('[MEDIUM] No try-except blocks found - missing error handling')
    if 'raise' not in content and 'Error' in content:
        print('[LOW] Error classes defined but no raise statements')
    if 'finally:' not in content and 'close' in content.lower():
        print('[LOW] Resources may not be properly closed (no finally blocks)')
    
elif criterion == 'security':
    if 'os.environ' in content and 'default' not in content.lower():
        print('[INFO] Environment variables accessed - verify no sensitive defaults')
    if '.format(' in content or "f'" in content or 'f"' in content:
        print('[INFO] String formatting used - verify no injection vectors')

elif criterion == 'performance':
    if 'async def' in content and 'await' not in content:
        print('[HIGH] Async functions without await - blocking the event loop')
    if 'for' in content and '.append' in content:
        print('[LOW] Consider list comprehension instead of loop+append')

print()
print(f'Total issues: {len(issues_found)}')
