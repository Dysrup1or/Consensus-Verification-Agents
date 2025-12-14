"""
CVA Health Check System
-----------------------
Pre-flight verification for all CVA subsystems.
Based on 12-Factor App principles (explicit dependencies, config, fail-fast).

Usage:
    python preflight.py          # Run all checks
    python preflight.py --fix    # Attempt auto-fixes where possible
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from typing import NamedTuple, List, Callable, Optional
from enum import Enum

class Status(Enum):
    PASS = "✅"
    FAIL = "❌"
    WARN = "⚠️"
    SKIP = "⏭️"

class CheckResult(NamedTuple):
    name: str
    status: Status
    message: str
    fix_hint: Optional[str] = None

# ============================================================
# CONFIGURATION
# ============================================================
BACKEND_DIR = Path(__file__).parent / "dysruption_cva"
FRONTEND_DIR = Path(__file__).parent / "dysruption-ui"

REQUIRED_PYTHON_VERSION = (3, 10)
REQUIRED_NODE_VERSION = 18

REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
]

REQUIRED_PYTHON_PACKAGES = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "litellm",
    "watchdog",
    "pylint",
    "bandit",
    "loguru",
]

REQUIRED_BACKEND_FILES = [
    "modules/__init__.py",
    "modules/api.py",
    "modules/schemas.py",
    "modules/parser.py",
    "modules/tribunal.py",
    "modules/watcher.py",
    "modules/watcher_v2.py",
    "config.yaml",
]

REQUIRED_FRONTEND_FILES = [
    "package.json",
    "app/page.tsx",
    "components/Verdict.tsx",
    "components/PatchDiff.tsx",
    "lib/ws.ts",
    "lib/mock.ts",
]

# ============================================================
# CHECK FUNCTIONS
# ============================================================

def check_python_version() -> CheckResult:
    """Verify Python version meets minimum requirements."""
    current = sys.version_info[:2]
    if current >= REQUIRED_PYTHON_VERSION:
        return CheckResult(
            "Python Version",
            Status.PASS,
            f"Python {current[0]}.{current[1]} >= {REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}"
        )
    return CheckResult(
        "Python Version",
        Status.FAIL,
        f"Python {current[0]}.{current[1]} < {REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}",
        f"Install Python {REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}+"
    )

def check_node_version() -> CheckResult:
    """Verify Node.js version meets minimum requirements."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        version_str = result.stdout.strip().lstrip('v')
        major = int(version_str.split('.')[0])
        if major >= REQUIRED_NODE_VERSION:
            return CheckResult("Node.js Version", Status.PASS, f"Node.js v{version_str} >= v{REQUIRED_NODE_VERSION}")
        return CheckResult(
            "Node.js Version",
            Status.FAIL,
            f"Node.js v{version_str} < v{REQUIRED_NODE_VERSION}",
            f"Install Node.js v{REQUIRED_NODE_VERSION}+"
        )
    except FileNotFoundError:
        return CheckResult("Node.js Version", Status.FAIL, "Node.js not found", "Install Node.js from nodejs.org")
    except Exception as e:
        return CheckResult("Node.js Version", Status.WARN, f"Could not check: {e}")

def check_env_file() -> CheckResult:
    """Verify .env file exists and contains required keys."""
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return CheckResult(
            ".env File",
            Status.FAIL,
            "Missing .env file",
            f"Create {env_path} with API keys"
        )
    
    content = env_path.read_text()
    missing = [var for var in REQUIRED_ENV_VARS if var not in content]
    
    if missing:
        return CheckResult(
            ".env File",
            Status.WARN,
            f"Missing keys: {', '.join(missing)}",
            "Add missing API keys to .env"
        )
    return CheckResult(".env File", Status.PASS, "All required API keys present")

def check_python_packages() -> CheckResult:
    """Verify required Python packages are installed."""
    missing = []
    for pkg in REQUIRED_PYTHON_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        return CheckResult(
            "Python Packages",
            Status.FAIL,
            f"Missing: {', '.join(missing)}",
            f"Run: pip install -r requirements.txt"
        )
    return CheckResult("Python Packages", Status.PASS, f"All {len(REQUIRED_PYTHON_PACKAGES)} packages installed")

def check_backend_files() -> CheckResult:
    """Verify all required backend files exist."""
    missing = [f for f in REQUIRED_BACKEND_FILES if not (BACKEND_DIR / f).exists()]
    if missing:
        return CheckResult(
            "Backend Files",
            Status.FAIL,
            f"Missing: {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}",
            "Check dysruption_cva directory structure"
        )
    return CheckResult("Backend Files", Status.PASS, f"All {len(REQUIRED_BACKEND_FILES)} files present")

