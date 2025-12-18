/**
 * CVA Extension Constants
 * 
 * Centralized configuration constants and default values.
 */

// ============================================================================
// Extension Identifiers
// ============================================================================

export const EXTENSION_ID = 'dysruption.cva-verifier';
export const EXTENSION_NAME = 'CVA Verifier';
export const OUTPUT_CHANNEL_NAME = 'CVA Verifier';

// ============================================================================
// Command IDs
// ============================================================================

export const COMMANDS = {
  START: 'cva.start',
  STOP: 'cva.stop',
  RESTART: 'cva.restart',
  VERIFY: 'cva.verify',
  VERIFY_FILE: 'cva.verifyFile',
  SHOW_OUTPUT: 'cva.showOutput',
  CLEAR_DIAGNOSTICS: 'cva.clearDiagnostics',
  OPEN_DOCS: 'cva.openDocs',
  SELECT_BACKEND_PATH: 'cva.selectBackendPath',
  SELECT_PYTHON_PATH: 'cva.selectPythonPath',
  SHOW_STATUS: 'cva.showStatus',
  CREATE_SPEC: 'cva.createSpec',
  OPEN_WALKTHROUGH: 'cva.openWalkthrough',
} as const;

// ============================================================================
// View IDs
// ============================================================================

export const VIEWS = {
  VERDICTS: 'cvaVerdicts',
} as const;

// ============================================================================
// Configuration Keys
// ============================================================================

export const CONFIG_SECTION = 'cva';

export const CONFIG_KEYS = {
  ENABLED: 'enabled',
  DEBOUNCE_MS: 'debounceMs',
  BACKEND_PORT: 'backendPort',
  AUTO_START_BACKEND: 'autoStartBackend',
  PYTHON_PATH: 'pythonPath',
  CVA_BACKEND_PATH: 'cvaBackendPath',
  CONSTITUTION_PATH: 'constitutionPath',
  WATCH_PATTERNS: 'watchPatterns',
  IGNORE_PATTERNS: 'ignorePatterns',
  SHOW_INLINE_HINTS: 'showInlineHints',
  AUTO_VERIFY_ON_SAVE: 'autoVerifyOnSave',
  MAX_RESTART_ATTEMPTS: 'maxRestartAttempts',
  HEALTH_CHECK_INTERVAL_MS: 'healthCheckIntervalMs',
  // Cloud backend options
  USE_CLOUD_BACKEND: 'useCloudBackend',
  CLOUD_BACKEND_URL: 'cloudBackendUrl',
  CLOUD_API_TOKEN: 'cloudApiToken',
} as const;

// ============================================================================
// Default Configuration Values
// ============================================================================

export const DEFAULTS = {
  ENABLED: true,
  DEBOUNCE_MS: 3000,
  BACKEND_PORT: 8001,
  AUTO_START_BACKEND: true,
  PYTHON_PATH: 'python',
  MAX_RESTART_ATTEMPTS: 3,
  HEALTH_CHECK_INTERVAL_MS: 30000,
  HEALTH_CHECK_TIMEOUT_MS: 5000,
  BACKEND_STARTUP_TIMEOUT_MS: 30000,
  WEBSOCKET_RECONNECT_DELAY_MS: 5000,
  WEBSOCKET_MAX_RECONNECT_ATTEMPTS: 10,
  HTTP_TIMEOUT_MS: 30000,
  // Cloud backend
  USE_CLOUD_BACKEND: false,
  CLOUD_BACKEND_URL: 'https://invariant.dysrupt-ion.com',
  CLOUD_BACKEND_URL_STAGING: 'https://staging.invariant.dysrupt-ion.com',
} as const;

// ============================================================================
// File Patterns
// ============================================================================

export const DEFAULT_WATCH_PATTERNS = [
  '**/*.py',
  '**/*.js',
  '**/*.ts',
  '**/*.jsx',
  '**/*.tsx',
  '**/*.java',
  '**/*.go',
  '**/*.rs',
] as const;

export const DEFAULT_IGNORE_PATTERNS = [
  '**/node_modules/**',
  '**/.git/**',
  '**/__pycache__/**',
  '**/.venv/**',
  '**/venv/**',
  '**/dist/**',
  '**/build/**',
  '**/out/**',
  '**/.next/**',
  '**/.cache/**',
  '**/coverage/**',
  '**/*.min.js',
  '**/*.min.css',
] as const;

// ============================================================================
// Backend API Endpoints
// ============================================================================

export const API_ENDPOINTS = {
  HEALTH: '/health',
  RUN: '/run',
  STATUS: '/status',
  VERDICT: '/verdict',
  DOCS: '/docs',
  WEBSOCKET: '/ws',
} as const;

// ============================================================================
// Status Bar Icons
// ============================================================================

export const STATUS_ICONS = {
  IDLE: '$(circle-outline)',
  STARTING: '$(loading~spin)',
  WATCHING: '$(eye)',
  VERIFYING: '$(sync~spin)',
  PASSED: '$(check)',
  FAILED: '$(warning)',
  ERROR: '$(error)',
  DISABLED: '$(circle-slash)',
} as const;

// ============================================================================
// Diagnostic Source
// ============================================================================

export const DIAGNOSTIC_SOURCE = 'CVA';
export const DIAGNOSTIC_COLLECTION_NAME = 'cva-violations';

// ============================================================================
// Bulk Change Detection
// ============================================================================

export const BULK_CHANGE = {
  /** Number of files to consider a bulk operation */
  THRESHOLD: 5,
  /** Time window in ms to detect bulk operations */
  WINDOW_MS: 500,
  /** Extended debounce multiplier for bulk operations */
  DEBOUNCE_MULTIPLIER: 2,
  /** Maximum debounce time in ms */
  MAX_DEBOUNCE_MS: 10000,
} as const;

// ============================================================================
// Retry Configuration
// ============================================================================

export const RETRY = {
  /** Initial delay for exponential backoff */
  INITIAL_DELAY_MS: 1000,
  /** Maximum delay between retries */
  MAX_DELAY_MS: 30000,
  /** Backoff multiplier */
  MULTIPLIER: 2,
  /** Maximum number of retries */
  MAX_ATTEMPTS: 3,
} as const;

// ============================================================================
// Log Prefixes
// ============================================================================

export const LOG_PREFIX = {
  INFO: '[CVA]',
  WARN: '[CVA WARN]',
  ERROR: '[CVA ERROR]',
  DEBUG: '[CVA DEBUG]',
} as const;
