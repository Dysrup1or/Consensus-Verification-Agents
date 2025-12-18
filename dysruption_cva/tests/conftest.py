# Pytest configuration for Dysruption CVA test suite
# Created: 2025-12-16
#
# Timeout strategy:
# - FAST tests: 10s (pure unit tests, no I/O)
# - MEDIUM tests: 30s (file I/O, mocked HTTP)
# - SLOW tests: 60s (integration, TestClient, subprocess)
# - VERY_SLOW tests: 90s (full integration with async waits)

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Timeout configuration by test file
# ---------------------------------------------------------------------------
# Maps test file patterns to timeout values (seconds)
# More specific patterns should come first

TIMEOUT_MAP = {
    # SLOW tests (60s) - Integration, real DB, complex flows
    "test_migrations": 60,
    "test_integration_flow": 60,
    "test_tribunal_integration_intent_trigger_webhook": 90,
    
    # MEDIUM tests (30s) - File I/O, mocked HTTP, TestClient
    "test_tribunal": 30,
    "test_watcher": 60,  # 31 tests, complex setup
    "test_phase1_coverage_plan_large_changeset": 30,
    "test_phase4_self_heal_patch_loop": 30,
    "test_config_endpoints": 15,
    "test_github_app_auth": 30,
    "test_monitor_webhook": 30,
    
    # FAST tests (10s) - Pure unit tests
    "test_parser": 10,
    "test_tribunal_verdict_schema": 5,
    "test_telemetry_schema": 5,
    "test_treesitter_status": 5,
    "test_phase2": 10,
    "test_phase3": 20,
    "test_phase5": 10,
    "test_tribunal_diff_detection": 10,
    "test_tribunal_import_resolution": 10,
    "test_tribunal_token_budget": 20,
    "test_ws_token": 10,
}


def pytest_collection_modifyitems(config, items):
    """Apply timeout markers based on test file names."""
    for item in items:
        # Get the test file name without path
        test_file = item.fspath.basename if hasattr(item.fspath, 'basename') else str(item.fspath).split('/')[-1]
        test_name = test_file.replace('.py', '')
        
        # Find matching timeout
        timeout = 30  # default
        for pattern, t in TIMEOUT_MAP.items():
            if pattern in test_name:
                timeout = t
                break
        
        # Apply timeout marker if not already set
        existing_timeout = item.get_closest_marker('timeout')
        if existing_timeout is None:
            item.add_marker(pytest.mark.timeout(timeout))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for Windows compatibility."""
    import asyncio
    import sys
    if sys.platform == "win32":
        # Use ProactorEventLoop on Windows for subprocess support
        return asyncio.WindowsProactorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def reset_caches():
    """Clear LRU caches between tests to ensure isolation."""
    yield
    # Clear dependency resolver caches
    try:
        from dysruption_cva.modules.dependency_resolver import (
            _load_tsconfig_paths,
            _load_root_workspaces_patterns,
            _workspace_name_to_dir,
        )
        _load_tsconfig_paths.cache_clear()
        _load_root_workspaces_patterns.cache_clear()
        _workspace_name_to_dir.cache_clear()
    except (ImportError, AttributeError):
        pass
