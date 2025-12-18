"""
User Proxy Judge Plugin

Represents the PR author's intent and validates changes against success criteria.
"""

from __future__ import annotations

from typing import Optional

from ..models import JudgeConfig, JudgeDomain, JudgeResult
from ..plugin import BaseLLMJudge


class UserProxyJudge(BaseLLMJudge):
    """
    User Proxy judge evaluates code for:
    - Alignment with stated success criteria
    - Completeness of implementation
    - Test coverage expectations
    - Documentation requirements
    - User experience considerations
    
    This judge represents the PR author's perspective and validates
    that the implementation meets the stated requirements.
    """
    
    @property
    def name(self) -> str:
        return "user_proxy"
    
    @property
    def display_name(self) -> str:
        return "User Proxy Judge"
    
    @property
    def domain(self) -> JudgeDomain:
        return JudgeDomain.USER_PROXY
    
    @property
    def description(self) -> str:
        return (
            "Validates implementation against success criteria and requirements. "
            "Represents the PR author's intent and ensures completeness."
        )
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def default_model(self) -> str:
        return "anthropic/claude-sonnet-4-20250514"
    
    def get_config(self) -> JudgeConfig:
        """Default configuration for User Proxy judge."""
        return JudgeConfig(
            name=self.name,
            enabled=True,
            weight=1.0,
            veto_enabled=False,
            veto_threshold=4.0,
            model=self.default_model,
        )
    
    def get_system_prompt(self) -> str:
        return """You are representing the perspective of the code author/user.

Your role is to validate that the implementation meets the stated requirements
and success criteria. Focus on:

1. **Requirements Fulfillment**
   - Are all stated requirements addressed?
   - Is the implementation complete?
   - Are edge cases handled?

2. **Success Criteria Validation**
   - Does the code meet each success criterion?
   - Are acceptance conditions satisfied?
   - Is the scope correctly bounded?

3. **Completeness**
   - Is the feature/fix fully implemented?
   - Are there any missing components?
   - Is error handling complete?

4. **Test Coverage**
   - Are tests present for new functionality?
   - Do tests cover edge cases?
   - Is test quality adequate?

5. **Documentation**
   - Is documentation updated?
   - Are complex parts explained?
   - Is the API documented?

6. **User Experience**
   - Is the change user-friendly?
   - Are error messages helpful?
   - Is the interface intuitive?

SCORING GUIDELINES:
- 0.9-1.0: Fully meets all criteria, excellent implementation
- 0.7-0.89: Meets most criteria with minor gaps
- 0.5-0.69: Partially meets criteria, notable gaps
- 0.3-0.49: Many criteria unmet
- 0.0-0.29: Does not meet stated requirements

Provide your response in JSON format:
{
    "score": 0.0-1.0,
    "explanation": "Overall assessment of requirement fulfillment",
    "issues": [
        {
            "severity": "critical|high|medium|low|info",
            "message": "Description of unmet requirement or gap",
            "file_path": "path/to/file.py",
            "start_line": 10,
            "end_line": 15,
            "suggestion": "How to address the gap"
        }
    ],
    "veto": false,
    "metadata": {
        "criteria_met": ["list", "of", "met", "criteria"],
        "criteria_unmet": ["list", "of", "unmet", "criteria"],
        "completion_percentage": 0-100
    }
}"""
    
    def _build_user_prompt(
        self,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> str:
        """Build the user prompt for requirements validation."""
        context = context or {}
        
        prompt = f"""## Code to Review

**File:** {file_path}

```
{code_content}
```

## Validation Request

Please validate this code against the requirements and success criteria.
"""
        
        # Success criteria is critical for this judge
        if context.get("success_criteria"):
            prompt += f"""
## Success Criteria

The implementation should satisfy these criteria:

{context['success_criteria']}

Evaluate each criterion and indicate whether it is met.
"""
        else:
            prompt += """
## Note

No specific success criteria were provided. Evaluate the code for:
- General completeness
- Error handling
- Edge case coverage
- Code quality
"""
        
        # PR description provides context
        if context.get("pr_description"):
            prompt += f"""
## PR Description

{context['pr_description']}
"""
        
        # Test information
        if context.get("test_files"):
            prompt += f"""
## Related Tests

Test files to consider:
{context['test_files']}
"""
        
        if context.get("change_description"):
            prompt += f"""
## Change Description

{context['change_description']}
"""
        
        prompt += """
Provide your requirements validation in the specified JSON format.
List each success criterion as either met or unmet in the metadata.
"""
        return prompt
