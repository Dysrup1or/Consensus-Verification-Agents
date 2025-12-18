"""
Tests for Workflow Composition System

Verifies:
- Workflow base class behavior
- Chain execution and result aggregation
- Abort behavior and failure handling
- Predefined workflows
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
from pathlib import Path

from modules.workflows import (
    Workflow,
    WorkflowResult,
    WorkflowStatus,
    WorkflowContext,
    WorkflowChain,
    ChainResult,
    ChainExecutionMode,
    LintWorkflow,
    SecurityWorkflow,
    StyleWorkflow,
    FullVerificationWorkflow,
    create_standard_chain,
    create_fast_chain,
    create_security_chain,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_context():
    """Create a sample workflow context."""
    return WorkflowContext(
        file_tree={
            "main.py": "def hello():\n    print('Hello')\n",
            "utils.py": "def helper():\n    return 42\n",
        },
        spec_content="A simple hello world application",
        target_dir="/tmp/test",
    )


@pytest.fixture
def empty_context():
    """Create an empty workflow context."""
    return WorkflowContext()


@pytest.fixture
def failing_code_context():
    """Create context with code that has syntax errors."""
    return WorkflowContext(
        file_tree={
            "broken.py": "def broken(\n    print('missing paren'",  # Syntax error
        },
        spec_content="Test spec",
    )


# =============================================================================
# WORKFLOW CONTEXT TESTS
# =============================================================================

class TestWorkflowContext:
    """Tests for WorkflowContext dataclass."""
    
    def test_add_issue(self, empty_context):
        """Test adding issues to context."""
        empty_context.add_issue(
            workflow_name="test_workflow",
            file_path="test.py",
            line=10,
            message="Test issue",
            severity="medium",
        )
        
        assert len(empty_context.accumulated_issues) == 1
        issue = empty_context.accumulated_issues[0]
        assert issue["workflow"] == "test_workflow"
        assert issue["file"] == "test.py"
        assert issue["line"] == 10
        assert issue["message"] == "Test issue"
        assert issue["severity"] == "medium"
        assert "timestamp" in issue
    
    def test_request_abort(self, empty_context):
        """Test abort request."""
        assert not empty_context.should_abort
        
        empty_context.request_abort("Critical error")
        
        assert empty_context.should_abort
        assert empty_context.abort_reason == "Critical error"
    
    def test_modified_files_tracking(self, sample_context):
        """Test modified files set."""
        assert len(sample_context.modified_files) == 0
        
        sample_context.modified_files.add("main.py")
        sample_context.modified_files.add("new_file.py")
        
        assert len(sample_context.modified_files) == 2
        assert "main.py" in sample_context.modified_files


# =============================================================================
# WORKFLOW RESULT TESTS
# =============================================================================

class TestWorkflowResult:
    """Tests for WorkflowResult dataclass."""
    
    def test_passed_property(self):
        """Test passed property."""
        result = WorkflowResult(
            workflow_name="test",
            workflow_type="test",
            status=WorkflowStatus.PASSED,
            score=1.0,
        )
        assert result.passed
        assert not result.failed
    
    def test_failed_property(self):
        """Test failed property for various failure states."""
        for status in [WorkflowStatus.FAILED, WorkflowStatus.ABORTED, WorkflowStatus.ERROR]:
            result = WorkflowResult(
                workflow_name="test",
                workflow_type="test",
                status=status,
                score=0.0,
            )
            assert result.failed
            assert not result.passed
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = WorkflowResult(
            workflow_name="test_workflow",
            workflow_type="security",
            status=WorkflowStatus.PASSED,
            score=0.95,
            message="All checks passed",
            issues=[{"file": "test.py", "line": 1}],
            suggestions=["Consider adding tests"],
        )
        
        data = result.to_dict()
        
        assert data["workflow_name"] == "test_workflow"
        assert data["workflow_type"] == "security"
        assert data["status"] == "passed"
        assert data["score"] == 0.95
        assert len(data["issues"]) == 1


# =============================================================================
# MOCK WORKFLOW TESTS
# =============================================================================

class MockPassingWorkflow(Workflow):
    """A workflow that always passes."""
    
    @property
    def name(self):
        return "mock_passing"
    
    @property
    def workflow_type(self):
        return "test"
    
    async def execute(self, context):
        return self.create_result(
            status=WorkflowStatus.PASSED,
            score=1.0,
            message="Mock passed",
        )


class MockFailingWorkflow(Workflow):
    """A workflow that always fails."""
    
    def __init__(self, abort_chain: bool = False):
        self._abort_chain = abort_chain
    
    @property
    def name(self):
        return "mock_failing"
    
    @property
    def workflow_type(self):
        return "test"
    
    @property
    def abort_on_fail(self):
        return self._abort_chain
    
    async def execute(self, context):
        return self.create_result(
            status=WorkflowStatus.FAILED,
            score=0.0,
            message="Mock failed",
            abort_chain=self._abort_chain,
            abort_reason="Test abort" if self._abort_chain else "",
        )


class MockSkipWorkflow(Workflow):
    """A workflow that should be skipped."""
    
    @property
    def name(self):
        return "mock_skip"
    
    @property
    def workflow_type(self):
        return "test"
    
    async def should_run(self, context):
        return False
    
    async def execute(self, context):
        return self.create_result(
            status=WorkflowStatus.PASSED,
            message="Should not see this",
        )


# =============================================================================
# WORKFLOW CHAIN TESTS
# =============================================================================

class TestWorkflowChain:
    """Tests for WorkflowChain."""
    
    @pytest.mark.asyncio
    async def test_empty_chain(self, sample_context):
        """Test executing empty chain."""
        chain = WorkflowChain("empty")
        result = await chain.execute(sample_context)
        
        # Empty chain with no workflows passes (nothing to fail)
        assert result.status == WorkflowStatus.PASSED
        assert result.total_workflows == 0
    
    @pytest.mark.asyncio
    async def test_single_passing_workflow(self, sample_context):
        """Test chain with single passing workflow."""
        chain = WorkflowChain("single_pass")
        chain.add(MockPassingWorkflow())
        
        result = await chain.execute(sample_context)
        
        assert result.status == WorkflowStatus.PASSED
        assert result.passed_count == 1
        assert result.failed_count == 0
        assert len(result.workflow_results) == 1
    
    @pytest.mark.asyncio
    async def test_single_failing_workflow(self, sample_context):
        """Test chain with single failing workflow."""
        chain = WorkflowChain("single_fail")
        chain.add(MockFailingWorkflow())
        
        result = await chain.execute(sample_context)
        
        assert result.status == WorkflowStatus.FAILED
        assert result.passed_count == 0
        assert result.failed_count == 1
    
    @pytest.mark.asyncio
    async def test_mixed_workflow_chain(self, sample_context):
        """Test chain with mixed results."""
        chain = WorkflowChain(
            "mixed",
            mode=ChainExecutionMode.CONTINUE_ON_FAILURE,
        )
        chain.add(MockPassingWorkflow())
        chain.add(MockFailingWorkflow())
        chain.add(MockPassingWorkflow())
        
        result = await chain.execute(sample_context)
        
        assert result.status == WorkflowStatus.FAILED  # Overall fail due to one failure
        assert result.passed_count == 2
        assert result.failed_count == 1
        assert len(result.workflow_results) == 3
    
    @pytest.mark.asyncio
    async def test_fail_fast_mode(self, sample_context):
        """Test fail-fast mode stops on first failure."""
        chain = WorkflowChain(
            "fail_fast",
            mode=ChainExecutionMode.FAIL_FAST,
        )
        chain.add(MockPassingWorkflow())
        chain.add(MockFailingWorkflow())
        chain.add(MockPassingWorkflow())  # Should not run
        
        result = await chain.execute(sample_context)
        
        assert result.was_aborted
        assert result.passed_count == 1
        assert result.failed_count == 1
        assert len(result.workflow_results) == 2  # Third workflow not executed
    
    @pytest.mark.asyncio
    async def test_abort_on_request_mode(self, sample_context):
        """Test abort-on-request mode."""
        chain = WorkflowChain(
            "abort_request",
            mode=ChainExecutionMode.ABORT_ON_REQUEST,
        )
        chain.add(MockPassingWorkflow())
        chain.add(MockFailingWorkflow(abort_chain=True))  # Requests abort
        chain.add(MockPassingWorkflow())  # Should not run
        
        result = await chain.execute(sample_context)
        
        assert result.was_aborted
        assert result.aborted_by_workflow == "mock_failing"
        assert len(result.workflow_results) == 2
    
    @pytest.mark.asyncio
    async def test_skipped_workflow(self, sample_context):
        """Test workflow skipping."""
        chain = WorkflowChain("with_skip")
        chain.add(MockPassingWorkflow())
        chain.add(MockSkipWorkflow())
        chain.add(MockPassingWorkflow())
        
        result = await chain.execute(sample_context)
        
        assert result.status == WorkflowStatus.PASSED
        assert result.passed_count == 2
        assert result.skipped_count == 1
    
    @pytest.mark.asyncio
    async def test_context_created_from_params(self):
        """Test context creation from execute parameters."""
        chain = WorkflowChain("from_params")
        chain.add(MockPassingWorkflow())
        
        result = await chain.execute(
            file_tree={"test.py": "pass"},
            spec_content="Test spec",
            target_dir="/tmp",
        )
        
        assert result.passed
    
    def test_fluent_api(self):
        """Test fluent chain construction."""
        chain = (
            WorkflowChain("fluent")
            .add(MockPassingWorkflow())
            .add(MockPassingWorkflow())
        )
        
        assert len(chain) == 2
        assert chain.workflow_names == ["mock_passing", "mock_passing"]
    
    @pytest.mark.asyncio
    async def test_overall_score_calculation(self, sample_context):
        """Test overall score is weighted average."""
        class ScoredWorkflow(Workflow):
            def __init__(self, score: float):
                self._score = score
            
            @property
            def name(self):
                return f"scored_{self._score}"
            
            @property
            def workflow_type(self):
                return "test"
            
            async def execute(self, context):
                return self.create_result(
                    status=WorkflowStatus.PASSED,
                    score=self._score,
                )
        
        chain = WorkflowChain("scored")
        chain.add(ScoredWorkflow(1.0))
        chain.add(ScoredWorkflow(0.5))
        chain.add(ScoredWorkflow(0.8))
        
        result = await chain.execute(sample_context)
        
        expected_avg = (1.0 + 0.5 + 0.8) / 3
        assert abs(result.overall_score - expected_avg) < 0.01
    
    @pytest.mark.asyncio
    async def test_issue_accumulation(self, sample_context):
        """Test issues are accumulated from all workflows."""
        class IssueWorkflow(Workflow):
            @property
            def name(self):
                return "issue_workflow"
            
            @property
            def workflow_type(self):
                return "test"
            
            async def execute(self, context):
                return self.create_result(
                    status=WorkflowStatus.PASSED,
                    issues=[
                        {"file": "test.py", "line": 1, "message": "Issue 1"},
                        {"file": "test.py", "line": 2, "message": "Issue 2"},
                    ],
                )
        
        chain = WorkflowChain("with_issues")
        chain.add(IssueWorkflow())
        chain.add(IssueWorkflow())
        
        result = await chain.execute(sample_context)
        
        assert len(result.all_issues) == 4


# =============================================================================
# CHAIN RESULT TESTS
# =============================================================================

class TestChainResult:
    """Tests for ChainResult."""
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        result = ChainResult(
            chain_id="test",
            chain_name="test",
            status=WorkflowStatus.FAILED,
            passed_count=3,
            failed_count=1,
        )
        
        assert result.success_rate == 0.75
    
    def test_success_rate_no_executions(self):
        """Test success rate with no executions."""
        result = ChainResult(
            chain_id="test",
            chain_name="test",
            status=WorkflowStatus.SKIPPED,
            passed_count=0,
            failed_count=0,
        )
        
        assert result.success_rate == 0.0
    
    def test_to_dict(self):
        """Test chain result serialization."""
        result = ChainResult(
            chain_id="abc123",
            chain_name="test_chain",
            status=WorkflowStatus.PASSED,
            overall_score=0.9,
            total_workflows=3,
            passed_count=3,
        )
        
        data = result.to_dict()
        
        assert data["chain_id"] == "abc123"
        assert data["chain_name"] == "test_chain"
        assert data["status"] == "passed"
        assert data["overall_score"] == 0.9


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

class TestFactoryFunctions:
    """Tests for workflow chain factory functions."""
    
    def test_create_standard_chain(self):
        """Test standard chain creation."""
        chain = create_standard_chain()
        
        assert chain.name == "standard_verification"
        assert len(chain) == 3
        assert "lint_check" in chain.workflow_names
        assert "security_scan" in chain.workflow_names
        assert "full_verification" in chain.workflow_names
    
    def test_create_fast_chain(self):
        """Test fast chain creation."""
        chain = create_fast_chain()
        
        assert chain.name == "fast_verification"
        assert len(chain) == 2
        assert "lint_check" in chain.workflow_names
        assert "style_check" in chain.workflow_names
    
    def test_create_security_chain(self):
        """Test security chain creation."""
        chain = create_security_chain()
        
        assert chain.name == "security_verification"
        assert len(chain) == 2
        assert "security_scan" in chain.workflow_names
        assert "full_verification" in chain.workflow_names


# =============================================================================
# PREDEFINED WORKFLOW TESTS
# =============================================================================

class TestLintWorkflow:
    """Tests for LintWorkflow."""
    
    def test_properties(self):
        """Test workflow properties."""
        wf = LintWorkflow()
        
        assert wf.name == "lint_check"
        assert wf.workflow_type == "lint"
        assert wf.abort_on_fail is True
        assert "*.py" in wf.file_patterns
    
    @pytest.mark.asyncio
    async def test_no_python_files(self, empty_context):
        """Test with no Python files."""
        wf = LintWorkflow()
        result = await wf.execute(empty_context)
        
        assert result.status == WorkflowStatus.SKIPPED
    
    @pytest.mark.asyncio
    async def test_clean_code(self, sample_context):
        """Test with clean Python code."""
        wf = LintWorkflow(run_pylint=True, run_bandit=True)
        result = await wf.execute(sample_context)
        
        # Should pass since sample code is valid
        assert result.status in [WorkflowStatus.PASSED, WorkflowStatus.SKIPPED]


class TestSecurityWorkflow:
    """Tests for SecurityWorkflow."""
    
    def test_properties(self):
        """Test workflow properties."""
        wf = SecurityWorkflow()
        
        assert wf.name == "security_scan"
        assert wf.workflow_type == "security"
        assert wf.abort_on_fail is True


class TestStyleWorkflow:
    """Tests for StyleWorkflow."""
    
    def test_properties(self):
        """Test workflow properties."""
        wf = StyleWorkflow()
        
        assert wf.name == "style_check"
        assert wf.workflow_type == "style"
        assert wf.abort_on_fail is False


class TestFullVerificationWorkflow:
    """Tests for FullVerificationWorkflow."""
    
    def test_properties(self):
        """Test workflow properties."""
        wf = FullVerificationWorkflow()
        
        assert wf.name == "full_verification"
        assert wf.workflow_type == "verification"
        assert wf.abort_on_fail is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestWorkflowIntegration:
    """Integration tests for workflow system."""
    
    @pytest.mark.asyncio
    async def test_context_passed_between_workflows(self, sample_context):
        """Test context is shared between workflows."""
        class WriterWorkflow(Workflow):
            @property
            def name(self):
                return "writer"
            
            @property
            def workflow_type(self):
                return "test"
            
            async def execute(self, context):
                context.shared_data["writer_ran"] = True
                return self.create_result(status=WorkflowStatus.PASSED)
        
        class ReaderWorkflow(Workflow):
            @property
            def name(self):
                return "reader"
            
            @property
            def workflow_type(self):
                return "test"
            
            async def execute(self, context):
                saw_writer = context.shared_data.get("writer_ran", False)
                return self.create_result(
                    status=WorkflowStatus.PASSED if saw_writer else WorkflowStatus.FAILED,
                    message=f"Saw writer: {saw_writer}",
                )
        
        chain = WorkflowChain("context_test")
        chain.add(WriterWorkflow())
        chain.add(ReaderWorkflow())
        
        result = await chain.execute(sample_context)
        
        assert result.passed
        assert sample_context.shared_data.get("writer_ran") is True
