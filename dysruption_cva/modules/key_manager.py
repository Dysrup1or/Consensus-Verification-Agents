"""
Dysruption CVA - Key Manager Module

Handles API key validation, rotation, and credit monitoring for LLM providers.
Provides early warnings when API credits are running low.

Version: 2.0
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import yaml
from loguru import logger
from pathlib import Path

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class KeyStatus:
    """Status of an API key"""
    provider: str
    key_suffix: str  # Last 4 chars for identification
    is_valid: bool
    last_checked: datetime
    error_count: int
    last_error: Optional[str]
    credit_balance: Optional[float]
    credit_warning: bool


@dataclass
class ProviderHealth:
    """Health status for a provider"""
    provider: str
    is_healthy: bool
    available_keys: int
    total_keys: int
    last_successful_call: Optional[datetime]
    rate_limited: bool
    rate_limit_reset: Optional[datetime]


# =============================================================================
# KEY MANAGER
# =============================================================================


class KeyManager:
    """
    Manages API keys for multiple LLM providers.
    
    Features:
    - Key validation on startup
    - Credit balance monitoring (where supported)
    - Automatic key rotation on rate limit/quota errors
    - Low credit alerts via loguru
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.env_keys_config = self.config.get("env_keys", {})
        self.credits_config = self.config.get("credits", {})
        
        # Key status tracking
        self._key_status: Dict[str, KeyStatus] = {}
        self._provider_health: Dict[str, ProviderHealth] = {}
        
        # Error tracking for rate limits
        self._error_counts: Dict[str, int] = {}
        self._rate_limit_until: Dict[str, datetime] = {}
        
        # Monitoring thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        
        # Initialize
        self._initialize_keys()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML."""
        config_file = Path(config_path)
        if not config_file.exists():
            return {}
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def _initialize_keys(self) -> None:
        """Initialize and validate all API keys."""
        providers = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        
        # Override with config if specified
        for provider, default_key in providers.items():
            env_key = self.env_keys_config.get(provider, default_key)
            key_value = os.environ.get(env_key, "")
            
            is_valid = bool(key_value and len(key_value) > 10)
            key_suffix = key_value[-4:] if key_value else "NONE"
            
            self._key_status[provider] = KeyStatus(
                provider=provider,
                key_suffix=key_suffix,
                is_valid=is_valid,
                last_checked=datetime.now(),
                error_count=0,
                last_error=None,
                credit_balance=None,
                credit_warning=False,
            )
            
            self._provider_health[provider] = ProviderHealth(
                provider=provider,
                is_healthy=is_valid,
                available_keys=1 if is_valid else 0,
                total_keys=1,
                last_successful_call=None,
                rate_limited=False,
                rate_limit_reset=None,
            )
            
            if is_valid:
                logger.info(f"✓ {provider.upper()} key found (****{key_suffix})")
            else:
                logger.warning(f"✗ {provider.upper()} key not set or invalid")

    def check_all_keys(self) -> Dict[str, bool]:
        """Check validity of all API keys."""
        results = {}
        for provider, status in self._key_status.items():
            results[provider] = status.is_valid
        return results

    def get_healthy_provider(self, preferred: str) -> Optional[str]:
        """
        Get a healthy provider, preferring the specified one.
        Falls back to other providers if preferred is unhealthy.
        """
        # Check preferred first
        health = self._provider_health.get(preferred)
        if health and health.is_healthy and not health.rate_limited:
            return preferred
        
        # Fallback chain
        fallback_order = ["deepseek", "openai", "anthropic", "google", "groq"]
        
        for provider in fallback_order:
            if provider == preferred:
                continue
            health = self._provider_health.get(provider)
            if health and health.is_healthy and not health.rate_limited:
                logger.warning(f"Preferred provider {preferred} unhealthy, using {provider}")
                return provider
        
        return None

    def record_success(self, provider: str) -> None:
        """Record a successful API call."""
        if provider in self._provider_health:
            self._provider_health[provider].is_healthy = True
            self._provider_health[provider].last_successful_call = datetime.now()
            self._provider_health[provider].rate_limited = False
            self._error_counts[provider] = 0

    def record_error(self, provider: str, error: str, is_rate_limit: bool = False) -> None:
        """Record an API error."""
        self._error_counts[provider] = self._error_counts.get(provider, 0) + 1
        
        if provider in self._key_status:
            self._key_status[provider].error_count += 1
            self._key_status[provider].last_error = error[:100]
        
        if provider in self._provider_health:
            # Mark as rate limited if hit limit
            if is_rate_limit:
                self._provider_health[provider].rate_limited = True
                # Estimate reset time (usually 60 seconds)
                from datetime import timedelta
                self._provider_health[provider].rate_limit_reset = (
                    datetime.now() + timedelta(seconds=60)
                )
                logger.warning(f"⚠️ {provider.upper()} rate limited, retry after 60s")
            
            # Mark as unhealthy after 3 consecutive errors
            if self._error_counts.get(provider, 0) >= 3:
                self._provider_health[provider].is_healthy = False
                logger.error(f"🔴 {provider.upper()} marked unhealthy (3+ errors)")

    def check_rate_limit_expired(self, provider: str) -> bool:
        """Check if rate limit has expired for a provider."""
        health = self._provider_health.get(provider)
        if not health or not health.rate_limited:
            return True
        
        if health.rate_limit_reset and datetime.now() >= health.rate_limit_reset:
            health.rate_limited = False
            health.rate_limit_reset = None
            logger.info(f"✓ {provider.upper()} rate limit expired")
            return True
        
        return False

    def get_status_report(self) -> str:
        """Generate a status report for all providers."""
        lines = ["# API Key Status Report", f"Generated: {datetime.now().isoformat()}", ""]
        
        for provider, status in self._key_status.items():
            health = self._provider_health.get(provider)
            
            icon = "✅" if (status.is_valid and health and health.is_healthy) else "❌"
            rate_icon = "⚠️" if (health and health.rate_limited) else ""
            
            lines.append(f"## {provider.upper()} {icon} {rate_icon}")
            lines.append(f"- Key: ****{status.key_suffix}")
            lines.append(f"- Valid: {status.is_valid}")
            lines.append(f"- Errors: {status.error_count}")
            if status.last_error:
                lines.append(f"- Last Error: {status.last_error}")
            if status.credit_balance is not None:
                lines.append(f"- Credit: ${status.credit_balance:.2f}")
            if health and health.rate_limited:
                lines.append(f"- Rate Limited Until: {health.rate_limit_reset}")
            lines.append("")
        
        return "\n".join(lines)

    def start_monitoring(self, interval_seconds: int = 300) -> None:
        """Start background credit monitoring."""
        if not self.credits_config.get("monitor_enabled", False):
            logger.debug("Credit monitoring disabled in config")
            return
        
        def monitor_loop():
            while not self._stop_monitoring.is_set():
                try:
                    self._check_credits()
                except Exception as e:
                    logger.error(f"Credit monitoring error: {e}")
                
                self._stop_monitoring.wait(interval_seconds)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Started credit monitoring (interval: {interval_seconds}s)")

    def stop_monitoring(self) -> None:
        """Stop background credit monitoring."""
        if self._monitor_thread:
            self._stop_monitoring.set()
            self._monitor_thread.join(timeout=5)
            logger.info("Stopped credit monitoring")

    def _check_credits(self) -> None:
        """Check credit balances (placeholder - requires provider-specific implementation)."""
        # This would need provider-specific API calls to check balance
        # For now, just check for recent errors that indicate low credit
        
        alert_thresholds = self.credits_config.get("alert_thresholds", {})
        
        for provider, status in self._key_status.items():
            if status.last_error and "credit" in status.last_error.lower():
                logger.warning(f"💳 CREDIT ALERT: {provider.upper()} may have low balance")
                status.credit_warning = True


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================


_key_manager: Optional[KeyManager] = None


def get_key_manager(config_path: str = "config.yaml") -> KeyManager:
    """Get or create the singleton KeyManager instance."""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager(config_path)
    return _key_manager


def check_environment() -> Dict[str, bool]:
    """Quick check of environment variables."""
    km = get_key_manager()
    return km.check_all_keys()


# =============================================================================
# CLI
# =============================================================================


if __name__ == "__main__":
    import sys
    
    logger.add(sys.stderr, level="DEBUG")
    
    km = get_key_manager()
    print(km.get_status_report())
