"""
Pre-commit Hook for CVA Layered Verification

This module provides a Git pre-commit hook that:
1. Scans only staged files (fast)
2. Blocks commits with critical/high severity issues
3. Provides clear error messages with file:line references
4. Can be bypassed with `git commit --no-verify`

Installation:
    python -m modules.monitoring.precommit_hook --install

Usage (automatic via git):
    git commit -m "your message"  # Hook runs automatically

Manual testing:
    python -m modules.monitoring.precommit_hook --check
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from modules.monitoring.layered_verification import (
    QuickConstitutionalScanner,
    QuickViolation,
)


# Exit codes
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_HOOK_ERROR = 2

# Severity levels that block commits
BLOCKING_SEVERITIES = {"critical", "high"}

# Color codes for terminal output
class Colors:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def get_staged_files() -> List[str]:
    """Get list of files staged for commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            check=True
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except subprocess.CalledProcessError:
        return []


def get_repo_root() -> Optional[Path]:
    """Get the git repository root directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def filter_scannable_files(files: List[str]) -> List[str]:
    """Filter to only code files we should scan."""
    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".html"}
    ignore_patterns = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"}
    
    result = []
    for f in files:
        path = Path(f)
        if path.suffix.lower() not in code_extensions:
            continue
        if any(ignore in str(path) for ignore in ignore_patterns):
            continue
        result.append(f)
    return result


def print_banner() -> None:
    """Print the CVA pre-commit hook banner."""
    print(f"\n{Colors.CYAN}╔═══════════════════════════════════════════════════════════╗{Colors.RESET}")
    print(f"{Colors.CYAN}║  {Colors.BOLD}CVA Pre-commit Security Scan{Colors.RESET}{Colors.CYAN}                              ║{Colors.RESET}")
    print(f"{Colors.CYAN}╚═══════════════════════════════════════════════════════════╝{Colors.RESET}\n")


def print_violation(v: QuickViolation, repo_root: Path) -> None:
    """Print a single violation in a readable format."""
    severity_colors = {
        "critical": Colors.RED,
        "high": Colors.RED,
        "medium": Colors.YELLOW,
        "low": Colors.CYAN,
    }
    color = severity_colors.get(v.severity, Colors.RESET)
    severity_label = f"[{v.severity.upper()}]"
    
    # Relative path for cleaner output
    try:
        rel_path = Path(v.file).relative_to(repo_root)
    except ValueError:
        rel_path = Path(v.file)
    
    print(f"  {color}{Colors.BOLD}{severity_label:10}{Colors.RESET} {rel_path}:{v.line_start}")
    print(f"             {v.rule_id}: {v.message}")
    if v.pattern_matched:
        # Truncate long matches
        match_preview = v.pattern_matched[:60] + "..." if len(v.pattern_matched) > 60 else v.pattern_matched
        print(f"             Match: {match_preview}")
    print()


def run_precommit_check(constitution_path: Optional[str] = None) -> Tuple[int, List[QuickViolation]]:
    """
    Run the pre-commit security check.
    
    Returns:
        Tuple of (exit_code, violations_list)
    """
    print_banner()
    
    # Get repository root
    repo_root = get_repo_root()
    if not repo_root:
        print(f"{Colors.RED}Error: Not in a git repository{Colors.RESET}")
        return EXIT_HOOK_ERROR, []
    
    # Get staged files
    staged_files = get_staged_files()
    if not staged_files:
        print(f"{Colors.GREEN}✓ No files staged for commit{Colors.RESET}\n")
        return EXIT_SUCCESS, []
    
    # Filter to scannable files
    scannable = filter_scannable_files(staged_files)
    if not scannable:
        print(f"{Colors.GREEN}✓ No code files to scan ({len(staged_files)} non-code files staged){Colors.RESET}\n")
        return EXIT_SUCCESS, []
    
    print(f"Scanning {len(scannable)} staged file(s)...\n")
    
    # Initialize scanner
    scanner = QuickConstitutionalScanner(constitution_path)
    
    # Scan each file
    all_violations: List[QuickViolation] = []
    for rel_path in scannable:
        abs_path = repo_root / rel_path
        if abs_path.exists():
            violations = scanner.scan_file(str(abs_path))
            all_violations.extend(violations)
    
    # Separate blocking vs warning violations
    blocking = [v for v in all_violations if v.severity in BLOCKING_SEVERITIES]
    warnings = [v for v in all_violations if v.severity not in BLOCKING_SEVERITIES]
    
    # Print results
    if not all_violations:
        print(f"{Colors.GREEN}✓ No security issues found{Colors.RESET}\n")
        return EXIT_SUCCESS, []
    
    # Print blocking issues first
    if blocking:
        print(f"{Colors.RED}{Colors.BOLD}✗ BLOCKING ISSUES ({len(blocking)} found){Colors.RESET}\n")
        for v in blocking:
            print_violation(v, repo_root)
    
    # Print warnings
    if warnings:
        print(f"{Colors.YELLOW}⚠ WARNINGS ({len(warnings)} found){Colors.RESET}\n")
        for v in warnings:
            print_violation(v, repo_root)
    
    # Summary
    print("─" * 60)
    if blocking:
        print(f"\n{Colors.RED}{Colors.BOLD}Commit blocked: {len(blocking)} critical/high severity issue(s){Colors.RESET}")
        print(f"{Colors.YELLOW}To bypass: git commit --no-verify{Colors.RESET}\n")
        return EXIT_FAILURE, all_violations
    else:
        print(f"\n{Colors.GREEN}✓ Commit allowed (warnings only){Colors.RESET}\n")
        return EXIT_SUCCESS, all_violations


def install_hook(repo_path: Optional[str] = None) -> bool:
    """
    Install the pre-commit hook in the repository.
    
    Args:
        repo_path: Path to repository (defaults to current)
        
    Returns:
        True if installation succeeded
    """
    repo_root = Path(repo_path) if repo_path else get_repo_root()
    if not repo_root:
        print(f"{Colors.RED}Error: Not in a git repository{Colors.RESET}")
        return False
    
    hooks_dir = repo_root / ".git" / "hooks"
    if not hooks_dir.exists():
        print(f"{Colors.RED}Error: .git/hooks directory not found{Colors.RESET}")
        return False
    
    hook_path = hooks_dir / "pre-commit"
    
    # Check for existing hook
    if hook_path.exists():
        print(f"{Colors.YELLOW}Warning: pre-commit hook already exists{Colors.RESET}")
        response = input("Overwrite? (y/N): ").strip().lower()
        if response != 'y':
            print("Installation cancelled")
            return False
    
    # Determine Python path
    python_path = sys.executable
    
    # Create hook script (works on Windows Git Bash and Unix)
    hook_content = f'''#!/bin/sh
# CVA Pre-commit Security Hook
# Auto-generated by install_hooks.ps1 or precommit_hook.py

# Run the Python pre-commit checker
"{python_path}" -m modules.monitoring.precommit_hook --check

# Capture exit code
exit_code=$?

# Exit with the same code
exit $exit_code
'''
    
    try:
        hook_path.write_text(hook_content, encoding="utf-8")
        
        # Make executable on Unix-like systems
        if os.name != 'nt':
            os.chmod(hook_path, 0o755)
        
        print(f"{Colors.GREEN}✓ Pre-commit hook installed successfully{Colors.RESET}")
        print(f"  Location: {hook_path}")
        print(f"\n  The hook will run automatically on each commit.")
        print(f"  To bypass: git commit --no-verify")
        return True
        
    except Exception as e:
        print(f"{Colors.RED}Error installing hook: {e}{Colors.RESET}")
        return False


def uninstall_hook(repo_path: Optional[str] = None) -> bool:
    """Remove the pre-commit hook."""
    repo_root = Path(repo_path) if repo_path else get_repo_root()
    if not repo_root:
        print(f"{Colors.RED}Error: Not in a git repository{Colors.RESET}")
        return False
    
    hook_path = repo_root / ".git" / "hooks" / "pre-commit"
    
    if not hook_path.exists():
        print(f"{Colors.YELLOW}No pre-commit hook found{Colors.RESET}")
        return True
    
    try:
        # Check if it's our hook
        content = hook_path.read_text(encoding="utf-8")
        if "CVA Pre-commit" not in content:
            print(f"{Colors.YELLOW}Warning: Existing hook is not from CVA{Colors.RESET}")
            response = input("Remove anyway? (y/N): ").strip().lower()
            if response != 'y':
                print("Uninstallation cancelled")
                return False
        
        hook_path.unlink()
        print(f"{Colors.GREEN}✓ Pre-commit hook removed{Colors.RESET}")
        return True
        
    except Exception as e:
        print(f"{Colors.RED}Error removing hook: {e}{Colors.RESET}")
        return False


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="CVA Pre-commit Security Hook"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run pre-commit check (used by git hook)"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install the pre-commit hook"
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the pre-commit hook"
    )
    parser.add_argument(
        "--constitution", "-c",
        help="Path to constitution file"
    )
    parser.add_argument(
        "--repo", "-r",
        help="Path to git repository"
    )
    
    args = parser.parse_args()
    
    if args.install:
        success = install_hook(args.repo)
        sys.exit(EXIT_SUCCESS if success else EXIT_FAILURE)
    
    elif args.uninstall:
        success = uninstall_hook(args.repo)
        sys.exit(EXIT_SUCCESS if success else EXIT_FAILURE)
    
    elif args.check or not any([args.install, args.uninstall]):
        # Default action is to run check
        exit_code, _ = run_precommit_check(args.constitution)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
