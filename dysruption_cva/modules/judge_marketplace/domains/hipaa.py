"""
HIPAA Compliance Judge Plugin

Evaluates code for HIPAA (Health Insurance Portability and Accountability Act)
compliance, focusing on Protected Health Information (PHI) handling.
"""

from __future__ import annotations

from typing import Optional

from ..models import JudgeConfig, JudgeDomain, JudgeResult
from ..plugin import BaseLLMJudge


class HIPAAJudge(BaseLLMJudge):
    """
    HIPAA compliance judge evaluates code for:
    - PHI (Protected Health Information) handling
    - Data encryption requirements
    - Access control and authorization
    - Audit logging requirements
    - Data retention and disposal
    - Minimum necessary standard
    
    This judge has veto power - HIPAA violations can block merges.
    """
    
    @property
    def name(self) -> str:
        return "hipaa"
    
    @property
    def display_name(self) -> str:
        return "HIPAA Compliance Judge"
    
    @property
    def domain(self) -> JudgeDomain:
        return JudgeDomain.HIPAA
    
    @property
    def description(self) -> str:
        return (
            "Evaluates code for HIPAA compliance including PHI handling, "
            "encryption, access control, audit logging, and data retention. "
            "Has veto power for critical HIPAA violations."
        )
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def default_model(self) -> str:
        return "anthropic/claude-sonnet-4-20250514"
    
    def get_config(self) -> JudgeConfig:
        """Default configuration for HIPAA judge."""
        return JudgeConfig(
            name=self.name,
            enabled=True,
            weight=2.0,  # High weight for compliance
            veto_enabled=True,  # Can block on critical violations
            veto_threshold=3.0,  # Stricter threshold for compliance
            model=self.default_model,
        )
    
    def get_system_prompt(self) -> str:
        return """You are a HIPAA compliance expert reviewing code for healthcare applications.

Your role is to evaluate code for HIPAA (Health Insurance Portability and 
Accountability Act) compliance, focusing on protecting PHI (Protected Health Information).

## HIPAA REQUIREMENTS TO EVALUATE

### 1. PHI Identification and Handling
PHI includes any individually identifiable health information:
- Patient names
- Dates (birth, admission, discharge, death)
- Phone numbers, fax numbers, email
- SSN, medical record numbers
- Health plan numbers
- Account numbers
- Vehicle/device identifiers
- IP addresses
- Biometric data
- Photos

Check for:
- Unencrypted PHI in transit or at rest
- PHI in logs, error messages, or debug output
- PHI exposure in URLs or query parameters
- PHI in client-side storage

### 2. Technical Safeguards (§164.312)

**Access Controls (a)(1)**
- Unique user identification
- Emergency access procedures
- Automatic logoff
- Encryption and decryption

**Audit Controls (b)**
- Activity logging for PHI access
- Log integrity protection
- Audit log retention

**Integrity (c)(1)**
- PHI modification protection
- Electronic signature requirements

**Transmission Security (e)(1)**
- Encryption in transit (TLS 1.2+)
- Integrity controls

### 3. Minimum Necessary Standard
- Only access PHI needed for specific purpose
- Role-based access control
- Query limiting

### 4. Data Retention and Disposal
- Proper data destruction
- Retention period compliance
- Secure deletion methods

## SEVERITY GUIDELINES

- **CRITICAL** (VETO): Direct PHI exposure, missing encryption, no access control
- **HIGH**: Weak encryption, insufficient audit logging, access control gaps
- **MEDIUM**: Minimum necessary violations, logging issues
- **LOW**: Documentation gaps, minor configuration issues
- **INFO**: Best practice recommendations

## SCORING GUIDELINES
- 0.9-1.0: Fully HIPAA compliant, excellent safeguards
- 0.7-0.89: Mostly compliant with minor improvements needed
- 0.5-0.69: Compliance gaps present
- 0.3-0.49: Significant violations (VETO likely)
- 0.0-0.29: Critical violations, not compliant (VETO required)

Provide your response in JSON format:
{
    "score": 0.0-1.0,
    "explanation": "Overall HIPAA compliance assessment",
    "issues": [
        {
            "severity": "critical|high|medium|low|info",
            "message": "Description of the HIPAA violation",
            "file_path": "path/to/file.py",
            "start_line": 10,
            "end_line": 15,
            "suggestion": "Remediation steps",
            "hipaa_section": "§164.312(a)(1)",
            "phi_types": ["patient_name", "ssn"]
        }
    ],
    "veto": true/false,
    "metadata": {
        "phi_detected": true/false,
        "phi_types_found": ["list", "of", "phi", "types"],
        "hipaa_sections_violated": ["§164.312(a)(1)"],
        "safeguards_missing": ["encryption", "audit_logging"],
        "compliance_percentage": 0-100
    }
}

IMPORTANT: Set veto=true if ANY critical PHI exposure or violation is found."""
    
    def _build_user_prompt(
        self,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> str:
        """Build the user prompt for HIPAA compliance analysis."""
        context = context or {}
        
        prompt = f"""## Code to Review

**File:** {file_path}

```
{code_content}
```

## HIPAA Compliance Analysis Request

Please evaluate this code for HIPAA compliance. Check for:

1. **PHI handling issues**
   - Unencrypted PHI
   - PHI in logs/errors
   - PHI exposure in URLs

2. **Technical safeguards**
   - Access control mechanisms
   - Audit logging
   - Encryption (at rest and in transit)

3. **Minimum necessary standard**
   - Excessive PHI access
   - Missing role-based controls

4. **Data handling**
   - Retention compliance
   - Secure disposal
"""
        
        # Healthcare context
        if context.get("application_type"):
            prompt += f"""
## Application Context

Type: {context['application_type']}
"""
        
        if context.get("phi_fields"):
            prompt += f"""
## Known PHI Fields

The following fields are known to contain PHI:
{context['phi_fields']}
"""
        
        if context.get("existing_safeguards"):
            prompt += f"""
## Existing Safeguards

Current security measures in place:
{context['existing_safeguards']}
"""
        
        prompt += """
Provide your HIPAA compliance assessment in the specified JSON format.
Set veto=true for any critical PHI exposure or violation.
"""
        return prompt
