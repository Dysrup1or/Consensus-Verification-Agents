# GitHub Code Scanning Integration with CVA SARIF Export

This guide explains how to integrate CVA's SARIF export with GitHub Code Scanning to display verdict results directly in your pull requests.

## Overview

CVA automatically generates [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) (Static Analysis Results Interchange Format) output when running evaluations. This format is natively supported by GitHub Code Scanning, enabling:

- **In-PR Annotations**: CVA verdicts appear as code annotations in pull requests
- **Security Tab Integration**: Results are visible in the repository's Security > Code scanning tab
- **Trend Analysis**: Track CVA verdict history over time
- **Status Checks**: Block merges when CVA detects critical issues

## Quick Start

### 1. Basic GitHub Action

Create `.github/workflows/cva.yml`:

```yaml
name: CVA Code Verification

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

jobs:
  cva-analysis:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write  # Required for SARIF upload
      
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for diff analysis
          
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install CVA
        run: |
          pip install -r dysruption_cva/requirements.txt
          
      - name: Run CVA Analysis
        run: |
          cd dysruption_cva
          python cva.py analyze --output sarif
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          
      - name: Upload SARIF to GitHub
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: dysruption_cva/verdict.sarif
          category: cva-verification
```

### 2. Required Secrets

Add these secrets to your repository (Settings > Secrets > Actions):

| Secret | Description | Required |
|--------|-------------|----------|
| `ANTHROPIC_API_KEY` | Claude API key for Architect Judge | Yes |
| `DEEPSEEK_API_KEY` | DeepSeek API key for Security Judge | Yes |
| `GEMINI_API_KEY` | Gemini API key for User Proxy Judge | Yes |
| `OPENAI_API_KEY` | OpenAI API key for Remediation | Optional |

### 3. Enable Code Scanning

1. Go to your repository on GitHub
2. Navigate to **Settings > Code security and analysis**
3. Enable **Code scanning** (may require GitHub Advanced Security for private repos)

## Advanced Configuration

### CVA Config for SARIF

Update `config.yaml` to customize SARIF output:

```yaml
output:
  # SARIF Configuration
  sarif_enabled: true
  sarif_file: "verdict.sarif"
  
  # Include passing criteria in SARIF (default: false)
  # Set to true for full visibility, false to only show issues
  sarif_include_passing: false
  
  # Other outputs
  verdict_file: "verdict.json"
  report_file: "REPORT.md"
```

### Conditional SARIF Upload

Only upload SARIF when the workflow succeeds or has relevant findings:

```yaml
      - name: Upload SARIF to GitHub
        uses: github/codeql-action/upload-sarif@v3
        if: always()  # Upload even if CVA finds issues
        with:
          sarif_file: dysruption_cva/verdict.sarif
          category: cva-verification
          wait-for-processing: true
```

### Multiple Categories

If running CVA on multiple projects/components:

```yaml
      - name: Upload Frontend SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: frontend/verdict.sarif
          category: cva-frontend
          
      - name: Upload Backend SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: backend/verdict.sarif
          category: cva-backend
```

### Required Status Check

To block merges on CVA failures:

1. Go to **Settings > Branches > Branch protection rules**
2. Edit or create a rule for `main`
3. Enable **Require status checks to pass before merging**
4. Add `cva-analysis` (or your job name) as a required check

## SARIF Output Structure

CVA generates SARIF with the following structure:

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "Dysruption CVA",
        "version": "1.2",
        "rules": [
          {
            "id": "S1",
            "name": "CVA-S1",
            "shortDescription": { "text": "Security criterion description" },
            "defaultConfiguration": { "level": "error" }
          }
        ]
      }
    },
    "results": [
      {
        "ruleId": "S1",
        "level": "error",
        "kind": "fail",
        "message": {
          "text": "**Security criterion description**\n\nScore: 3.5/10\nConsensus: 100%\n\n🚫 **VETO**: Security Judge veto triggered"
        },
        "locations": [{
          "physicalLocation": {
            "artifactLocation": { "uri": "modules/auth.py" },
            "region": { "startLine": 1 }
          }
        }]
      }
    ],
    "invocations": [{
      "executionSuccessful": false,
      "properties": {
        "overall_verdict": "VETO",
        "overall_score": 5.5,
        "veto_triggered": true
      }
    }]
  }]
}
```

### Severity Mapping

| CVA Criterion Type | SARIF Level | GitHub Display |
|-------------------|-------------|----------------|
| Security | `error` | 🔴 Error |
| Functionality | `warning` | 🟡 Warning |
| Style | `note` | ℹ️ Note |

### Verdict Mapping

| CVA Verdict | SARIF Kind | Description |
|-------------|------------|-------------|
| PASS | `pass` | Criterion satisfied |
| FAIL | `fail` | Criterion not met |
| VETO | `fail` | Security veto triggered |
| PARTIAL | `review` | Needs review |

## Troubleshooting

### SARIF Upload Fails

**Error**: "SARIF file not found"

```yaml
      - name: Debug SARIF
        run: |
          ls -la dysruption_cva/
          cat dysruption_cva/verdict.sarif | head -50
