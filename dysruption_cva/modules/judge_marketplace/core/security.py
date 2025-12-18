"""
Security Judge Plugin

Evaluates code for security vulnerabilities and best practices.
"""

from __future__ import annotations

from typing import Optional

from ..models import JudgeConfig, JudgeDomain, JudgeResult
from ..plugin import BaseLLMJudge


class SecurityJudge(BaseLLMJudge):
    """
    Security judge evaluates code for:
    - Common vulnerability patterns (OWASP Top 10)
    - Injection vulnerabilities (SQL, XSS, command injection)
    - Authentication and authorization issues
    - Cryptographic weaknesses
    - Sensitive data exposure
    - Security misconfigurations
    
    This judge has veto power - critical security issues can block merges.
    """
    
    @property
    def name(self) -> str:
        return "security"
    
    @property
    def display_name(self) -> str:
        return "Security Judge"
    
    @property
    def domain(self) -> JudgeDomain:
        return JudgeDomain.SECURITY
    
    @property
    def description(self) -> str:
        return (
            "Evaluates code for security vulnerabilities including OWASP Top 10, "
            "injection attacks, authentication issues, and cryptographic weaknesses. "
            "Has veto power for critical security issues."
        )
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def default_model(self) -> str:
        return "anthropic/claude-sonnet-4-20250514"
    
    def get_config(self) -> JudgeConfig:
        """Default configuration for Security judge."""
        return JudgeConfig(
            name=self.name,
            enabled=True,
            weight=1.5,  # Higher weight for security
            veto_enabled=True,  # Can block on critical issues
            veto_threshold=3.0,
            model=self.default_model,
        )
    
    def get_system_prompt(self) -> str:
        return """You are an expert security auditor reviewing code changes.

Your role is to identify security vulnerabilities and risks, focusing on:

1. **Injection Vulnerabilities**
   - SQL injection
   - Cross-site scripting (XSS)
   - Command injection
   - LDAP injection
   - Template injection

2. **Authentication & Authorization**
   - Broken authentication
   - Session management flaws
   - Privilege escalation
   - Insecure direct object references

3. **Cryptographic Issues**
   - Weak algorithms (MD5, SHA1 for passwords)
   - Hard-coded secrets/keys
   - Insufficient entropy
   - Improper key management

4. **Data Exposure**
   - Sensitive data in logs
   - PII exposure
   - Information leakage
   - Insecure storage

5. **Security Misconfigurations**
   - Debug mode in production
   - Default credentials
   - Missing security headers
   - Overly permissive CORS

6. **Input Validation**
   - Missing validation
   - Path traversal
   - File upload vulnerabilities
   - Deserialization issues

SEVERITY GUIDELINES:
- CRITICAL: Direct exploitation possible, immediate fix required (triggers VETO)
- HIGH: Serious vulnerability, high-priority fix needed
- MEDIUM: Moderate risk, should be addressed
- LOW: Minor security improvement
- INFO: Security best practice suggestion

SCORING GUIDELINES:
- 0.9-1.0: No security issues found
- 0.7-0.89: Minor security improvements suggested
- 0.5-0.69: Moderate security concerns
- 0.3-0.49: Significant vulnerabilities present
- 0.0-0.29: Critical security flaws (VETO recommended)

Provide your response in JSON format:
{
    "score": 0.0-1.0,
    "explanation": "Brief overall security assessment",
    "issues": [
        {
            "severity": "critical|high|medium|low|info",
            "message": "Description of the vulnerability",
            "file_path": "path/to/file.py",
            "start_line": 10,
            "end_line": 15,
            "suggestion": "How to remediate",
            "cwe_id": "CWE-XXX",
            "owasp_category": "A01:2021"
        }
    ],
    "veto": true/false,
    "metadata": {
        "vulnerabilities_found": 0,
        "critical_count": 0,
        "high_count": 0,
        "cwe_ids": ["CWE-XXX"],
        "owasp_categories": ["A01:2021"]
    }
}

IMPORTANT: Set veto=true if ANY critical vulnerability is found."""
    
    def _build_user_prompt(
        self,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> str:
        """Build the user prompt for security analysis."""
        context = context or {}
        
        prompt = f"""## Code to Review

**File:** {file_path}

```
{code_content}
```

## Security Analysis Request

Please perform a thorough security audit of this code. Check for:

1. **Injection vulnerabilities** (SQL, XSS, command, etc.)
2. **Authentication/authorization issues**
3. **Cryptographic weaknesses**
4. **Sensitive data exposure**
5. **Security misconfigurations**
6. **Input validation gaps**
"""
        
        # Add file type context
        if file_path.endswith(".py"):
            prompt += """
### Python-Specific Checks
- subprocess with shell=True
- eval/exec usage
- pickle deserialization
- Format string vulnerabilities
- SQL string concatenation
"""
        elif file_path.endswith((".js", ".ts")):
            prompt += """
### JavaScript/TypeScript-Specific Checks
- innerHTML usage
- eval usage
- Prototype pollution
- CORS issues
- Cookie security
"""
        
        # Add context if available
        if context.get("dependencies"):
            prompt += f"""
## Dependencies

Known dependencies with potential CVEs to consider:
{context['dependencies']}
"""
        
        if context.get("change_description"):
            prompt += f"""
## Change Description

{context['change_description']}
"""
        
        prompt += """
Provide your security assessment in the specified JSON format.
Remember to set veto=true for any critical vulnerabilities.
"""
        return prompt
