"""
Tests for the Parser module (Module B: Constitution Parser / Extraction)
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.parser import ConstitutionParser, run_extraction


class TestConstitutionParser:
    """Tests for the ConstitutionParser class."""
    
    @pytest.fixture
    def temp_config(self):
        """Create a temporary config file."""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir, 'config.yaml')
        config_path.write_text("""
llms:
  extraction:
    model: "gemini/gemini-1.5-flash"
    max_tokens: 4096
    temperature: 0.0
thresholds:
  min_invariants: 3
retry:
  max_attempts: 2
  backoff_seconds: 1
output:
  criteria_file: "criteria.json"
""")
        yield str(config_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def temp_spec(self):
        """Create a temporary spec file."""
        temp_dir = tempfile.mkdtemp()
        spec_path = Path(temp_dir, 'spec.txt')
        spec_path.write_text("""
# Project Specification

## Technical Requirements
1. Use Python 3.10+
2. Use Flask framework
3. Implement REST API

## Functional Requirements
1. User authentication
2. CRUD operations for items
3. Error handling
""")
        yield str(spec_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    def test_init_defaults(self):
        """Test parser initialization with defaults."""
        parser = ConstitutionParser()
        
        assert parser.min_invariants == 5
        assert parser.max_attempts == 3
        
    def test_init_custom_config(self, temp_config):
        """Test parser initialization with custom config."""
        parser = ConstitutionParser(temp_config)
        
        assert parser.min_invariants == 3
        assert parser.max_attempts == 2
        
    def test_read_spec(self, temp_spec):
        """Test reading specification file."""
        parser = ConstitutionParser()
        content = parser.read_spec(temp_spec)
        
        assert 'Technical Requirements' in content
        assert 'Functional Requirements' in content
        assert 'Python 3.10+' in content
        
    def test_read_spec_not_found(self):
        """Test reading non-existent spec file."""
        parser = ConstitutionParser()
        
        with pytest.raises(FileNotFoundError):
            parser.read_spec('/nonexistent/spec.txt')
            
    def test_read_spec_empty(self):
        """Test reading empty spec file."""
        temp_dir = tempfile.mkdtemp()
        try:
            spec_path = Path(temp_dir, 'empty.txt')
            spec_path.write_text('')
            
            parser = ConstitutionParser()
            
            with pytest.raises(ValueError, match="empty"):
                parser.read_spec(str(spec_path))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_validate_invariants_valid(self):
        """Test validation of valid invariants."""
        parser = ConstitutionParser()
        
        invariants = {
            "technical": [
                {"id": 1, "desc": "Use Python"},
                {"id": 2, "desc": "Use Flask"}
            ],
            "functional": [
                {"id": 1, "desc": "User auth"}
            ]
        }
        
        assert parser._validate_invariants(invariants) is True
        
    def test_validate_invariants_missing_key(self):
        """Test validation with missing key."""
        parser = ConstitutionParser()
        
        invariants = {
            "technical": [{"id": 1, "desc": "Use Python"}]
            # Missing "functional"
        }
        
        assert parser._validate_invariants(invariants) is False
        
    def test_validate_invariants_wrong_type(self):
        """Test validation with wrong type."""
        parser = ConstitutionParser()
        
        invariants = {
            "technical": "not a list",
            "functional": []
        }
        
        assert parser._validate_invariants(invariants) is False
        
    def test_validate_invariants_missing_id(self):
        """Test validation with missing id."""
        parser = ConstitutionParser()
        
        invariants = {
            "technical": [{"desc": "Missing id"}],
            "functional": []
        }
        
        assert parser._validate_invariants(invariants) is False
        
    def test_validate_invariants_wrong_id_type(self):
        """Test validation with wrong id type."""
        parser = ConstitutionParser()
        
        invariants = {
            "technical": [{"id": "not int", "desc": "Wrong type"}],
            "functional": []
        }
        
        assert parser._validate_invariants(invariants) is False
        
    def test_extract_json_from_response_plain(self):
        """Test JSON extraction from plain JSON response."""
        parser = ConstitutionParser()
        
        response = '{"technical": [{"id": 1, "desc": "test"}], "functional": []}'
        result = parser._extract_json_from_response(response)
        
        assert result is not None
        assert "technical" in result
        
    def test_extract_json_from_response_code_block(self):
        """Test JSON extraction from code block."""
        parser = ConstitutionParser()
        
        response = '''Here is the JSON:
```json
{"technical": [{"id": 1, "desc": "test"}], "functional": []}
```
'''
        result = parser._extract_json_from_response(response)
        
        assert result is not None
        assert "technical" in result
        
    def test_extract_json_from_response_embedded(self):
        """Test JSON extraction from embedded JSON."""
        parser = ConstitutionParser()
        
        response = '''Here are the requirements:
{"technical": [{"id": 1, "desc": "test"}], "functional": []}
Additional notes...'''
        
        result = parser._extract_json_from_response(response)
        
        assert result is not None
        assert "technical" in result
        
    def test_extract_json_from_response_invalid(self):
        """Test JSON extraction from invalid response."""
        parser = ConstitutionParser()
        
        response = "This is just plain text with no JSON"
        result = parser._extract_json_from_response(response)
        
        assert result is None
        
    def test_save_criteria(self, temp_config):
        """Test saving criteria to file."""
        temp_dir = tempfile.mkdtemp()
        try:
            parser = ConstitutionParser(temp_config)
            
            invariants = {
                "technical": [{"id": 1, "desc": "test"}],
                "functional": [{"id": 1, "desc": "test2"}]
            }
            
            output_path = os.path.join(temp_dir, 'criteria.json')
            saved_path = parser.save_criteria(invariants, output_path)
            
            assert os.path.exists(saved_path)
            
            with open(saved_path, 'r') as f:
                loaded = json.load(f)
            
            assert loaded == invariants
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_load_criteria(self, temp_config):
        """Test loading criteria from file."""
        temp_dir = tempfile.mkdtemp()
        try:
            criteria_path = Path(temp_dir, 'criteria.json')
            criteria_path.write_text(json.dumps({
                "technical": [{"id": 1, "desc": "test"}],
                "functional": [{"id": 1, "desc": "test2"}]
            }))
            
            parser = ConstitutionParser(temp_config)
            loaded = parser.load_criteria(str(criteria_path))
            
            assert "technical" in loaded
            assert "functional" in loaded
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_load_criteria_not_found(self, temp_config):
        """Test loading non-existent criteria file."""
        parser = ConstitutionParser(temp_config)
        
        with pytest.raises(FileNotFoundError):
            parser.load_criteria('/nonexistent/criteria.json')
            
    def test_load_criteria_invalid(self, temp_config):
        """Test loading invalid criteria file."""
        temp_dir = tempfile.mkdtemp()
        try:
            criteria_path = Path(temp_dir, 'criteria.json')
            criteria_path.write_text('{"technical": "not a list"}')
            
            parser = ConstitutionParser(temp_config)
            
            with pytest.raises(ValueError):
                parser.load_criteria(str(criteria_path))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestExtractInvariants:
    """Tests for invariant extraction with mocked LLM."""
    
    @pytest.fixture
    def mock_litellm(self):
        """Mock litellm.completion."""
        with patch('modules.parser.litellm') as mock:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps({
                "technical": [
                    {"id": 1, "desc": "Use Python 3.10+"},
                    {"id": 2, "desc": "Use Flask framework"}
                ],
                "functional": [
                    {"id": 1, "desc": "User authentication"},
                    {"id": 2, "desc": "CRUD operations"}
                ]
            })
            mock.completion.return_value = mock_response
            yield mock
    
    def test_extract_invariants_success(self, mock_litellm):
        """Test successful invariant extraction."""
        parser = ConstitutionParser()
        
        spec_content = """
        Technical: Use Python
        Functional: User auth
        """
        
        result = parser.extract_invariants(spec_content)
        
        assert "technical" in result
        assert "functional" in result
        assert len(result["technical"]) == 2
        assert len(result["functional"]) == 2
        
    def test_extract_invariants_llm_error(self):
        """Test handling of LLM errors."""
        with patch('modules.parser.litellm') as mock:
            mock.completion.side_effect = Exception("API Error")
            
            parser = ConstitutionParser()
            parser.max_attempts = 1
            
            with pytest.raises(Exception):
                parser.extract_invariants("test spec")


class TestClarifyIfNeeded:
    """Tests for the clarification step."""
    
    def test_clarify_not_needed(self):
        """Test that clarification is skipped when enough invariants."""
        parser = ConstitutionParser()
        parser.min_invariants = 3
        
        invariants = {
            "technical": [{"id": 1, "desc": "t1"}, {"id": 2, "desc": "t2"}],
            "functional": [{"id": 1, "desc": "f1"}, {"id": 2, "desc": "f2"}]
        }
        
        result = parser.clarify_if_needed(invariants, "spec content")
        
        assert result == invariants  # Unchanged
        
    @patch('modules.parser.litellm')
    def test_clarify_needed(self, mock_litellm):
        """Test that clarification happens when few invariants."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "technical": [{"id": 1, "desc": "t1"}, {"id": 2, "desc": "t2"}, {"id": 3, "desc": "t3"}],
            "functional": [{"id": 1, "desc": "f1"}, {"id": 2, "desc": "f2"}, {"id": 3, "desc": "f3"}]
        })
        mock_litellm.completion.return_value = mock_response
        
        parser = ConstitutionParser()
        parser.min_invariants = 5
        
        invariants = {
            "technical": [{"id": 1, "desc": "t1"}],
            "functional": [{"id": 1, "desc": "f1"}]
        }
        
        result = parser.clarify_if_needed(invariants, "spec content")
        
        # Should have more invariants after clarification
        assert len(result["technical"]) + len(result["functional"]) > 2