```

**Solution**: Ensure CVA runs successfully and generates `verdict.sarif`.

### No Results in Code Scanning

**Cause**: All criteria passed (passing results excluded by default).

**Solution**: Set `sarif_include_passing: true` in config, or check that there are actual issues.

### "This repository does not have GitHub Advanced Security enabled"

**Solution**: For private repositories, enable GitHub Advanced Security:
1. Go to **Settings > Code security and analysis**
2. Enable **GitHub Advanced Security**

(Free for public repositories)

### API Rate Limits

**Error**: Rate limit errors from LLM providers

**Solution**: Add retry delays in your workflow:

```yaml
      - name: Run CVA with retry
        uses: nick-fields/retry@v3
        with:
          timeout_minutes: 15
          max_attempts: 3
          retry_wait_seconds: 60
          command: |
            cd dysruption_cva
            python cva.py analyze --output sarif
```

## Example PR Annotations

When CVA finds issues, they appear directly in the PR diff:

```
┌─────────────────────────────────────────────────────────────────┐
│ 🔴 CVA-S2: No hardcoded secrets in codebase                    │
│                                                                 │
│ Score: 3.0/10 | Consensus: 100%                                │
│                                                                 │
│ 🚫 VETO: Security Judge detected critical vulnerabilities       │
│                                                                 │
│ **Judge Scores:**                                               │
│ - Architect Judge: ❌ 4/10                                       │
│ - Security Judge: ❌ 2/10                                        │
│ - User Proxy Judge: ❌ 3/10                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Complete Production Workflow

Here's a full production-ready workflow with caching, conditional uploads, and notifications:

```yaml
name: CVA Code Verification

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

concurrency:
  group: cva-${{ github.ref }}
  cancel-in-progress: true

jobs:
  cva-analysis:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: read
      security-events: write
      pull-requests: write
      
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: dysruption_cva/requirements.txt
          
      - name: Install dependencies
        run: |
          pip install -r dysruption_cva/requirements.txt
          pip install pylint bandit  # Static analysis tools
          
      - name: Run CVA Analysis
        id: cva
        run: |
          cd dysruption_cva
          python cva.py analyze --output sarif,json,markdown
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        continue-on-error: true
          
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: dysruption_cva/verdict.sarif
          category: cva-verification
          wait-for-processing: true
          
      - name: Comment on PR
        if: github.event_name == 'pull_request' && always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('dysruption_cva/REPORT.md', 'utf8');
            const verdict = JSON.parse(fs.readFileSync('dysruption_cva/verdict.json', 'utf8'));
            
            const emoji = verdict.overall_verdict === 'PASS' ? '✅' : 
                          verdict.veto_triggered ? '🚫' : '❌';
            
            const body = `## ${emoji} CVA Verification: ${verdict.overall_verdict}
            
            **Score**: ${verdict.overall_score.toFixed(1)}/10
            **Criteria**: ${verdict.passed_criteria}/${verdict.total_criteria} passed
            
            <details>
            <summary>📋 Full Report</summary>
            
            ${report}
            
            </details>`;
            
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            });
            
      - name: Fail on VETO
        if: steps.cva.outcome == 'failure'
        run: exit 1
```

## Next Steps

- [CVA Configuration Guide](./CONFIG.md)
- [Custom Criteria Definition](./CRITERIA.md)
- [Remediation Patches](./REMEDIATION.md)
