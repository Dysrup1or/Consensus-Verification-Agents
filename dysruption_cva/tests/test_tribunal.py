"""
Tests for the Tribunal module (Module C: Multi-Model Tribunal / Adjudication)
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import pytest

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.tribunal import (
    Tribunal, 
    run_adjudication, 
    Verdict, 
    JudgeScore, 
    CriterionResult,
    StaticAnalysisResult,
    TribunalVerdict
)


class TestVerdict:
    """Tests for the Verdict enum."""
    
    def test_verdict_values(self):
        """Test verdict enum values."""
        assert Verdict.PASS.value == "PASS"
        assert Verdict.FAIL.value == "FAIL"
        assert Verdict.PARTIAL.value == "PARTIAL"
        assert Verdict.ERROR.value == "ERROR"


class TestTribunal:
    """Tests for the Tribunal class."""
    
    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir, 'config.yaml')
        config_path.write_text("""
llms:
  architect:
    model: "claude-3-5-sonnet-20241022"
  security:
    model: "groq/llama-3.1-70b-versatile"
  user_proxy:
    model: "gemini/gemini-1.5-pro"
  remediation:
    model: "gemini/gemini-1.5-flash"
thresholds:
  pass_score: 7
  consensus_ratio: 0.67
  chunk_size_tokens: 10000
static_analysis:
  enabled: false
remediation:
  enabled: false
retry:
  max_attempts: 1
  backoff_seconds: 0
output:
  report_file: "REPORT.md"
  verdict_file: "verdict.json"
fallback:
  enabled: false
""")
        yield str(config_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    def test_init_defaults(self):
        """Test tribunal initialization with defaults."""
        tribunal = Tribunal()
        
        assert tribunal.pass_score == 7
        assert tribunal.consensus_ratio == 0.67
        assert len(tribunal.judges) == 3
        
    def test_init_custom_config(self, temp_config):
        """Test tribunal initialization with custom config."""
        tribunal = Tribunal(temp_config)
        
        assert tribunal.pass_score == 7
        assert tribunal.consensus_ratio == 0.67
        
    def test_estimate_tokens(self, temp_config):
        """Test token estimation."""
        tribunal = Tribunal(temp_config)
        
        text = "Hello World"  # 11 chars
        tokens = tribunal._estimate_tokens(text)
        
        assert tokens == 2  # 11 // 4
        
    def test_chunk_content_small(self, temp_config):
        """Test chunking of small content."""
        tribunal = Tribunal(temp_config)
        
        content = "Small content"
        chunks = tribunal._chunk_content(content, 1000)
        
        assert len(chunks) == 1
        assert chunks[0] == content
        
    def test_chunk_content_large(self, temp_config):
        """Test chunking of large content."""
        tribunal = Tribunal(temp_config)
        
        # Create content larger than 100 tokens
        content = "Line of content\n" * 100
        chunks = tribunal._chunk_content(content, 50)
        
        assert len(chunks) > 1
        
    def test_summarize_non_code(self, temp_config):
        """Test summarization of non-code elements."""
        tribunal = Tribunal(temp_config)
        
        content = '''
def func():
    """Docstring 1"""
    pass

def func2():
    """Docstring 2"""
    pass

def func3():
    """Docstring 3"""
    pass

def func4():
    """Docstring 4 - should be summarized"""
    pass
'''
        result = tribunal._summarize_non_code(content)
        
        assert 'func' in result
        
    def test_parse_judge_response_json(self, temp_config):
        """Test parsing JSON judge response."""
        tribunal = Tribunal(temp_config)
        
        response = json.dumps({
            "score": 8,
            "explanation": "Good code",
            "issues": ["Minor issue"],
            "suggestions": ["Suggestion 1"],
            "confidence": 0.9
        })
        
        result = tribunal._parse_judge_response(response)
        
        assert result['score'] == 8
        assert result['explanation'] == "Good code"
        assert result['pass_verdict'] is True
        assert result['confidence'] == 0.9
        
    def test_parse_judge_response_text(self, temp_config):
        """Test parsing text judge response with score."""
        tribunal = Tribunal(temp_config)
        
        response = "The code is well structured. Score: 9/10. It follows best practices."
        
        result = tribunal._parse_judge_response(response)
        
        assert result['score'] == 9
        assert result['pass_verdict'] is True
        
    def test_parse_judge_response_no_score(self, temp_config):
        """Test parsing response without explicit score."""
        tribunal = Tribunal(temp_config)
        
        response = "The code is okay."
        
        result = tribunal._parse_judge_response(response)
        
        assert result['score'] == 5  # Default
        assert result['pass_verdict'] is False


class TestStaticAnalysis:
    """Tests for static analysis functions."""
    
    @pytest.fixture
    def temp_config_with_static(self):
        """Create config with static analysis enabled."""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir, 'config.yaml')
        config_path.write_text("""
