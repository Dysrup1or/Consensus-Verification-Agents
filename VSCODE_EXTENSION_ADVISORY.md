# VS Code / Cursor Extension Advisory
## CVA (Consensus Verifier Agent) as an IDE Extension

**Document Version:** 1.0  
**Date:** December 18, 2025  
**Purpose:** Technical advisory on transforming CVA into a VS Code/Cursor extension

---

## Executive Summary

A VS Code extension would provide **native file change detection** through VS Code's built-in APIs, solving the core question of "how does the program detect when a change has been made?" This approach is **ideal for AI agent workflows** where many files are created/modified rapidly.

**Estimated Effort:** 3-4 weeks for MVP, 6-8 weeks for production-ready

---

## 1. Why an Extension is the Right Approach

### Current Limitations

| Current Approach | Limitation |
|------------------|------------|
| Browser-based GitHub import | Requires internet, GitHub account |
| Local file picker (File System Access API) | Browser security restrictions, no real-time watching |
| Standalone watchdog watcher | Requires separate terminal process, no IDE integration |

### Extension Advantages

| Advantage | Description |
|-----------|-------------|
| **Native File Detection** | VS Code APIs fire events on every save, create, delete |
| **Agent Compatibility** | Detects changes from Cursor AI, GitHub Copilot, Aider, etc. |
| **No External Process** | Extension runs within the IDE, no separate watcher needed |
| **Rich UI Integration** | Sidebar panels, status bar, inline diagnostics, CodeLens |
| **Cross-Platform** | Works on Windows, macOS, Linux identically |
| **Cursor Compatibility** | Cursor is a VS Code fork - same extension API works |

---

## 2. How VS Code Detects File Changes

VS Code provides multiple APIs for change detection:

### 2.1 Document-Level Events (Editor Changes)

```typescript
// Fires on EVERY keystroke/change in an open document
vscode.workspace.onDidChangeTextDocument((event) => {
  const uri = event.document.uri;
  const changes = event.contentChanges; // What changed
  // Great for real-time validation
});

// Fires when user saves a document
vscode.workspace.onDidSaveTextDocument((document) => {
  const filePath = document.uri.fsPath;
  // Trigger CVA verification after save
});

// Fires BEFORE save (can modify content)
vscode.workspace.onWillSaveTextDocument((event) => {
  // Can inject transformations before save
});
```

### 2.2 File System Events (Disk Changes)

```typescript
// Watch for file changes across the workspace
const watcher = vscode.workspace.createFileSystemWatcher(
  '**/*.{py,js,ts,jsx,tsx}', // Pattern
  false, // Don't ignore creates
  false, // Don't ignore changes
  false  // Don't ignore deletes
);

watcher.onDidCreate((uri) => {
  console.log(`File created: ${uri.fsPath}`);
  // ADD to dirty files set
});

watcher.onDidChange((uri) => {
  console.log(`File changed: ${uri.fsPath}`);
  // ADD to dirty files set
});

watcher.onDidDelete((uri) => {
  console.log(`File deleted: ${uri.fsPath}`);
  // REMOVE from tracking
});
```

### 2.3 Workspace Events (Bulk Operations)

```typescript
// Fires when files are created via VS Code (including AI agents)
vscode.workspace.onDidCreateFiles((event) => {
  for (const file of event.files) {
    console.log(`Created: ${file.fsPath}`);
  }
});

// Fires when files are deleted via VS Code
vscode.workspace.onDidDeleteFiles((event) => {
  for (const file of event.files) {
    console.log(`Deleted: ${file.fsPath}`);
  }
});

// Fires when files are renamed/moved
vscode.workspace.onDidRenameFiles((event) => {
  for (const { oldUri, newUri } of event.files) {
    console.log(`Renamed: ${oldUri.fsPath} → ${newUri.fsPath}`);
  }
});
```

---

## 3. Handling AI Agent Bulk Changes

When an AI agent (Cursor, Copilot, Aider, etc.) creates multiple files at once, the extension must handle this gracefully:

### 3.1 Smart Debouncing (Matching Your Current Design)

