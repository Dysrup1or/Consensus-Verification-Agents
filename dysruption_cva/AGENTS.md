# CVA Agent Instructions

> **For AI Assistants**: This file provides context for AI coding agents (Cursor, Copilot, Claude) working on this codebase.

## Project Overview

**CVA (Consensus Verifier Agent)** is a code verification system that uses multiple LLM judges to validate code against natural language specifications ("constitutions").

**Core Value Proposition**: Instead of one AI checking code, CVA uses a tribunal of 3+ AI judges voting on compliance, achieving higher accuracy through consensus.

## Quick Start

```bash
# Start backend
cd dysruption_cva
python -m uvicorn modules.api:app --port 8001

# Test endpoint
curl http://localhost:8001/docs
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                            │
│              POST /run { target_dir, spec_content }             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    PARSER (modules/parser.py)                    │
│        Extracts invariants from natural language spec           │
│                                                                  │
│   "All functions must have docstrings" → Invariant(rule=...,    │
│                                           category=DOCUMENTATION)│
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                  TRIBUNAL (modules/tribunal.py)                  │
│                                                                  │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐                     │
│   │ Judge 1 │    │ Judge 2 │    │ Judge 3 │   (3+ LLM judges)   │
│   │ (GPT-4) │    │ (Claude)│    │ (Gemini)│                     │
│   └────┬────┘    └────┬────┘    └────┬────┘                     │
│        │              │              │                          │
│        ▼              ▼              ▼                          │
│   ┌─────────────────────────────────────┐                       │
│   │        CONSENSUS ENGINE             │                       │
│   │   Aggregates votes → Verdict        │                       │
│   └─────────────────────────────────────┘                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      VERDICT OUTPUT                              │
│   { verdict: "PASS"|"FAIL", confidence: 0.87, violations: [] }  │
└──────────────────────────────────────────────────────────────────┘
```

## Key Files Reference

| File | Purpose | When to Modify |
|------|---------|----------------|
| `modules/api.py` | FastAPI endpoints | Adding/changing REST routes |
| `modules/tribunal.py` | Multi-judge consensus engine | Changing voting logic |
| `modules/parser.py` | Constitution → Invariants | Parsing rule changes |
| `modules/schemas.py` | Pydantic models | Adding new data structures |
| `modules/judge_engine.py` | Individual judge logic | Prompt engineering |
| `modules/prompt_synthesizer.py` | Fix recommendations | AI suggestion logic |
| `config.yaml` | Runtime configuration | Changing judges, thresholds |
| `.env` | API keys and secrets | Adding new providers |

## Domain Vocabulary

- **Constitution**: Natural language specification document with rules to verify
- **Invariant**: Single parsed rule extracted from constitution
- **Tribunal**: Panel of 3+ LLM judges voting on code compliance
- **Verdict**: Consensus result (PASS/FAIL/INCONCLUSIVE) with confidence score
- **Run**: Single execution of the CVA pipeline with a run_id for tracking
- **Quorum**: Minimum number of agreeing judges required for consensus

## Common Tasks

### Adding a New API Endpoint

1. Define request/response schemas in `modules/schemas.py`:
```python
class MyNewRequest(BaseModel):
    """Description of what this request does."""
    field: str = Field(..., description="What this field contains")
```

2. Add the route in `modules/api.py`:
```python
@app.post("/my-endpoint", response_model=MyNewResponse)
async def my_endpoint(request: MyNewRequest) -> MyNewResponse:
    """Clear docstring explaining the endpoint."""
    # Implementation
```

3. Add test in `tests/test_api_*.py`:
```python
async def test_my_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/my-endpoint", json={...})
        assert response.status_code == 200
```

### Modifying Judge Behavior

1. Judge configuration is in `config.yaml`:
```yaml
judges:
  - model: gpt-4o
    provider: openai
    weight: 1.0
  - model: claude-sonnet
    provider: anthropic
    weight: 1.0
```

2. Judge prompt templates are in `modules/judge_engine.py`

3. Consensus logic is in `modules/tribunal.py:run_adjudication()`

### Adding a New LLM Provider

1. Add provider adapter in `modules/provider_adapter.py`
2. Add API key to `.env` (e.g., `NEW_PROVIDER_API_KEY=...`)
3. Register in `modules/key_manager.py`
4. Add to `config.yaml` judges list

## Code Style Guidelines

1. **Type hints** on all public functions
2. **Docstrings** in Google format with Args, Returns, Raises, Example
3. **Async** for all I/O operations (API calls, file reads)
4. **Pydantic** for all API schemas (not raw dicts)
5. **Loguru** for logging (not print statements)

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_tribunal.py -v

# Run with coverage
pytest tests/ --cov=modules --cov-report=html
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT judges |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude judges |
| `GOOGLE_API_KEY` | Optional | Google API key for Gemini judges |
| `PORT` | No | Server port (default: 8001) |
| `CVA_PRODUCTION` | No | Set to "true" for production mode |

## Deployment

- **Local**: `python -m uvicorn modules.api:app --port 8001`
- **Railway**: Deployed via `railway.json` configuration
- **Docker**: `docker build -t cva . && docker run -p 8001:8001 cva`

## Related Documentation

- [API Reference](./docs/API_REFERENCE.md) - Full endpoint documentation
- [AI-Friendly Architecture](./docs/AI_FRIENDLY_ARCHITECTURE.md) - Extension integration guide
- [VS Code Extension Advisory](./VSCODE_EXTENSION_ADVISORY.md) - Extension development plan

---

*Last updated: December 18, 2025*