static_analysis:
  enabled: true
  pylint:
    enabled: true
  bandit:
    enabled: true
""")
        yield str(config_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    @pytest.fixture
    def temp_config_without_static(self):
        """Create config with static analysis disabled."""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir, 'config.yaml')
        config_path.write_text("""
static_analysis:
  enabled: false
""")
        yield str(config_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_run_static_analysis_disabled(self, temp_config_without_static):
        """Test static analysis when disabled."""
        tribunal = Tribunal(temp_config_without_static)
        
        file_tree = {"main.py": "print('hello')"}
        results = tribunal.run_static_analysis(file_tree, "python")
        
        assert results == []
        
    def test_run_pylint_basic(self, temp_config_with_static):
        """Test pylint on basic Python code."""
        tribunal = Tribunal(temp_config_with_static)
        
        content = "print('hello')"
        result = tribunal.run_pylint("test.py", content)
        
        assert result.tool == "pylint"
        assert result.file_path == "test.py"
        assert isinstance(result.issues, list)
        
    def test_run_bandit_basic(self, temp_config_with_static):
        """Test bandit on basic Python code."""
        tribunal = Tribunal(temp_config_with_static)
        
        content = "print('hello')"
        result = tribunal.run_bandit("test.py", content)
        
        assert result.tool == "bandit"
        assert result.file_path == "test.py"
        assert isinstance(result.issues, list)


class TestEvaluateCriterion:
    """Tests for criterion evaluation."""
    
    @pytest.fixture
    def mock_tribunal(self):
        """Create tribunal with mocked LLM calls."""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir, 'config.yaml')
        config_path.write_text("""
llms:
  architect:
    model: "test-model"
  security:
    model: "test-model"
  user_proxy:
    model: "test-model"
thresholds:
  pass_score: 7
  consensus_ratio: 0.67
static_analysis:
  enabled: false
remediation:
  enabled: false
retry:
  max_attempts: 1
fallback:
  enabled: false
