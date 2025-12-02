"""
Dysruption CVA - Tribunal Module (Module C: Multi-Model Tribunal / Adjudication)
Runs static analysis, routes code to multiple LLM judges, computes consensus, generates reports.
"""

import os
import json
import time
import subprocess
import tempfile
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

from loguru import logger
import yaml

try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.error("LiteLLM not available. Install with: pip install litellm")


class Verdict(Enum):
    """Verdict enumeration."""
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass
class JudgeScore:
    """Score from a single judge."""
    judge_name: str
    model: str
    score: int
    explanation: str
    pass_verdict: bool
    confidence: float
    issues: List[str]
    suggestions: List[str]


@dataclass
class CriterionResult:
    """Result for a single criterion."""
    criterion_id: int
    criterion_type: str  # 'technical' or 'functional'
    criterion_desc: str
    scores: List[JudgeScore]
    average_score: float
    consensus_verdict: Verdict
    majority_ratio: float
    final_explanation: str
    relevant_files: List[str]


@dataclass
class StaticAnalysisResult:
    """Result from static analysis tools."""
    tool: str
    file_path: str
    issues: List[Dict[str, Any]]
    severity_counts: Dict[str, int]


@dataclass
class TribunalVerdict:
    """Final tribunal verdict."""
    timestamp: str
    overall_verdict: Verdict
    overall_score: float
    total_criteria: int
    passed_criteria: int
    failed_criteria: int
    static_analysis_issues: int
    criterion_results: List[CriterionResult]
    static_analysis_results: List[StaticAnalysisResult]
    remediation_suggestions: List[Dict[str, Any]]
    execution_time_seconds: float