```typescript
class CVAChangeTracker {
  private dirtyFiles: Set<string> = new Set();
  private debounceTimer: NodeJS.Timeout | null = null;
  private readonly DEBOUNCE_MS = 3000; // Match your 3-second debounce

  addDirtyFile(filePath: string) {
    this.dirtyFiles.add(filePath);
    
    // Reset debounce timer on every change (smart debounce)
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
    
    this.debounceTimer = setTimeout(() => {
      this.triggerVerification();
    }, this.DEBOUNCE_MS);
  }

  private async triggerVerification() {
    const filesToVerify = Array.from(this.dirtyFiles);
    this.dirtyFiles.clear();
    
    // Show progress in VS Code
    await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: `CVA: Verifying ${filesToVerify.length} files...`,
      cancellable: true
    }, async (progress, token) => {
      await this.runCVAVerification(filesToVerify);
    });
  }
}
```

### 3.2 Batch Detection Pattern

```typescript
// Detect if we're in a "bulk change" scenario
class BulkChangeDetector {
  private changeBuffer: string[] = [];
  private bufferStartTime: number = 0;
  private readonly BULK_THRESHOLD = 5; // 5+ files in 500ms = bulk operation
  private readonly BULK_WINDOW_MS = 500;

  recordChange(filePath: string) {
    const now = Date.now();
    
    if (now - this.bufferStartTime > this.BULK_WINDOW_MS) {
      // New batch window
      this.changeBuffer = [filePath];
      this.bufferStartTime = now;
    } else {
      this.changeBuffer.push(filePath);
    }

    if (this.changeBuffer.length >= this.BULK_THRESHOLD) {
      // AI agent is creating many files - extend debounce
      this.extendDebounce();
    }
  }
}
```

---

## 4. Extension Architecture

### 4.1 Option A: Extension with Embedded Backend (Recommended)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VS CODE / CURSOR                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     CVA EXTENSION (TypeScript)                       │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │                                                                      │   │
│  │  ┌──────────────────┐  ┌───────────────────┐  ┌──────────────────┐  │   │
│  │  │ FileWatcher      │  │ ChangeTracker     │  │ UI Components   │  │   │
│  │  │ - onDidSave      │  │ - dirtyFiles Set  │  │ - Sidebar Panel │  │   │
│  │  │ - onDidCreate    │──│ - smartDebounce() │──│ - Status Bar    │  │   │
│  │  │ - onDidDelete    │  │ - batchDetect()   │  │ - Diagnostics   │  │   │
│  │  └──────────────────┘  └─────────┬─────────┘  └──────────────────┘  │   │
│  │                                  │                                   │   │
│  │                                  ▼                                   │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │               EMBEDDED PYTHON RUNTIME                         │  │   │
│  │  │  (python-shell or child_process spawn)                        │  │   │
│  │  │                                                               │  │   │
│  │  │  ┌─────────────┐ ┌──────────────┐ ┌────────────────────────┐ │  │   │
│  │  │  │ Parser      │ │ Tribunal     │ │ Judge Engine           │ │  │   │
│  │  │  │ (existing)  │ │ (existing)   │ │ (existing LLM calls)   │ │  │   │
│  │  │  └─────────────┘ └──────────────┘ └────────────────────────┘ │  │   │
│  │  │                                                               │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Self-contained, no external server required
- User installs extension + Python runtime, done
- Works fully offline (with local LLM)

**Cons:**
- Bundling Python is complex
- Extension size may be large

### 4.2 Option B: Extension + External Backend (Current Architecture)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VS CODE / CURSOR                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     CVA EXTENSION (TypeScript)                       │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  FileWatcher → ChangeTracker → HTTP Client → UI Components          │   │
│  └────────────────────────────────────┬────────────────────────────────┘   │
│                                       │                                     │
│                                       │ HTTP/WebSocket                      │
│                                       ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              CVA BACKEND (FastAPI - Existing)                        │   │
│  │              http://localhost:8001                                   │   │
│  │                                                                      │   │
│  │  /run, /upload, /verdicts, /ws (WebSocket for live updates)         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Minimal changes to existing backend
- Extension is lightweight
- Easier to develop incrementally

**Cons:**
- User must run backend separately (unless auto-started)
- Network dependency (localhost, but still)

### 4.3 Option C: Hybrid (Recommended for Your Case)

Extension **auto-starts** the Python backend as a subprocess:

```typescript
// extension.ts
import { spawn } from 'child_process';

let backendProcess: ChildProcess | null = null;

export async function activate(context: vscode.ExtensionContext) {
  // Auto-start CVA backend
  const pythonPath = await getPythonPath(); // Detect Python
  const cvaPath = context.asAbsolutePath('cva_backend');
  
  backendProcess = spawn(pythonPath, ['-m', 'uvicorn', 'api:app', '--port', '8001'], {
    cwd: cvaPath,
    env: { ...process.env, CVA_PROD: 'false' }
  });

  // Wait for backend to be ready
  await waitForBackend('http://localhost:8001/health');

  // Now set up file watchers...
}

export function deactivate() {
  backendProcess?.kill();
}
```

