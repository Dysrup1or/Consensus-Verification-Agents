"""Test script for security analysis of key_manager.py"""

from modules.monitoring.context_windowing import (
    ASTWindowAnalyzer, RelevanceScorer, ContextPruner, ScoredWindow
)
from pathlib import Path
import re

# Read the file
file_path = 'modules/key_manager.py'
content = Path(file_path).read_text(encoding='utf-8')

# Analyze with security focus
analyzer = ASTWindowAnalyzer(context_lines=3)
scorer = RelevanceScorer(inclusion_threshold=0.1)

# Treat entire file as changed for full analysis
lines = content.splitlines()
windows = analyzer.analyze_file(file_path, content, [(1, len(lines))])

# Score with security criterion
scored = scorer.score_windows(
    windows.windows,
    criterion_type='security',
    criterion_text='Check for hardcoded secrets, insecure key storage, credential exposure, and API key handling vulnerabilities'
)

print('='*70)
print('TEST 1: key_manager.py - Security Analysis')
print('='*70)
print(f'Total windows analyzed: {len(scored)}')
print()

# Direct pattern scanning for more detail
SECURITY_PATTERNS = {
    'hardcoded_secret': r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
    'env_key_exposure': r'os\.environ\.get\(["\'][^"\']+["\']\s*,\s*["\'][^"\']+["\']\)',
    'key_logging': r'logger\.\w+\(.*(?:key|password|secret|token)',
    'insecure_comparison': r'==\s*["\'][^"\']+["\'].*(?:key|password|secret)',
    'key_in_exception': r'except.*:\s*\n.*(?:key|password|secret)',
    'plaintext_storage': r'(?:write|save|store).*(?:key|password|secret)',
}

print('PATTERN-BASED SECURITY SCAN:')
print('-'*70)
issues_found = []
for pattern_name, pattern in SECURITY_PATTERNS.items():
    matches = list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE))
    if matches:
        for m in matches:
            line_num = content[:m.start()].count('\n') + 1
            issues_found.append({
                'type': pattern_name,
                'line': line_num,
                'match': m.group()[:80]
            })
            print(f'[Line {line_num}] {pattern_name}')
            print(f'  Match: {m.group()[:80]}...')
            print()

# Additional manual checks
print('MANUAL SECURITY REVIEW:')
print('-'*70)

# Check 1: Key suffix logging (potential info leak)
if 'key_suffix' in content and 'logger' in content:
    print('[MEDIUM] Key suffix is logged - could aid in key identification attacks')

# Check 2: No encryption at rest
if 'encrypt' not in content.lower():
    print('[LOW] No encryption mentioned - keys stored in plaintext in memory')

# Check 3: Threading without locks for sensitive data
if 'threading' in content and 'Lock' not in content:
    print('[LOW] Threading used but no explicit Lock for key status updates')

# Check 4: Hardcoded fallback chain
if 'fallback_order' in content:
    print('[INFO] Hardcoded provider fallback order - consider making configurable')

# Check 5: Default config path
if 'config.yaml' in content:
    print('[INFO] Default config path hardcoded - could expose config location')

print()
print(f'Total issues found: {len(issues_found)}')