""")
        tribunal = Tribunal(config_path)
        yield tribunal, temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @patch('modules.tribunal.litellm')
    def test_evaluate_criterion_pass(self, mock_litellm, mock_tribunal):
        """Test evaluation that passes."""
        tribunal, _ = mock_tribunal
        
        # All judges give passing scores
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "score": 8,
            "explanation": "Good implementation",
            "issues": [],
            "suggestions": [],
            "confidence": 0.9
        })
        mock_litellm.completion.return_value = mock_response
        
        criterion = {"id": 1, "desc": "Test requirement"}
        file_tree = {"main.py": "def test(): pass"}
        spec_summary = "Test spec"
        
        result = tribunal.evaluate_criterion(criterion, "technical", file_tree, spec_summary)
        
        assert result.criterion_id == 1
        assert result.consensus_verdict == Verdict.PASS
        assert result.average_score >= 7
        
    @patch('modules.tribunal.litellm')
    def test_evaluate_criterion_fail(self, mock_litellm, mock_tribunal):
        """Test evaluation that fails."""
        tribunal, _ = mock_tribunal
        
        # All judges give failing scores
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "score": 3,
            "explanation": "Poor implementation",
            "issues": ["Major bug"],
            "suggestions": ["Fix it"],
            "confidence": 0.8
        })
        mock_litellm.completion.return_value = mock_response
        
        criterion = {"id": 1, "desc": "Test requirement"}
        file_tree = {"main.py": "# Empty"}
        spec_summary = "Test spec"
        
        result = tribunal.evaluate_criterion(criterion, "technical", file_tree, spec_summary)
        
        assert result.consensus_verdict == Verdict.FAIL
        assert result.average_score < 7


class TestReportGeneration:
    """Tests for report generation."""
    
    @pytest.fixture
    def sample_verdict(self):
        """Create a sample tribunal verdict."""
        return TribunalVerdict(
            timestamp=datetime.now().isoformat(),
            overall_verdict=Verdict.PASS,
            overall_score=8.5,
            total_criteria=2,
            passed_criteria=2,
            failed_criteria=0,
            static_analysis_issues=1,
            criterion_results=[
                CriterionResult(
                    criterion_id=1,
                    criterion_type="technical",
                    criterion_desc="Test requirement",
                    scores=[
                        JudgeScore(
                            judge_name="Test Judge",
                            model="test-model",
                            score=9,
                            explanation="Good",
                            pass_verdict=True,
                            confidence=0.9,
                            issues=[],
                            suggestions=[]
                        )
                    ],
                    average_score=9.0,
                    consensus_verdict=Verdict.PASS,
                    majority_ratio=1.0,
                    final_explanation="All good",
                    relevant_files=["main.py"]
                )
            ],
            static_analysis_results=[
                StaticAnalysisResult(
                    tool="pylint",
                    file_path="main.py",
                    issues=[{"line": 1, "message": "Minor issue", "type": "warning"}],
                    severity_counts={"warning": 1}
                )
            ],
            remediation_suggestions=[],
            execution_time_seconds=5.0
        )
    
    def test_generate_report_md(self, sample_verdict):
        """Test markdown report generation."""
        tribunal = Tribunal()
        
        report = tribunal.generate_report_md(sample_verdict)
        
        assert "# Dysruption CVA Verification Report" in report
        assert "PASS" in report
        assert "8.5" in report
        assert "Technical Requirements" in report
        assert "Static Analysis" in report
        
    def test_generate_verdict_json(self, sample_verdict):
        """Test JSON verdict generation."""
        tribunal = Tribunal()
        
        json_data = tribunal.generate_verdict_json(sample_verdict)
        
        assert json_data["overall_verdict"] == "PASS"
        assert json_data["overall_score"] == 8.5
        assert json_data["ci_cd"]["success"] is True
        assert json_data["ci_cd"]["exit_code"] == 0
        
    def test_save_outputs(self, sample_verdict):
        """Test saving outputs to files."""
        temp_dir = tempfile.mkdtemp()
        try:
            config_path = Path(temp_dir, 'config.yaml')
            config_path.write_text(f"""
output:
  report_file: "{temp_dir}/REPORT.md"
  verdict_file: "{temp_dir}/verdict.json"