---

## 5. Key Extension Features

### 5.1 File Change Detection

```typescript
// Smart watcher setup
function setupFileWatchers(context: vscode.ExtensionContext) {
  const tracker = new CVAChangeTracker();

  // Watch code files
  const watcher = vscode.workspace.createFileSystemWatcher(
    '**/*.{py,js,ts,jsx,tsx,pyi}'
  );

  watcher.onDidChange(uri => tracker.addDirtyFile(uri.fsPath));
  watcher.onDidCreate(uri => tracker.addDirtyFile(uri.fsPath));
  watcher.onDidDelete(uri => tracker.removeFile(uri.fsPath));

  // Also listen to save events for immediate feedback
  vscode.workspace.onDidSaveTextDocument(doc => {
    if (isCodeFile(doc.uri)) {
      tracker.addDirtyFile(doc.uri.fsPath);
    }
  });

  context.subscriptions.push(watcher);
}
```

### 5.2 Sidebar Panel (Verification Results)

```typescript
// TreeDataProvider for sidebar
class CVAVerdictTreeProvider implements vscode.TreeDataProvider<VerdictItem> {
  private verdicts: VerdictItem[] = [];
  private _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  updateVerdicts(newVerdicts: Verdict[]) {
    this.verdicts = newVerdicts.map(v => new VerdictItem(v));
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: VerdictItem) {
    return element;
  }

  getChildren() {
    return this.verdicts;
  }
}
```

### 5.3 Inline Diagnostics (Squiggly Lines)

```typescript
const diagnosticCollection = vscode.languages.createDiagnosticCollection('cva');

function showVerdictAsDiagnostic(verdict: Verdict) {
  const uri = vscode.Uri.file(verdict.file_path);
  const range = new vscode.Range(verdict.line - 1, 0, verdict.line - 1, 100);
  
  const diagnostic = new vscode.Diagnostic(
    range,
    `CVA: ${verdict.invariant} - ${verdict.verdict}`,
    verdict.passed ? vscode.DiagnosticSeverity.Information : vscode.DiagnosticSeverity.Warning
  );

  diagnosticCollection.set(uri, [diagnostic]);
}
```

### 5.4 Status Bar Indicator

```typescript
const statusBarItem = vscode.window.createStatusBarItem(
  vscode.StatusBarAlignment.Right,
  100
);

function updateStatusBar(state: 'idle' | 'watching' | 'verifying' | 'passed' | 'failed') {
  const icons = {
    idle: '$(circle-outline)',
    watching: '$(eye)',
    verifying: '$(sync~spin)',
    passed: '$(check)',
    failed: '$(warning)'
  };
  
  statusBarItem.text = `${icons[state]} CVA`;
  statusBarItem.show();
}
```

### 5.5 CodeLens (Inline Actions)

