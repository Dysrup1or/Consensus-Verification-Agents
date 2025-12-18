# Modular Judge Marketplace - Implementation Plan

**Created:** December 17, 2025  
**Status:** ✅ COMPLETED  
**Goal:** Domain extensibility through plugin-based judge architecture  
**Effort:** Completed in single session

---

## Implementation Status

### Files Created

```
modules/judge_marketplace/
├── __init__.py              # Package exports
├── models.py                # Core data models (JudgeDomain, JudgeResult, JudgeConfig, etc.)
├── plugin.py                # JudgePlugin ABC and BaseLLMJudge
├── registry.py              # JudgeRegistry for plugin management
├── tribunal_integration.py  # Adapter for existing Tribunal
├── core/
│   ├── __init__.py
│   ├── architect.py         # ArchitectJudge - design patterns
│   ├── security.py          # SecurityJudge - vulnerabilities [VETO]
│   └── user_proxy.py        # UserProxyJudge - requirements validation
└── domains/
    ├── __init__.py
    ├── hipaa.py             # HIPAA compliance judge [VETO]
    └── pci_dss.py           # PCI-DSS compliance judge [VETO]
```

### Quick Start

```python
from modules.judge_marketplace import (
    get_registry, register_judge, create_tribunal_adapter,
    JudgeDomain, BaseLLMJudge
)

# Get global registry and register judges
registry = get_registry()
registry.register(ArchitectJudge())
registry.register(SecurityJudge())
registry.register(HIPAAJudge())

# Use with Tribunal adapter
adapter = create_tribunal_adapter()
results = await adapter.evaluate_all(code, file_path)
passed, score, explanation = adapter.calculate_consensus(results)
```

---

## System Overview

The **Modular Judge Marketplace** transforms the CVA Tribunal from a fixed 3-judge system into an extensible plugin architecture where:

1. **Domain experts** can create specialized judges (Healthcare, Finance, Gaming, etc.)
2. **Community** can contribute and share judge plugins
3. **Organizations** can develop private internal judges
4. **Dynamic loading** allows runtime judge configuration without code changes

### Current State (Baseline)

```python
# tribunal.py - Hardcoded judge configuration
self.judges = {
    "architect": {"role": JudgeRole.ARCHITECT, "model": "anthropic/claude-sonnet-4-..."},
    "security": {"role": JudgeRole.SECURITY, "model": "deepseek/deepseek-chat"},
    "user_proxy": {"role": JudgeRole.USER_PROXY, "model": "gemini/gemini-2.0-flash-exp"},
}
```

**Limitations:**
- Fixed 3 judges only
- Cannot add domain-specific expertise
- No runtime configuration
- Tightly coupled to Tribunal class

### Target State

```python
# Load judges dynamically from registry
from modules.judge_marketplace import JudgeRegistry, load_judges_from_config

registry = JudgeRegistry()
registry.discover_plugins("./judges/")  # Auto-discover from folder
registry.load_from_config("config.yaml")  # Or from config

# Use in tribunal
tribunal = Tribunal(judge_registry=registry)
result = await tribunal.run_verification(code, spec)
```

**Improvements:**
- Unlimited custom judges
- Domain-specific verification (HIPAA, PCI-DSS, GDPR, etc.)
- Runtime configuration
- Plugin marketplace ecosystem

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Modular Judge Marketplace                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      JudgeRegistry                              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │  │
│  │  │   Core      │  │   Domain    │  │   Custom    │            │  │
│  │  │   Judges    │  │   Judges    │  │   Judges    │            │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                             │                                        │
│                             ▼                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      JudgePlugin (ABC)                         │  │
│  │                                                                 │  │
│  │  • name: str           • evaluate(code, spec) -> JudgeScore    │  │
│  │  • domain: str         • get_system_prompt() -> str            │  │
│  │  • weight: float       • supports_veto: bool                   │  │
│  │  • model: str          • validate_config() -> bool             │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                             │                                        │
│          ┌──────────────────┼──────────────────┐                    │
│          ▼                  ▼                  ▼                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │ Architect   │    │ Healthcare  │    │ Financial   │             │
│  │ Judge       │    │ Judge       │    │ Judge       │             │
│  │ (core)      │    │ (HIPAA)     │    │ (PCI-DSS)   │             │
│  └─────────────┘    └─────────────┘    └─────────────┘             │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. JudgePlugin (Abstract Base Class)

