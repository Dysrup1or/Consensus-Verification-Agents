"""
Judge Marketplace - Registry

Central registry for discovering, loading, and managing judge plugins.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import yaml
from loguru import logger

from .models import JudgeConfig, JudgeDomain, JudgeResult
from .plugin import JudgePlugin


class JudgeRegistry:
    """
    Central registry for all judge plugins.
    
    Supports:
    - Manual registration of judge instances
    - Auto-discovery from directories
    - Configuration-based loading
    - Domain-based filtering
    
    Usage:
        registry = JudgeRegistry()
        
        # Register a judge
        registry.register(MyCustomJudge())
        
        # Discover plugins from directory
        registry.discover_plugins("./custom_judges/")
        
        # Get judges
        all_judges = registry.get_active_judges()
        security_judges = registry.get_judges_for_domain(JudgeDomain.SECURITY)
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._judges: Dict[str, JudgePlugin] = {}
        self._configs: Dict[str, JudgeConfig] = {}
        self._domains: Dict[str, List[str]] = defaultdict(list)
        self._enabled: set = set()
        self._load_order: List[str] = []
    
    # =========================================================================
    # REGISTRATION
    # =========================================================================
    
    def register(
        self,
        judge: JudgePlugin,
        config: Optional[JudgeConfig] = None,
        enabled: bool = True,
    ) -> bool:
        """
        Register a judge plugin.
        
        Args:
            judge: The judge plugin instance
            config: Optional configuration (uses judge defaults if None)
            enabled: Whether the judge is initially enabled
            
        Returns:
            True if registered successfully, False otherwise
        """
        if not judge.validate():
            logger.warning(f"Judge {judge.name} failed validation, not registered")
            return False
        
        name = judge.name
        
        if name in self._judges:
            logger.debug(f"Replacing existing judge: {name}")
        
        self._judges[name] = judge
        self._configs[name] = config or judge.get_config()
        self._domains[judge.domain.value].append(name)
        self._load_order.append(name)
        
        if enabled:
            self._enabled.add(name)
        
        logger.info(f"Registered judge: {judge.display_name} ({name})")
        return True
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a judge.
        
        Args:
            name: Judge name to remove
            
        Returns:
            True if removed, False if not found
        """
        if name not in self._judges:
            return False
        
        judge = self._judges[name]
        del self._judges[name]
        del self._configs[name]
        self._enabled.discard(name)
        
        if name in self._domains[judge.domain.value]:
            self._domains[judge.domain.value].remove(name)
        
        if name in self._load_order:
            self._load_order.remove(name)
        
        logger.info(f"Unregistered judge: {name}")
        return True
    
    # =========================================================================
    # DISCOVERY
    # =========================================================================
    
    def discover_plugins(
        self,
        directory: str,
        pattern: str = "*.py",
        recursive: bool = True,
    ) -> int:
        """
        Auto-discover and load judge plugins from a directory.
        
        Plugins should be Python files containing classes that inherit
        from JudgePlugin.
        
        Args:
            directory: Path to search
            pattern: File pattern to match
            recursive: Whether to search subdirectories
            
        Returns:
            Number of plugins discovered
        """
        dir_path = Path(directory).resolve()
        
        if not dir_path.exists():
            logger.warning(f"Plugin directory not found: {directory}")
            return 0
        
        discovered = 0
        glob_method = dir_path.rglob if recursive else dir_path.glob
        
        for file_path in glob_method(pattern):
            if file_path.name.startswith("_"):
                continue
            
            try:
                judges = self._load_plugins_from_file(file_path)
                for judge in judges:
                    if self.register(judge):
                        discovered += 1
            except Exception as e:
                logger.warning(f"Failed to load plugins from {file_path}: {e}")
        
        logger.info(f"Discovered {discovered} plugins from {directory}")
        return discovered
    
    def _load_plugins_from_file(self, file_path: Path) -> List[JudgePlugin]:
        """Load all JudgePlugin subclasses from a Python file."""
        judges = []
        
        # Generate unique module name
        module_name = f"_judge_plugin_{file_path.stem}_{id(file_path)}"
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return judges
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        
        try:
            spec.loader.exec_module(module)
            
            # Find all JudgePlugin subclasses
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, JudgePlugin)
                    and obj is not JudgePlugin
                    and not getattr(obj, '__abstractmethods__', None)
                ):
                    try:
                        instance = obj()
                        judges.append(instance)
                        logger.debug(f"Loaded plugin: {instance.name} from {file_path.name}")
                    except Exception as e:
                        logger.warning(f"Failed to instantiate {name}: {e}")
        finally:
            # Clean up
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        return judges
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    def load_from_config(self, config_path: str) -> int:
        """
        Load and configure judges from a YAML config file.
        
        Expected format:
            judge_marketplace:
              active_judges:
                - architect
                - security
              judges:
                architect:
                  model: "anthropic/claude-sonnet-4"
                  weight: 1.2
        
        Args:
            config_path: Path to YAML config file
            
        Returns:
            Number of judges configured
        """
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}")
            return 0
        
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return 0
        
        marketplace_config = config.get("judge_marketplace", {})
        
        # Configure active judges
        active = marketplace_config.get("active_judges", [])
        if active:
            self._enabled = set(active) & set(self._judges.keys())
        
        # Apply judge-specific configuration
        judges_config = marketplace_config.get("judges", {})
        configured = 0
        
        for name, judge_config in judges_config.items():
            if name not in self._judges:
                logger.warning(f"Config for unknown judge: {name}")
                continue
            
            self._configs[name] = JudgeConfig.from_dict({
                "name": name,
                **judge_config,
            })
            configured += 1
        
        # Load from plugin directories
        for plugin_dir in marketplace_config.get("plugin_directories", []):
            self.discover_plugins(os.path.expanduser(plugin_dir))
        
        return configured
    
    def configure_judge(self, name: str, config: JudgeConfig) -> bool:
        """
        Update configuration for a specific judge.
        
        Args:
            name: Judge name
            config: New configuration
            
        Returns:
            True if configured, False if judge not found
        """
        if name not in self._judges:
            return False
        
        self._configs[name] = config
        
        if config.enabled:
            self._enabled.add(name)
        else:
            self._enabled.discard(name)
        
        return True
    
    # =========================================================================
    # RETRIEVAL
    # =========================================================================
    
    def get_judge(self, name: str) -> Optional[JudgePlugin]:
        """Get a specific judge by name."""
        return self._judges.get(name)
    
    def get_config(self, name: str) -> Optional[JudgeConfig]:
        """Get configuration for a specific judge."""
        return self._configs.get(name)
    
    def get_judges_for_domain(
        self,
        domain: JudgeDomain,
        enabled_only: bool = True,
    ) -> List[JudgePlugin]:
        """Get all judges for a specific domain."""
        names = self._domains.get(domain.value, [])
        judges = []
        
        for name in names:
            if enabled_only and name not in self._enabled:
                continue
            if name in self._judges:
                judges.append(self._judges[name])
        
        return judges
    
    def get_active_judges(self) -> List[JudgePlugin]:
        """Get all currently enabled judges."""
        return [
            self._judges[name]
            for name in self._load_order
            if name in self._enabled and name in self._judges
        ]
    
    def get_all_judges(self) -> List[JudgePlugin]:
        """Get all registered judges (enabled or not)."""
        return [
            self._judges[name]
            for name in self._load_order
            if name in self._judges
        ]
    
    def get_veto_judges(self) -> List[JudgePlugin]:
        """Get all judges that can trigger a veto."""
        veto_judges = []
        for name in self._enabled:
            if name not in self._judges:
                continue
            config = self._configs.get(name)
            if config and config.veto_enabled:
                veto_judges.append(self._judges[name])
        return veto_judges
    
    # =========================================================================
    # ENABLE/DISABLE
    # =========================================================================
    
    def enable(self, name: str) -> bool:
        """Enable a judge."""
        if name not in self._judges:
            return False
        self._enabled.add(name)
        return True
    
    def disable(self, name: str) -> bool:
        """Disable a judge."""
        if name not in self._judges:
            return False
        self._enabled.discard(name)
        return True
    
    def is_enabled(self, name: str) -> bool:
        """Check if a judge is enabled."""
        return name in self._enabled
    
    # =========================================================================
    # INFORMATION
    # =========================================================================
    
    def list_judges(self) -> Dict[str, Dict[str, Any]]:
        """Get a summary of all registered judges."""
        summary = {}
        for name in self._load_order:
            if name not in self._judges:
                continue
            judge = self._judges[name]
            config = self._configs.get(name)
            
            summary[name] = {
                "display_name": judge.display_name,
                "domain": judge.domain.value,
                "description": judge.description,
                "version": judge.version,
                "enabled": name in self._enabled,
                "veto_enabled": config.veto_enabled if config else False,
                "weight": config.weight if config else 1.0,
                "model": config.model if config else judge.default_model,
            }
        
        return summary
    
    def get_domains(self) -> List[str]:
        """Get list of all domains with registered judges."""
        return [d for d in self._domains if self._domains[d]]
    
    def __len__(self) -> int:
        """Number of registered judges."""
        return len(self._judges)
    
    def __contains__(self, name: str) -> bool:
        """Check if a judge is registered."""
        return name in self._judges
    
    def __iter__(self):
        """Iterate over active judges."""
        return iter(self.get_active_judges())


# =============================================================================
# GLOBAL REGISTRY
# =============================================================================

_global_registry: Optional[JudgeRegistry] = None


def get_registry() -> JudgeRegistry:
    """Get or create the global judge registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = JudgeRegistry()
    return _global_registry


def register_judge(judge: JudgePlugin, **kwargs) -> bool:
    """Register a judge with the global registry."""
    return get_registry().register(judge, **kwargs)


def get_judge(name: str) -> Optional[JudgePlugin]:
    """Get a judge from the global registry."""
    return get_registry().get_judge(name)
