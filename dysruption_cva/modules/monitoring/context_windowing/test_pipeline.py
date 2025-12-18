"""Test script for Context Windowing pipeline."""

from context_pruner import ContextPruner, IntelligentContextBuilder, build_windowed_llm_context
from relevance_scorer import RelevanceScorer, ScoredWindow
from ast_window_analyzer import ASTWindowAnalyzer, CodeWindow

# Test with multiple files - simulating only auth.py and database.py as "changed"
file_texts = {
    'auth.py': '''
import hashlib
import secrets

def authenticate_user(username, password):
    \"\"\"Authenticate user with password hash\"\"\"
    stored_hash = get_hash_from_db(username)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return secrets.compare_digest(stored_hash, password_hash)

def create_token():
    return secrets.token_urlsafe(32)

def format_date(dt):
    return dt.strftime('%Y-%m-%d')
''',
    'database.py': '''
import sqlite3

def get_user(user_id):
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    return cursor.fetchone()

def search_users(name):
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    # Potential SQL injection
    query = f'SELECT * FROM users WHERE name LIKE "%{name}%"'
    cursor.execute(query)
    return cursor.fetchall()

def count_users():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    return cursor.fetchone()[0]
''',
    'utils.py': '''
def format_currency(amount):
    return f'${amount:,.2f}'

def format_phone(phone):
    return f'({phone[:3]}) {phone[3:6]}-{phone[6:]}'

def generate_report(data):
    lines = []
    for row in data:
        lines.append(', '.join(str(v) for v in row))
    return "\\n".join(lines)

def pad_string(s, width):
    return s.ljust(width)

def calculate_average(numbers):
    return sum(numbers) / len(numbers)

def merge_lists(list1, list2):
    return list1 + list2

def deduplicate(items):
    return list(set(items))
'''
}

# Test the actual savings by marking only specific code as changed
analyzer = ASTWindowAnalyzer(context_lines=3)
scorer = RelevanceScorer(inclusion_threshold=0.15)
pruner = ContextPruner(token_budget=50000)

all_windows = []

# Mark only auth.py and database.py functions as changed
changed_files = {'auth.py', 'database.py'}

for file_path, content in file_texts.items():
    if file_path in changed_files:
        # These files are changed - mark all content as changed
        changed_ranges = [(1, len(content.splitlines()))]
    else:
        # utils.py - not changed, no ranges
        changed_ranges = []
    
    file_windows = analyzer.analyze_file(
        file_path=file_path,
        content=content,
        changed_ranges=changed_ranges,
    )
    all_windows.extend(file_windows.windows)

# Score windows
scored_windows = scorer.score_windows(
    windows=all_windows,
    criterion_type='security',
    criterion_text='Verify no SQL injection, proper secret handling, and secure authentication',
)

# Calculate original context (all files full)
original = ''.join([f'# FILE: {p}\n{t}' for p, t in file_texts.items()])
original_tokens = len(original) // 4

# Prune
result = pruner.prune(scored_windows)

print('='*60)
print('CONTEXT WINDOWING TEST RESULTS')
print('='*60)
print(f'Original tokens:    {original_tokens:,}')
print(f'Windowed tokens:    {result.total_tokens:,}')
# Calculate actual savings vs original full context
actual_savings = 100.0 * (1.0 - result.total_tokens / original_tokens) if original_tokens > 0 else 0
print(f'Savings:            {actual_savings:.1f}%')
print(f'Files included:     {result.files_included}')
print(f'Windows included:   {result.windows_included}')
print(f'Windows excluded:   {result.windows_excluded}')
print()

print('INCLUDED WINDOWS:')
for sw in result.included_windows:
    print(f'  - {sw.window.file_path}: {sw.window.symbol_name or "lines " + str(sw.window.start_line)}'
          f' (score: {sw.overall_score:.2f}, reason: {sw.inclusion_reason})')

print()
print('EXCLUDED WINDOWS:')
for sw in result.excluded_windows:
    print(f'  - {sw.window.file_path}: {sw.window.symbol_name or "lines " + str(sw.window.start_line)}'
          f' (score: {sw.overall_score:.2f}, reason: {sw.exclusion_reason})')

print()
print('Context output:')
print('-'*40)
print(result.context_text[:1200])