```typescript
class CVACodeLensProvider implements vscode.CodeLensProvider {
  provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
    const lenses: vscode.CodeLens[] = [];
    
    // Add "Verify This Function" lens above each function
    const functionRegex = /^(async\s+)?function\s+(\w+)|^(export\s+)?(const|let)\s+(\w+)\s*=\s*(async\s+)?\(/gm;
    
    let match;
    while ((match = functionRegex.exec(document.getText()))) {
      const line = document.positionAt(match.index).line;
      const range = new vscode.Range(line, 0, line, 0);
      
      lenses.push(new vscode.CodeLens(range, {
        title: '🔍 Verify with CVA',
        command: 'cva.verifyFunction',
        arguments: [document.uri, line]
      }));
    }
    
    return lenses;
  }
}
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Set up VS Code extension scaffold
- [ ] Implement FileSystemWatcher integration
- [ ] Create CVAChangeTracker with smart debounce
- [ ] Basic status bar indicator
- [ ] Command: "CVA: Verify Workspace"

### Phase 2: Backend Integration (Week 2-3)
- [ ] Auto-start Python backend as subprocess
- [ ] HTTP client for /run, /verdicts endpoints
- [ ] WebSocket connection for live updates
- [ ] Health check and error handling

### Phase 3: Rich UI (Week 3-4)
- [ ] Sidebar panel with verdict tree
- [ ] Inline diagnostics (squiggly lines)
- [ ] Quick fix actions (auto-remediation)
- [ ] Progress notifications

### Phase 4: AI Agent Support (Week 4-5)
- [ ] Bulk change detection
- [ ] Extended debounce for agent activity
- [ ] "Agent Mode" toggle in settings
- [ ] Integration tests with Cursor AI

### Phase 5: Polish & Publish (Week 5-6)
- [ ] Configuration settings UI
- [ ] Onboarding walkthrough
- [ ] Extension marketplace assets
- [ ] Documentation

---

## 7. Settings Configuration

```json
// package.json - contributes.configuration
{
  "cva.enabled": {
    "type": "boolean",
    "default": true,
    "description": "Enable CVA file watching and verification"
  },
  "cva.debounceMs": {
    "type": "number",
    "default": 3000,
    "description": "Milliseconds to wait after last change before verification"
  },
  "cva.agentMode": {
    "type": "boolean",
    "default": false,
    "description": "Extended debounce for AI agent bulk operations"
  },
  "cva.constitution": {
    "type": "string",
    "default": "",
    "description": "Path to constitution file or inline rules"
  },
  "cva.backendUrl": {
    "type": "string",
    "default": "http://localhost:8001",
    "description": "CVA backend URL"
  },
  "cva.autoStartBackend": {
    "type": "boolean",
    "default": true,
    "description": "Automatically start CVA backend when extension activates"
  }
}
```

---

## 8. Cursor-Specific Considerations

Cursor is a fork of VS Code with AI features. The CVA extension would work identically with some bonus opportunities:

### 8.1 Cursor AI Integration Points

```typescript
// Detect Cursor's AI-generated changes
// Cursor uses the same VS Code extension API

// When Cursor's AI generates code, it triggers:
// 1. onDidChangeTextDocument (as typing)
// 2. onDidSaveTextDocument (when accepting)
// 3. onDidCreateFiles (for new files)

// The smart debounce naturally handles this!
```

### 8.2 Cursor Composer Detection

```typescript
// Cursor's Composer can create multiple files at once
// Our bulk detection pattern handles this:

function detectCursorComposer(changes: string[]): boolean {
  // If 3+ files change within 500ms, likely Composer
  return changes.length >= 3;
}
```

---

## 9. Comparison: Browser vs Extension

| Feature | Browser (Current) | VS Code Extension |
|---------|-------------------|-------------------|
| File change detection | Manual refresh / File System Access API | Native `onDidSave`, `onDidCreate` |
| Real-time watching | Limited (experimental `FileSystemObserver`) | Full support via `FileSystemWatcher` |
| AI agent compatibility | ❌ Can't detect external changes | ✅ Detects all workspace changes |
| Bulk file creation | Limited handling | Smart debounce + batch detection |
| Offline operation | ✅ (with local upload) | ✅ (embedded or auto-start backend) |
| User experience | Tab switching, manual upload | Integrated sidebar, inline diagnostics |
| Cross-platform | Browser-dependent | Consistent across OS |

---

## 10. Recommendation

**Build the VS Code extension using Option C (Hybrid):**

1. Extension handles all file change detection natively
2. Extension auto-starts the existing FastAPI backend as a subprocess
3. Communication via HTTP + WebSocket for live updates
4. No changes to core CVA logic (parser, tribunal, judge engine)
5. Cursor compatibility comes for free

This approach:
- Solves the "how does it detect changes" problem completely
- Handles AI agent bulk operations gracefully
- Reuses 95% of existing backend code
- Provides rich IDE integration (diagnostics, sidebar, status bar)
- Works offline with local LLM

**Estimated Effort:** 4-6 weeks for production-ready MVP

---

## Appendix: Extension Scaffold Commands

```bash
# Install VS Code extension generator
npm install -g yo generator-code

# Generate extension scaffold
yo code
# Choose: New Extension (TypeScript)
# Name: cva-verifier
# Identifier: dysruption.cva-verifier
# Description: AI Consensus Verifier for vibecoding

# Project structure:
cva-extension/
├── src/
│   ├── extension.ts        # Entry point
│   ├── fileWatcher.ts      # FileSystemWatcher setup
│   ├── changeTracker.ts    # Smart debounce logic
│   ├── backendClient.ts    # HTTP/WebSocket client
│   ├── sidebarProvider.ts  # TreeView for verdicts
│   ├── diagnostics.ts      # Inline warnings
│   └── statusBar.ts        # Status indicator
├── package.json            # Extension manifest
├── tsconfig.json
└── cva_backend/            # Embedded Python backend (your existing code)
    ├── modules/
    ├── api.py
    └── requirements.txt
```
