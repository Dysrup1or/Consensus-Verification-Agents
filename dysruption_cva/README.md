# Dysruption Consensus Verifier Agent (CVA) v1.0

A multi-model AI tribunal for automated code verification against specifications.

## Overview

The Dysruption CVA is a Python-based system that:

1. **Watches** your codebase for changes (or runs on-demand)
2. **Extracts** requirements from a specification file using AI
3. **Adjudicates** code quality using a tribunal of 3 LLM judges:
   - **Claude 3.5 Sonnet**: Architecture and logic evaluation
   - **Llama 3 (via Groq)**: Security and efficiency scanning
   - **Gemini 1.5 Pro**: Spec alignment and user intent verification
4. **Generates** detailed reports with verdicts, scores, and fix suggestions

## Features

- ⚖️ Multi-model consensus voting (2/3 majority required)
- 🔍 Static analysis via pylint and bandit (pre-LLM screening)
- 📊 Color-coded REPORT.md with detailed explanations
- 🔄 CI/CD compatible JSON output (verdict.json)
- 👁️ Watch mode with 15-second debounce
- 🔧 Optional AI-powered remediation suggestions
- 🌐 Git repository support (clone and verify)
- 🔐 Configurable LLM selection and thresholds

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager

### Install Dependencies

```bash
# Clone or create the project directory
cd dysruption_cva

# Install required packages
pip install watchdog litellm loguru pylint bandit gitpython pyyaml requests

# Or install from requirements.txt
pip install -r requirements.txt
```

### Set Environment Variables

The CVA requires API keys for the LLM providers:

```bash
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "your-anthropic-key"
$env:GOOGLE_API_KEY = "your-google-key"
$env:GROQ_API_KEY = "your-groq-key"

# Linux/macOS
export ANTHROPIC_API_KEY="your-anthropic-key"
export GOOGLE_API_KEY="your-google-key"
export GROQ_API_KEY="your-groq-key"
```

**Note**: At minimum, you need `GOOGLE_API_KEY` (for Gemini extraction) and one of the judge API keys.

## Usage

### Basic Usage

```bash
# Verify current directory
python cva.py --dir .

# Verify a specific project
python cva.py --dir ./my_project

# Use custom spec file
python cva.py --dir ./my_project --spec requirements.txt
```

### Watch Mode

```bash
# Watch for changes (re-verifies after 15s of inactivity)
python cva.py --dir ./my_project --watch
```

### Git Repository

```bash
# Clone and verify a GitHub repository
python cva.py --git https://github.com/user/repo
```

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
# LLM Models
llms:
  architect:
    model: "claude-3-5-sonnet-20241022"
  security:
    model: "groq/llama-3.1-70b-versatile"
  user_proxy:
    model: "gemini/gemini-1.5-pro"
  extraction:
    model: "gemini/gemini-1.5-flash"

# Thresholds
thresholds:
  pass_score: 7          # Minimum score (1-10)
  consensus_ratio: 0.67  # 2/3 majority

# Enable remediation suggestions
remediation:
  enabled: true
```

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
├── cva.py              # Main CLI entry point
├── config.yaml         # Configuration file
├── spec.txt            # Sample specification
├── README.md           # This file
├── modules/
│   ├── __init__.py
│   ├── watcher.py      # Directory watcher (Module A)
│   ├── parser.py       # Constitution parser (Module B)
│   └── tribunal.py     # Multi-model tribunal (Module C)
├── tests/
│   ├── __init__.py
│   ├── test_watcher.py
│   ├── test_parser.py
│   └── test_tribunal.py
└── sample_project/     # Sample project for testing
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
- Routes code to 3 LLM judges:
  - **Architect (Claude)**: Logic and architecture
  - **Security (Llama)**: Vulnerabilities and efficiency
  - **User Proxy (Gemini)**: Spec alignment
- Computes weighted consensus (2/3 majority)
- Generates REPORT.md and verdict.json
- Optional: AI remediation suggestions

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
- **Version**: 1.0
- **LLM Providers**: Anthropic, Google, Groq