class Tribunal:
    """
    Multi-model tribunal for code adjudication.
    Uses multiple LLM judges to evaluate code against criteria.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.llms_config = self.config.get('llms', {})
        self.thresholds = self.config.get('thresholds', {})
        self.retry_config = self.config.get('retry', {})
        self.output_config = self.config.get('output', {})
        self.static_config = self.config.get('static_analysis', {})
        self.remediation_config = self.config.get('remediation', {})
        self.fallback_config = self.config.get('fallback', {})
        
        # Thresholds
        self.pass_score = self.thresholds.get('pass_score', 7)
        self.consensus_ratio = self.thresholds.get('consensus_ratio', 0.67)
        self.chunk_size_tokens = self.thresholds.get('chunk_size_tokens', 10000)
        self.context_window = self.thresholds.get('context_window', 128000)
        
        # Retry settings
        self.max_attempts = self.retry_config.get('max_attempts', 3)
        self.backoff_seconds = self.retry_config.get('backoff_seconds', 2)
        
        # Judge configurations
        self.judges = {
            'architect': {
                'name': 'Architect Judge (Claude)',
                'model': self.llms_config.get('architect', {}).get('model', 'claude-3-5-sonnet-20241022'),
                'role': 'architecture and logic',
                'weight': 1.2  # Slightly higher weight for architecture
            },
            'security': {
                'name': 'Security Judge (Llama)',
                'model': self.llms_config.get('security', {}).get('model', 'groq/llama-3.1-70b-versatile'),
                'role': 'security and efficiency',
                'weight': 1.1
            },
            'user_proxy': {
                'name': 'User Proxy Judge (Gemini)',
                'model': self.llms_config.get('user_proxy', {}).get('model', 'gemini/gemini-1.5-pro'),
                'role': 'overall alignment and user intent',
                'weight': 1.0
            }
        }
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return {}
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return len(text) // 4
    
    def _chunk_content(self, content: str, max_tokens: int) -> List[str]:
        """Split content into chunks that fit within token limit."""
        estimated_tokens = self._estimate_tokens(content)
        
        if estimated_tokens <= max_tokens:
            return [content]
        
        # Split by lines and group into chunks
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = self._estimate_tokens(line)
            
            if current_tokens + line_tokens > max_tokens:
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_tokens = line_tokens
            else:
                current_chunk.append(line)
                current_tokens += line_tokens
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        logger.debug(f"Split content into {len(chunks)} chunks")
        return chunks
    
    def _summarize_non_code(self, content: str) -> str:
        """Summarize non-code elements (comments, docstrings) for large files."""
        lines = content.split('\n')
        result_lines = []
        in_docstring = False
        docstring_count = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Detect docstrings
            if '"""' in stripped or "'''" in stripped:
                in_docstring = not in_docstring
                if in_docstring:
                    docstring_count += 1
                    if docstring_count <= 3:  # Keep first few docstrings
                        result_lines.append(line)
                    else:
                        result_lines.append('    # [Docstring summarized]')
                continue
            
            if in_docstring:
                if docstring_count <= 3:
                    result_lines.append(line)
                continue
            
            # Keep code lines
            result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    def run_pylint(self, file_path: str, content: str) -> StaticAnalysisResult:
        """Run pylint on a Python file."""
        issues = []
        severity_counts = {'error': 0, 'warning': 0, 'convention': 0, 'refactor': 0}
        
        if not self.static_config.get('pylint', {}).get('enabled', True):
            return StaticAnalysisResult(
                tool='pylint',
                file_path=file_path,
                issues=[],
                severity_counts=severity_counts
            )
        
        try:
            # Write content to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_path = f.name
            
            try:
                # Run pylint
                disabled = self.static_config.get('pylint', {}).get('disable', [])
                disable_str = ','.join(disabled) if disabled else ''
                
                cmd = ['python', '-m', 'pylint', '--output-format=json']
                if disable_str:
                    cmd.append(f'--disable={disable_str}')
                cmd.append(temp_path)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.stdout:
                    try:
                        pylint_output = json.loads(result.stdout)
                        for issue in pylint_output:
                            issues.append({
                                'line': issue.get('line', 0),
                                'column': issue.get('column', 0),
                                'message': issue.get('message', ''),
                                'symbol': issue.get('symbol', ''),
                                'type': issue.get('type', 'warning')
                            })
                            
                            issue_type = issue.get('type', 'warning')
                            if issue_type in severity_counts:
                                severity_counts[issue_type] += 1
                    except json.JSONDecodeError:
                        pass
                        
            finally:
                os.unlink(temp_path)
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Pylint timed out for {file_path}")
        except Exception as e:
            logger.warning(f"Pylint failed for {file_path}: {e}")
        
        return StaticAnalysisResult(
            tool='pylint',
            file_path=file_path,
            issues=issues,
            severity_counts=severity_counts
        )
    
    def run_bandit(self, file_path: str, content: str) -> StaticAnalysisResult:
        """Run bandit security scanner on a Python file."""
        issues = []
        severity_counts = {'high': 0, 'medium': 0, 'low': 0}
        
        if not self.static_config.get('bandit', {}).get('enabled', True):
            return StaticAnalysisResult(
                tool='bandit',
                file_path=file_path,
                issues=[],
                severity_counts=severity_counts
            )
        
        try:
            # Write content to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_path = f.name
            
            try:
                # Run bandit
                cmd = ['python', '-m', 'bandit', '-f', 'json', temp_path]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.stdout:
                    try:
                        bandit_output = json.loads(result.stdout)
                        for issue in bandit_output.get('results', []):
                            issues.append({
                                'line': issue.get('line_number', 0),
                                'severity': issue.get('issue_severity', 'LOW'),
                                'confidence': issue.get('issue_confidence', 'LOW'),
                                'message': issue.get('issue_text', ''),
                                'test_id': issue.get('test_id', '')
                            })
                            
                            severity = issue.get('issue_severity', 'LOW').lower()
                            if severity in severity_counts:
                                severity_counts[severity] += 1
                    except json.JSONDecodeError:
                        pass
                        
            finally:
                os.unlink(temp_path)
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Bandit timed out for {file_path}")
        except Exception as e:
            logger.warning(f"Bandit failed for {file_path}: {e}")
        
        return StaticAnalysisResult(
            tool='bandit',
            file_path=file_path,
            issues=issues,
            severity_counts=severity_counts
        )
    
    def run_static_analysis(self, file_tree: Dict[str, str], language: str) -> List[StaticAnalysisResult]:
        """Run static analysis on all files."""
        results = []
        
        if not self.static_config.get('enabled', True):
            logger.info("Static analysis disabled in config")
            return results
        
        logger.info(f"Running static analysis on {len(file_tree)} files...")
        
        for file_path, content in file_tree.items():
            if language == 'python' and file_path.endswith('.py'):
                results.append(self.run_pylint(file_path, content))
                results.append(self.run_bandit(file_path, content))
        
        total_issues = sum(len(r.issues) for r in results)
        logger.info(f"Static analysis complete. Found {total_issues} issues.")
        
        return results
    
    def _call_llm(self, model: str, messages: List[Dict], max_tokens: int = 4096) -> Optional[str]:
        """Call LLM with retry logic and fallback."""
        if not LITELLM_AVAILABLE:
            raise RuntimeError("LiteLLM not available")
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                logger.debug(f"LLM call to {model} (attempt {attempt}/{self.max_attempts})")
                
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.1
                )
                
                content = response.choices[0].message.content
                return content
                
            except Exception as e:
                logger.warning(f"LLM call to {model} failed (attempt {attempt}): {e}")
                
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_seconds * attempt)
                else:
                    # Try fallback
                    if self.fallback_config.get('enabled', True):
                        fallback_model = self.fallback_config.get('model')
                        if fallback_model and fallback_model != model:
                            logger.info(f"Trying fallback model: {fallback_model}")
                            try:
                                response = litellm.completion(
                                    model=fallback_model,
                                    messages=messages,
                                    max_tokens=max_tokens,
                                    temperature=0.1
                                )
                                return response.choices[0].message.content
                            except Exception as fallback_error:
                                logger.error(f"Fallback also failed: {fallback_error}")
                    
                    raise
        
        return None
    
    def _parse_judge_response(self, response: str) -> Dict[str, Any]:
        """Parse judge response to extract score and details."""
        result = {
            'score': 5,
            'explanation': response,
            'issues': [],
            'suggestions': [],
            'pass_verdict': False,
            'confidence': 0.5
        }
        
        # Try to extract JSON from response
        json_pattern = r'\{[\s\S]*\}'
        matches = re.findall(json_pattern, response)
        
        for match in matches:
            try:
                parsed = json.loads(match)
                if 'score' in parsed:
                    result['score'] = int(parsed.get('score', 5))
                    result['explanation'] = parsed.get('explanation', response)
                    result['issues'] = parsed.get('issues', [])
                    result['suggestions'] = parsed.get('suggestions', [])
                    result['confidence'] = float(parsed.get('confidence', 0.7))
                    break
            except (json.JSONDecodeError, ValueError):
                continue
        
        # Fallback: extract score from text
        if result['score'] == 5:
            score_pattern = r'(?:score|rating)[:\s]*(\d+)(?:/10)?'
            score_match = re.search(score_pattern, response.lower())
            if score_match:
                result['score'] = min(10, max(1, int(score_match.group(1))))
        
        result['pass_verdict'] = result['score'] >= self.pass_score
        
        return result
    
    def _get_judge_prompt(self, judge_key: str, criterion: Dict, code_content: str, spec_summary: str) -> Tuple[str, str]:
        """Generate system and user prompts for a judge."""
        judge = self.judges[judge_key]
        
        system_prompts = {
            'architect': f"""You are an expert code architect and logic reviewer.
Your role is to assess code architecture and logic correctness.
You must evaluate if the code meets specific requirements.

Respond in this JSON format:
{{
    "score": <1-10>,
    "explanation": "Your detailed assessment",
    "issues": ["Issue 1", "Issue 2"],
    "suggestions": ["Suggestion 1", "Suggestion 2"],
    "confidence": <0.0-1.0>
}}

Be strict but fair. Score 7+ means the code meets the requirement.
Score below 7 means significant issues exist.""",

            'security': f"""You are an expert security and efficiency auditor.
Your role is to identify security vulnerabilities and performance issues.
You must evaluate if the code is secure and efficient.

Respond in this JSON format:
{{
    "score": <1-10>,
    "explanation": "Your security/efficiency assessment",
    "issues": ["Vulnerability 1", "Performance issue 1"],
    "suggestions": ["Fix 1", "Optimization 1"],
    "confidence": <0.0-1.0>
}}

Focus on: SQL injection, XSS, auth issues, data exposure, inefficient algorithms.
Score 7+ means acceptable security/efficiency. Below 7 means critical issues.""",

            'user_proxy': f"""You are a user advocate and spec alignment checker.
Your role is to verify the code matches user intent and overall specification.
You represent the end user's perspective.

Respond in this JSON format:
{{
    "score": <1-10>,
    "explanation": "Your alignment assessment",
    "issues": ["Misalignment 1", "Missing feature 1"],
    "suggestions": ["Improvement 1", "Feature suggestion 1"],
    "confidence": <0.0-1.0>
}}

Consider: Does this feel right? Would users be satisfied?
Score 7+ means good alignment. Below 7 means significant deviation from intent."""
        }
        
        user_prompt = f"""Evaluate this code against the following requirement:

**Requirement ID**: {criterion['id']}
**Requirement**: {criterion['desc']}

**Overall Specification Summary**:
{spec_summary}

**Code to Review**:
```
{code_content}
```

Provide your assessment as JSON with score (1-10), explanation, issues, suggestions, and confidence."""

        return system_prompts[judge_key], user_prompt
    
    def evaluate_criterion(
        self,
        criterion: Dict,
        criterion_type: str,
        file_tree: Dict[str, str],
        spec_summary: str
    ) -> CriterionResult:
        """Evaluate a single criterion across all relevant files."""
        logger.info(f"Evaluating criterion {criterion_type}:{criterion['id']}: {criterion['desc'][:50]}...")
        
        # Combine relevant code content
        code_content = ""
        relevant_files = []
        
        for file_path, content in file_tree.items():
            # Check if content might be relevant to criterion
            # For now, include all files (could be optimized with semantic search)
            if self._estimate_tokens(code_content + content) < self.chunk_size_tokens:
                code_content += f"\n\n# File: {file_path}\n{content}"
                relevant_files.append(file_path)
        
        # If content is too large, chunk and summarize
        if self._estimate_tokens(code_content) > self.chunk_size_tokens:
            code_content = self._summarize_non_code(code_content)
        
        # Get scores from all judges
        scores: List[JudgeScore] = []
        
        for judge_key, judge_config in self.judges.items():
            try:
                system_prompt, user_prompt = self._get_judge_prompt(
                    judge_key, criterion, code_content, spec_summary
                )
                
                response = self._call_llm(
                    judge_config['model'],
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                
                if response:
                    parsed = self._parse_judge_response(response)
                    scores.append(JudgeScore(
                        judge_name=judge_config['name'],
                        model=judge_config['model'],
                        score=parsed['score'],
                        explanation=parsed['explanation'],
                        pass_verdict=parsed['pass_verdict'],
                        confidence=parsed['confidence'],
                        issues=parsed['issues'],
                        suggestions=parsed['suggestions']
                    ))
                    logger.debug(f"{judge_config['name']}: Score {parsed['score']}/10")
                    
            except Exception as e:
                logger.error(f"Judge {judge_key} failed: {e}")
                scores.append(JudgeScore(
                    judge_name=judge_config['name'],
                    model=judge_config['model'],
                    score=5,
                    explanation=f"Evaluation failed: {str(e)}",
                    pass_verdict=False,
                    confidence=0.0,
                    issues=["Evaluation failed"],
                    suggestions=[]
                ))
        
        # Compute consensus
        if not scores:
            return CriterionResult(
                criterion_id=criterion['id'],
                criterion_type=criterion_type,
                criterion_desc=criterion['desc'],
                scores=[],
                average_score=0.0,
                consensus_verdict=Verdict.ERROR,
                majority_ratio=0.0,
                final_explanation="No judges could evaluate this criterion",
                relevant_files=relevant_files
            )
        
        # Weighted average score
        total_weight = 0
        weighted_sum = 0
        for i, score in enumerate(scores):
            judge_key = list(self.judges.keys())[i] if i < len(self.judges) else 'unknown'
            weight = self.judges.get(judge_key, {}).get('weight', 1.0) * score.confidence
            weighted_sum += score.score * weight
            total_weight += weight
        
        average_score = weighted_sum / total_weight if total_weight > 0 else 0
        
        # Majority vote
        pass_votes = sum(1 for s in scores if s.pass_verdict)
        majority_ratio = pass_votes / len(scores)
        
        # Determine consensus verdict
        if majority_ratio >= self.consensus_ratio and average_score >= self.pass_score:
            consensus_verdict = Verdict.PASS
        elif majority_ratio >= 0.5:
            consensus_verdict = Verdict.PARTIAL
        else:
            consensus_verdict = Verdict.FAIL
        
        # Compile final explanation
        explanations = [f"**{s.judge_name}** (Score: {s.score}/10): {s.explanation[:200]}..." 
                       for s in scores]
        final_explanation = "\n\n".join(explanations)
        
        logger.info(f"Criterion {criterion['id']}: {consensus_verdict.value} (avg: {average_score:.1f}, majority: {majority_ratio:.0%})")
        
        return CriterionResult(
            criterion_id=criterion['id'],
            criterion_type=criterion_type,
            criterion_desc=criterion['desc'],
            scores=scores,
            average_score=round(average_score, 2),
            consensus_verdict=consensus_verdict,
            majority_ratio=round(majority_ratio, 2),
            final_explanation=final_explanation,
            relevant_files=relevant_files
        )
    
    def generate_remediation(self, failed_results: List[CriterionResult], file_tree: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate remediation suggestions for failed criteria using cheap LLM."""
        if not self.remediation_config.get('enabled', False):
            return []
        
        remediation_model = self.llms_config.get('remediation', {}).get('model', 'gemini/gemini-1.5-flash')
        max_fixes = self.remediation_config.get('max_fixes_per_file', 5)
        
        suggestions = []
        
        for result in failed_results[:max_fixes]:
            try:
                # Get relevant file content
                relevant_code = ""
                for file_path in result.relevant_files[:3]:
                    if file_path in file_tree:
                        relevant_code += f"\n# {file_path}\n{file_tree[file_path][:2000]}"
                
                # Compile issues from all judges
                all_issues = []
                for score in result.scores:
                    all_issues.extend(score.issues)
                
                system_prompt = """You are a code remediation expert. 
Generate specific code fixes for the issues identified.
Respond in JSON format:
{
    "criterion_id": <id>,
    "fixes": [
        {
            "file": "filename.py",
            "description": "What to fix",
            "code_before": "problematic code snippet",
            "code_after": "fixed code snippet"
        }
    ]
}
Keep fixes minimal and focused."""

                user_prompt = f"""Generate fixes for this failed requirement:

**Requirement**: {result.criterion_desc}
**Score**: {result.average_score}/10
**Issues**: {json.dumps(all_issues)}

**Relevant Code**:
{relevant_code}

Provide targeted fixes as JSON."""

                response = self._call_llm(
                    remediation_model,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=2048
                )
                
                if response:
                    # Extract JSON
                    json_match = re.search(r'\{[\s\S]*\}', response)
                    if json_match:
                        try:
                            fix_data = json.loads(json_match.group())
                            suggestions.append(fix_data)
                        except json.JSONDecodeError:
                            pass
                            
            except Exception as e:
                logger.warning(f"Remediation generation failed for criterion {result.criterion_id}: {e}")
        
        return suggestions
    
    def run(
        self,
        file_tree: Dict[str, str],
        criteria: Dict[str, List[Dict]],
        language: str = "python"
    ) -> TribunalVerdict:
        """
        Main adjudication pipeline.
        
        Args:
            file_tree: Dict of file paths to content
            criteria: Extracted invariants (technical and functional)
            language: Detected language
            
        Returns:
            TribunalVerdict with all results
        """
        start_time = time.time()
        
        logger.info("=" * 60)
        logger.info("TRIBUNAL SESSION STARTING")
        logger.info("=" * 60)
        
        # Run static analysis first
        static_results = self.run_static_analysis(file_tree, language)
        
        # Build spec summary for context
        spec_summary = "Technical Requirements:\n"
        for item in criteria.get('technical', []):
            spec_summary += f"- {item['desc']}\n"
        spec_summary += "\nFunctional Requirements:\n"
        for item in criteria.get('functional', []):
            spec_summary += f"- {item['desc']}\n"
        
        # Evaluate each criterion
        criterion_results: List[CriterionResult] = []
        
        # Process technical criteria
        for criterion in criteria.get('technical', []):
            result = self.evaluate_criterion(criterion, 'technical', file_tree, spec_summary)
            criterion_results.append(result)
        
        # Process functional criteria
        for criterion in criteria.get('functional', []):
            result = self.evaluate_criterion(criterion, 'functional', file_tree, spec_summary)
            criterion_results.append(result)
        
        # Calculate overall verdict
        passed = sum(1 for r in criterion_results if r.consensus_verdict == Verdict.PASS)
        failed = sum(1 for r in criterion_results if r.consensus_verdict == Verdict.FAIL)
        total = len(criterion_results)
        
        if total == 0:
            overall_verdict = Verdict.ERROR
            overall_score = 0.0
        else:
            overall_score = sum(r.average_score for r in criterion_results) / total
            pass_ratio = passed / total
            
            if pass_ratio >= self.consensus_ratio and overall_score >= self.pass_score:
                overall_verdict = Verdict.PASS
            elif pass_ratio >= 0.5:
                overall_verdict = Verdict.PARTIAL
            else:
                overall_verdict = Verdict.FAIL
        
        # Generate remediation for failed criteria
        failed_results = [r for r in criterion_results if r.consensus_verdict == Verdict.FAIL]
        remediation_suggestions = self.generate_remediation(failed_results, file_tree)
        
        # Calculate static analysis issue count
        static_issue_count = sum(len(r.issues) for r in static_results)
        
        execution_time = time.time() - start_time
        
        verdict = TribunalVerdict(
            timestamp=datetime.now().isoformat(),
            overall_verdict=overall_verdict,
            overall_score=round(overall_score, 2),
            total_criteria=total,
            passed_criteria=passed,
            failed_criteria=failed,
            static_analysis_issues=static_issue_count,
            criterion_results=criterion_results,
            static_analysis_results=static_results,
            remediation_suggestions=remediation_suggestions,
            execution_time_seconds=round(execution_time, 2)
        )
        
        logger.info("=" * 60)
        logger.info(f"TRIBUNAL VERDICT: {overall_verdict.value}")
        logger.info(f"Overall Score: {overall_score:.1f}/10")
        logger.info(f"Passed: {passed}/{total} | Failed: {failed}/{total}")
        logger.info(f"Execution Time: {execution_time:.1f}s")
        logger.info("=" * 60)
        
        return verdict
    
    def generate_report_md(self, verdict: TribunalVerdict) -> str:
        """Generate REPORT.md with color-coded sections."""
        
        # Color codes for terminal/markdown
        def status_emoji(v: Verdict) -> str:
            return {
                Verdict.PASS: "✅",
                Verdict.FAIL: "❌",
                Verdict.PARTIAL: "⚠️",
                Verdict.ERROR: "🔴"
            }.get(v, "❓")
        
        def score_color(score: float) -> str:
            if score >= 8:
                return "🟢"
            elif score >= 6:
                return "🟡"
            else:
                return "🔴"
        
        report = f"""# Dysruption CVA Verification Report

**Generated**: {verdict.timestamp}
**Execution Time**: {verdict.execution_time_seconds}s

---

## 📊 Summary

| Metric | Value |
|--------|-------|
| **Overall Verdict** | {status_emoji(verdict.overall_verdict)} **{verdict.overall_verdict.value}** |
| **Overall Score** | {score_color(verdict.overall_score)} {verdict.overall_score}/10 |
| **Criteria Passed** | {verdict.passed_criteria}/{verdict.total_criteria} |
| **Criteria Failed** | {verdict.failed_criteria}/{verdict.total_criteria} |
| **Static Analysis Issues** | {verdict.static_analysis_issues} |

---

## 🔍 Per-Criterion Breakdown

"""
        
        # Group by type
        technical = [r for r in verdict.criterion_results if r.criterion_type == 'technical']
        functional = [r for r in verdict.criterion_results if r.criterion_type == 'functional']
        
        if technical:
            report += "### Technical Requirements\n\n"
            for r in technical:
                report += f"""#### {status_emoji(r.consensus_verdict)} T{r.criterion_id}: {r.criterion_desc}

- **Score**: {score_color(r.average_score)} {r.average_score}/10
- **Majority**: {r.majority_ratio:.0%}
- **Verdict**: {r.consensus_verdict.value}
- **Files**: {', '.join(r.relevant_files[:5]) if r.relevant_files else 'N/A'}

<details>
<summary>Judge Details</summary>

{r.final_explanation}

</details>

"""
        
        if functional:
            report += "### Functional Requirements\n\n"
            for r in functional:
                report += f"""#### {status_emoji(r.consensus_verdict)} F{r.criterion_id}: {r.criterion_desc}

- **Score**: {score_color(r.average_score)} {r.average_score}/10
- **Majority**: {r.majority_ratio:.0%}
- **Verdict**: {r.consensus_verdict.value}
- **Files**: {', '.join(r.relevant_files[:5]) if r.relevant_files else 'N/A'}

<details>
<summary>Judge Details</summary>

{r.final_explanation}

</details>

"""
        
        # Static analysis section
        if verdict.static_analysis_results:
            report += "---\n\n## 🛠️ Static Analysis Issues\n\n"
            
            for result in verdict.static_analysis_results:
                if result.issues:
                    report += f"### {result.tool.upper()} - {result.file_path}\n\n"
                    report += f"**Severity Counts**: {json.dumps(result.severity_counts)}\n\n"
                    
                    report += "| Line | Message | Type |\n"
                    report += "|------|---------|------|\n"
                    for issue in result.issues[:10]:  # Limit to 10 per file
                        line = issue.get('line', '-')
                        msg = issue.get('message', issue.get('symbol', 'Unknown'))[:50]
                        itype = issue.get('type', issue.get('severity', 'info'))
                        report += f"| {line} | {msg} | {itype} |\n"
                    
                    if len(result.issues) > 10:
                        report += f"\n*...and {len(result.issues) - 10} more issues*\n"
                    report += "\n"
        
        # Remediation section
        if verdict.remediation_suggestions:
            report += "---\n\n## 🔧 Suggested Fixes\n\n"
            
            for suggestion in verdict.remediation_suggestions:
                cid = suggestion.get('criterion_id', '?')
                report += f"### Fixes for Criterion {cid}\n\n"
                
                for fix in suggestion.get('fixes', []):
                    report += f"**File**: `{fix.get('file', 'unknown')}`\n\n"
                    report += f"**Issue**: {fix.get('description', 'N/A')}\n\n"
                    
                    if fix.get('code_before'):
                        report += f"**Before**:\n```\n{fix['code_before']}\n```\n\n"
                    if fix.get('code_after'):
                        report += f"**After**:\n```\n{fix['code_after']}\n```\n\n"
        
        # Footer
        report += """---

## 📋 CI/CD Integration

This report was generated by **Dysruption CVA v1.0**.

For CI/CD integration, use `verdict.json` which contains machine-readable results.

```bash
# Example GitHub Actions usage
if [ $(jq '.overall_verdict' verdict.json) == '"PASS"' ]; then
  echo "Verification passed!"
else
  echo "Verification failed!"
  exit 1
fi
```

---
*Generated by Dysruption Consensus Verifier Agent*
"""
        
        return report
    
    def generate_verdict_json(self, verdict: TribunalVerdict) -> Dict[str, Any]:
        """Generate JSON verdict for CI/CD integration."""
        
        def serialize_verdict(v):
            if isinstance(v, Verdict):
                return v.value
            elif isinstance(v, (list, tuple)):
                return [serialize_verdict(item) for item in v]
            elif hasattr(v, '__dict__'):
                return {k: serialize_verdict(val) for k, val in v.__dict__.items() if not k.startswith('_')}
            elif isinstance(v, dict):
                return {k: serialize_verdict(val) for k, val in v.items()}
            return v
        
        json_data = {
            "timestamp": verdict.timestamp,
            "overall_verdict": verdict.overall_verdict.value,
            "overall_score": verdict.overall_score,
            "total_criteria": verdict.total_criteria,
            "passed_criteria": verdict.passed_criteria,
            "failed_criteria": verdict.failed_criteria,
            "static_analysis_issues": verdict.static_analysis_issues,
            "execution_time_seconds": verdict.execution_time_seconds,
            "criteria": [],
            "static_analysis": [],
            "ci_cd": {
                "success": verdict.overall_verdict == Verdict.PASS,
                "exit_code": 0 if verdict.overall_verdict == Verdict.PASS else 1,
                "summary": f"{verdict.passed_criteria}/{verdict.total_criteria} criteria passed"
            }
        }
        
        for r in verdict.criterion_results:
            json_data["criteria"].append({
                "id": r.criterion_id,
                "type": r.criterion_type,
                "description": r.criterion_desc,
                "score": r.average_score,
                "verdict": r.consensus_verdict.value,
                "majority_ratio": r.majority_ratio,
                "relevant_files": r.relevant_files
            })
        
        for r in verdict.static_analysis_results:
            json_data["static_analysis"].append({
                "tool": r.tool,
                "file": r.file_path,
                "issue_count": len(r.issues),
                "severity_counts": r.severity_counts
            })
        
        return json_data
    
    def save_outputs(self, verdict: TribunalVerdict) -> Tuple[str, str]:
        """Save REPORT.md and verdict.json."""
        report_path = self.output_config.get('report_file', 'REPORT.md')
        verdict_path = self.output_config.get('verdict_file', 'verdict.json')
        
        # Generate and save report
        report_content = self.generate_report_md(verdict)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        logger.info(f"Saved report to: {report_path}")
        
        # Generate and save verdict JSON
        verdict_json = self.generate_verdict_json(verdict)
        with open(verdict_path, 'w', encoding='utf-8') as f:
            json.dump(verdict_json, f, indent=2)
        logger.info(f"Saved verdict to: {verdict_path}")
        
        return report_path, verdict_path


def run_adjudication(
    file_tree: Dict[str, str],
    language: str = "python",
    criteria_path: str = "criteria.json",
    config_path: str = "config.yaml"
) -> TribunalVerdict:
    """
    Main entry point for the tribunal module.
    
    Args:
        file_tree: Dict of file paths to content
        language: Detected language
        criteria_path: Path to criteria.json
        config_path: Path to config.yaml
        
    Returns:
        TribunalVerdict with all results
    """
    # Load criteria
    with open(criteria_path, 'r', encoding='utf-8') as f:
        criteria = json.load(f)
    
    tribunal = Tribunal(config_path)
    verdict = tribunal.run(file_tree, criteria, language)
    tribunal.save_outputs(verdict)
    
    return verdict


if __name__ == "__main__":
    # Test the tribunal module
    import sys
    
    logger.add(sys.stderr, level="DEBUG")
    
    # Sample test
    file_tree = {
        "main.py": """
def hello():
    print("Hello World")
    
if __name__ == "__main__":
    hello()
"""
    }
    
    criteria = {
        "technical": [
            {"id": 1, "desc": "Use Python 3.10+ syntax"}
        ],
        "functional": [
            {"id": 1, "desc": "Print a greeting message"}
        ]
    }
    
    tribunal = Tribunal()
    verdict = tribunal.run(file_tree, criteria, "python")
    tribunal.save_outputs(verdict)
    
    print(f"\nVerdict: {verdict.overall_verdict.value}")
    print(f"Score: {verdict.overall_score}/10")
