# AI-Friendly Architecture Guide: Building Systems That AI Agents Can Understand

> **Research-Backed Technical Report**  
> **Date**: December 18, 2025  
> **Purpose**: Extension-Backend Integration + AI-Agent-Readable Codebase Design  
> **Deployment Target**: Railway.app (Cloud) + VS Code Extension (Local)

---

## Executive Summary

This document answers four critical questions:
1. **How would the VS Code extension interact with our local backend?**
2. **What changes are needed for Railway.app deployment?**
3. **What does research say about AI-friendly code architecture?**
4. **Can we build a system that is AI-friendly, built by AIs?**

### Key Findings

| Research Source | Core Insight |
|-----------------|--------------|
| **Anthropic (Building Effective Agents)** | "Invest just as much effort in creating good agent-computer interfaces (ACI) as you would for human-computer interfaces." |
| **OpenAI (Function Calling Best Practices)** | "Write clear descriptions, use enums to make invalid states unrepresentable, pass the intern test." |
| **Cursor (Rules System)** | Project-level `.cursor/rules/` and `AGENTS.md` files provide persistent AI context. |
| **Harper Reed (LLM Codegen Workflow)** | Save `spec.md`, `prompt_plan.md`, and `todo.md` in repo for AI continuity across sessions. |
| **Model Context Protocol (MCP)** | Standardized interface for AI ↔ External System communication ("USB-C for AI"). |

---

## Part 1: Extension ↔ Backend Communication Architecture

### Current State Analysis

Your backend ([modules/api.py](../modules/api.py)) already exposes:
- **REST endpoints**: `/run`, `/status`, `/verdict`, `/prompt`, `/docs`
- **WebSocket**: `/ws` for real-time status streaming
- **Port**: `8001` (configurable via `PORT` environment variable)

### Recommended Integration Pattern

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VS CODE EXTENSION                           │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ FileWatcher     │  │ BackendClient   │  │ DiagnosticsProvider │  │
│  │ (workspace)     │──│ (HTTP/WS)       │──│ (squiggly lines)    │  │
│  └─────────────────┘  └────────┬────────┘  └─────────────────────┘  │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                    HTTP :8001 / WebSocket
                                 │
┌────────────────────────────────┼────────────────────────────────────┐
│                         PYTHON BACKEND                              │
├────────────────────────────────┼────────────────────────────────────┤
│  ┌─────────────────┐  ┌────────┴────────┐  ┌─────────────────────┐  │
│  │ FastAPI Router  │──│ Tribunal Engine │──│ Prompt Synthesizer  │  │
│  │ (modules/api.py)│  │ (judge_engine)  │  │ (AI recommendations)│  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Communication Flow

```typescript
// extension/src/backendClient.ts (Proposed)
export class BackendClient {
  private baseUrl: string;
  private ws: WebSocket | null = null;

  constructor(private port: number = 8001) {
    this.baseUrl = `http://localhost:${port}`;
  }

  // Health check before enabling features
  async isHealthy(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/docs`);
      return res.ok;
    } catch { return false; }
  }

  // Trigger a CVA run on changed files
  async triggerRun(targetDir: string, specContent: string): Promise<RunResponse> {
    const res = await fetch(`${this.baseUrl}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_dir: targetDir, spec_content: specContent })
    });
    return res.json();
  }

  // WebSocket for real-time verdict streaming
  connectWs(onMessage: (msg: WebSocketMessage) => void): void {
    this.ws = new WebSocket(`ws://localhost:${this.port}/ws`);
    this.ws.onmessage = (event) => onMessage(JSON.parse(event.data));
  }
}
```

### Backend Auto-Start Pattern

```typescript
// extension/src/backendManager.ts (Proposed)
import { spawn, ChildProcess } from 'child_process';
import * as vscode from 'vscode';

export class BackendManager {
  private process: ChildProcess | null = null;

  async start(cvaPath: string): Promise<void> {
    // Check if already running
    const client = new BackendClient();
    if (await client.isHealthy()) {
      vscode.window.showInformationMessage('CVA backend already running');
      return;
    }

    // Start the backend
    this.process = spawn('python', ['-m', 'uvicorn', 'modules.api:app', '--port', '8001'], {
      cwd: cvaPath,
      shell: true
    });

    // Wait for health check
    for (let i = 0; i < 10; i++) {
      await new Promise(r => setTimeout(r, 1000));
      if (await client.isHealthy()) return;
    }
    throw new Error('Backend failed to start');
  }