**Purpose:** Define the interface all judges must implement

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class JudgeResult:
    score: float              # 1-10 score
    explanation: str          # Why this score
    issues: List[str]         # Specific issues found
    suggestions: List[str]    # Improvement suggestions
    veto: bool = False        # Trigger veto?
    veto_reason: str = ""     # Why veto
    confidence: float = 0.8   # Confidence in result
    metadata: Dict = None     # Extra data

class JudgePlugin(ABC):
    """Base class for all judge plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable judge name."""
        pass
    
    @property
    @abstractmethod
    def domain(self) -> str:
        """Domain this judge specializes in (e.g., 'security', 'healthcare')."""
        pass
    
    @property
    def weight(self) -> float:
        """Weight in consensus calculation (default 1.0)."""
        return 1.0
    
    @property
    def supports_veto(self) -> bool:
        """Whether this judge can trigger a veto."""
        return False
    
    @property
    def veto_threshold(self) -> float:
        """Score below which veto triggers (if supports_veto)."""
        return 4.0
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this judge."""
        pass
    
    @abstractmethod
    async def evaluate(
        self,
        code_context: str,
        success_spec: Dict[str, Any],
        model: Optional[str] = None,
    ) -> JudgeResult:
        """Evaluate code against specification."""
        pass
    
    def validate(self) -> bool:
        """Validate judge configuration."""
        return bool(self.name and self.domain and self.get_system_prompt())
```

### 2. JudgeRegistry

**Purpose:** Manage discovery, loading, and access to judge plugins

```python
class JudgeRegistry:
    """Central registry for all judge plugins."""
    
    def __init__(self):
        self._judges: Dict[str, JudgePlugin] = {}
        self._domains: Dict[str, List[str]] = defaultdict(list)
    
    def register(self, judge: JudgePlugin) -> None:
        """Register a judge plugin."""
        ...
    
    def discover_plugins(self, directory: str) -> int:
        """Auto-discover and load plugins from directory."""
        ...
    
    def load_from_config(self, config_path: str) -> None:
        """Load judges specified in config file."""
        ...
    
    def get_judge(self, name: str) -> Optional[JudgePlugin]:
        """Get a specific judge by name."""
        ...
    
    def get_judges_for_domain(self, domain: str) -> List[JudgePlugin]:
        """Get all judges for a domain."""
        ...
    
    def get_active_judges(self) -> List[JudgePlugin]:
        """Get all currently active judges."""
        ...
```

### 3. Built-in Core Judges

The existing judges refactored as plugins:
- `ArchitectJudge` - Architecture and logic
- `SecurityJudge` - Security vulnerabilities (veto-enabled)
- `UserProxyJudge` - User intent alignment

### 4. Example Domain Judges

New specialized judges for specific domains:
- `HIPAAJudge` - Healthcare compliance (PHI handling)
- `PCIDSSJudge` - Payment card security
- `GDPRJudge` - Data privacy compliance
- `AccessibilityJudge` - WCAG/ADA compliance
- `PerformanceJudge` - Performance optimization

---

## Tasks

### Task 1: Create JudgePlugin Interface
**Objective:** Define the abstract base class for all judges
**Location:** `modules/judge_marketplace/plugin.py`
**Verification:** Can instantiate a mock judge implementing the interface

### Task 2: Create JudgeResult Dataclass  
**Objective:** Standardize judge output format
**Location:** `modules/judge_marketplace/models.py`
**Verification:** JudgeResult serializes to JSON correctly

### Task 3: Implement JudgeRegistry
**Objective:** Central management of judge plugins
**Location:** `modules/judge_marketplace/registry.py`
**Verification:** Can register, discover, and retrieve judges

### Task 4: Refactor Core Judges as Plugins
**Objective:** Convert existing judges to plugin architecture
**Location:** `modules/judge_marketplace/core/`
**Verification:** Existing functionality preserved, all tests pass

### Task 5: Create Domain Judge Examples
**Objective:** Build 2-3 example domain-specific judges
**Location:** `modules/judge_marketplace/domains/`
**Verification:** Domain judges evaluate correctly with relevant criteria

### Task 6: Integrate with Tribunal
**Objective:** Modify Tribunal to use JudgeRegistry
**Location:** `modules/tribunal.py`
**Verification:** Tribunal uses registry, backward compatible

### Task 7: Add Configuration Support
**Objective:** Enable config.yaml-based judge selection
**Location:** `modules/judge_marketplace/config.py`
**Verification:** Judges load from config file

### Task 8: Create Tests and Documentation
**Objective:** Comprehensive testing and docs
**Location:** `tests/test_judge_marketplace.py`, `docs/JUDGE_MARKETPLACE.md`
**Verification:** 80%+ test coverage, clear documentation

---

## File Structure

```
modules/judge_marketplace/
├── __init__.py              # Package exports
├── plugin.py                # JudgePlugin ABC
├── models.py                # JudgeResult, JudgeConfig
├── registry.py              # JudgeRegistry
├── config.py                # Configuration loading
├── core/                    # Built-in core judges
│   ├── __init__.py
│   ├── architect.py         # ArchitectJudge
│   ├── security.py          # SecurityJudge
│   └── user_proxy.py        # UserProxyJudge
└── domains/                 # Domain-specific judges
    ├── __init__.py
    ├── hipaa.py             # HIPAAJudge
    ├── pci_dss.py           # PCIDSSJudge
    └── accessibility.py     # AccessibilityJudge
```

---

## Configuration Format

```yaml
# config.yaml
judge_marketplace:
  # Which judges to use
  active_judges:
    - architect      # Core: architecture review
    - security       # Core: security (veto-enabled)
    - user_proxy     # Core: intent alignment
    - hipaa          # Domain: healthcare compliance
  
  # Judge-specific configuration
  judges:
    architect:
      model: "anthropic/claude-sonnet-4-20250514"
      weight: 1.2
    
    security:
      model: "deepseek/deepseek-chat"
      weight: 1.3
      veto_enabled: true
      veto_threshold: 4.0
    
    hipaa:
      model: "anthropic/claude-sonnet-4-20250514"
      weight: 1.5  # High weight for compliance
      veto_enabled: true
      patterns:
        - "PHI"
        - "patient_data"
        - "medical_record"
  
  # Plugin discovery
  plugin_directories:
    - "./custom_judges/"
    - "~/.cva/judges/"
```

---

## Verification Criteria

| Task | Success Criteria |
|------|------------------|
| Task 1 | JudgePlugin ABC importable, mock implementation works |
| Task 2 | JudgeResult JSON serializable, all fields accessible |
| Task 3 | Registry discovers 3+ plugins from directory |
| Task 4 | All existing tribunal tests pass |
| Task 5 | Domain judge evaluates code with 80%+ accuracy |
| Task 6 | Tribunal.run_verification() uses registry |
| Task 7 | Judges load from config.yaml |
| Task 8 | pytest passes, docs complete |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing Tribunal | Keep backward compatibility, feature flag |
| Plugin security | Sandboxed execution, validated prompts |
| Performance degradation | Parallel judge execution, caching |
| Configuration complexity | Sensible defaults, validation |

---

## Dependencies

- Python 3.9+
- pydantic (for data models)
- litellm (for LLM calls)
- PyYAML (for config loading)
- importlib (for dynamic loading)

---

## Success Metrics

1. **Extensibility:** Can add new judge in <30 minutes
2. **Performance:** No regression vs current 3-judge system
3. **Compatibility:** All existing tests pass
4. **Adoption:** Clear docs enable community contributions