def check_frontend_files() -> CheckResult:
    """Verify all required frontend files exist."""
    if not FRONTEND_DIR.exists():
        return CheckResult(
            "Frontend Files",
            Status.FAIL,
            "Frontend directory not found",
            "Create dysruption-ui with Next.js scaffold"
        )
    
    missing = [f for f in REQUIRED_FRONTEND_FILES if not (FRONTEND_DIR / f).exists()]
    if missing:
        return CheckResult(
            "Frontend Files",
            Status.FAIL,
            f"Missing: {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}",
            "Check dysruption-ui directory structure"
        )
    return CheckResult("Frontend Files", Status.PASS, f"All {len(REQUIRED_FRONTEND_FILES)} files present")

def check_frontend_deps() -> CheckResult:
    """Verify frontend dependencies are installed."""
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        return CheckResult(
            "Frontend Dependencies",
            Status.WARN,
            "node_modules not found",
            "Run: cd dysruption-ui && npm install"
        )
    return CheckResult("Frontend Dependencies", Status.PASS, "node_modules present")

def check_config_yaml() -> CheckResult:
    """Verify config.yaml is valid YAML."""
    config_path = BACKEND_DIR / "config.yaml"
    if not config_path.exists():
        return CheckResult("Config YAML", Status.FAIL, "config.yaml not found")
    
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        if not config:
            return CheckResult("Config YAML", Status.WARN, "config.yaml is empty")
        return CheckResult("Config YAML", Status.PASS, "Valid YAML with configuration")
    except ImportError:
        return CheckResult("Config YAML", Status.SKIP, "PyYAML not installed")
    except Exception as e:
        return CheckResult("Config YAML", Status.FAIL, f"Invalid YAML: {e}")

def check_module_imports() -> CheckResult:
    """Verify all CVA modules can be imported without errors."""
    sys.path.insert(0, str(BACKEND_DIR))
    errors = []
    modules = ["modules.schemas", "modules.parser", "modules.tribunal", "modules.api", "modules.watcher_v2"]
    
    for mod in modules:
        try:
            __import__(mod)
        except Exception as e:
            errors.append(f"{mod}: {type(e).__name__}")
    
    sys.path.pop(0)
    
    if errors:
        return CheckResult(
            "Module Imports",
            Status.FAIL,
            f"Import errors: {'; '.join(errors[:2])}",
            "Check module dependencies and syntax"
        )
    return CheckResult("Module Imports", Status.PASS, f"All {len(modules)} modules import successfully")

def check_port_availability() -> CheckResult:
    """Check if required ports are available."""
    import socket
    # Backend runs on 8001 (see dysruption_cva/STARTUP.md)
    ports = {"Backend (8001)": 8001, "Frontend (3000)": 3000}
    in_use = []
    
    for name, port in ports.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        if result == 0:
            in_use.append(name)
    
    if in_use:
        return CheckResult(
            "Port Availability",
            Status.WARN,
            f"Ports in use: {', '.join(in_use)}",
            "Stop conflicting services or use different ports"
        )
    return CheckResult("Port Availability", Status.PASS, "Ports 8001 and 3000 available")