  stop(): void {
    this.process?.kill();
    this.process = null;
  }
}
```

---

## Part 2: File Structure Changes for Railway.app Deployment

### Current Structure (Single Deployable Backend)

```
dysruption_cva/
├── modules/           # Python backend (Railway deploys this)
├── railway.json       # Railway config ✅ Already exists
├── requirements.txt   # Dependencies ✅ Already exists
└── config.yaml        # Runtime config
```

### Proposed Monorepo Structure (Extension + Backend)

```
invariant/
├── README.md                    # Project overview
├── AGENTS.md                    # 🆕 AI agent instructions (Cursor/Claude)
├── ARCHITECTURE.md              # 🆕 Visual system diagrams
│
├── packages/
│   ├── backend/                 # 🔄 Move dysruption_cva here
│   │   ├── modules/
│   │   ├── railway.json
│   │   ├── requirements.txt
│   │   └── Dockerfile           # 🆕 For Railway
│   │
│   ├── extension/               # 🆕 VS Code/Cursor extension
│   │   ├── src/
│   │   │   ├── extension.ts
│   │   │   ├── backendClient.ts
│   │   │   ├── backendManager.ts
│   │   │   ├── diagnosticsProvider.ts
│   │   │   └── sidebarProvider.ts
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── shared/                  # 🆕 Shared types/schemas
│       ├── schemas/
│       │   ├── run_request.json
│       │   ├── verdict.json
│       │   └── websocket_message.json
│       └── types/
│           └── index.d.ts
│
├── .cursor/                     # 🆕 Cursor rules
│   └── rules/
│       └── cva-development/
│           └── RULE.md
│
└── docs/
    ├── AI_FRIENDLY_ARCHITECTURE.md  # This document
    └── API_REFERENCE.md
