# CVA VS Code Extension Development Plan

## Phase 1: MVP - Extension + Local Backend Integration

**Document Version:** 1.0  
**Created:** December 18, 2025  
**Status:** PLANNING  
**Estimated Duration:** 4-6 weeks

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Description](#2-system-description)
3. [Architecture Overview](#3-architecture-overview)
4. [Prerequisites & Dependencies](#4-prerequisites--dependencies)
5. [Development Phases](#5-development-phases)
6. [Detailed Task Breakdown](#6-detailed-task-breakdown)
7. [Testing Strategy](#7-testing-strategy)
8. [Verification Criteria](#8-verification-criteria)
9. [Risk Assessment](#9-risk-assessment)
10. [Appendices](#10-appendices)

---

## 1. Executive Summary

### 1.1 Objective

Build a VS Code/Cursor extension that:
- **Detects file changes** in real-time using VS Code's native FileSystemWatcher API
- **Communicates with the CVA backend** via HTTP REST and WebSocket
- **Auto-starts the Python backend** as a subprocess when the extension activates
- **Displays verification results** through inline diagnostics, sidebar, and status bar

### 1.2 Success Criteria

| Metric | Target |
|--------|--------|
| File change detection latency | < 100ms |
| Backend auto-start time | < 10 seconds |
| Health check success rate | 99%+ |
| WebSocket reconnection | Automatic within 5s |
| User interaction to verification | ≤ 2 clicks |

### 1.3 Deliverables

1. **VS Code Extension** (`dysruption.cva-verifier`)
2. **Extension Marketplace Package** (`.vsix`)
3. **Integration Test Suite** (100% core path coverage)
4. **User Documentation** (README, CHANGELOG)
5. **Developer Documentation** (architecture, API reference)

---

## 2. System Description

### 2.1 What is CVA Extension?

The CVA Extension brings AI-powered code verification directly into VS Code/Cursor. When a developer saves a file, the extension:

1. Detects the change via VS Code's FileSystemWatcher
2. Applies smart debouncing (waits for activity to settle)
3. Sends changed files to the local CVA backend
4. Receives verdicts from the tribunal of AI judges
5. Displays results as inline diagnostics (squiggly lines)
6. Shows a summary in the sidebar panel

### 2.2 Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CVA VS CODE EXTENSION                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌─────────────┐  │
│  │ ACTIVATION    │  │ FILE WATCHER  │  │ BACKEND MGR   │  │ UI LAYER    │  │
│  │               │  │               │  │               │  │             │  │
│  │ • onStartup   │  │ • onCreate    │  │ • autoStart() │  │ • Sidebar   │  │
│  │ • onLanguage  │  │ • onChange    │  │ • healthCheck │  │ • StatusBar │  │
│  │ • onCommand   │  │ • onDelete    │  │ • restart()   │  │ • Diagnostics│ │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘  └──────┬──────┘  │
│          │                  │                  │                 │         │
│          └──────────────────┴──────────────────┴─────────────────┘         │
│                                    │                                        │
│                         ┌──────────┴──────────┐                             │
│                         │   CHANGE TRACKER    │                             │
│                         │                     │                             │
│                         │ • dirtyFiles Set    │                             │
│                         │ • smartDebounce()   │                             │
│                         │ • batchDetection()  │                             │
│                         └──────────┬──────────┘                             │
│                                    │                                        │
│                         ┌──────────┴──────────┐                             │
│                         │   BACKEND CLIENT    │                             │
│                         │                     │                             │
│                         │ • HTTP: /run, /status│                            │
│                         │ • WebSocket: /ws    │                             │
│                         │ • Retry logic       │                             │
│                         └──────────┬──────────┘                             │
│                                    │                                        │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                        HTTP :8001 / WebSocket /ws
                                     │
┌────────────────────────────────────┼────────────────────────────────────────┐
│                          CVA PYTHON BACKEND                                 │
│                        (FastAPI on localhost:8001)                          │
├────────────────────────────────────┼────────────────────────────────────────┤
│                                    ▼                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ modules/    │  │ modules/    │  │ modules/    │  │ modules/            │ │
│  │ api.py      │  │ tribunal.py │  │ parser.py   │  │ prompt_synthesizer.py│ │
│  │             │  │             │  │             │  │                     │ │
│  │ REST+WS     │  │ Judge Panel │  │ Constitution│  │ Fix Recommendations │ │
│  │ Endpoints   │  │ Consensus   │  │ → Invariants│  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Communication Protocol

#### HTTP REST Endpoints

| Endpoint | Method | Purpose | Request Body | Response |
|----------|--------|---------|--------------|----------|
| `/health` | GET | Health check | None | `{ "status": "ok" }` |
| `/run` | POST | Start verification | `{ target_dir, spec_content }` | `{ run_id }` |
| `/status/{run_id}` | GET | Check run status | None | `{ status, progress }` |
| `/verdict/{run_id}` | GET | Get final verdict | None | `{ verdict, violations }` |
| `/docs` | GET | OpenAPI docs | None | HTML |

#### WebSocket Protocol

| Event | Direction | Payload |
|-------|-----------|---------|
| `connect` | Client→Server | None |
| `status_update` | Server→Client | `{ run_id, phase, progress }` |
| `verdict_ready` | Server→Client | `{ run_id, verdict, violations }` |
| `error` | Server→Client | `{ run_id, error_message }` |

---

## 3. Architecture Overview

### 3.1 Technology Stack

| Layer | Technology | Version | Justification |
|-------|------------|---------|---------------|
| Extension Runtime | VS Code API | ^1.85.0 | Latest stable with full FileSystemWatcher support |
| Extension Language | TypeScript | 5.3+ | Type safety, VS Code standard |
| Build System | esbuild | 0.19+ | Fast bundling, VS Code recommended |
| HTTP Client | node-fetch | 3.x | Lightweight, Promise-based |
| WebSocket Client | ws | 8.x | Robust, well-maintained |
| Process Management | child_process (Node.js) | Built-in | Spawn Python backend |
| Testing | Mocha + @vscode/test-electron | Latest | Official VS Code testing |
| Backend | FastAPI (Python) | Existing | CVA backend already built |

### 3.2 File Structure

```
cva-extension/
├── .vscode/
│   ├── launch.json              # Debug configurations
│   ├── tasks.json               # Build tasks
│   └── settings.json            # Workspace settings
├── src/
│   ├── extension.ts             # Entry point, activation
│   ├── constants.ts             # Configuration constants
│   ├── types.ts                 # TypeScript interfaces
│   │
│   ├── core/
│   │   ├── backendManager.ts    # Subprocess management
│   │   ├── backendClient.ts     # HTTP + WebSocket client
│   │   ├── changeTracker.ts     # Smart debounce logic
│   │   └── fileWatcher.ts       # FileSystemWatcher setup
│   │
│   ├── ui/
│   │   ├── statusBar.ts         # Status bar indicator
│   │   ├── sidebarProvider.ts   # TreeView for verdicts
│   │   ├── diagnosticsProvider.ts # Inline warnings
│   │   └── outputChannel.ts     # Logging output
│   │
│   └── test/
│       ├── suite/
│       │   ├── index.ts         # Test runner
│       │   ├── extension.test.ts
│       │   ├── backendClient.test.ts
│       │   ├── changeTracker.test.ts
│       │   └── integration.test.ts
│       └── runTest.ts
│
├── media/
│   ├── icon.png                 # Extension icon (128x128)
│   ├── icon-dark.svg            # TreeView icons
│   └── icon-light.svg
│
├── resources/
│   └── cva-backend/             # Symlink or copy of backend
│
├── .vscode-test.mjs             # Test configuration
├── .vscodeignore                # Files to exclude from package
├── CHANGELOG.md
├── LICENSE
├── package.json                 # Extension manifest
├── README.md
├── tsconfig.json
└── esbuild.js                   # Build script
```

### 3.3 Extension Manifest (package.json) Key Sections

```json
{
  "name": "cva-verifier",
  "displayName": "CVA - AI Code Verifier",
  "description": "Verify code against constitutional specifications using AI judges",
  "version": "0.1.0",
  "publisher": "dysruption",
  "engines": { "vscode": "^1.85.0" },
  "categories": ["Linters", "Testing", "Other"],
  "keywords": ["ai", "verification", "consensus", "tribunal", "code quality"],
  
  "activationEvents": [
    "onStartupFinished",
    "workspaceContains:**/*.cva.yaml"
  ],
  
  "main": "./out/extension.js",
  
  "contributes": {
    "commands": [
      { "command": "cva.start", "title": "CVA: Start Backend" },
      { "command": "cva.stop", "title": "CVA: Stop Backend" },
      { "command": "cva.verify", "title": "CVA: Verify Workspace" },
      { "command": "cva.verifyFile", "title": "CVA: Verify Current File" },
      { "command": "cva.showOutput", "title": "CVA: Show Output" }
    ],
    "views": {
      "explorer": [
        {
          "id": "cvaVerdicts",
          "name": "CVA Verdicts",
          "icon": "media/icon.svg"
        }
      ]
    },
    "configuration": {
      "title": "CVA Verifier",
      "properties": {
        "cva.enabled": { "type": "boolean", "default": true },
        "cva.debounceMs": { "type": "number", "default": 3000 },
        "cva.backendPort": { "type": "number", "default": 8001 },
        "cva.autoStartBackend": { "type": "boolean", "default": true },
        "cva.pythonPath": { "type": "string", "default": "python" },
        "cva.constitutionPath": { "type": "string", "default": "" }
      }
    }
  }
}
```

---

## 4. Prerequisites & Dependencies

### 4.1 Development Environment

| Requirement | Version | Verification Command |
|-------------|---------|---------------------|
| Node.js | 18.x or 20.x LTS | `node --version` |
| npm | 9.x+ | `npm --version` |
| VS Code | 1.85+ | `code --version` |
| Python | 3.10+ | `python --version` |
| Git | 2.x+ | `git --version` |

### 4.2 VS Code Extension Dependencies

```json
{
  "dependencies": {
    "ws": "^8.16.0"
  },
  "devDependencies": {
    "@types/vscode": "^1.85.0",
    "@types/node": "^20.10.0",
    "@types/mocha": "^10.0.6",
    "@types/ws": "^8.5.10",
    "@vscode/test-cli": "^0.0.4",
    "@vscode/test-electron": "^2.3.8",
    "@vscode/vsce": "^2.22.0",
    "esbuild": "^0.19.0",
    "mocha": "^10.2.0",
    "typescript": "^5.3.0"
  }
}
```

### 4.3 Backend Dependencies (Already Exist)

The CVA backend in `dysruption_cva/` is already functional with:
- FastAPI + Uvicorn
- WebSocket support (`/ws` endpoint)
- All tribunal/parser/synthesizer modules

### 4.4 Assumptions

| ID | Assumption | Impact if False |
|----|------------|-----------------|
| A1 | Python is installed and in PATH | Backend won't start |
| A2 | Port 8001 is available | Backend fails to bind |
| A3 | User has API keys configured in `.env` | Tribunal returns errors |
| A4 | Backend modules are stable | Runtime errors |
| A5 | VS Code is version 1.85+ | FileSystemWatcher may differ |

---

## 5. Development Phases

### Phase Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           DEVELOPMENT TIMELINE                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Week 1        Week 2        Week 3        Week 4        Week 5        Week 6│
│  ────────────  ────────────  ────────────  ────────────  ────────────  ──────│
│                                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ PHASE 1  │  │ PHASE 2  │  │ PHASE 3  │  │ PHASE 4  │  │ PHASE 5  │       │
│  │          │  │          │  │          │  │          │  │          │       │
│  │ Scaffold │  │ Backend  │  │ File     │  │ UI       │  │ Polish   │       │
│  │ + Setup  │  │ Manager  │  │ Watcher  │  │ Layer    │  │ + Test   │       │
│  │          │  │ + Client │  │ + Track  │  │          │  │          │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                              │
│  Deliverable:  Deliverable:  Deliverable:  Deliverable:  Deliverable:       │
│  Empty ext     Backend runs  Changes       Full UI      Marketplace         │
│  activates     on activate   detected      working      ready              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Extension Scaffold (Week 1)
- Set up extension project structure
- Configure TypeScript, esbuild, testing
- Create package.json manifest
- Verify extension activates in dev host

### Phase 2: Backend Manager + Client (Week 2)
- Implement BackendManager (spawn Python subprocess)
- Implement BackendClient (HTTP + WebSocket)
- Health check polling
- Graceful shutdown

### Phase 3: File Watcher + Change Tracker (Week 3)
- FileSystemWatcher integration
- Smart debouncing algorithm
- Batch change detection
- Trigger verification on changes

### Phase 4: UI Layer (Week 4)
- Status bar indicator
- Sidebar TreeView for verdicts
- Diagnostics (inline squiggly lines)
- Output channel for logs

### Phase 5: Polish + Testing (Week 5-6)
- Integration tests
- Error handling refinement
- Configuration UI
- README and documentation
- Marketplace packaging

---

## 6. Detailed Task Breakdown

### PHASE 1: Extension Scaffold

#### Task 1.1: Initialize Extension Project

**Objective:** Create a new VS Code extension project with TypeScript and testing setup.

**Steps:**
1. Create directory `cva-extension` in the Invariant workspace
2. Run `npx --package yo --package generator-code -- yo code`
3. Select: New Extension (TypeScript)
4. Name: `cva-verifier`
5. Identifier: `dysruption.cva-verifier`
6. Publisher: `dysruption`

**Verification:**
- [ ] `package.json` exists with correct metadata
- [ ] `src/extension.ts` exists with activate/deactivate functions
- [ ] `npm install` completes without errors
- [ ] `npm run compile` produces `out/extension.js`

**Exit Criteria:**
```bash
# Run in Extension Development Host (F5)
# Execute command: "Hello World"
# Should show notification "Hello World from cva-verifier!"
```

---

#### Task 1.2: Configure Build System (esbuild)

**Objective:** Replace default tsc with esbuild for faster builds and smaller bundle.

**Steps:**
1. Install esbuild: `npm install -D esbuild`
2. Create `esbuild.js` build script
3. Update `package.json` scripts
4. Configure `.vscodeignore`

**Files to Create:**

`esbuild.js`:
```javascript
const esbuild = require('esbuild');

const production = process.argv.includes('--production');
const watch = process.argv.includes('--watch');

async function main() {
  const ctx = await esbuild.context({
    entryPoints: ['src/extension.ts'],
    bundle: true,
    format: 'cjs',
    minify: production,
    sourcemap: !production,
    sourcesContent: false,
    platform: 'node',
    outfile: 'out/extension.js',
    external: ['vscode'],
    logLevel: 'info',
  });

  if (watch) {
    await ctx.watch();
  } else {
    await ctx.rebuild();
    await ctx.dispose();
  }
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
```

**Verification:**
- [ ] `npm run compile` uses esbuild
- [ ] `out/extension.js` is a single bundled file
- [ ] Source maps work in debugger
- [ ] Bundle size < 100KB

---

#### Task 1.3: Set Up Test Infrastructure

**Objective:** Configure Mocha-based VS Code integration tests.

**Steps:**
1. Create `.vscode-test.mjs` configuration
2. Create test directory structure
3. Add test scripts to package.json
4. Write first sanity test

**Files to Create:**

`.vscode-test.mjs`:
```javascript
import { defineConfig } from '@vscode/test-cli';

export default defineConfig({
  files: 'out/test/**/*.test.js',
  version: 'stable',
  mocha: {
    ui: 'tdd',
    timeout: 20000
  }
});
```

`src/test/suite/extension.test.ts`:
```typescript
import * as assert from 'assert';
import * as vscode from 'vscode';

suite('Extension Test Suite', () => {
  test('Extension should be present', () => {
    assert.ok(vscode.extensions.getExtension('dysruption.cva-verifier'));
  });

  test('Extension should activate', async () => {
    const ext = vscode.extensions.getExtension('dysruption.cva-verifier');
    await ext?.activate();
    assert.ok(ext?.isActive);
  });
});
```

**Verification:**
- [ ] `npm test` runs without errors
- [ ] Tests execute in VS Code Extension Host
- [ ] Test results show in terminal

---

#### Task 1.4: Define TypeScript Interfaces

**Objective:** Create type definitions for all data structures.

**File: `src/types.ts`**
```typescript
// Backend communication types
export interface RunRequest {
  target_dir: string;
  spec_content: string;
  judges?: string[];
}

export interface RunResponse {
  run_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
}

export interface StatusResponse {
  run_id: string;
  status: 'running' | 'completed' | 'failed';
  phase: string;
  progress: number;
}

export interface Violation {
  file: string;
  line: number;
  column: number;
  invariant: string;
  message: string;
  severity: 'error' | 'warning' | 'info';
}

export interface VerdictResponse {
  run_id: string;
  verdict: 'PASS' | 'FAIL' | 'INCONCLUSIVE';
  confidence: number;
  violations: Violation[];
  recommendations: string[];
}

// WebSocket message types
export interface WebSocketMessage {
  type: 'status_update' | 'verdict_ready' | 'error';
  payload: StatusResponse | VerdictResponse | { message: string };
}

// Extension state
export interface ExtensionState {
  backendRunning: boolean;
  currentRunId: string | null;
  dirtyFiles: Set<string>;
  lastVerdict: VerdictResponse | null;
}

// Configuration
export interface CVAConfig {
  enabled: boolean;
  debounceMs: number;
  backendPort: number;
  autoStartBackend: boolean;
  pythonPath: string;
  constitutionPath: string;
}
```

**Verification:**
- [ ] File compiles without TypeScript errors
- [ ] Types are exported and importable
- [ ] Intellisense works in VS Code

---

### PHASE 2: Backend Manager + Client

#### Task 2.1: Implement BackendManager

**Objective:** Create a class that starts/stops the Python CVA backend as a subprocess.

**File: `src/core/backendManager.ts`**

**Functionality:**
1. Spawn Python process with uvicorn
2. Monitor process stdout/stderr
3. Detect when server is ready (parse "Uvicorn running on")
4. Handle process crashes with auto-restart
5. Graceful shutdown on extension deactivate

**Key Code Points:**
```typescript
import { spawn, ChildProcess } from 'child_process';
import * as vscode from 'vscode';
import * as path from 'path';

export class BackendManager {
  private process: ChildProcess | null = null;
  private outputChannel: vscode.OutputChannel;
  private isReady: boolean = false;
  private restartAttempts: number = 0;
  private readonly MAX_RESTARTS = 3;

  constructor(outputChannel: vscode.OutputChannel) {
    this.outputChannel = outputChannel;
  }

  async start(cvaPath: string, pythonPath: string, port: number): Promise<boolean> {
    // Implementation
  }

  stop(): void {
    // Implementation
  }

  isRunning(): boolean {
    return this.process !== null && this.isReady;
  }
}
```

**Verification:**
- [ ] Backend starts when `start()` is called
- [ ] Logs appear in output channel
- [ ] `isRunning()` returns true after startup
- [ ] `stop()` terminates the process cleanly
- [ ] Crashed backend triggers restart (up to 3 times)

**Test Cases:**
1. Start backend with valid Python path → Success
2. Start backend with invalid Python path → Error thrown
3. Stop running backend → Process terminated
4. Backend crashes → Auto-restart triggered

---

#### Task 2.2: Implement BackendClient (HTTP)

**Objective:** Create HTTP client for REST API communication.

**File: `src/core/backendClient.ts`**

**Functionality:**
1. Health check endpoint polling
2. POST /run to trigger verification
3. GET /status/:run_id for progress
4. GET /verdict/:run_id for results
5. Retry logic with exponential backoff

**Key Code Points:**
```typescript
export class BackendClient {
  private baseUrl: string;
  
  constructor(port: number = 8001) {
    this.baseUrl = `http://localhost:${port}`;
  }

  async isHealthy(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000)
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async triggerRun(request: RunRequest): Promise<RunResponse> {
    // Implementation
  }

  async getStatus(runId: string): Promise<StatusResponse> {
    // Implementation
  }

  async getVerdict(runId: string): Promise<VerdictResponse> {
    // Implementation
  }
}
```

**Verification:**
- [ ] `isHealthy()` returns true when backend is running
- [ ] `isHealthy()` returns false when backend is down
- [ ] `triggerRun()` returns a run_id
- [ ] `getVerdict()` returns verdict after completion

**Test Cases:**
1. Health check with running backend → true
2. Health check with stopped backend → false
3. Trigger run with valid request → run_id returned
4. Get verdict for completed run → VerdictResponse returned
5. Request timeout → Error handled gracefully

---

#### Task 2.3: Implement BackendClient (WebSocket)

**Objective:** Add WebSocket support for real-time updates.

**Additional Code in `src/core/backendClient.ts`:**

```typescript
import WebSocket from 'ws';

export class BackendClient {
  // ... existing HTTP code ...

  private ws: WebSocket | null = null;
  private wsReconnectTimer: NodeJS.Timeout | null = null;

  connectWebSocket(
    onMessage: (msg: WebSocketMessage) => void,
    onError: (err: Error) => void
  ): void {
    this.ws = new WebSocket(`ws://localhost:${this.port}/ws`);
    
    this.ws.on('open', () => {
      console.log('[CVA] WebSocket connected');
    });

    this.ws.on('message', (data: Buffer) => {
      const msg = JSON.parse(data.toString()) as WebSocketMessage;
      onMessage(msg);
    });

    this.ws.on('error', onError);

    this.ws.on('close', () => {
      // Auto-reconnect after 5 seconds
      this.wsReconnectTimer = setTimeout(() => {
        this.connectWebSocket(onMessage, onError);
      }, 5000);
    });
  }

  disconnectWebSocket(): void {
    if (this.wsReconnectTimer) {
      clearTimeout(this.wsReconnectTimer);
    }
    this.ws?.close();
    this.ws = null;
  }
}
```

**Verification:**
- [ ] WebSocket connects to backend
- [ ] Messages are received and parsed
- [ ] Reconnection happens after disconnect
- [ ] Clean disconnection on extension deactivate

---

#### Task 2.4: Integrate with Extension Activation

**Objective:** Auto-start backend when extension activates.

**Update `src/extension.ts`:**

```typescript
import * as vscode from 'vscode';
import { BackendManager } from './core/backendManager';
import { BackendClient } from './core/backendClient';

let backendManager: BackendManager;
let backendClient: BackendClient;
let outputChannel: vscode.OutputChannel;

export async function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel('CVA Verifier');
  
  const config = vscode.workspace.getConfiguration('cva');
  const autoStart = config.get<boolean>('autoStartBackend', true);
  const port = config.get<number>('backendPort', 8001);
  const pythonPath = config.get<string>('pythonPath', 'python');

  backendManager = new BackendManager(outputChannel);
  backendClient = new BackendClient(port);

  if (autoStart) {
    const cvaPath = getCvaPath(context);
    await backendManager.start(cvaPath, pythonPath, port);
    
    // Wait for health check
    await waitForBackend(backendClient, 30000);
    
    // Connect WebSocket
    backendClient.connectWebSocket(handleWebSocketMessage, handleWebSocketError);
  }

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('cva.start', () => startBackend(context)),
    vscode.commands.registerCommand('cva.stop', () => stopBackend()),
    vscode.commands.registerCommand('cva.verify', () => triggerVerification())
  );
}

export function deactivate() {
  backendClient?.disconnectWebSocket();
  backendManager?.stop();
}
```

**Verification:**
- [ ] Backend starts automatically on extension activate
- [ ] Health check polling succeeds
- [ ] WebSocket connection established
- [ ] Commands are registered and functional
- [ ] Backend stops on extension deactivate

---

### PHASE 3: File Watcher + Change Tracker

#### Task 3.1: Implement FileWatcher

**Objective:** Set up VS Code FileSystemWatcher to detect file changes.

**File: `src/core/fileWatcher.ts`**

```typescript
import * as vscode from 'vscode';

export class FileWatcher {
  private watcher: vscode.FileSystemWatcher;
  private onChangeCallback: (uri: vscode.Uri) => void;

  constructor(
    pattern: string = '**/*.{py,js,ts,jsx,tsx,java,go,rs}',
    onChange: (uri: vscode.Uri) => void
  ) {
    this.onChangeCallback = onChange;
    
    this.watcher = vscode.workspace.createFileSystemWatcher(
      pattern,
      false, // ignoreCreateEvents
      false, // ignoreChangeEvents
      false  // ignoreDeleteEvents
    );

    this.watcher.onDidCreate(this.handleChange.bind(this));
    this.watcher.onDidChange(this.handleChange.bind(this));
    this.watcher.onDidDelete(this.handleDelete.bind(this));
  }

  private handleChange(uri: vscode.Uri): void {
    // Ignore node_modules, .git, etc.
    if (this.shouldIgnore(uri)) return;
    this.onChangeCallback(uri);
  }

  private handleDelete(uri: vscode.Uri): void {
    // Handle deletion
  }

  private shouldIgnore(uri: vscode.Uri): boolean {
    const ignoredPatterns = [
      'node_modules',
      '.git',
      '__pycache__',
      '.venv',
      'dist',
      'build',
      'out'
    ];
    return ignoredPatterns.some(p => uri.fsPath.includes(p));
  }

  dispose(): void {
    this.watcher.dispose();
  }
}
```

**Verification:**
- [ ] File save triggers onChange callback
- [ ] File create triggers onChange callback
- [ ] File delete triggers onDelete callback
- [ ] Ignored directories are filtered out

---

#### Task 3.2: Implement ChangeTracker with Smart Debouncing

**Objective:** Collect changed files and debounce verification triggers.

**File: `src/core/changeTracker.ts`**

```typescript
import * as vscode from 'vscode';

export class ChangeTracker {
  private dirtyFiles: Set<string> = new Set();
  private debounceTimer: NodeJS.Timeout | null = null;
  private debounceMs: number;
  private onTrigger: (files: string[]) => void;

  // Bulk change detection
  private changeBuffer: string[] = [];
  private bufferStartTime: number = 0;
  private readonly BULK_THRESHOLD = 5;
  private readonly BULK_WINDOW_MS = 500;

  constructor(debounceMs: number, onTrigger: (files: string[]) => void) {
    this.debounceMs = debounceMs;
    this.onTrigger = onTrigger;
  }

  addFile(filePath: string): void {
    this.dirtyFiles.add(filePath);
    this.detectBulkChange(filePath);
    this.scheduleVerification();
  }

  private detectBulkChange(filePath: string): void {
    const now = Date.now();
    
    if (now - this.bufferStartTime > this.BULK_WINDOW_MS) {
      this.changeBuffer = [filePath];
      this.bufferStartTime = now;
    } else {
      this.changeBuffer.push(filePath);
    }

    // If bulk operation detected, extend debounce
    if (this.changeBuffer.length >= this.BULK_THRESHOLD) {
      this.debounceMs = Math.min(this.debounceMs * 2, 10000);
    }
  }

  private scheduleVerification(): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    this.debounceTimer = setTimeout(() => {
      const files = Array.from(this.dirtyFiles);
      this.dirtyFiles.clear();
      this.onTrigger(files);
    }, this.debounceMs);
  }

  clear(): void {
    this.dirtyFiles.clear();
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
  }
}
```

**Verification:**
- [ ] Single file change triggers after debounce period
- [ ] Rapid changes reset debounce timer
- [ ] Bulk changes (5+ in 500ms) extend debounce
- [ ] All changed files are collected in the trigger

**Test Cases:**
1. Single file save → Verification triggered after 3s
2. Two files saved 1s apart → Verification triggered 3s after second save
3. 10 files in 200ms → Debounce extended, verification after ~6s

---

#### Task 3.3: Wire FileWatcher to ChangeTracker

**Objective:** Connect file detection to change tracking.

**Update `src/extension.ts`:**

```typescript
import { FileWatcher } from './core/fileWatcher';
import { ChangeTracker } from './core/changeTracker';

let fileWatcher: FileWatcher;
let changeTracker: ChangeTracker;

export async function activate(context: vscode.ExtensionContext) {
  // ... existing activation code ...

  const config = vscode.workspace.getConfiguration('cva');
  const debounceMs = config.get<number>('debounceMs', 3000);

  changeTracker = new ChangeTracker(debounceMs, handleVerificationTrigger);
  
  fileWatcher = new FileWatcher('**/*.{py,js,ts,jsx,tsx}', (uri) => {
    changeTracker.addFile(uri.fsPath);
    updateStatusBar('watching');
  });

  context.subscriptions.push(fileWatcher);
}

async function handleVerificationTrigger(files: string[]): Promise<void> {
  updateStatusBar('verifying');
  
  try {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceFolder) return;

    const config = vscode.workspace.getConfiguration('cva');
    const constitutionPath = config.get<string>('constitutionPath', '');
    
    const specContent = await loadConstitution(constitutionPath);
    
    const response = await backendClient.triggerRun({
      target_dir: workspaceFolder,
      spec_content: specContent
    });

    // WebSocket will receive updates
    outputChannel.appendLine(`[CVA] Run started: ${response.run_id}`);
  } catch (error) {
    updateStatusBar('failed');
    vscode.window.showErrorMessage(`CVA verification failed: ${error}`);
  }
}
```

**Verification:**
- [ ] File save triggers changeTracker
- [ ] Debounce timer resets on rapid saves
- [ ] After debounce, backend /run is called
- [ ] Status bar updates through phases

---

### PHASE 4: UI Layer

#### Task 4.1: Implement StatusBar

**Objective:** Show verification status in VS Code status bar.

**File: `src/ui/statusBar.ts`**

```typescript
import * as vscode from 'vscode';

export type StatusBarState = 'idle' | 'watching' | 'verifying' | 'passed' | 'failed';

export class StatusBarProvider {
  private statusBarItem: vscode.StatusBarItem;

  constructor() {
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.statusBarItem.command = 'cva.showOutput';
    this.update('idle');
    this.statusBarItem.show();
  }

  update(state: StatusBarState): void {
    const icons: Record<StatusBarState, string> = {
      idle: '$(circle-outline)',
      watching: '$(eye)',
      verifying: '$(sync~spin)',
      passed: '$(check)',
      failed: '$(warning)'
    };

    const tooltips: Record<StatusBarState, string> = {
      idle: 'CVA: Ready',
      watching: 'CVA: Watching for changes',
      verifying: 'CVA: Verifying...',
      passed: 'CVA: All checks passed',
      failed: 'CVA: Violations found'
    };

    this.statusBarItem.text = `${icons[state]} CVA`;
    this.statusBarItem.tooltip = tooltips[state];
    
    // Color based on state
    this.statusBarItem.backgroundColor = state === 'failed' 
      ? new vscode.ThemeColor('statusBarItem.warningBackground')
      : undefined;
  }

  dispose(): void {
    this.statusBarItem.dispose();
  }
}
```

**Verification:**
- [ ] Status bar shows "CVA" with icon
- [ ] Icon changes based on state
- [ ] Clicking opens output channel
- [ ] Background color changes on failure

---

#### Task 4.2: Implement DiagnosticsProvider

**Objective:** Show violations as inline diagnostics (squiggly lines).

**File: `src/ui/diagnosticsProvider.ts`**

```typescript
import * as vscode from 'vscode';
import { Violation } from '../types';

export class DiagnosticsProvider {
  private collection: vscode.DiagnosticCollection;

  constructor() {
    this.collection = vscode.languages.createDiagnosticCollection('cva');
  }

  update(violations: Violation[]): void {
    // Clear existing
    this.collection.clear();

    // Group by file
    const byFile = new Map<string, Violation[]>();
    for (const v of violations) {
      const existing = byFile.get(v.file) || [];
      existing.push(v);
      byFile.set(v.file, existing);
    }

    // Create diagnostics
    for (const [file, fileViolations] of byFile) {
      const uri = vscode.Uri.file(file);
      const diagnostics = fileViolations.map(v => this.toDiagnostic(v));
      this.collection.set(uri, diagnostics);
    }
  }

  private toDiagnostic(violation: Violation): vscode.Diagnostic {
    const range = new vscode.Range(
      violation.line - 1,
      violation.column,
      violation.line - 1,
      violation.column + 50 // Approximate end
    );

    const severity = {
      error: vscode.DiagnosticSeverity.Error,
      warning: vscode.DiagnosticSeverity.Warning,
      info: vscode.DiagnosticSeverity.Information
    }[violation.severity];

    const diagnostic = new vscode.Diagnostic(
      range,
      `[CVA] ${violation.invariant}: ${violation.message}`,
      severity
    );

    diagnostic.source = 'CVA';
    diagnostic.code = violation.invariant;

    return diagnostic;
  }

  clear(): void {
    this.collection.clear();
  }

  dispose(): void {
    this.collection.dispose();
  }
}
```

**Verification:**
- [ ] Violations appear as squiggly lines in editor
- [ ] Hovering shows the violation message
- [ ] Problems panel shows all violations
- [ ] Clearing verdicts removes diagnostics

---

#### Task 4.3: Implement SidebarProvider

**Objective:** Create TreeView in sidebar showing verdict summary.

**File: `src/ui/sidebarProvider.ts`**

```typescript
import * as vscode from 'vscode';
import { VerdictResponse, Violation } from '../types';

export class VerdictTreeProvider implements vscode.TreeDataProvider<VerdictItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<VerdictItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private verdictResponse: VerdictResponse | null = null;

  update(verdict: VerdictResponse): void {
    this.verdictResponse = verdict;
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: VerdictItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: VerdictItem): VerdictItem[] {
    if (!this.verdictResponse) {
      return [new VerdictItem('No verification run yet', 'info')];
    }

    if (!element) {
      // Root level: show verdict summary and violations
      const items: VerdictItem[] = [
        new VerdictItem(
          `Verdict: ${this.verdictResponse.verdict}`,
          this.verdictResponse.verdict === 'PASS' ? 'pass' : 'fail',
          vscode.TreeItemCollapsibleState.None
        ),
        new VerdictItem(
          `Confidence: ${(this.verdictResponse.confidence * 100).toFixed(1)}%`,
          'info',
          vscode.TreeItemCollapsibleState.None
        )
      ];

      if (this.verdictResponse.violations.length > 0) {
        items.push(new VerdictItem(
          `Violations (${this.verdictResponse.violations.length})`,
          'violations',
          vscode.TreeItemCollapsibleState.Expanded
        ));
      }

      return items;
    }

    // Children: individual violations
    if (element.type === 'violations') {
      return this.verdictResponse.violations.map(v => 
        new VerdictItem(
          `${v.file}:${v.line} - ${v.invariant}`,
          'violation',
          vscode.TreeItemCollapsibleState.None,
          v
        )
      );
    }

    return [];
  }
}

class VerdictItem extends vscode.TreeItem {
  constructor(
    label: string,
    public readonly type: string,
    collapsibleState: vscode.TreeItemCollapsibleState = vscode.TreeItemCollapsibleState.None,
    public readonly violation?: Violation
  ) {
    super(label, collapsibleState);

    // Set icon based on type
    const iconMap: Record<string, string> = {
      pass: 'check',
      fail: 'warning',
      info: 'info',
      violations: 'error',
      violation: 'circle-filled'
    };
    this.iconPath = new vscode.ThemeIcon(iconMap[type] || 'question');

    // Click on violation opens file at line
    if (violation) {
      this.command = {
        command: 'vscode.open',
        title: 'Open File',
        arguments: [
          vscode.Uri.file(violation.file),
          { selection: new vscode.Range(violation.line - 1, 0, violation.line - 1, 0) }
        ]
      };
    }
  }
}
```

**Verification:**
- [ ] Sidebar view "CVA Verdicts" appears in Explorer
- [ ] Verdict summary shown after verification
- [ ] Violations listed with file and line
- [ ] Clicking violation opens file at correct line

---

#### Task 4.4: Wire UI to WebSocket Events

**Objective:** Update UI components when WebSocket messages arrive.

**Update `src/extension.ts`:**

```typescript
function handleWebSocketMessage(msg: WebSocketMessage): void {
  switch (msg.type) {
    case 'status_update':
      const status = msg.payload as StatusResponse;
      statusBarProvider.update('verifying');
      outputChannel.appendLine(`[CVA] ${status.phase}: ${status.progress}%`);
      break;

    case 'verdict_ready':
      const verdict = msg.payload as VerdictResponse;
      statusBarProvider.update(verdict.verdict === 'PASS' ? 'passed' : 'failed');
      diagnosticsProvider.update(verdict.violations);
      sidebarProvider.update(verdict);
      
      // Show notification
      if (verdict.verdict === 'FAIL') {
        vscode.window.showWarningMessage(
          `CVA: ${verdict.violations.length} violation(s) found`,
          'Show Details'
        ).then(selection => {
          if (selection) {
            vscode.commands.executeCommand('cvaVerdicts.focus');
          }
        });
      }
      break;

    case 'error':
      const error = msg.payload as { message: string };
      statusBarProvider.update('failed');
      vscode.window.showErrorMessage(`CVA Error: ${error.message}`);
      break;
  }
}
```

**Verification:**
- [ ] Status bar updates during verification
- [ ] Diagnostics appear after verdict
- [ ] Sidebar updates with verdict details
- [ ] Notification shown on failures

---

### PHASE 5: Polish + Testing

#### Task 5.1: Write Integration Tests

**Objective:** Create comprehensive test suite.

**Test Files:**
- `src/test/suite/backendClient.test.ts`
- `src/test/suite/changeTracker.test.ts`
- `src/test/suite/integration.test.ts`

**Sample Integration Test:**
```typescript
import * as assert from 'assert';
import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

suite('Integration Tests', () => {
  const testWorkspace = path.join(__dirname, '../../test-workspace');

  suiteSetup(async () => {
    // Create test workspace
    fs.mkdirSync(testWorkspace, { recursive: true });
    fs.writeFileSync(
      path.join(testWorkspace, 'test.py'),
      'def hello():\n    print("world")\n'
    );
  });

  suiteTeardown(() => {
    fs.rmSync(testWorkspace, { recursive: true });
  });

  test('File change triggers verification', async function() {
    this.timeout(30000);

    // Open test file
    const doc = await vscode.workspace.openTextDocument(
      path.join(testWorkspace, 'test.py')
    );
    const editor = await vscode.window.showTextDocument(doc);

    // Edit and save
    await editor.edit(editBuilder => {
      editBuilder.insert(new vscode.Position(0, 0), '# Modified\n');
    });
    await doc.save();

    // Wait for verification to complete (debounce + processing)
    await new Promise(resolve => setTimeout(resolve, 10000));

    // Check diagnostics exist
    const diagnostics = vscode.languages.getDiagnostics(doc.uri);
    // Assert based on expected violations
  });
});
```

**Verification:**
- [ ] All tests pass with `npm test`
- [ ] Tests run in CI pipeline
- [ ] Coverage > 80% for core modules

---

#### Task 5.2: Error Handling & Edge Cases

**Objective:** Handle all error scenarios gracefully.

**Error Scenarios to Handle:**

| Scenario | Expected Behavior |
|----------|-------------------|
| Backend not installed | Show error with install link |
| Port 8001 in use | Try alternative ports |
| Python not in PATH | Prompt for Python path |
| API keys missing | Show configuration guide |
| WebSocket disconnect | Auto-reconnect with backoff |
| Backend crash | Auto-restart (max 3 times) |
| Network timeout | Retry with exponential backoff |
| Invalid constitution | Show parse error in output |

**Implementation:**
- Add try-catch blocks to all async operations
- Show user-friendly error messages
- Log detailed errors to output channel
- Add "Report Issue" button in error dialogs

---

#### Task 5.3: Documentation

**Files to Create:**

1. **README.md** - User-facing documentation
   - Features
   - Installation
   - Configuration
   - Usage guide
   - Troubleshooting

2. **CHANGELOG.md** - Version history
   - v0.1.0: Initial release

3. **CONTRIBUTING.md** - Developer guide
   - Development setup
   - Testing
   - Pull request process

---

#### Task 5.4: Package for Marketplace

**Objective:** Create .vsix package for distribution.

**Steps:**
1. Update `package.json` version to 0.1.0
2. Add 128x128 icon
3. Run `vsce package`
4. Test install from .vsix

**Verification:**
- [ ] `vsce package` completes without errors
- [ ] `.vsix` file < 5MB
- [ ] Install from `.vsix` works
- [ ] All features functional in installed extension

---

## 7. Testing Strategy

### 7.1 Test Pyramid

```
                    ┌───────────────┐
                    │   E2E Tests   │  (5%)
                    │  (Integration)│
                    └───────────────┘
               ┌─────────────────────────┐
               │    Integration Tests    │  (20%)
               │ (Backend + Extension)   │
               └─────────────────────────┘
          ┌───────────────────────────────────┐
          │          Unit Tests               │  (75%)
          │ (Individual modules)              │
          └───────────────────────────────────┘
```

### 7.2 Test Coverage Requirements

| Module | Min Coverage | Critical Paths |
|--------|--------------|----------------|
| `backendManager.ts` | 80% | start, stop, restart |
| `backendClient.ts` | 85% | HTTP methods, WebSocket |
| `changeTracker.ts` | 90% | debounce, bulk detection |
| `fileWatcher.ts` | 75% | filter logic |
| UI components | 60% | state updates |

### 7.3 Test Execution

```bash
# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run specific test file
npm test -- --grep "BackendClient"

# Debug tests
# F5 with "Extension Tests" launch config
```

---

## 8. Verification Criteria

### 8.1 Phase Completion Checklist

#### Phase 1 Complete When:
- [ ] Extension activates in Extension Development Host
- [ ] "Hello World" command works
- [ ] TypeScript compiles without errors
- [ ] Tests run with `npm test`
- [ ] esbuild produces bundled output

#### Phase 2 Complete When:
- [ ] Backend starts automatically on extension activate
- [ ] Health check succeeds within 10 seconds
- [ ] HTTP client can call /run endpoint
- [ ] WebSocket connects and receives messages
- [ ] Backend stops cleanly on deactivate

#### Phase 3 Complete When:
- [ ] File save triggers changeTracker.addFile()
- [ ] Debounce waits correct duration
- [ ] Bulk changes extend debounce
- [ ] Verification triggered with correct files
- [ ] Status bar shows "watching" during idle

#### Phase 4 Complete When:
- [ ] Status bar shows correct icons for all states
- [ ] Violations appear as squiggly lines
- [ ] Problems panel shows CVA diagnostics
- [ ] Sidebar TreeView displays verdict summary
- [ ] Clicking violation opens file at line

#### Phase 5 Complete When:
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Documentation complete
- [ ] .vsix package builds
- [ ] Extension installs and works from .vsix

### 8.2 Final Acceptance Criteria

The extension is **production-ready** when:

1. **Functionality**: All features work as specified
2. **Performance**: < 100ms latency on file change detection
3. **Reliability**: Backend auto-restarts on crash
4. **Usability**: First-time user can start verification in < 2 minutes
5. **Quality**: No critical bugs, < 5 medium bugs
6. **Documentation**: README covers all features and common issues

---

## 9. Risk Assessment

### 9.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Python spawn fails on Windows | Medium | High | Test extensively, use shell: true |
| Port 8001 conflict | Medium | Medium | Configurable port, auto-find available |
| WebSocket reconnection loops | Low | Medium | Exponential backoff, max retries |
| Large file change batches | Low | High | Throttle verification requests |
| Extension conflicts with other linters | Medium | Low | Unique diagnostic source ID |

### 9.2 Project Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Backend API changes | Medium | High | Version backend, API contract tests |
| Scope creep | High | Medium | Strict MVP definition |
| Testing in CI environment | Medium | Medium | Docker-based test environment |
| Marketplace rejection | Low | High | Follow all guidelines, manual review |

---

## 10. Appendices

### 10.1 Command Reference

| Command | Description |
|---------|-------------|
| `cva.start` | Start CVA backend |
| `cva.stop` | Stop CVA backend |
| `cva.verify` | Verify entire workspace |
| `cva.verifyFile` | Verify current file only |
| `cva.showOutput` | Show CVA output channel |

### 10.2 Configuration Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `cva.enabled` | boolean | true | Enable/disable extension |
| `cva.debounceMs` | number | 3000 | Debounce wait time in ms |
| `cva.backendPort` | number | 8001 | Backend server port |
| `cva.autoStartBackend` | boolean | true | Auto-start on activate |
| `cva.pythonPath` | string | "python" | Python interpreter path |
| `cva.constitutionPath` | string | "" | Path to constitution file |

### 10.3 API Endpoints (Backend)

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/health` | GET | - | `{ "status": "ok" }` |
| `/run` | POST | RunRequest | RunResponse |
| `/status/{run_id}` | GET | - | StatusResponse |
| `/verdict/{run_id}` | GET | - | VerdictResponse |
| `/ws` | WebSocket | - | Stream of WebSocketMessage |

### 10.4 Glossary

| Term | Definition |
|------|------------|
| **Constitution** | Natural language rules for code verification |
| **Invariant** | Single parsed rule from constitution |
| **Tribunal** | Panel of AI judges voting on code compliance |
| **Verdict** | Final consensus result (PASS/FAIL/INCONCLUSIVE) |
| **Run** | Single verification execution with tracking ID |
| **Debounce** | Wait period to batch rapid changes |

---

**Document End**

*This plan should be reviewed and updated as development progresses.*
