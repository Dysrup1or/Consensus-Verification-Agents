# Dysruption Consensus Verifier Agent (CVA) v1.1

A multi-model AI tribunal for automated code verification against specifications.

## Overview

The Dysruption CVA is a Python-based system that:

1. **Watches** your codebase for changes (or runs on-demand)
2. **Extracts** requirements from a specification file using AI
3. **Adjudicates** code quality using a tribunal of 3 LLM judges:
   - **Claude 4 Sonnet**: Architecture, design patterns, and logic evaluation
   - **DeepSeek V3**: Security vulnerabilities and efficiency analysis (Veto Authority)
   - **Gemini 2.5 Pro**: Spec alignment and user intent verification
4. **Generates** detailed reports with verdicts, scores, and diff-based fix suggestions

## v1.1 Updates

### New Features
- 🆕 **New Models**: Claude 4 Sonnet, DeepSeek V3, Gemini 2.5 Pro, GPT-4o-mini
- 📝 **Enhanced Prompts**: Rubric-based scoring with few-shot examples
- 🔧 **Diff-Based Remediation**: GPT-4o-mini generates unified diff patches
- 🔒 **Improved Security Analysis**: Detailed vulnerability checklists
- 📊 **Better Scoring**: 1-10 rubric with clear criteria for each level

### Backend API (NEW)
- 🚀 **FastAPI Backend**: REST endpoints + WebSocket for real-time streaming
- 🚫 **Veto Protocol**: Security judge FAIL with >80% confidence = final FAIL
- ⛔ **Fail-Fast**: Critical pylint/bandit issues abort pipeline immediately
- 📋 **Category Coverage**: Enforced Security, Functionality, Style categories
- 🕒 **Smart Debounce**: 3-second debounce that resets on each file save

## Features

- ⚖️ Multi-model consensus voting (2/3 majority required)
- 🚫 Security Veto Protocol (>80% confidence FAIL = final FAIL)
- ⛔ Fail-fast on critical static analysis issues
- 🔍 Static analysis via pylint and bandit (pre-LLM screening)
- 📊 Color-coded REPORT.md with detailed explanations
- 🔄 CI/CD compatible JSON output (verdict.json)
- 👁️ Watch mode with smart 3-second debounce
- 🔧 AI-powered remediation with unified diff output
- 🌐 Git repository support (clone and verify)
- 🔐 Configurable LLM selection and thresholds
- 🚀 FastAPI REST + WebSocket API

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager

### Install Dependencies

```bash
# Clone or create the project directory
cd dysruption_cva

# Install required packages
pip install -r requirements.txt

# Or install manually
pip install watchdog litellm loguru pylint bandit gitpython pyyaml requests \
            pydantic fastapi uvicorn websockets httpx
```

### Set Environment Variables

The CVA requires API keys for the LLM providers. Create a `.env` file or set them directly:

```bash
# Windows (PowerShell)
$env:GOOGLE_API_KEY = "your-google-key"          # Gemini (extraction + user proxy)
$env:ANTHROPIC_API_KEY = "your-anthropic-key"    # Claude (architect)
$env:DEEPSEEK_API_KEY = "your-deepseek-key"      # DeepSeek (security)
$env:OPENAI_API_KEY = "your-openai-key"          # GPT-4o-mini (remediation)

# Linux/macOS
export GOOGLE_API_KEY="your-google-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
export DEEPSEEK_API_KEY="your-deepseek-key"
export OPENAI_API_KEY="your-openai-key"
```

**Note**: At minimum, you need `GOOGLE_API_KEY` (for Gemini extraction) and one of the judge API keys.

## Usage

### CLI Usage

```bash
# Verify current directory
python cva.py --dir .

# Verify a specific project
python cva.py --dir ./my_project

# Use custom spec file
python cva.py --dir ./my_project --spec requirements.txt

# Watch for changes (re-verifies after 3s of inactivity)
python cva.py --dir ./my_project --watch

# Clone and verify a GitHub repository
python cva.py --git https://github.com/user/repo
```

### FastAPI Backend (NEW)

```bash
# Start the API server
uvicorn modules.api:app --host 0.0.0.0 --port 8001 --reload

# Or run directly
python -m modules.api
```

#### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/run` | POST | Start a verification run |
| `/status/{run_id}` | GET | Get run status and progress |
| `/verdict/{run_id}` | GET | Get final verdict (when complete) |
| `/runs` | GET | List all verification runs |
| `/run/{run_id}` | DELETE | Cancel a running verification |

#### WebSocket

Connect to `/ws/{run_id}` for real-time status streaming:

```javascript
const ws = new WebSocket('ws://localhost:8001/ws/abc123');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`[${data.type}] ${data.data.message}`);
    // Types: 'status', 'progress', 'verdict', 'error'
};
```

#### Example API Usage

```bash
# Start verification
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{"target_dir": "./my_project", "generate_patches": true}'

# Response: {"run_id": "abc123", "status": "scanning", "message": "..."}

# Check status
curl http://localhost:8001/status/abc123

# Get verdict (when complete)
curl http://localhost:8001/verdict/abc123
```

When running with `CVA_PRODUCTION=true`, the API is locked down behind an auth token.
At minimum, all run-control and run-data endpoints require the token: `/upload`, `/run`, `/status/{run_id}`, `/verdict/{run_id}`, `/prompt/{run_id}`, `/runs`, and `/run/{run_id}` (cancel).
Provide it as either `Authorization: Bearer <token>` or `X-API-Token: <token>`.

In production, the WebSocket endpoint requires a token via query param (browser WebSocket APIs cannot set auth headers):
`ws://localhost:8001/ws/<run_id>?token=<token>`

### Options

```
usage: cva.py [-h] [--dir DIR] [--git GIT] [--spec SPEC] [--config CONFIG]
              [--watch] [--verbose] [--log-file LOG_FILE] [--check-env]
              [--version]

Options:
  --dir, -d       Target directory to verify (default: .)
  --git, -g       Git repository URL to clone and verify
  --spec, -s      Path to specification file (default: spec.txt)
  --config, -c    Path to configuration file (default: config.yaml)
  --watch, -w     Enable watch mode
  --verbose, -v   Enable debug output
  --log-file      Path to log file
  --check-env     Check API keys and exit
  --version       Show version
```

## Configuration

Edit `config.yaml` to customize:

```yaml
# LLM Models (v1.1)
llms:
  extraction:
    model: "google/gemini-1.5-flash-latest"
  architect:
    model: "anthropic/claude-4-sonnet-20250514"
  security:
    model: "deepseek/deepseek-chat"
  user_proxy:
    model: "google/gemini-2.5-pro-exp-03-25"
  remediation:
    model: "openai/gpt-4o-mini"

# Thresholds
thresholds:
  pass_score: 7          # Minimum score (1-10)
  consensus_ratio: 0.67  # 2/3 majority
  min_per_category: 2    # Minimum invariants per category

# Static Analysis (Fail-Fast)
static_analysis:
  enabled: true
  fail_fast: true        # Abort on critical issues
  pylint:
    enabled: true
  bandit:
    enabled: true

# Enable remediation suggestions
remediation:
  enabled: true
```

## Veto Protocol (v1.1)

The Security Judge has **veto authority**. If the Security Judge:
1. Votes **FAIL** on a criterion
2. With **confidence > 80%**

Then the **final verdict is FAIL**, regardless of other judges.

This ensures critical security issues cannot be overridden by majority vote.

```
Example Scenario:
- Architect Judge: PASS (8/10)
- Security Judge: FAIL (3/10, 95% confidence) ← VETO
- User Proxy Judge: PASS (7/10)

Result: VETO (Security issues detected with high confidence)
```

## Fail-Fast Static Analysis (v1.1)

If static analysis (pylint/bandit) finds **critical issues**, the pipeline aborts immediately:

- **Pylint**: `error` or `fatal` type issues
- **Bandit**: `HIGH` severity issues

This saves API costs by not calling LLM judges on fundamentally broken code.

## Category Coverage Enforcement (v1.1)

The parser now enforces that extracted invariants cover all three required categories:

1. **Security** (min 2 requirements): Auth, validation, encryption, secrets
2. **Functionality** (min 3 requirements): Features, logic, data handling
3. **Style** (min 2 requirements): Formatting, types, docs, linting

If a category is missing or sparse, the parser **re-prompts specifically** for that category.

## Creating a Specification File

Create a `spec.txt` file with your project requirements:

```txt
# Project Specification: My App

## Technical Requirements
1. Use Python 3.10+
2. Implement RESTful API design
3. Use environment variables for secrets
4. Follow PEP 8 style guidelines

## Functional Requirements
1. Users can create and manage items
2. All inputs must be validated
3. Errors return proper HTTP status codes
4. API should respond within 200ms
```

The CVA will extract these as verifiable invariants.

## Output Files

After verification, the following files are generated:

### REPORT.md

Human-readable report with:
- Overall verdict (PASS/FAIL/PARTIAL)
- Per-criterion breakdown with scores
- Static analysis issues
- Suggested fixes (if enabled)