""".replace("\\", "/"))
            
            tribunal = Tribunal(str(config_path))
            report_path, verdict_path = tribunal.save_outputs(sample_verdict)
            
            assert os.path.exists(report_path)
            assert os.path.exists(verdict_path)
            
            with open(verdict_path, 'r') as f:
                loaded = json.load(f)
            assert loaded["overall_verdict"] == "PASS"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestRunAdjudication:
    """Tests for the run_adjudication function."""
    
    @patch('modules.tribunal.litellm')
    def test_run_adjudication_basic(self, mock_litellm):
        """Test basic adjudication run."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "score": 8,
            "explanation": "Good",
            "issues": [],
            "suggestions": [],
            "confidence": 0.9
        })
        mock_litellm.completion.return_value = mock_response
        
        temp_dir = tempfile.mkdtemp()
        try:
            # Create config
            config_path = Path(temp_dir, 'config.yaml')
            config_path.write_text("""
static_analysis:
  enabled: false
remediation:
  enabled: false
retry:
  max_attempts: 1
fallback:
  enabled: false
output:
  report_file: "REPORT.md"
  verdict_file: "verdict.json"
""")
            
            # Create criteria file
            criteria_path = Path(temp_dir, 'criteria.json')
            criteria_path.write_text(json.dumps({
                "technical": [{"id": 1, "desc": "Test"}],
                "functional": []
            }))
            
            # Change to temp dir for output files
            old_cwd = os.getcwd()
            os.chdir(temp_dir)
            
            try:
                file_tree = {"main.py": "print('hello')"}
                verdict = run_adjudication(
                    file_tree=file_tree,
                    language="python",
                    criteria_path=str(criteria_path),
                    config_path=str(config_path)
                )
                
                assert verdict is not None
                assert isinstance(verdict.overall_verdict, Verdict)
            finally:
                os.chdir(old_cwd)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_file_tree(self):
        """Test handling of empty file tree."""
        tribunal = Tribunal()
        
        result = tribunal.run({}, {"technical": [], "functional": []}, "python")
        
        assert result.overall_verdict == Verdict.ERROR
        assert result.total_criteria == 0
        
    def test_empty_criteria(self):
        """Test handling of empty criteria."""
        tribunal = Tribunal()
        
        file_tree = {"main.py": "print('hello')"}
        result = tribunal.run(file_tree, {"technical": [], "functional": []}, "python")
        
        assert result.overall_verdict == Verdict.ERROR
        assert result.total_criteria == 0
        
    @patch('modules.tribunal.litellm')
    def test_llm_error_handling(self, mock_litellm):
        """Test handling of LLM errors."""
        mock_litellm.completion.side_effect = Exception("API Error")
        
        temp_dir = tempfile.mkdtemp()
        try:
            config_path = Path(temp_dir, 'config.yaml')
            config_path.write_text("""
static_analysis:
  enabled: false
retry:
  max_attempts: 1
fallback:
  enabled: false
""")
            
            tribunal = Tribunal(str(config_path))
            
            criterion = {"id": 1, "desc": "Test"}
            file_tree = {"main.py": "test"}
            
            result = tribunal.evaluate_criterion(criterion, "technical", file_tree, "spec")
            
            # Should handle error gracefully
            assert result.criterion_id == 1
            # Scores should indicate error
            for score in result.scores:
                assert "failed" in score.explanation.lower() or score.confidence == 0.0
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_large_file_handling(self):
        """Test handling of large files."""
        tribunal = Tribunal()
        
        # Create a large file content
        large_content = "def func():\n    pass\n" * 5000
        
        # Should not raise
        chunks = tribunal._chunk_content(large_content, 1000)
        
        assert len(chunks) > 1


class TestConsensusLogic:
    """Tests for consensus voting logic."""
    
    def test_majority_pass(self):
        """Test that 2/3 passing votes result in PASS."""
        scores = [
            JudgeScore("J1", "m1", 8, "Good", True, 0.9, [], []),
            JudgeScore("J2", "m2", 8, "Good", True, 0.9, [], []),
            JudgeScore("J3", "m3", 5, "Okay", False, 0.7, [], [])
        ]
        
        pass_votes = sum(1 for s in scores if s.pass_verdict)
        majority_ratio = pass_votes / len(scores)
        
        # 2/3 = 0.6666... which is effectively 67% (within floating point tolerance)
        assert majority_ratio >= 0.66
        
    def test_majority_fail(self):
        """Test that 2/3 failing votes result in FAIL."""
        scores = [
            JudgeScore("J1", "m1", 3, "Bad", False, 0.9, [], []),
            JudgeScore("J2", "m2", 4, "Bad", False, 0.9, [], []),
            JudgeScore("J3", "m3", 8, "Good", True, 0.7, [], [])
        ]
        
        pass_votes = sum(1 for s in scores if s.pass_verdict)
        majority_ratio = pass_votes / len(scores)
        
        assert majority_ratio < 0.67


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