```

### Railway.json Updates

```json
{
  "$schema": "https://railway.com/schema.json",
  "build": {
    "builder": "nixpacks",
    "nixpacksVersion": "1.29.1",
    "buildCommand": "pip install -r packages/backend/requirements.txt"
  },
  "deploy": {
    "startCommand": "cd packages/backend && python -m uvicorn modules.api:app --host 0.0.0.0 --port ${PORT:-8001}",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

---

## Part 3: Research on AI-Friendly Code Architecture

### 3.1 Anthropic's Agent-Computer Interface (ACI) Principles

From [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents):

> "We spent more time optimizing our tools than the overall prompt."

**Key Recommendations:**
1. **Clear function names**: `get_weather` not `gw`
2. **Detailed descriptions**: Include edge cases and format requirements
3. **Enums over strings**: Prevent invalid inputs
4. **Example usage**: Show what a valid call looks like
5. **Pass the intern test**: "Can an intern correctly use this given only what you gave the model?"

### 3.2 OpenAI Function Calling Best Practices

From [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling):

```python
# ✅ GOOD: Clear, typed, with description
{
    "type": "function",
    "name": "run_cva_analysis",
    "description": "Run CVA analysis on a directory. Returns a run_id for tracking.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_dir": {
                "type": "string",
                "description": "Absolute path to the project directory to analyze"
            },
            "spec_content": {
                "type": "string",
                "description": "The constitution/spec content (invariants to verify)"
            }
        },
        "required": ["target_dir", "spec_content"]
    }
}

# ❌ BAD: Vague, untyped
{
    "name": "run",
    "description": "Runs analysis",
    "parameters": { "type": "object" }
}
```

### 3.3 Cursor Rules System

From [Cursor Rules Documentation](https://docs.cursor.com/context/rules):

**Project Rules** (`.cursor/rules/`):
- Version-controlled, scoped to codebase
- Use `RULE.md` with frontmatter for metadata
- Keep under 500 lines, split large rules

**AGENTS.md** (Simple Alternative):
- Plain markdown in project root
- No complex configuration
- Perfect for simple, readable instructions

### 3.4 Harper Reed's Spec-Driven Development

From [My LLM Codegen Workflow](https://harper.blog/2025/02/16/my-llm-codegen-workflow-atm/):

**Files to maintain for AI continuity:**
1. `spec.md` - Comprehensive specification
2. `prompt_plan.md` - Step-by-step implementation prompts
3. `todo.md` - Checkable task list for state tracking

**Key insight**: "Planning is done per task, not for the entire project."

---

## Part 4: Building an AI-Friendly System

### 4.1 The AGENTS.md Pattern

Create an `AGENTS.md` in your project root:

```markdown
# CVA Agent Instructions

## Project Overview
CVA (Consensus Verifier Agent) is a code verification system that uses multiple LLM judges to validate code against constitutional specifications.

## Architecture Quick Reference
- **Entry Point**: `modules/api.py` (FastAPI server)
- **Core Engine**: `modules/tribunal.py` (multi-judge consensus)
- **Parser**: `modules/parser.py` (constitution → invariants)
- **Config**: `config.yaml` (runtime settings)

## Key Concepts
1. **Constitution**: Natural language rules (e.g., "All functions must have error handling")
2. **Invariant**: Parsed, enforceable rule extracted from constitution
3. **Tribunal**: Panel of 3 LLM judges voting on compliance
4. **Verdict**: Consensus result (PASS/FAIL with confidence)

## Common Tasks

### Adding a New Endpoint
1. Define Pydantic schemas in `modules/schemas.py`
2. Add route in `modules/api.py` with clear docstring
3. Add test in `tests/test_api_*.py`

### Modifying the Tribunal
1. Judges are defined in `config.yaml` under `judges`
2. Consensus logic is in `modules/tribunal.py:run_adjudication()`
3. Each judge's prompt is in `modules/judge_engine.py`

## File Naming Conventions
- `test_*.py` - Test files (pytest)
- `*_store.py` - Persistence modules
- `*_engine.py` - Core business logic
- `*_provider.py` - External service adapters

## Code Style
- Use type hints on all public functions
- Docstrings in Google format
- Async functions for I/O operations
- Pydantic for all API schemas
```

### 4.2 Comprehensive Docstring Template

```python
async def run_tribunal_analysis(
    target_dir: str,
    spec_content: str,
    judges: list[str] = None,
    quorum: int = 3
) -> ConsensusResult:
    """
    Execute a full CVA tribunal analysis on a target directory.

    This function orchestrates the complete verification pipeline:
    1. Parses the spec_content into individual invariants
    2. Scans target_dir for relevant source files
    3. Dispatches each file to a panel of LLM judges
    4. Aggregates votes into a consensus verdict

    Args:
        target_dir: Absolute path to the project to analyze.
            Must exist and contain at least one source file.
            Example: "/home/user/my-project" or "C:\\Users\\alex\\project"
        
        spec_content: Natural language constitution/specification.
            Each line should be one rule. Blank lines are ignored.
            Example: "All API endpoints must validate input.\nNo hardcoded secrets."
        
        judges: Optional list of judge model IDs.
            Defaults to config.yaml's judge list.
            Valid options: ["gpt-4o", "claude-sonnet", "gemini-pro"]
        
        quorum: Minimum judges required for consensus.
            Must be <= len(judges) and > 0.

    Returns:
        ConsensusResult with fields:
            - verdict: "PASS" | "FAIL" | "INCONCLUSIVE"
            - confidence: float 0.0-1.0
            - violations: list of specific rule violations
            - recommendations: suggested fixes

    Raises:
        FileNotFoundError: If target_dir doesn't exist
        ValueError: If spec_content is empty
        TribunalError: If judges fail to reach consensus

    Example:
        >>> result = await run_tribunal_analysis(
        ...     target_dir="/app/src",
        ...     spec_content="All functions must have docstrings.",
        ...     judges=["gpt-4o", "claude-sonnet"],
        ...     quorum=2
        ... )
        >>> print(result.verdict)  # "PASS" or "FAIL"
    """
```

### 4.3 Schema-First Design for AI Comprehension

```python
# modules/schemas.py - Self-documenting Pydantic models

from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum

class VerdictStatus(str, Enum):
    """Possible outcomes of a CVA tribunal judgment."""
    PASS = "pass"         # Code complies with all invariants
    FAIL = "fail"         # Code violates one or more invariants
    INCONCLUSIVE = "inconclusive"  # Judges could not reach consensus

class RunRequest(BaseModel):
    """Request body for POST /run endpoint."""
    
    target_dir: str = Field(
        ...,
        description="Absolute path to the project directory to analyze",
        examples=["/home/user/my-project", "C:\\Users\\alex\\repo"]
    )
    
    spec_content: str = Field(
        ...,
        description="Natural language specification. One rule per line.",
        examples=["All functions must have error handling.\nNo SQL injection."]
    )
    
    judges: list[str] | None = Field(
        default=None,
        description="Override default judge panel. Use model IDs.",
        examples=[["gpt-4o", "claude-sonnet"]]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "target_dir": "/app/src",
                "spec_content": "All API endpoints must validate input.",
                "judges": ["gpt-4o", "claude-sonnet", "gemini-pro"]
            }
        }
```

### 4.4 MCP Server Pattern for Tool Exposure

Consider exposing CVA as an MCP server for Claude/Cursor integration:

```python
# modules/mcp_server.py (Proposed)
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("cva")

@mcp.tool()
async def analyze_code(target_dir: str, specification: str) -> str:
    """
    Run CVA code analysis against a specification.

    Args:
        target_dir: Path to the code directory to analyze
        specification: Natural language rules to verify against

    Returns:
        JSON string with verdict and any violations found
    """
    from .tribunal import run_adjudication
    result = await run_adjudication(target_dir, specification)
    return result.model_dump_json()

@mcp.tool()
async def get_fix_recommendations(run_id: str) -> str:
    """
    Get AI-generated fix recommendations for a failed CVA run.

    Args:
        run_id: The run_id from a previous analyze_code call

    Returns:
        Markdown-formatted recommendations for fixing violations
    """
    from .prompt_synthesizer import get_recommendations
    return await get_recommendations(run_id)
```

---

## Part 5: Implementation Checklist

### Phase 1: AI-Readable Documentation (Week 1)

- [ ] Create `AGENTS.md` in project root
- [ ] Create `ARCHITECTURE.md` with diagrams
- [ ] Add comprehensive docstrings to all public functions in:
  - [ ] `modules/api.py`
  - [ ] `modules/tribunal.py`
  - [ ] `modules/parser.py`
  - [ ] `modules/schemas.py`
- [ ] Add `examples` field to all Pydantic models

### Phase 2: Extension Scaffold (Week 2)

- [ ] Initialize extension with `yo code`
- [ ] Create `BackendClient` for HTTP/WebSocket
- [ ] Create `BackendManager` for auto-start
- [ ] Implement `DiagnosticsProvider` for inline errors
- [ ] Implement `SidebarProvider` for verdict display

### Phase 3: Monorepo Migration (Week 3)

- [ ] Restructure into `packages/backend` and `packages/extension`
- [ ] Create `packages/shared` for JSON schemas
- [ ] Update `railway.json` for new paths
- [ ] Add TypeScript type generation from Pydantic models

### Phase 4: MCP Integration (Week 4)

- [ ] Add `mcp` to `requirements.txt`
- [ ] Create `modules/mcp_server.py`
- [ ] Test with Claude Desktop
- [ ] Document MCP setup in README

---

## Appendix A: Current Module Documentation Audit

| Module | Docstrings | Type Hints | Examples | AI-Ready? |
|--------|------------|------------|----------|-----------|
| `api.py` | ✅ Good | ✅ Yes | ❌ Missing | 🟡 Partial |
| `tribunal.py` | 🟡 Basic | ✅ Yes | ❌ Missing | 🟡 Partial |
| `parser.py` | 🟡 Basic | ✅ Yes | ❌ Missing | 🟡 Partial |
| `schemas.py` | ✅ Good | ✅ Yes | 🟡 Some | 🟢 Good |
| `prompt_synthesizer.py` | ❌ Missing | 🟡 Partial | ❌ Missing | 🔴 Needs Work |

### Priority Actions
1. Add Google-format docstrings with examples to `tribunal.py`
2. Add `Field(examples=...)` to all Pydantic models
3. Create `AGENTS.md` with architecture quick reference

---

## Appendix B: Research Sources

1. **Anthropic - Building Effective Agents**
   - URL: https://www.anthropic.com/research/building-effective-agents
   - Key: Agent-Computer Interface (ACI) design patterns

2. **OpenAI - Function Calling Guide**
   - URL: https://platform.openai.com/docs/guides/function-calling
   - Key: Best practices for tool definitions

3. **Cursor - Rules Documentation**
   - URL: https://docs.cursor.com/context/rules
   - Key: AGENTS.md and .cursor/rules patterns

4. **Harper Reed - LLM Codegen Workflow**
   - URL: https://harper.blog/2025/02/16/my-llm-codegen-workflow-atm/
   - Key: spec.md, prompt_plan.md, todo.md workflow

5. **Model Context Protocol (MCP)**
   - URL: https://modelcontextprotocol.io/quickstart
   - Key: Standardized AI ↔ Tool interface

---

*This document should be updated as new AI-agent patterns emerge. Last updated: December 18, 2025*