def check_llm_models_accessible() -> CheckResult:
    """Best-effort validation that configured LLM model names are reachable.

    This is OPT-IN to avoid accidental API calls/costs.

    Enable by setting env var: CVA_PREFLIGHT_VALIDATE_MODELS=1
    """

    if os.environ.get("CVA_PREFLIGHT_VALIDATE_MODELS", "").strip() not in {"1", "true", "TRUE", "yes", "YES"}:
        return CheckResult(
            "LLM Model Validation",
            Status.SKIP,
            "Skipped (set CVA_PREFLIGHT_VALIDATE_MODELS=1 to enable)",
        )

    # Load models from config.yaml
    config_path = BACKEND_DIR / "config.yaml"
    if not config_path.exists():
        return CheckResult("LLM Model Validation", Status.FAIL, "config.yaml not found")

    try:
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8", errors="replace")) or {}
    except Exception as e:
        return CheckResult("LLM Model Validation", Status.FAIL, f"Could not read config.yaml: {e}")

    llms = (config.get("llms") or {})
    # Support both historical layouts: top-level llms, or llms under another key.
    if "llms" in config and isinstance(config.get("llms"), dict):
        llms = config["llms"]
    elif "llms" in (config.get("llm") or {}):
        llms = (config.get("llm") or {}).get("llms") or {}

    # In current config.yaml, llms are under llms: { architect: {model: ...}, ... }
    if "llms" in llms and isinstance(llms.get("llms"), dict):
        llms = llms["llms"]

    models: List[str] = []
    for _, cfg in (llms or {}).items():
        if isinstance(cfg, dict) and isinstance(cfg.get("model"), str):
            models.append(cfg["model"])

    # Also validate fallback chain if present.
    fb = config.get("fallback") or {}
    if isinstance(fb, dict):
        if isinstance(fb.get("models"), list):
            models.extend([m for m in fb.get("models") if isinstance(m, str)])
        if isinstance(fb.get("model"), str):
            models.append(fb["model"])

    models = sorted({m.strip() for m in models if m and m.strip()})
    if not models:
        return CheckResult("LLM Model Validation", Status.WARN, "No models found in config.yaml")

    # Require provider keys (if missing, skip rather than fail).
    env_path = BACKEND_DIR / ".env"
    env_text = env_path.read_text(encoding="utf-8", errors="ignore") if env_path.exists() else ""
    required_keys = ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"]
    if not any(k in env_text or os.environ.get(k) for k in required_keys):
        return CheckResult(
            "LLM Model Validation",
            Status.SKIP,
            "Skipped (no API keys found in .env or environment)",
        )

    try:
        import litellm
    except Exception:
        return CheckResult("LLM Model Validation", Status.SKIP, "Skipped (litellm not installed)")

    failures: List[str] = []
    warnings: List[str] = []

    # Cheap ping (min tokens) with a short timeout.
    messages = [{"role": "user", "content": "ping"}]
    for model in models:
        try:
            litellm.completion(
                model=model,
                messages=messages,
                max_tokens=1,
                temperature=0.0,
                timeout=12,
            )
        except Exception as e:
            et = type(e).__name__
            msg = str(e)

            # Treat model-not-found as hard fail; rate limits/timeouts as warnings.
            is_not_found = "NotFound" in et or "not_found" in msg.lower() or "model not" in msg.lower()
            is_rate_limit = "Rate" in et or "429" in msg or "limit" in msg.lower()
            is_timeout = "Timeout" in et or "timed out" in msg.lower()

            if is_not_found:
                failures.append(model)
            elif is_rate_limit or is_timeout:
                warnings.append(f"{model} ({et})")
            else:
                warnings.append(f"{model} ({et})")

    if failures:
        return CheckResult(
            "LLM Model Validation",
            Status.FAIL,
            f"Model(s) not found: {', '.join(failures[:3])}{'...' if len(failures) > 3 else ''}",
            "Update dysruption_cva/config.yaml to valid model names",
        )
    if warnings:
        return CheckResult(
            "LLM Model Validation",
            Status.WARN,
            f"Some models could not be validated: {', '.join(warnings[:2])}{'...' if len(warnings) > 2 else ''}",
            "Check API keys, provider status, and model names",
        )

    return CheckResult("LLM Model Validation", Status.PASS, f"Validated {len(models)} model(s)")

def check_git_status() -> CheckResult:
    """Check for uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=BACKEND_DIR.parent,
            timeout=10
        )
        if result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            return CheckResult(
                "Git Status",
                Status.WARN,
                f"{len(lines)} uncommitted changes",
                "Consider committing changes before running"
            )
        return CheckResult("Git Status", Status.PASS, "Working directory clean")
    except Exception as e:
        return CheckResult("Git Status", Status.SKIP, f"Could not check: {e}")

# ============================================================
# MAIN RUNNER
# ============================================================

ALL_CHECKS: List[Callable[[], CheckResult]] = [
    check_python_version,
    check_node_version,
    check_env_file,
    check_python_packages,
    check_backend_files,
    check_frontend_files,
    check_frontend_deps,
    check_config_yaml,
    check_llm_models_accessible,
    check_module_imports,
    check_port_availability,
    check_git_status,
]

def run_preflight(verbose: bool = True) -> bool:
    """Run all preflight checks. Returns True if all pass."""
    print("\n" + "=" * 60)
    print("🚀 CVA PREFLIGHT CHECK")
    print("=" * 60 + "\n")
    
    results: List[CheckResult] = []
    
    for check_fn in ALL_CHECKS:
        try:
            result = check_fn()
        except Exception as e:
            result = CheckResult(check_fn.__name__, Status.FAIL, f"Check crashed: {e}")
        results.append(result)
        
        icon = result.status.value
        print(f"  {icon} {result.name}: {result.message}")
        if result.fix_hint and result.status in (Status.FAIL, Status.WARN):
            print(f"      💡 {result.fix_hint}")
    
    # Summary
    passed = sum(1 for r in results if r.status == Status.PASS)
    failed = sum(1 for r in results if r.status == Status.FAIL)
    warned = sum(1 for r in results if r.status == Status.WARN)
    
    print("\n" + "-" * 60)
    print(f"  SUMMARY: {passed} passed, {warned} warnings, {failed} failed")
    print("-" * 60)
    
    if failed > 0:
        print("\n❌ PREFLIGHT FAILED - Fix issues before starting\n")
        return False
    elif warned > 0:
        print("\n⚠️  PREFLIGHT PASSED WITH WARNINGS\n")
        return True
    else:
        print("\n✅ ALL SYSTEMS GO!\n")
        return True

if __name__ == "__main__":
    success = run_preflight()
    sys.exit(0 if success else 1)
