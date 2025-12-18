# CVA - AI Code Verifier

> Verify your code against constitutional specifications using a tribunal of AI judges

[![VS Code Marketplace](https://img.shields.io/badge/VS%20Code-Marketplace-blue)](https://marketplace.visualstudio.com/items?itemName=dysruption.cva-verifier)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

CVA (Consensus Verifier Agent) brings AI-powered code verification directly into VS Code and Cursor. Instead of relying on a single AI to check your code, CVA uses a **tribunal of 3+ AI judges** that vote on code compliance, achieving higher accuracy through consensus.

![CVA Demo](media/demo.gif)

## Features

### 🔍 Real-Time File Watching
- Automatically detects file changes as you code
- Smart debouncing prevents excessive verification during rapid edits
- Bulk operation detection for AI agent workflows (Cursor, Copilot, etc.)

### ⚖️ AI Tribunal Verification
- Multiple AI judges evaluate your code
- Consensus-based verdicts (PASS/FAIL/INCONCLUSIVE)
- Confidence scores based on judge agreement

### 📊 Rich IDE Integration
- **Sidebar Panel**: View verdicts, violations, and recommendations
- **Inline Diagnostics**: Squiggly lines showing violations in the editor
- **Status Bar**: Real-time verification status indicator
- **Problems Panel**: All violations in one place

### 🔧 Configurable
- Custom debounce timing
- Flexible file watch patterns
- Support for custom constitution files
- Configurable backend settings

## Installation

### From VS Code Marketplace
1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X)
3. Search for "CVA Verifier"
4. Click Install

### From VSIX
1. Download the `.vsix` file from releases
2. In VS Code, go to Extensions
3. Click the `...` menu → "Install from VSIX..."
4. Select the downloaded file

## Requirements

- **VS Code** 1.85.0 or later
- **Python** 3.10 or later
- **CVA Backend** (dysruption_cva) installed

## Quick Start

1. **Install the extension**
2. **Open a workspace** containing your code
3. **Create a constitution file** (`spec.txt` in your workspace root):
   ```
   # My Project Rules
   
   ## Code Quality
   - All functions must have docstrings
   - No unused imports
   
   ## Security
   - No hardcoded credentials
   - Input validation required
   ```
4. **Save a file** - verification starts automatically!

## Commands

| Command | Shortcut | Description |
|---------|----------|-------------|
| `CVA: Verify Workspace` | `Ctrl+Shift+V` | Verify all files in workspace |
| `CVA: Verify Current File` | `Ctrl+Alt+V` | Verify the active file only |
| `CVA: Start Backend` | - | Start the CVA backend server |
| `CVA: Stop Backend` | - | Stop the CVA backend server |
| `CVA: Restart Backend` | - | Restart the backend |
| `CVA: Show Output` | - | Open the CVA output channel |
| `CVA: Clear Diagnostics` | - | Clear all CVA diagnostics |
| `CVA: Open Backend Docs` | - | Open API documentation |

## Configuration

Configure CVA in your VS Code settings (`settings.json`):

```json
{
  // Enable/disable the extension
  "cva.enabled": true,
  
  // Debounce time in milliseconds (wait after last change)
  "cva.debounceMs": 3000,
  
  // Backend server port
  "cva.backendPort": 8001,
  
  // Auto-start backend when extension activates
  "cva.autoStartBackend": true,
  
  // Path to Python interpreter
  "cva.pythonPath": "python",
  
  // Path to CVA backend (leave empty for auto-detect)
  "cva.cvaBackendPath": "",
  
  // Path to constitution file
  "cva.constitutionPath": "spec.txt",
  
  // File patterns to watch
  "cva.watchPatterns": [
    "**/*.py",
    "**/*.js",
    "**/*.ts"
  ],
  
  // Patterns to ignore
  "cva.ignorePatterns": [
    "**/node_modules/**",
    "**/.git/**"
  ],
  
  // Show inline diagnostic hints
  "cva.showInlineHints": true,
  
  // Auto-verify when files are saved
  "cva.autoVerifyOnSave": true
}
```

## Constitution Files

CVA uses natural language rules (a "constitution") to verify code. Create a `spec.txt` file in your workspace:

```
# Project Constitution

## Documentation
- All public functions must have docstrings
- README must be kept up to date

## Code Quality
- No unused variables
- Maximum function length: 50 lines
- Prefer composition over inheritance

## Security
- Never commit secrets or API keys
- Validate all user input
- Use parameterized queries for database access

## Testing
- All public APIs must have tests
- Test coverage must be > 80%
```

The extension auto-detects these constitution files:
- `spec.txt`
- `.cva/spec.txt`
- `cva.spec.txt`
- `.cva.yaml`
- `constitution.txt`

## Understanding Verdicts

### Verdict Types
- **PASS**: Code complies with all rules
- **FAIL**: One or more violations detected
- **INCONCLUSIVE**: Judges couldn't reach consensus

### Confidence Score
The confidence score (0-100%) indicates how strongly the tribunal agrees:
- **90-100%**: Strong consensus
- **70-89%**: Moderate consensus
- **50-69%**: Weak consensus (consider review)
- **<50%**: Very low confidence

### Violations
Each violation includes:
- **File and line number**: Click to navigate
- **Invariant**: Which rule was violated
- **Message**: Explanation of the issue
- **Suggestion**: AI-generated fix recommendation

## Troubleshooting

### Backend won't start
1. Check Python is installed: `python --version`
2. Verify CVA backend path is correct
3. Check the output channel for errors: `CVA: Show Output`

### No verification happening
1. Check `cva.enabled` is `true`
2. Verify files match `cva.watchPatterns`
3. Check files aren't matched by `cva.ignorePatterns`

### WebSocket disconnections
The extension auto-reconnects with exponential backoff. If issues persist:
1. Check backend is still running
2. Verify port 8001 is accessible
3. Restart the backend: `CVA: Restart Backend`

## Development

### Building from Source
```bash
# Clone repository
git clone https://github.com/dysruption/cva-extension.git
cd cva-extension

# Install dependencies
npm install

# Compile
npm run compile

# Run tests
npm test

# Package extension
npm run package
```

### Debug in VS Code
1. Open the extension folder in VS Code
2. Press F5 to launch Extension Development Host
3. Test the extension in the new window

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) first.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/dysruption/cva-extension/issues)
- **Discussions**: [GitHub Discussions](https://github.com/dysruption/cva-extension/discussions)

---

Made with ❤️ by [Dysruption](https://github.com/dysruption)
