"""
Tests for Judge Marketplace System

Verifies:
- Plugin interface and validation
- Registry operations
- Domain-based filtering
- Tribunal integration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Optional

from modules.judge_marketplace import (
    JudgePlugin,
    JudgeResult,
    JudgeConfig,
    JudgeDomain,
    JudgeIssue,
    VerdictSeverity,
    JudgeRegistry,
    get_registry,
    register_judge,
    TribunalAdapter,
    create_tribunal_adapter,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_code_context():
    """Sample code context for evaluation."""
    return {
        "main.py": "def main():\n    print('Hello')\n",
        "utils.py": "def helper():\n    return 42\n",
    }


@pytest.fixture
def sample_success_spec():
    """Sample success specification."""
    return "A simple application that prints Hello."


@pytest.fixture
def fresh_registry():
    """Create a fresh registry for testing."""
    return JudgeRegistry()


# =============================================================================
# MOCK JUDGE IMPLEMENTATIONS
# =============================================================================

class MockJudge(JudgePlugin):
    """A minimal mock judge for testing."""
    
    def __init__(
        self,
        name: str = "mock_judge",
        display_name: str = "Mock Judge",
        domain: JudgeDomain = JudgeDomain.CUSTOM,
        score: float = 8.0,
    ):
        self._name = name
        self._display_name = display_name
        self._domain = domain
        self._score = score
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def display_name(self) -> str:
        return self._display_name
    
    @property
    def domain(self) -> JudgeDomain:
        return self._domain
    
    def get_system_prompt(self) -> str:
        return f"You are the {self._display_name}."
    
    async def evaluate(
        self,
        code_context: Dict[str, str],
        success_spec: str,
        config: Optional[JudgeConfig] = None,
    ) -> JudgeResult:
        return JudgeResult(
            score=self._score,
            explanation=f"Mock evaluation for {len(code_context)} files",
            confidence=0.9,
            issues=[],
            suggestions=[],
        )


class SecurityMockJudge(MockJudge):
    """Mock security judge."""
    
    def __init__(self):
        super().__init__(
            name="security_mock",
            display_name="Security Mock Judge",
            domain=JudgeDomain.SECURITY,
            score=7.5,
        )


class ArchitectMockJudge(MockJudge):
    """Mock architect judge."""
    
    def __init__(self):
        super().__init__(
            name="architect_mock",
            display_name="Architect Mock Judge",
            domain=JudgeDomain.ARCHITECTURE,
            score=8.5,
        )


class HIPAAMockJudge(MockJudge):
    """Mock HIPAA compliance judge."""
    
    def __init__(self):
        super().__init__(
            name="hipaa_mock",
            display_name="HIPAA Mock Judge",
            domain=JudgeDomain.HIPAA,
            score=9.0,
        )


# =============================================================================
# JUDGE PLUGIN TESTS
# =============================================================================

class TestJudgePlugin:
    """Tests for JudgePlugin interface."""
    
    def test_mock_judge_properties(self):
        """Test basic judge properties."""
        judge = MockJudge()
        
        assert judge.name == "mock_judge"
        assert judge.display_name == "Mock Judge"
        assert judge.domain == JudgeDomain.CUSTOM
    
    def test_custom_properties(self):
        """Test judge with custom properties."""
        judge = MockJudge(
            name="custom_test",
            display_name="Custom Test Judge",
            domain=JudgeDomain.SECURITY,
        )
        
        assert judge.name == "custom_test"
        assert judge.domain == JudgeDomain.SECURITY
    
    def test_get_system_prompt(self):
        """Test system prompt generation."""
        judge = MockJudge(display_name="Test Judge")
        prompt = judge.get_system_prompt()
        
        assert "Test Judge" in prompt
    
    @pytest.mark.asyncio
    async def test_evaluate(self, sample_code_context, sample_success_spec):
        """Test evaluate method."""
        judge = MockJudge(score=8.5)
        
        result = await judge.evaluate(
            code_context=sample_code_context,
            success_spec=sample_success_spec,
        )
        
        assert isinstance(result, JudgeResult)
        assert result.score == 8.5
        assert result.confidence == 0.9
        assert "2 files" in result.explanation


# =============================================================================
# JUDGE DOMAIN TESTS
# =============================================================================

class TestJudgeDomain:
    """Tests for JudgeDomain enum."""
    
    def test_core_domains_exist(self):
        """Test that core domains are defined."""
        assert JudgeDomain.ARCHITECTURE
        assert JudgeDomain.SECURITY
        assert JudgeDomain.INTENT
        assert JudgeDomain.USER_PROXY
    
    def test_compliance_domains_exist(self):
        """Test that compliance domains are defined."""
        assert JudgeDomain.HIPAA
        assert JudgeDomain.PCI_DSS
        assert JudgeDomain.GDPR
        assert JudgeDomain.SOC2
    
    def test_domain_values(self):
        """Test domain string values."""
        assert JudgeDomain.SECURITY.value == "security"
        assert JudgeDomain.HIPAA.value == "hipaa"
        assert JudgeDomain.CUSTOM.value == "custom"


# =============================================================================
# JUDGE RESULT TESTS
# =============================================================================

class TestJudgeResult:
    """Tests for JudgeResult dataclass."""
    
    def test_basic_result(self):
        """Test basic result creation."""
        result = JudgeResult(
            score=8.0,
            explanation="Code looks good",
        )
        
        assert result.score == 8.0
        assert result.explanation == "Code looks good"
        assert result.confidence == 0.8  # Default
    
    def test_result_with_issues(self):
        """Test result with issues."""
        issue = JudgeIssue(
            severity=VerdictSeverity.MEDIUM,
            message="Potential SQL injection",
            file_path="db.py",
            line_start=42,
        )
        
        result = JudgeResult(
            score=5.0,
            explanation="Security concerns found",
            issues=[issue],
        )
        
        assert len(result.issues) == 1
        assert result.issues[0].severity == VerdictSeverity.MEDIUM


# =============================================================================
# JUDGE ISSUE TESTS
# =============================================================================

class TestJudgeIssue:
    """Tests for JudgeIssue dataclass."""
    
    def test_basic_issue(self):
        """Test basic issue creation."""
        issue = JudgeIssue(
            severity=VerdictSeverity.HIGH,
            message="Hardcoded password detected",
        )
        
        assert issue.severity == VerdictSeverity.HIGH
        assert issue.message == "Hardcoded password detected"
        assert issue.file_path is None
    
    def test_detailed_issue(self):
        """Test issue with full details."""
        issue = JudgeIssue(
            severity=VerdictSeverity.CRITICAL,
            message="SQL injection vulnerability",
            file_path="api/routes.py",
            line_start=45,
            line_end=48,
            code_snippet="query = f'SELECT * FROM {table}'",
            suggested_fix="Use parameterized queries",
            rule_id="SEC001",
        )
        
        assert issue.file_path == "api/routes.py"
        assert issue.line_start == 45
        assert issue.rule_id == "SEC001"
    
    def test_to_dict(self):
        """Test issue serialization."""
        issue = JudgeIssue(
            severity=VerdictSeverity.MEDIUM,
            message="Test message",
            file_path="test.py",
        )
        
        data = issue.to_dict()
        
        assert data["severity"] == "medium"
        assert data["message"] == "Test message"
        assert data["file_path"] == "test.py"


# =============================================================================
# VERDICT SEVERITY TESTS
# =============================================================================

class TestVerdictSeverity:
    """Tests for VerdictSeverity enum."""
    
    def test_severity_levels(self):
        """Test all severity levels exist."""
        assert VerdictSeverity.CRITICAL
        assert VerdictSeverity.HIGH
        assert VerdictSeverity.MEDIUM
        assert VerdictSeverity.LOW
        assert VerdictSeverity.INFO
    
    def test_severity_values(self):
        """Test severity string values."""
        assert VerdictSeverity.CRITICAL.value == "critical"
        assert VerdictSeverity.INFO.value == "info"


# =============================================================================
# JUDGE REGISTRY TESTS
# =============================================================================

class TestJudgeRegistry:
    """Tests for JudgeRegistry."""
    
    def test_empty_registry(self, fresh_registry):
        """Test fresh registry is empty."""
        judges = fresh_registry.get_active_judges()
        assert len(judges) == 0
    
    def test_register_single_judge(self, fresh_registry):
        """Test registering a single judge."""
        judge = MockJudge()
        result = fresh_registry.register(judge)
        
        assert result is True
        assert "mock_judge" in fresh_registry.list_judges()
    
    def test_register_multiple_judges(self, fresh_registry):
        """Test registering multiple judges."""
        fresh_registry.register(SecurityMockJudge())
        fresh_registry.register(ArchitectMockJudge())
        fresh_registry.register(HIPAAMockJudge())
        
        judges = fresh_registry.list_judges()
        
        assert len(judges) == 3
        assert "security_mock" in judges
        assert "architect_mock" in judges
        assert "hipaa_mock" in judges
    
    def test_get_judge_by_name(self, fresh_registry):
        """Test retrieving judge by name."""
        original = SecurityMockJudge()
        fresh_registry.register(original)
        
        retrieved = fresh_registry.get_judge("security_mock")
        
        assert retrieved is not None
        assert retrieved.name == "security_mock"
    
    def test_get_nonexistent_judge(self, fresh_registry):
        """Test getting non-existent judge returns None."""
        result = fresh_registry.get_judge("does_not_exist")
        assert result is None
    
    def test_get_judges_by_domain(self, fresh_registry):
        """Test filtering judges by domain."""
        fresh_registry.register(SecurityMockJudge())
        fresh_registry.register(ArchitectMockJudge())
        fresh_registry.register(HIPAAMockJudge())
        
        security_judges = fresh_registry.get_judges_for_domain(JudgeDomain.SECURITY)
        
        assert len(security_judges) == 1
        assert security_judges[0].name == "security_mock"
    
    def test_unregister_judge(self, fresh_registry):
        """Test unregistering a judge."""
        fresh_registry.register(MockJudge())
        assert "mock_judge" in fresh_registry.list_judges()
        
        result = fresh_registry.unregister("mock_judge")
        
        assert result is True
        assert "mock_judge" not in fresh_registry.list_judges()
    
    def test_unregister_nonexistent(self, fresh_registry):
        """Test unregistering non-existent judge."""
        result = fresh_registry.unregister("does_not_exist")
        assert result is False
    
    def test_enable_disable_judge(self, fresh_registry):
        """Test enabling and disabling judges."""
        fresh_registry.register(MockJudge(), enabled=True)
        
        # Should be in active list initially
        active = fresh_registry.get_active_judges()
        assert len(active) == 1
        
        # Disable
        fresh_registry.disable("mock_judge")
        active = fresh_registry.get_active_judges()
        assert len(active) == 0
        
        # Re-enable
        fresh_registry.enable("mock_judge")
        active = fresh_registry.get_active_judges()
        assert len(active) == 1
    
    def test_replace_existing_judge(self, fresh_registry):
        """Test replacing a judge with same name."""
        judge1 = MockJudge(name="test", score=5.0)
        judge2 = MockJudge(name="test", score=9.0)
        
        fresh_registry.register(judge1)
        fresh_registry.register(judge2)
        
        retrieved = fresh_registry.get_judge("test")
        assert retrieved._score == 9.0


# =============================================================================
# TRIBUNAL INTEGRATION TESTS
# =============================================================================

class TestTribunalAdapter:
    """Tests for TribunalAdapter."""
    
    def test_create_adapter(self):
        """Test adapter creation."""
        adapter = create_tribunal_adapter()
        assert adapter is not None
        assert isinstance(adapter, TribunalAdapter)
    
    def test_adapter_with_registry(self, fresh_registry):
        """Test adapter with custom registry."""
        fresh_registry.register(SecurityMockJudge())
        fresh_registry.register(ArchitectMockJudge())
        
        adapter = TribunalAdapter(registry=fresh_registry)
        
        assert adapter.registry is fresh_registry


# =============================================================================
# GLOBAL REGISTRY TESTS
# =============================================================================

class TestGlobalRegistry:
    """Tests for global registry functions."""
    
    def test_get_registry_singleton(self):
        """Test get_registry returns same instance."""
        reg1 = get_registry()
        reg2 = get_registry()
        
        assert reg1 is reg2
    
    def test_register_judge_convenience(self):
        """Test register_judge convenience function."""
        judge = MockJudge(name="global_test")
        
        # Should not raise
        result = register_judge(judge)
        assert result is True


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestJudgeMarketplaceIntegration:
    """Integration tests for the complete marketplace system."""
    
    @pytest.mark.asyncio
    async def test_full_evaluation_flow(
        self,
        fresh_registry,
        sample_code_context,
        sample_success_spec,
    ):
        """Test complete evaluation flow."""
        # Register judges
        fresh_registry.register(SecurityMockJudge())
        fresh_registry.register(ArchitectMockJudge())
        
        # Get active judges
        judges = fresh_registry.get_active_judges()
        assert len(judges) == 2
        
        # Evaluate with each judge
        results = []
        for judge in judges:
            result = await judge.evaluate(
                code_context=sample_code_context,
                success_spec=sample_success_spec,
            )
            results.append(result)
        
        # Verify results
        assert len(results) == 2
        assert all(isinstance(r, JudgeResult) for r in results)
        scores = [r.score for r in results]
        assert 7.5 in scores  # Security mock
        assert 8.5 in scores  # Architect mock
    
    def test_multi_domain_filtering(self, fresh_registry):
        """Test filtering judges across multiple domains."""
        # Register various judges
        fresh_registry.register(SecurityMockJudge())
        fresh_registry.register(ArchitectMockJudge())
        fresh_registry.register(HIPAAMockJudge())
        fresh_registry.register(MockJudge(name="custom1", domain=JudgeDomain.CUSTOM))
        fresh_registry.register(MockJudge(name="custom2", domain=JudgeDomain.CUSTOM))
        
        # Filter by domain
        security = fresh_registry.get_judges_for_domain(JudgeDomain.SECURITY)
        compliance = fresh_registry.get_judges_for_domain(JudgeDomain.HIPAA)
        custom = fresh_registry.get_judges_for_domain(JudgeDomain.CUSTOM)
        
        assert len(security) == 1
        assert len(compliance) == 1
        assert len(custom) == 2