class TestRunExtraction:
    """Tests for the run_extraction function."""
    
    @patch('modules.parser.litellm')
    def test_run_extraction_success(self, mock_litellm):
        """Test successful extraction pipeline."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "technical": [{"id": 1, "desc": "t1"}, {"id": 2, "desc": "t2"}, {"id": 3, "desc": "t3"}],
            "functional": [{"id": 1, "desc": "f1"}, {"id": 2, "desc": "f2"}, {"id": 3, "desc": "f3"}]
        })
        mock_litellm.completion.return_value = mock_response
        
        temp_dir = tempfile.mkdtemp()
        try:
            spec_path = Path(temp_dir, 'spec.txt')
            spec_path.write_text("Test specification")
            
            config_path = Path(temp_dir, 'config.yaml')
            config_path.write_text("thresholds:\n  min_invariants: 3")
            
            result = run_extraction(
                spec_path=str(spec_path),
                config_path=str(config_path),
                output_path=str(Path(temp_dir, 'criteria.json'))
            )
            
            assert "technical" in result
            assert "functional" in result
            
            # Check that criteria.json was created
            assert Path(temp_dir, 'criteria.json').exists()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_spec_with_unicode(self):
        """Test handling of unicode in spec file."""
        temp_dir = tempfile.mkdtemp()
        try:
            spec_path = Path(temp_dir, 'spec.txt')
            spec_path.write_text("""
# 仕様書
1. 日本語対応
2. Unicode characters: 🎉 ✓ ★
""", encoding='utf-8')
            
            parser = ConstitutionParser()
            content = parser.read_spec(str(spec_path))
            
            assert '日本語' in content
            assert '🎉' in content
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_very_long_spec(self):
        """Test handling of very long spec file."""
        temp_dir = tempfile.mkdtemp()
        try:
            spec_path = Path(temp_dir, 'spec.txt')
            # Create a long spec
            long_content = "# Specification\n" + "Requirement\n" * 10000
            spec_path.write_text(long_content)
            
            parser = ConstitutionParser()
            content = parser.read_spec(str(spec_path))
            
            assert len(content) > 100000
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_malformed_json_recovery(self):
        """Test recovery from malformed JSON in response."""
        parser = ConstitutionParser()
        
        # Response with slightly malformed JSON that can still be extracted
        response = '''
Here is the result:
{
  "technical": [{"id": 1, "desc": "test"}],
  "functional": []
}
Additional text...
'''
        result = parser._extract_json_from_response(response)
        
        assert result is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