### verdict.json

Machine-readable output for CI/CD:

```json
{
  "overall_verdict": "PASS",
  "overall_score": 8.5,
  "passed_criteria": 15,
  "total_criteria": 18,
  "ci_cd": {
    "success": true,
    "exit_code": 0
  }
}
```

### criteria.json

Extracted requirements from spec.txt:

```json
{
  "technical": [
    {"id": 1, "desc": "Use Python 3.10+"}
  ],
  "functional": [
    {"id": 1, "desc": "Users can create items"}
  ]
}
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: CVA Verification

on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          
      - name: Install CVA
        run: pip install watchdog litellm loguru pylint bandit pyyaml requests
        
      - name: Run Verification
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
        run: python cva.py --dir . --spec spec.txt
        
      - name: Upload Report
        uses: actions/upload-artifact@v3
        with:
          name: cva-report
          path: |
            REPORT.md
            verdict.json
```

### Check Verdict in Scripts

```bash
# Bash
if [ $(jq '.ci_cd.success' verdict.json) == "true" ]; then
  echo "Verification passed!"
else
  echo "Verification failed!"
  exit 1
fi
```

```powershell
# PowerShell
$verdict = Get-Content verdict.json | ConvertFrom-Json
if ($verdict.ci_cd.success) {
    Write-Host "Verification passed!"
} else {
    Write-Host "Verification failed!"
    exit 1
}
```

## Project Structure

```
dysruption_cva/
├── cva.py                  # Main CLI entry point
├── config.yaml             # Configuration file
├── spec.txt                # Sample specification
├── README.md               # This file
├── requirements.txt        # Python dependencies
├── modules/
│   ├── __init__.py         # Module exports
│   ├── schemas.py          # Pydantic models (v1.1)
│   ├── watcher.py          # Directory watcher (Module A)
│   ├── watcher_v2.py       # Smart debounce watcher (v1.1)
│   ├── parser.py           # Constitution parser (Module B)
│   ├── tribunal.py         # Multi-model tribunal (Module C)
│   ├── api.py              # FastAPI backend (v1.1)
│   └── sandbox_runner.py   # Code execution stub (v1.1)
├── tests/
│   ├── __init__.py
│   ├── test_watcher.py
│   ├── test_parser.py
│   ├── test_tribunal.py
│   └── mocks/              # Deterministic test responses (v1.1)
│       ├── __init__.py
│       ├── extraction_response.json
│       ├── judge_verdicts.json
│       └── remediation_response.json
└── sample_project/         # Sample project for testing
    ├── app.py
    └── models.py
```

## How It Works

### 1. File Ingestion (watcher.py)

- Monitors directory for changes using watchdog
- Debounces events (15 seconds of inactivity)
- Builds file tree JSON with code contents
- Auto-detects language (Python/JavaScript)
- Supports git clone for remote repos

### 2. Requirement Extraction (parser.py)

- Reads spec.txt specification file
- Uses Gemini 1.5 Flash to extract invariants
- Outputs structured JSON with technical/functional requirements
- Re-prompts if too few requirements extracted (<5)

### 3. Tribunal Adjudication (tribunal.py)

- Pre-runs static analysis (pylint, bandit)
- Routes code to 3 LLM judges with rubric-based prompts:
  - **Architect (Claude 4 Sonnet)**: Logic, design patterns, and architecture
  - **Security (DeepSeek V3)**: Vulnerabilities and efficiency
  - **User Proxy (Gemini 2.5 Pro)**: Spec alignment and user intent
- Computes weighted consensus (2/3 majority)
- Generates REPORT.md and verdict.json
- GPT-4o-mini generates unified diff remediation patches

## Troubleshooting

### "No code files found"
- Check that your directory contains `.py` or `.js` files
- Check `config.yaml` for supported extensions
- Ensure files aren't in ignored directories

### "API key not set"
- Run `python cva.py --check-env` to see which keys are missing
- Set the required environment variables

### "LLM call failed"
- Check API key validity
- Verify internet connection
- The system will retry 3 times with backoff
- Falls back to Groq if primary model fails

### Large codebase taking too long
- Increase `chunk_size_tokens` in config
- Reduce number of criteria in spec.txt
- Use `--verbose` to see progress

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Run `pytest tests/`
5. Submit a pull request

## License

MIT License - See LICENSE file

## Credits

- **Author**: Dysruption
- **Version**: 1.1
- **LLM Providers**: Anthropic (Claude), Google (Gemini), DeepSeek, OpenAI (GPT-4o-mini)
