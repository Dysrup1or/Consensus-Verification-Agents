"""
Architect Judge Plugin

Evaluates code architecture, design patterns, maintainability, and structure.
"""

from __future__ import annotations

from typing import Optional

from ..models import JudgeConfig, JudgeDomain, JudgeResult
from ..plugin import BaseLLMJudge


class ArchitectJudge(BaseLLMJudge):
    """
    Architect judge evaluates code for:
    - Architectural patterns and anti-patterns
    - Code organization and structure
    - Modularity and separation of concerns
    - Design pattern usage
    - Maintainability and readability
    - Technical debt indicators
    
    This is a core judge that provides a general architectural assessment.
    """
    
    @property
    def name(self) -> str:
        return "architect"
    
    @property
    def display_name(self) -> str:
        return "Architect Judge"
    
    @property
    def domain(self) -> JudgeDomain:
        return JudgeDomain.ARCHITECTURE
    
    @property
    def description(self) -> str:
        return (
            "Evaluates code architecture, design patterns, and maintainability. "
            "Identifies structural issues, anti-patterns, and technical debt."
        )
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def default_model(self) -> str:
        return "anthropic/claude-sonnet-4-20250514"
    
    def get_config(self) -> JudgeConfig:
        """Default configuration for Architect judge."""
        return JudgeConfig(
            name=self.name,
            enabled=True,
            weight=1.0,
            veto_enabled=False,  # Architecture issues rarely need veto
            veto_threshold=4.0,
            model=self.default_model,
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert software architect reviewing code changes.

Your role is to evaluate code for architectural quality, focusing on:

1. **Structural Patterns**
   - Proper separation of concerns
   - Single Responsibility Principle adherence
   - Appropriate layering (presentation/business/data)
   - Module boundaries and coupling

2. **Design Patterns**
   - Correct pattern usage
   - Anti-pattern detection (God objects, spaghetti code, etc.)
   - Consistency with existing architecture

3. **Maintainability**
   - Code readability and clarity
   - Appropriate abstraction levels
   - Documentation quality
   - Naming conventions

4. **Technical Debt**
   - Hard-coded values
   - Magic numbers/strings
   - Copy-paste duplication
   - TODO/FIXME comments indicating unresolved issues

5. **Scalability**
   - Performance anti-patterns
   - Resource management
   - Concurrency considerations

SCORING GUIDELINES:
- 0.9-1.0: Excellent architecture, follows best practices
- 0.7-0.89: Good architecture with minor suggestions
- 0.5-0.69: Acceptable but has notable issues
- 0.3-0.49: Poor architecture with significant problems
- 0.0-0.29: Severe architectural flaws requiring refactoring

Provide your response in JSON format:
{
    "score": 0.0-1.0,
    "explanation": "Brief overall assessment",
    "issues": [
        {
            "severity": "critical|high|medium|low|info",
            "message": "Description of the issue",
            "file_path": "path/to/file.py",
            "start_line": 10,
            "end_line": 15,
            "suggestion": "How to fix the issue"
        }
    ],
    "veto": false,
    "metadata": {
        "patterns_detected": ["list", "of", "patterns"],
        "anti_patterns": ["list", "of", "anti_patterns"],
        "tech_debt_score": 0.0-1.0
    }
}"""
    
    def _build_user_prompt(
        self,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> str:
        """Build the user prompt for architecture analysis."""
        context = context or {}
        
        prompt = f"""## Code to Review

**File:** {file_path}

```
{code_content}
```

## Analysis Request

Please evaluate this code for architectural quality. Consider:
1. Code structure and organization
2. Design pattern usage (or misuse)
3. Separation of concerns
4. Maintainability indicators
5. Technical debt signals
"""
        
        # Add context if available
        if context.get("project_structure"):
            prompt += f"""
## Project Context

Project structure:
{context['project_structure']}
"""
        
        if context.get("related_files"):
            prompt += f"""
## Related Files

{context['related_files']}
"""
        
        if context.get("change_description"):
            prompt += f"""
## Change Description

{context['change_description']}
"""
        
        prompt += """
Provide your architectural assessment in the specified JSON format.
"""
        return prompt
