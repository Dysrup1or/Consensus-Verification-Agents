/**
 * CVA VS Code Extension
 * 
 * Main entry point for the CVA Verifier extension.
 * Handles activation, command registration, and coordination of all components.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

// Core components
import {
  BackendManager,
  BackendClient,
  FileWatcher,
  ChangeTracker,
} from './core';

// UI components
import {
  StatusBarProvider,
  DiagnosticsProvider,
  SidebarProvider,
  OutputChannelProvider,
} from './ui';

// Types and constants
import {
  CVAConfig,
  VerdictResponse,
  WebSocketMessage,
  StatusResponse,
  FileChangeBatch,
} from './types';

import {
  COMMANDS,
  VIEWS,
  CONFIG_SECTION,
  CONFIG_KEYS,
  DEFAULTS,
  DEFAULT_WATCH_PATTERNS,
  DEFAULT_IGNORE_PATTERNS,
} from './constants';

// ============================================================================
// Global State
// ============================================================================

let outputChannelProvider: OutputChannelProvider;
let statusBarProvider: StatusBarProvider;
let diagnosticsProvider: DiagnosticsProvider;
let sidebarProvider: SidebarProvider;
let backendManager: BackendManager;
let backendClient: BackendClient;
let fileWatcher: FileWatcher;
let changeTracker: ChangeTracker;

let currentConfig: CVAConfig;
let currentRunId: string | null = null;

// ============================================================================
// Activation
// ============================================================================

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  try {
    // Initialize output channel first for logging
    outputChannelProvider = new OutputChannelProvider();
    outputChannelProvider.info('CVA Extension activating...');

    // Load configuration
    currentConfig = loadConfiguration();

    // Initialize UI components
    statusBarProvider = new StatusBarProvider();
    diagnosticsProvider = new DiagnosticsProvider();
    sidebarProvider = new SidebarProvider();

    // Register sidebar view
    const treeView = vscode.window.createTreeView(VIEWS.VERDICTS, {
      treeDataProvider: sidebarProvider,
      showCollapseAll: true,
    });

    // Initialize core components
    backendManager = new BackendManager(
      outputChannelProvider.getChannel(),
      currentConfig.maxRestartAttempts
    );

    // Initialize backend client (cloud or local mode)
    if (currentConfig.useCloudBackend) {
      backendClient = new BackendClient({
        useCloud: true,
        cloudUrl: currentConfig.cloudBackendUrl,
        apiToken: currentConfig.cloudApiToken,
      });
      outputChannelProvider.info(`Using cloud backend: ${currentConfig.cloudBackendUrl}`);
    } else {
      backendClient = new BackendClient(currentConfig.backendPort);
      outputChannelProvider.info(`Using local backend on port ${currentConfig.backendPort}`);
    }

    // Set up file watching
    fileWatcher = new FileWatcher(
      [...currentConfig.watchPatterns],
      [...currentConfig.ignorePatterns],
      outputChannelProvider.getChannel()
    );

    // Set up change tracking
    changeTracker = new ChangeTracker(
      currentConfig.debounceMs,
      handleVerificationTrigger
    );

    // Wire up event handlers
    setupEventHandlers();

    // Register commands
    registerCommands(context);

    // Add disposables
    context.subscriptions.push(
      outputChannelProvider,
      statusBarProvider,
      diagnosticsProvider,
      sidebarProvider,
      treeView,
      fileWatcher,
    );

    // Auto-start backend if configured (skip for cloud mode)
    if (currentConfig.enabled && currentConfig.useCloudBackend) {
      // Cloud mode: just check health, no backend to start
      statusBarProvider.update('starting');
      const isHealthy = await backendClient.isHealthy();
      if (isHealthy) {
        statusBarProvider.update('watching');
        backendClient.connectWebSocket();
        outputChannelProvider.info('Connected to cloud backend');
      } else {
        statusBarProvider.update('error');
        if (!currentConfig.cloudApiToken) {
          vscode.window.showWarningMessage(
            'Cloud backend requires an API token. Set cva.cloudApiToken in settings.',
            'Open Settings'
          ).then(selection => {
            if (selection === 'Open Settings') {
              vscode.commands.executeCommand('workbench.action.openSettings', 'cva.cloud');
            }
          });
        } else {
          vscode.window.showErrorMessage('Could not connect to cloud backend. Check your API token.');
        }
      }
    } else if (currentConfig.enabled && currentConfig.autoStartBackend) {
      statusBarProvider.update('starting');
      await startBackend(context);
    } else if (!currentConfig.enabled) {
      statusBarProvider.update('disabled');
    } else {
      statusBarProvider.update('idle');
    }

    // Watch for configuration changes
    context.subscriptions.push(
      vscode.workspace.onDidChangeConfiguration(handleConfigurationChange)
    );

    outputChannelProvider.info('CVA Extension activated successfully');

  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    outputChannelProvider?.error(`Activation failed: ${message}`);
    vscode.window.showErrorMessage(`CVA Extension failed to activate: ${message}`);
  }
}

export function deactivate(): void {
  outputChannelProvider?.info('CVA Extension deactivating...');
  
  // Clean up
  backendClient?.dispose();
  backendManager?.dispose();
  changeTracker?.dispose();
  
  outputChannelProvider?.info('CVA Extension deactivated');
}

// ============================================================================
// Configuration
// ============================================================================

function loadConfiguration(): CVAConfig {
  const config = vscode.workspace.getConfiguration(CONFIG_SECTION);

  return {
    enabled: config.get<boolean>(CONFIG_KEYS.ENABLED, DEFAULTS.ENABLED),
    debounceMs: config.get<number>(CONFIG_KEYS.DEBOUNCE_MS, DEFAULTS.DEBOUNCE_MS),
    backendPort: config.get<number>(CONFIG_KEYS.BACKEND_PORT, DEFAULTS.BACKEND_PORT),
    autoStartBackend: config.get<boolean>(CONFIG_KEYS.AUTO_START_BACKEND, DEFAULTS.AUTO_START_BACKEND),
    pythonPath: config.get<string>(CONFIG_KEYS.PYTHON_PATH, DEFAULTS.PYTHON_PATH),
    cvaBackendPath: config.get<string>(CONFIG_KEYS.CVA_BACKEND_PATH, ''),
    constitutionPath: config.get<string>(CONFIG_KEYS.CONSTITUTION_PATH, ''),
    watchPatterns: config.get<string[]>(CONFIG_KEYS.WATCH_PATTERNS, [...DEFAULT_WATCH_PATTERNS]),
    ignorePatterns: config.get<string[]>(CONFIG_KEYS.IGNORE_PATTERNS, [...DEFAULT_IGNORE_PATTERNS]),
    showInlineHints: config.get<boolean>(CONFIG_KEYS.SHOW_INLINE_HINTS, true),
    autoVerifyOnSave: config.get<boolean>(CONFIG_KEYS.AUTO_VERIFY_ON_SAVE, true),
    maxRestartAttempts: config.get<number>(CONFIG_KEYS.MAX_RESTART_ATTEMPTS, DEFAULTS.MAX_RESTART_ATTEMPTS),
    healthCheckIntervalMs: config.get<number>(CONFIG_KEYS.HEALTH_CHECK_INTERVAL_MS, DEFAULTS.HEALTH_CHECK_INTERVAL_MS),
    // Cloud backend
    useCloudBackend: config.get<boolean>(CONFIG_KEYS.USE_CLOUD_BACKEND, DEFAULTS.USE_CLOUD_BACKEND),
    cloudBackendUrl: config.get<string>(CONFIG_KEYS.CLOUD_BACKEND_URL, DEFAULTS.CLOUD_BACKEND_URL),
    cloudApiToken: config.get<string>(CONFIG_KEYS.CLOUD_API_TOKEN, ''),
  };
}

function handleConfigurationChange(event: vscode.ConfigurationChangeEvent): void {
  if (!event.affectsConfiguration(CONFIG_SECTION)) {
    return;
  }

  outputChannelProvider.info('Configuration changed, reloading...');
  const newConfig = loadConfiguration();

  // Handle specific changes
  if (newConfig.debounceMs !== currentConfig.debounceMs) {
    changeTracker.setDebounceMs(newConfig.debounceMs);
  }

  if (newConfig.backendPort !== currentConfig.backendPort) {
    backendClient.setPort(newConfig.backendPort);
  }

  if (
    JSON.stringify(newConfig.watchPatterns) !== JSON.stringify(currentConfig.watchPatterns)
  ) {
    fileWatcher.updatePatterns([...newConfig.watchPatterns]);
  }

  if (
    JSON.stringify(newConfig.ignorePatterns) !== JSON.stringify(currentConfig.ignorePatterns)
  ) {
    fileWatcher.setIgnorePatterns([...newConfig.ignorePatterns]);
  }

  if (newConfig.enabled !== currentConfig.enabled) {
    statusBarProvider.update(newConfig.enabled ? 'idle' : 'disabled');
  }

  // Handle cloud mode changes
  if (newConfig.useCloudBackend !== currentConfig.useCloudBackend ||
      newConfig.cloudBackendUrl !== currentConfig.cloudBackendUrl ||
      newConfig.cloudApiToken !== currentConfig.cloudApiToken) {
    
    if (newConfig.useCloudBackend) {
      backendClient.setCloudMode(newConfig.cloudBackendUrl, newConfig.cloudApiToken);
      outputChannelProvider.info(`Switched to cloud backend: ${newConfig.cloudBackendUrl}`);
      
      // Stop local backend if running
      if (backendManager.isRunning()) {
        backendManager.stop();
      }
    } else {
      backendClient.setLocalMode(newConfig.backendPort);
      outputChannelProvider.info(`Switched to local backend on port ${newConfig.backendPort}`);
    }
  }

  currentConfig = newConfig;
}

// ============================================================================
// Event Handlers
// ============================================================================

function setupEventHandlers(): void {
  // File watcher events
  fileWatcher.onChange((event) => {
    if (!currentConfig.enabled || !currentConfig.autoVerifyOnSave) {
      return;
    }

    changeTracker.addFile(event);
    statusBarProvider.setPendingCount(changeTracker.getPendingCount());
    
    if (backendManager.isRunning()) {
      statusBarProvider.update('watching');
    }
  });

  // Backend manager events
  backendManager.on('ready', () => {
    outputChannelProvider.info('Backend is ready');
    statusBarProvider.update('watching');
    
    // Connect WebSocket
    backendClient.connectWebSocket();
  });

  backendManager.on('error', (error) => {
    const message = error instanceof Error ? error.message : String(error);
    outputChannelProvider.error(`Backend error: ${message}`);
    statusBarProvider.update('error');
  });

  backendManager.on('restart', (attempt) => {
    outputChannelProvider.warn(`Backend restarting (attempt ${attempt})`);
    statusBarProvider.update('starting');
  });

  backendManager.on('stopped', () => {
    statusBarProvider.update('idle');
  });

  // Backend client WebSocket events
  backendClient.onConnect(() => {
    outputChannelProvider.info('WebSocket connected');
  });

  backendClient.onDisconnect(() => {
    outputChannelProvider.warn('WebSocket disconnected');
  });

  backendClient.onMessage(handleWebSocketMessage);

  backendClient.onError((error) => {
    outputChannelProvider.error(`WebSocket error: ${error.message}`);
  });
}

function handleWebSocketMessage(message: WebSocketMessage): void {
  switch (message.type) {
    case 'status_update':
      const status = message.payload as StatusResponse;
      if (status.run_id === currentRunId) {
        outputChannelProvider.info(`Progress: ${status.phase} (${status.progress}%)`);
        statusBarProvider.update('verifying');
      }
      break;

    case 'verdict_ready':
      const verdict = message.payload as VerdictResponse;
      if (verdict.run_id === currentRunId) {
        handleVerdictReceived(verdict);
      }
      break;

    case 'error':
      const error = message.payload as { message: string; run_id?: string };
      if (!error.run_id || error.run_id === currentRunId) {
        outputChannelProvider.error(`Backend error: ${error.message}`);
        statusBarProvider.update('error');
        sidebarProvider.setError(error.message);
      }
      break;

    case 'connected':
      outputChannelProvider.info('WebSocket session established');
      break;

    case 'heartbeat':
      // Ignore heartbeats
      break;
  }
}

function handleVerdictReceived(verdict: VerdictResponse): void {
  currentRunId = null;

  // Update status bar
  const state = verdict.verdict === 'PASS' ? 'passed' : 'failed';
  statusBarProvider.update(state);

  // Update diagnostics
  if (currentConfig.showInlineHints) {
    diagnosticsProvider.updateFromVerdict(verdict);
  }

  // Update sidebar
  sidebarProvider.update(verdict);

  // Log summary
  outputChannelProvider.info(
    `Verification complete: ${verdict.verdict} (${(verdict.confidence * 100).toFixed(0)}% confidence)`
  );
  
  if (verdict.violations.length > 0) {
    outputChannelProvider.info(`Found ${verdict.violations.length} violation(s)`);
  }

  // Show notification for failures
  if (verdict.verdict === 'FAIL') {
    vscode.window.showWarningMessage(
      `CVA: ${verdict.violations.length} violation(s) found`,
      'Show Details'
    ).then(selection => {
      if (selection === 'Show Details') {
        vscode.commands.executeCommand(`${VIEWS.VERDICTS}.focus`);
      }
    });
  }
}

async function handleVerificationTrigger(files: string[], batch: FileChangeBatch): Promise<void> {
  if (!currentConfig.enabled || !backendManager.isRunning()) {
    outputChannelProvider.warn('Verification skipped: backend not running or extension disabled');
    return;
  }

  outputChannelProvider.info(`Triggering verification for ${files.length} file(s)`);
  
  if (batch.isBulkOperation) {
    outputChannelProvider.info('(Bulk operation detected)');
  }

  statusBarProvider.update('verifying');
  sidebarProvider.setLoading(true);

  try {
    // Get workspace folder
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceFolder) {
      throw new Error('No workspace folder open');
    }

    // Load constitution
    const specContent = await loadConstitution(workspaceFolder);

    // Trigger run
    const result = await backendClient.triggerRun({
      target_dir: workspaceFolder,
      spec_content: specContent,
      files: files.map(f => path.relative(workspaceFolder, f)),
    });

    if (result.success) {
      currentRunId = result.value.run_id;
      outputChannelProvider.info(`Run started: ${currentRunId}`);
    } else {
      throw result.error;
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    outputChannelProvider.error(`Verification failed: ${message}`);
    statusBarProvider.update('error');
    sidebarProvider.setError(message);
  }
}

// ============================================================================
// Commands
// ============================================================================

function registerCommands(context: vscode.ExtensionContext): void {
  // Start backend
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.START, async () => {
      await startBackend(context);
    })
  );

  // Stop backend
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.STOP, () => {
      backendManager.stop();
      backendClient.disconnectWebSocket();
      statusBarProvider.update('idle');
      outputChannelProvider.info('Backend stopped by user');
    })
  );

  // Restart backend
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.RESTART, async () => {
      outputChannelProvider.info('Restarting backend...');
      statusBarProvider.update('starting');
      
      const cvaPath = getCvaBackendPath(context);
      await backendManager.restart(cvaPath, currentConfig.pythonPath, currentConfig.backendPort);
    })
  );

  // Verify workspace
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.VERIFY, async () => {
      if (!backendManager.isRunning()) {
        vscode.window.showWarningMessage('CVA backend is not running. Start it first.');
        return;
      }

      // Get all tracked files
      const files = await fileWatcher.getWatchedFiles();
      const paths = files.map(f => f.fsPath);
      
      await handleVerificationTrigger(paths, {
        changes: [],
        isBulkOperation: true,
        duration: 0,
      });
    })
  );

  // Verify current file
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.VERIFY_FILE, async () => {
      if (!backendManager.isRunning()) {
        vscode.window.showWarningMessage('CVA backend is not running. Start it first.');
        return;
      }

      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage('No active file to verify');
        return;
      }

      const filePath = editor.document.uri.fsPath;
      await handleVerificationTrigger([filePath], {
        changes: [],
        isBulkOperation: false,
        duration: 0,
      });
    })
  );

  // Show output
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.SHOW_OUTPUT, () => {
      outputChannelProvider.show();
    })
  );

  // Clear diagnostics
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.CLEAR_DIAGNOSTICS, () => {
      diagnosticsProvider.clear();
      sidebarProvider.clear();
      statusBarProvider.update('watching');
      outputChannelProvider.info('Diagnostics cleared');
    })
  );

  // Open docs
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.OPEN_DOCS, () => {
      const docsUrl = backendClient.getDocsUrl();
      vscode.env.openExternal(vscode.Uri.parse(docsUrl));
    })
  );

  // Select backend path
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.SELECT_BACKEND_PATH, async () => {
      const result = await vscode.window.showOpenDialog({
        canSelectFiles: false,
        canSelectFolders: true,
        canSelectMany: false,
        openLabel: 'Select CVA Backend Folder',
        title: 'Select the dysruption_cva folder containing cva.py',
      });

      if (result && result[0]) {
        const selectedPath = result[0].fsPath;
        
        // Verify it looks like a valid CVA backend
        const cvaFile = path.join(selectedPath, 'cva.py');
        const modulesDir = path.join(selectedPath, 'modules');
        
        if (!fs.existsSync(cvaFile) && !fs.existsSync(modulesDir)) {
          const proceed = await vscode.window.showWarningMessage(
            'This folder does not appear to contain a CVA backend (no cva.py or modules/ found). Use anyway?',
            'Yes', 'No'
          );
          if (proceed !== 'Yes') {
            return;
          }
        }

        // Update configuration
        const config = vscode.workspace.getConfiguration(CONFIG_SECTION);
        await config.update(CONFIG_KEYS.CVA_BACKEND_PATH, selectedPath, vscode.ConfigurationTarget.Workspace);
        
        outputChannelProvider.info(`Backend path set to: ${selectedPath}`);
        vscode.window.showInformationMessage(`CVA backend path updated to: ${selectedPath}`);
        
        // Offer to restart
        const restart = await vscode.window.showInformationMessage(
          'Restart the backend with the new path?',
          'Yes', 'No'
        );
        if (restart === 'Yes') {
          await vscode.commands.executeCommand(COMMANDS.RESTART);
        }
      }
    })
  );

  // Select Python path
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.SELECT_PYTHON_PATH, async () => {
      const options = [
        { label: '$(folder) Browse...', description: 'Select Python executable manually' },
        { label: '$(refresh) Auto-detect', description: 'Scan for virtual environments' },
      ];

      // Try to find available Python interpreters
      const pythonPaths = await findPythonInterpreters();
      for (const pythonPath of pythonPaths) {
        options.push({
          label: `$(symbol-misc) ${path.basename(path.dirname(path.dirname(pythonPath)))}`,
          description: pythonPath,
        });
      }

      const selection = await vscode.window.showQuickPick(options, {
        placeHolder: 'Select Python interpreter for CVA backend',
        title: 'Select Python Interpreter',
      });

      if (!selection) {
        return;
      }

      let selectedPath: string | undefined;

      if (selection.label.includes('Browse')) {
        const result = await vscode.window.showOpenDialog({
          canSelectFiles: true,
          canSelectFolders: false,
          canSelectMany: false,
          openLabel: 'Select Python Executable',
          filters: process.platform === 'win32' 
            ? { 'Executable': ['exe'] }
            : { 'All Files': ['*'] },
        });
        if (result && result[0]) {
          selectedPath = result[0].fsPath;
        }
      } else if (selection.label.includes('Auto-detect')) {
        const cvaPath = getCvaBackendPath(context);
        selectedPath = await getPythonPath(cvaPath);
        vscode.window.showInformationMessage(`Auto-detected: ${selectedPath}`);
      } else {
        selectedPath = selection.description;
      }

      if (selectedPath) {
        const config = vscode.workspace.getConfiguration(CONFIG_SECTION);
        await config.update(CONFIG_KEYS.PYTHON_PATH, selectedPath, vscode.ConfigurationTarget.Workspace);
        
        outputChannelProvider.info(`Python path set to: ${selectedPath}`);
        
        const restart = await vscode.window.showInformationMessage(
          'Restart the backend with the new Python interpreter?',
          'Yes', 'No'
        );
        if (restart === 'Yes') {
          await vscode.commands.executeCommand(COMMANDS.RESTART);
        }
      }
    })
  );

  // Show status
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.SHOW_STATUS, async () => {
      const status = backendManager.getStatus();
      const isConnected = backendClient.isWebSocketConnected();
      const isReady = backendManager.isRunning() && await backendClient.isHealthy();
      
      let statusMessage = `**CVA Status**\n\n`;
      statusMessage += `• Backend: ${status.running ? '✓ Running' : '✗ Stopped'}\n`;
      statusMessage += `• Backend Ready: ${isReady ? '✓ Yes' : '✗ No'}\n`;
      statusMessage += `• WebSocket: ${isConnected ? '✓ Connected' : '✗ Disconnected'}\n`;
      statusMessage += `• Port: ${currentConfig.backendPort}\n`;
      
      if (status.startedAt) {
        const uptime = Math.floor((Date.now() - status.startedAt.getTime()) / 1000);
        statusMessage += `• Uptime: ${uptime}s\n`;
      }
      
      if (status.lastError) {
        statusMessage += `• Last Error: ${status.lastError}\n`;
      }

      // Check backend health
      if (status.running) {
        const health = await backendClient.isHealthy();
        statusMessage += `• Health Check: ${health ? '✓ Healthy' : '✗ Unhealthy'}\n`;
      }

      // Show in quick pick for better formatting
      const items = [
        { label: `Backend: ${status.running ? '✓ Running' : '✗ Stopped'}`, description: '' },
        { label: `WebSocket: ${isConnected ? '✓ Connected' : '✗ Disconnected'}`, description: '' },
        { label: `Port: ${currentConfig.backendPort}`, description: '' },
      ];

      if (status.startedAt) {
        const uptime = Math.floor((Date.now() - status.startedAt.getTime()) / 1000);
        items.push({ label: `Uptime: ${uptime}s`, description: '' });
      }

      vscode.window.showQuickPick(items, {
        placeHolder: 'CVA Extension Status',
        title: 'CVA Status',
      });
    })
  );

  // Create spec file
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.CREATE_SPEC, async () => {
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      
      if (!workspaceFolder) {
        vscode.window.showWarningMessage('Please open a folder first');
        return;
      }

      const specPath = path.join(workspaceFolder, 'spec.txt');
      
      if (fs.existsSync(specPath)) {
        const overwrite = await vscode.window.showWarningMessage(
          'spec.txt already exists. Open it?',
          'Open', 'Cancel'
        );
        if (overwrite === 'Open') {
          const doc = await vscode.workspace.openTextDocument(specPath);
          await vscode.window.showTextDocument(doc);
        }
        return;
      }

      const defaultSpec = `# Project Constitution
# 
# This file defines the rules your code must follow.
# CVA's AI tribunal will verify code against these specifications.
#
# Guidelines:
# - Be specific and measurable
# - Group related rules under headings
# - Use examples where helpful

## Code Quality
- All functions must have docstrings explaining their purpose
- No unused imports or variables
- Functions should do one thing well (single responsibility)

## Security
- No hardcoded API keys, passwords, or secrets
- Validate and sanitize all user input
- Use parameterized queries for database operations

## Error Handling
- All exceptions must be logged with context
- Critical operations must have try-catch blocks
- Provide meaningful error messages to users

## Documentation
- README must include setup instructions
- Complex algorithms should have explanatory comments
- Public APIs should have usage examples

# Add your project-specific rules below:

`;

      fs.writeFileSync(specPath, defaultSpec, 'utf-8');
      
      const doc = await vscode.workspace.openTextDocument(specPath);
      await vscode.window.showTextDocument(doc);
      
      vscode.window.showInformationMessage(
        'Created spec.txt! Customize it with your project rules, then run CVA: Verify.'
      );
    })
  );

  // Open walkthrough
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMANDS.OPEN_WALKTHROUGH, () => {
      vscode.commands.executeCommand(
        'workbench.action.openWalkthrough',
        'dysruption.cva-verifier#cva.welcome',
        false
      );
    })
  );
}

/**
 * Find available Python interpreters on the system
 */
