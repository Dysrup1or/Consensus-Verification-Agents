"""
PCI-DSS Compliance Judge Plugin

Evaluates code for PCI-DSS (Payment Card Industry Data Security Standard)
compliance, focusing on cardholder data protection.
"""

from __future__ import annotations

from typing import Optional

from ..models import JudgeConfig, JudgeDomain, JudgeResult
from ..plugin import BaseLLMJudge


class PCIDSSJudge(BaseLLMJudge):
    """
    PCI-DSS compliance judge evaluates code for:
    - Cardholder Data (CHD) protection
    - Primary Account Number (PAN) handling
    - Encryption and key management
    - Access control requirements
    - Audit trail requirements
    - Secure coding practices
    
    This judge has veto power - PCI-DSS violations can block merges.
    """
    
    @property
    def name(self) -> str:
        return "pci_dss"
    
    @property
    def display_name(self) -> str:
        return "PCI-DSS Compliance Judge"
    
    @property
    def domain(self) -> JudgeDomain:
        return JudgeDomain.PCI_DSS
    
    @property
    def description(self) -> str:
        return (
            "Evaluates code for PCI-DSS compliance including cardholder data "
            "protection, encryption, access control, and secure coding. "
            "Has veto power for critical PCI-DSS violations."
        )
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def default_model(self) -> str:
        return "anthropic/claude-sonnet-4-20250514"
    
    def get_config(self) -> JudgeConfig:
        """Default configuration for PCI-DSS judge."""
        return JudgeConfig(
            name=self.name,
            enabled=True,
            weight=2.0,  # High weight for compliance
            veto_enabled=True,  # Can block on critical violations
            veto_threshold=3.0,  # Stricter threshold
            model=self.default_model,
        )
    
    def get_system_prompt(self) -> str:
        return """You are a PCI-DSS compliance expert reviewing code for payment applications.

Your role is to evaluate code for PCI-DSS (Payment Card Industry Data Security Standard)
compliance, focusing on protecting cardholder data (CHD).

## PCI-DSS REQUIREMENTS TO EVALUATE

### Cardholder Data Elements
**Must protect:**
- Primary Account Number (PAN) - the card number
- Cardholder name
- Service code
- Expiration date

**Sensitive Authentication Data (never store after authorization):**
- Full track data (magnetic stripe)
- CAV2/CVC2/CVV2/CID
- PIN/PIN block

### Requirement 3: Protect Stored Cardholder Data

**3.1** Keep CHD storage to minimum
- Data retention policies
- Secure deletion when no longer needed

**3.2** Never store sensitive auth data after authorization
- No CVV/CVC storage
- No full track data
- No PIN data

**3.3** Mask PAN when displayed
- Show max first 6 and last 4 digits
- Only display full PAN if business need

**3.4** Render PAN unreadable anywhere stored
- Strong cryptography (AES-256)
- One-way hashes with salt
- Truncation
- Index tokens (with secure lookup)

**3.5-3.6** Protect cryptographic keys
- Key management procedures
- No hard-coded keys
- Key rotation

### Requirement 4: Encrypt CHD Transmission

**4.1** Use strong cryptography for transmission
- TLS 1.2+ for all CHD transmission
- No deprecated protocols (SSL, early TLS)
- Certificate validation

**4.2** Never send unencrypted PAN by end-user messaging
- No PAN in emails
- No PAN in chat
- No PAN in SMS

### Requirement 6: Secure Development

**6.1** Vulnerability management
- Security patching
- Known vulnerability tracking

**6.3** Secure coding practices
- Input validation
- Injection prevention
- Error handling (no CHD in errors)
- Secure session management

**6.4** Change control for code
- Code reviews
- Testing before production

### Requirement 10: Audit Trail

**10.1-10.3** Audit logging requirements
- User access to CHD logged
- Actions logged with timestamp
- Log integrity protection

## SEVERITY GUIDELINES

- **CRITICAL** (VETO): PAN exposure, CVV storage, unencrypted transmission
- **HIGH**: Weak encryption, missing audit logs, key management issues
- **MEDIUM**: Display masking gaps, logging deficiencies
- **LOW**: Minor configuration issues, documentation gaps
- **INFO**: Best practice recommendations

## SCORING GUIDELINES
- 0.9-1.0: Fully PCI-DSS compliant
- 0.7-0.89: Mostly compliant with minor issues
- 0.5-0.69: Compliance gaps present
- 0.3-0.49: Significant violations (VETO likely)
- 0.0-0.29: Critical violations (VETO required)

Provide your response in JSON format:
{
    "score": 0.0-1.0,
    "explanation": "Overall PCI-DSS compliance assessment",
    "issues": [
        {
            "severity": "critical|high|medium|low|info",
            "message": "Description of the PCI-DSS violation",
            "file_path": "path/to/file.py",
            "start_line": 10,
            "end_line": 15,
            "suggestion": "Remediation steps",
            "pci_requirement": "3.4",
            "chd_types": ["pan", "cvv"]
        }
    ],
    "veto": true/false,
    "metadata": {
        "chd_detected": true/false,
        "chd_types_found": ["pan", "cvv", "expiry"],
        "requirements_violated": ["3.4", "4.1"],
        "encryption_issues": ["description"],
        "compliance_percentage": 0-100
    }
}

IMPORTANT: 
- Set veto=true if PAN is exposed, CVV is stored, or transmission is unencrypted
- PAN patterns: 4XXX (Visa), 5XXX (MC), 3XXX (Amex), 6XXX (Discover)"""
    
    def _build_user_prompt(
        self,
        code_content: str,
        file_path: str,
        context: Optional[dict] = None,
    ) -> str:
        """Build the user prompt for PCI-DSS compliance analysis."""
        context = context or {}
        
        prompt = f"""## Code to Review

**File:** {file_path}

```
{code_content}
```

## PCI-DSS Compliance Analysis Request

Please evaluate this code for PCI-DSS compliance. Check for:

1. **Cardholder data handling**
   - PAN storage and display
   - CVV/CVC handling (should never be stored)
   - Expiration date handling

2. **Encryption requirements**
   - CHD encrypted at rest (AES-256)
   - CHD encrypted in transit (TLS 1.2+)
   - Key management

3. **Display masking**
   - PAN masking (first 6, last 4 max)
   - No full PAN in logs/errors

4. **Audit logging**
   - CHD access logged
   - Actions tracked
   - Log integrity

5. **Secure coding**
   - Input validation
   - Injection prevention
   - Error handling
"""
        
        # Payment processing context
        if context.get("payment_processor"):
            prompt += f"""
## Payment Context

Payment processor: {context['payment_processor']}
"""
        
        if context.get("card_data_fields"):
            prompt += f"""
## Known Card Data Fields

The following fields handle card data:
{context['card_data_fields']}
"""
        
        if context.get("tokenization"):
            prompt += f"""
## Tokenization

Tokenization status: {context['tokenization']}
"""
        
        prompt += """
Provide your PCI-DSS compliance assessment in the specified JSON format.
Set veto=true for any critical PAN/CVV exposure or encryption failures.

Pay special attention to:
- Regex patterns that might match card numbers: \\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}
- Variables named: card, pan, ccn, credit_card, payment
- Storage of CVV, CVC, CVV2, CID values
"""
        return prompt
