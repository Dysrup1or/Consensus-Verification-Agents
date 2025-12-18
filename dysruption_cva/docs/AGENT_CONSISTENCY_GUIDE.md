# CVA Agent Consistency & Constitution Guide
## Understanding How Agents Follow Workflows

## Table of Contents
1. [How the Spec/Constitution System Works](#1-how-the-specconstitution-system-works)
2. [Agent Consistency Best Practices](#2-agent-consistency-best-practices)
3. [Prompt Engineering for Consistent Results](#3-prompt-engineering-for-consistent-results)
4. [DeepSeek API Integration](#4-deepseek-api-integration)

---

## 1. How the Spec/Constitution System Works

### Flow Overview

```
spec.txt (Natural Language Requirements)
    │
    ▼
┌─────────────────────────────────────┐
│ ConstitutionParser (modules/parser.py) │
│   - Uses Gemini Flash to extract    │
│   - Produces structured JSON        │
│   - Categories: security, func, style │
└─────────────────────────────────────┘
    │
    ▼
criteria.json (Structured Invariants)
    │
    ▼
┌─────────────────────────────────────┐
│ Tribunal (modules/tribunal.py)      │
│   - Routes criteria to judges       │
│   - Each judge evaluates code       │
│   - Produces consensus verdict      │
└─────────────────────────────────────┘
    │
    ▼
verdict.json (Final Judgment)
```

### Key Components

#### 1. Specification File (`spec.txt`)
- **Purpose**: Human-readable project requirements
- **Format**: Markdown or plain text
- **Location**: Project root or specified via `--spec` flag
- **Contents**: Security rules, functionality requirements, style guidelines

#### 2. Constitution Parser (`modules/parser.py`)
- **Purpose**: Extract structured requirements from natural language
- **Model**: Gemini Flash (fast, accurate extraction)
- **Output**: JSON with three categories: security, functionality, style
- **Key Prompt**: `EXTRACTION_SYSTEM_PROMPT` defines extraction rules

#### 3. Criteria JSON (`criteria.json`)
- **Purpose**: Machine-readable requirements for judges
- **Structure**:
```json
{
  "security": [
    {"id": 1, "desc": "No hardcoded secrets", "severity": "critical"}
  ],
  "functionality": [
    {"id": 1, "desc": "API must validate input", "severity": "high"}
  ],
  "style": [
    {"id": 1, "desc": "Follow PEP 8", "severity": "medium"}
  ]
}
```

#### 4. Tribunal Judges (`modules/tribunal.py`)
- **ARCHITECT_SYSTEM_PROMPT**: Claude Sonnet - Architecture & Logic
- **SECURITY_SYSTEM_PROMPT**: DeepSeek V3 - Security & Efficiency
- **USER_PROXY_SYSTEM_PROMPT**: Gemini - Spec Alignment
- **REMEDIATION_SYSTEM_PROMPT**: GPT-4o-mini - Code Fixes

---

## 2. Agent Consistency Best Practices

### Constitutional AI Principles (from Anthropic Research)

1. **Clear Role Definition**
   - Each agent has ONE clear role (SRP for agents)
   - Role is stated explicitly in system prompt
   - Example: "You are an EXPERT SECURITY AUDITOR"

2. **Explicit Scoring Rubrics**
   - Provide exact criteria for each score level (1-10)
   - No ambiguity about what constitutes "good" vs "bad"
   - Example from CVA:
   ```
   - **10**: No vulnerabilities, optimal performance
   - **7**: Adequately secure, meets requirements
   - **4**: Multiple vulnerabilities, significant issues
   - **1**: Completely insecure or non-functional
   ```

3. **Few-Shot Examples (Critical)**
   - Show the agent EXACTLY what output looks like
   - Include realistic input → output examples
   - Example in CVA prompts shows SQL injection detection

4. **Strict Output Format**
   - Define JSON schema explicitly
   - Use `OUTPUT FORMAT (STRICT JSON)` heading
   - Validate output against schema

5. **Evaluation Criteria Checklists**
   - Provide numbered checklists
   - Agents can systematically verify each item
   - Example: "Security Checklist: SQL Injection, XSS, CSRF..."

### Why Agents Deviate (and How to Fix)

| Deviation Type | Cause | Fix |
|---------------|-------|-----|
| Format errors | Ambiguous output spec | Add explicit JSON schema |
| Inconsistent scoring | Vague rubrics | Add score examples (7 = X, 5 = Y) |
| Missing issues | Incomplete checklist | Add comprehensive criteria list |
| Hallucinated fixes | No code context | Provide relevant file snippets |
| Contradictory verdicts | No consensus rules | Define aggregation algorithm |

---

## 3. Prompt Engineering for Consistent Results

### OpenAI Prompt Engineering Best Practices

#### 1. Message Hierarchy
- **System/Developer Messages**: Highest authority, set behavior
- **User Messages**: Lower authority, can be overridden
- **Always put core rules in system prompt**

#### 2. Structured Formatting
```markdown
## SCORING RUBRIC (1-10):
- **10**: Perfect...
- **1**: Terrible...

## EVALUATION CRITERIA:
1. First criterion
2. Second criterion

## OUTPUT FORMAT (STRICT JSON):
```json
{...}
```
```

#### 3. Few-Shot Learning Pattern
```
**Requirement**: "Example requirement"

**Code Sample**:
```python
example code
```

**Output**:
```json
{
    "score": 3,
    "explanation": "Why this is scored 3...",
    "issues": ["Issue 1", "Issue 2"]
}
```
```

#### 4. Constraint Reinforcement
- State constraints multiple times in different ways
- Use bold/caps for critical constraints
- Example: "OUTPUT FORMAT (STRICT JSON - validate before responding)"

### CVA-Specific Patterns

1. **Judge Independence**: Each judge has unique expertise
2. **Confidence Scores**: Judges report uncertainty (0.0-1.0)
3. **Actionable Suggestions**: Not just problems, but solutions
4. **Context-Aware**: Judges receive file content + spec

---

## 4. DeepSeek API Integration

### API Configuration

```python
# Environment variable (required)
DEEPSEEK_API_KEY=sk-xxx

# Base URL (OpenAI-compatible)
https://api.deepseek.com

# Authorization header
Authorization: Bearer ${DEEPSEEK_API_KEY}
```

### LiteLLM Integration

```python
import litellm

# DeepSeek model prefixes
response = await litellm.acompletion(
    model="deepseek/deepseek-chat",  # DeepSeek V3
    messages=[{"role": "user", "content": "Hello"}],
)
```

### Error Handling

```python
try:
    response = await litellm.acompletion(...)
except litellm.exceptions.AuthenticationError:
    logger.error("Invalid DEEPSEEK_API_KEY")
except litellm.exceptions.RateLimitError:
    await asyncio.sleep(60)  # Wait for rate limit reset
except Exception as e:
    logger.error(f"DeepSeek API error: {e}")
```

---

## Creating Your Own Spec

### Template Structure

```markdown
# Project Name - Specification

## Mission Statement
Brief description of what the project does.

## Security Requirements
### Critical (Must Fix)
- Requirement 1
- Requirement 2

### High Priority
- Requirement 3

## Functionality Requirements
### Core Features (Critical)
- Feature 1 must work as described

### Secondary Features (High)
- Feature 2 should be implemented

## Style Requirements
### Code Quality (Medium)
- Follow style guide
- Use type annotations

## Performance Requirements
- Response times under X seconds
- Memory usage under Y MB
```

### Best Practices for Spec Writing

1. **Be Specific**: "No SQL injection" not "Be secure"
2. **Include Severities**: Critical, High, Medium, Low
3. **Cover All Categories**: Security, Functionality, Style
4. **Provide Context**: Why each requirement matters
5. **Set Boundaries**: What is NOT in scope

---

## Running Self-Verification

```powershell
# Set environment variable to allow self-verification
$env:CVA_SELF_VERIFY = "true"

# Run CVA against itself using the constitution
cd c:\Users\alexe\Invariant\dysruption_cva
python cva.py run --dir . --spec cva_constitution.txt
```

The CVA will now evaluate itself against the constitution requirements!