async function findPythonInterpreters(): Promise<string[]> {
  const found: string[] = [];
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

  if (!workspaceFolder) {
    return found;
  }

  const searchLocations = [
    path.join(workspaceFolder, '.venv', 'Scripts', 'python.exe'),
    path.join(workspaceFolder, '.venv', 'bin', 'python'),
    path.join(workspaceFolder, 'venv', 'Scripts', 'python.exe'),
    path.join(workspaceFolder, 'venv', 'bin', 'python'),
    path.join(path.dirname(workspaceFolder), '.venv', 'Scripts', 'python.exe'),
    path.join(path.dirname(workspaceFolder), '.venv', 'bin', 'python'),
  ];

  for (const loc of searchLocations) {
    if (fs.existsSync(loc)) {
      found.push(loc);
    }
  }

  return found;
}

// ============================================================================
// Helper Functions
// ============================================================================

async function startBackend(context: vscode.ExtensionContext): Promise<void> {
  try {
    const cvaPath = getCvaBackendPath(context);
    const pythonPath = await getPythonPath(cvaPath);
    
    outputChannelProvider.info(`Starting backend from: ${cvaPath}`);
    outputChannelProvider.info(`Using Python: ${pythonPath}`);

    const success = await backendManager.start(
      cvaPath,
      pythonPath,
      currentConfig.backendPort
    );

    if (!success) {
      statusBarProvider.update('error');
      vscode.window.showErrorMessage(
        'Failed to start CVA backend. Check the output for details.',
        'Show Output'
      ).then(selection => {
        if (selection === 'Show Output') {
          outputChannelProvider.show();
        }
      });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    outputChannelProvider.error(`Failed to start backend: ${message}`);
    statusBarProvider.update('error');
  }
}

/**
 * Get the Python path, auto-detecting virtual environments
 */
async function getPythonPath(cvaPath: string): Promise<string> {
  // If user configured a specific path, use it
  if (currentConfig.pythonPath && currentConfig.pythonPath !== 'python') {
    if (fs.existsSync(currentConfig.pythonPath)) {
      return currentConfig.pythonPath;
    }
  }

  // Auto-detect virtual environment
  const venvLocations = [
    // Check parent folder (common for monorepo setups)
    path.join(path.dirname(cvaPath), '.venv', 'Scripts', 'python.exe'),
    path.join(path.dirname(cvaPath), '.venv', 'bin', 'python'),
    path.join(path.dirname(cvaPath), 'venv', 'Scripts', 'python.exe'),
    path.join(path.dirname(cvaPath), 'venv', 'bin', 'python'),
    // Check in cva folder itself
    path.join(cvaPath, '.venv', 'Scripts', 'python.exe'),
    path.join(cvaPath, '.venv', 'bin', 'python'),
    path.join(cvaPath, 'venv', 'Scripts', 'python.exe'),
    path.join(cvaPath, 'venv', 'bin', 'python'),
    // Check workspace folder
    ...(vscode.workspace.workspaceFolders?.map(f => 
      path.join(f.uri.fsPath, '.venv', 'Scripts', 'python.exe')
    ) || []),
    ...(vscode.workspace.workspaceFolders?.map(f => 
      path.join(f.uri.fsPath, '.venv', 'bin', 'python')
    ) || []),
  ];

  for (const venvPath of venvLocations) {
    if (fs.existsSync(venvPath)) {
      outputChannelProvider.info(`Found virtual environment: ${venvPath}`);
      return venvPath;
    }
  }

  // Try to get Python from VS Code's Python extension
  try {
    const pythonExtension = vscode.extensions.getExtension('ms-python.python');
    if (pythonExtension?.isActive) {
      const pythonApi = pythonExtension.exports;
      const pythonPath = await pythonApi.settings.getExecutionDetails(
        vscode.workspace.workspaceFolders?.[0]?.uri
      )?.execCommand?.[0];
      if (pythonPath && fs.existsSync(pythonPath)) {
        outputChannelProvider.info(`Using Python from VS Code extension: ${pythonPath}`);
        return pythonPath;
      }
    }
  } catch {
    // Python extension API not available, continue with fallback
  }

  // Fallback to system Python
  outputChannelProvider.warn('No virtual environment found, using system Python');
  return 'python';
}

function getCvaBackendPath(context: vscode.ExtensionContext): string {
  // Check if custom path is configured
  if (currentConfig.cvaBackendPath && fs.existsSync(currentConfig.cvaBackendPath)) {
    return currentConfig.cvaBackendPath;
  }

  // Check workspace for dysruption_cva folder
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (workspaceFolder) {
    const workspaceCvaPath = path.join(workspaceFolder, 'dysruption_cva');
    if (fs.existsSync(workspaceCvaPath)) {
      return workspaceCvaPath;
    }
  }

  // Check extension's bundled backend (for packaged extension)
  const bundledPath = path.join(context.extensionPath, 'cva_backend');
  if (fs.existsSync(bundledPath)) {
    return bundledPath;
  }

  // Fallback: look for dysruption_cva relative to workspace
  if (workspaceFolder) {
    const parentCvaPath = path.join(path.dirname(workspaceFolder), 'dysruption_cva');
    if (fs.existsSync(parentCvaPath)) {
      return parentCvaPath;
    }
  }

  throw new Error(
    'CVA backend not found. Please set cva.cvaBackendPath in settings or place dysruption_cva in your workspace.'
  );
}

async function loadConstitution(workspaceFolder: string): Promise<string> {
  // Check configured path
  if (currentConfig.constitutionPath) {
    const configuredPath = path.isAbsolute(currentConfig.constitutionPath)
      ? currentConfig.constitutionPath
      : path.join(workspaceFolder, currentConfig.constitutionPath);

    if (fs.existsSync(configuredPath)) {
      return fs.readFileSync(configuredPath, 'utf-8');
    }
  }

  // Auto-detect spec files
  const specFiles = [
    'spec.txt',
    '.cva/spec.txt',
    'cva.spec.txt',
    '.cva.yaml',
    'constitution.txt',
  ];

  for (const specFile of specFiles) {
    const specPath = path.join(workspaceFolder, specFile);
    if (fs.existsSync(specPath)) {
      outputChannelProvider.info(`Using constitution: ${specFile}`);
      return fs.readFileSync(specPath, 'utf-8');
    }
  }

  // Check if dysruption_cva has a spec.txt
  const cvaSpecPath = path.join(workspaceFolder, 'dysruption_cva', 'spec.txt');
  if (fs.existsSync(cvaSpecPath)) {
    return fs.readFileSync(cvaSpecPath, 'utf-8');
  }

  // Return default constitution if none found
  outputChannelProvider.warn('No constitution file found, using default rules');
  return `
# Default CVA Constitution

## Code Quality
- All functions must have docstrings
- No unused imports
- No hardcoded credentials or secrets

## Error Handling
- All exceptions must be logged
- Critical operations must have try-catch blocks

## Security
- No SQL injection vulnerabilities
- Input validation required for user data
`;
}
