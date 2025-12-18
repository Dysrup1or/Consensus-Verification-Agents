/**
 * CVA Extension Type Definitions
 * 
 * This file contains all TypeScript interfaces and types used across the extension.
 */

// ============================================================================
// Backend Communication Types
// ============================================================================

/**
 * Request body for triggering a verification run
 */
export interface RunRequest {
  /** Directory containing files to verify */
  target_dir: string;
  /** Constitution/specification content as string */
  spec_content: string;
  /** Optional list of specific judges to use */
  judges?: string[];
  /** Optional list of specific files to verify (relative paths) */
  files?: string[];
}

/**
 * Response from POST /run endpoint
 */
export interface RunResponse {
  /** Unique identifier for this verification run */
  run_id: string;
  /** Current status of the run */
  status: RunStatus;
  /** Human-readable message */
  message?: string;
}

/**
 * Status of a verification run
 */
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

/**
 * Response from GET /status/:run_id endpoint
 */
export interface StatusResponse {
  /** Run identifier */
  run_id: string;
  /** Current status */
  status: RunStatus;
  /** Current phase of execution */
  phase: VerificationPhase;
  /** Progress percentage (0-100) */
  progress: number;
  /** Optional message about current activity */
  message?: string;
  /** Timestamp of last update */
  updated_at?: string;
}

/**
 * Phases of the verification pipeline
 */
export type VerificationPhase = 
  | 'initializing'
  | 'parsing_constitution'
  | 'analyzing_files'
  | 'running_tribunal'
  | 'aggregating_verdicts'
  | 'generating_recommendations'
  | 'completed'
  | 'failed';

/**
 * A single violation detected by the tribunal
 */
export interface Violation {
  /** Absolute or relative file path */
  file: string;
  /** Line number (1-based) */
  line: number;
  /** Column number (0-based) */
  column: number;
  /** Invariant ID or name that was violated */
  invariant: string;
  /** Human-readable violation message */
  message: string;
  /** Severity level */
  severity: ViolationSeverity;
  /** Optional code snippet showing the violation */
  code_snippet?: string;
  /** Optional fix recommendation */
  suggestion?: string;
}

/**
 * Violation severity levels
 */
export type ViolationSeverity = 'error' | 'warning' | 'info' | 'hint';

/**
 * Response from GET /verdict/:run_id endpoint
 */
export interface VerdictResponse {
  /** Run identifier */
  run_id: string;
  /** Final verdict from tribunal consensus */
  verdict: VerdictResult;
  /** Confidence score (0.0 - 1.0) */
  confidence: number;
  /** List of violations found */
  violations: Violation[];
  /** AI-generated fix recommendations */
  recommendations: string[];
  /** Number of judges that participated */
  judge_count?: number;
  /** Individual judge votes (for transparency) */
  judge_votes?: JudgeVote[];
  /** Timestamp when verdict was rendered */
  completed_at?: string;
}

/**
 * Possible verdict outcomes
 */
export type VerdictResult = 'PASS' | 'FAIL' | 'INCONCLUSIVE';

/**
 * Individual judge's vote
 */
export interface JudgeVote {
  /** Judge identifier (e.g., "gpt-4o", "claude-sonnet") */
  judge_id: string;
  /** Judge's verdict */
  verdict: VerdictResult;
  /** Judge's confidence in their verdict */
  confidence: number;
  /** Optional reasoning */
  reasoning?: string;
}

// ============================================================================
// WebSocket Message Types
// ============================================================================

/**
 * WebSocket message received from backend
 */
export interface WebSocketMessage {
  /** Type of message */
  type: WebSocketMessageType;
  /** Message payload */
  payload: WebSocketPayload;
}

/**
 * Types of WebSocket messages
 */
export type WebSocketMessageType = 
  | 'connected'
  | 'status_update'
  | 'verdict_ready'
  | 'error'
  | 'heartbeat';

/**
 * Union type for WebSocket payloads
 */
export type WebSocketPayload = 
  | ConnectedPayload
  | StatusResponse
  | VerdictResponse
  | ErrorPayload
  | HeartbeatPayload;

export interface ConnectedPayload {
  message: string;
  server_version?: string;
}

export interface ErrorPayload {
  run_id?: string;
  message: string;
  error_code?: string;
}

export interface HeartbeatPayload {
  timestamp: string;
}

// ============================================================================
// Extension State Types
// ============================================================================

/**
 * Current state of the extension
 */
export interface ExtensionState {
  /** Whether the backend is currently running */
  backendRunning: boolean;
  /** Whether the backend is healthy (responding to health checks) */
  backendHealthy: boolean;
  /** Current run ID if verification is in progress */
  currentRunId: string | null;
  /** Set of files with unsaved/pending changes */
  dirtyFiles: Set<string>;
  /** Last verdict received */
  lastVerdict: VerdictResponse | null;
  /** Extension enabled state */
  enabled: boolean;
  /** Error message if any */
  lastError: string | null;
}

/**
 * Status bar states
 */
export type StatusBarState = 
  | 'idle'
  | 'starting'
  | 'watching'
  | 'verifying'
  | 'passed'
  | 'failed'
  | 'error'
  | 'disabled';

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Extension configuration from VS Code settings
 */
export interface CVAConfig {
  /** Enable/disable the extension */
  enabled: boolean;
  /** Debounce time in milliseconds */
  debounceMs: number;
  /** Backend server port */
  backendPort: number;
  /** Auto-start backend on activation */
  autoStartBackend: boolean;
  /** Path to Python interpreter */
  pythonPath: string;
  /** Path to CVA backend directory */
  cvaBackendPath: string;
  /** Path to constitution file */
  constitutionPath: string;
  /** File patterns to watch */
  watchPatterns: string[];
  /** Patterns to ignore */
  ignorePatterns: string[];
  /** Show inline diagnostic hints */
  showInlineHints: boolean;
  /** Auto-verify on file save */
  autoVerifyOnSave: boolean;
  /** Maximum backend restart attempts */
  maxRestartAttempts: number;
  /** Health check interval in milliseconds */
  healthCheckIntervalMs: number;
  /** Use cloud backend instead of local */
  useCloudBackend: boolean;
  /** Cloud backend URL */
  cloudBackendUrl: string;
  /** Cloud API token */
  cloudApiToken: string;
}

// ============================================================================
// Backend Manager Types
// ============================================================================

/**
 * Backend process status
 */
export interface BackendStatus {
  /** Process is running */
  running: boolean;
  /** Process ID if running */
  pid?: number;
  /** Port the server is listening on */
  port: number;
  /** Number of restart attempts */
  restartCount: number;
  /** Last error if any */
  lastError?: string;
  /** Time when backend started */
  startedAt?: Date;
}

/**
 * Events emitted by BackendManager
 */
export interface BackendManagerEvents {
  started: () => void;
  stopped: () => void;
  ready: () => void;
  error: (error: Error) => void;
  restart: (attempt: number) => void;
  output: (data: string) => void;
}

// ============================================================================
// File Watcher Types
// ============================================================================

/**
 * File change event
 */
export interface FileChangeEvent {
  /** Type of change */
  type: 'create' | 'change' | 'delete';
  /** File URI */
  uri: string;
  /** File path */
  path: string;
  /** Timestamp of change */
  timestamp: Date;
}

/**
 * Batch of file changes (for bulk operations)
 */
export interface FileChangeBatch {
  /** All file changes in this batch */
  changes: FileChangeEvent[];
  /** Whether this appears to be a bulk operation (AI agent, etc.) */
  isBulkOperation: boolean;
  /** Time span of the batch in milliseconds */
  duration: number;
}

// ============================================================================
// Sidebar / TreeView Types
// ============================================================================

/**
 * Types of items in the verdict tree view
 */
export type VerdictTreeItemType = 
  | 'verdict-summary'
  | 'confidence'
  | 'violations-header'
  | 'violation'
  | 'recommendations-header'
  | 'recommendation'
  | 'info'
  | 'error';

/**
 * Data for a verdict tree item
 */
export interface VerdictTreeItemData {
  /** Item type */
  type: VerdictTreeItemType;
  /** Display label */
  label: string;
  /** Optional description */
  description?: string;
  /** Optional tooltip */
  tooltip?: string;
  /** Associated violation (for violation items) */
  violation?: Violation;
  /** Associated recommendation text */
  recommendation?: string;
  /** Icon ID */
  icon?: string;
  /** Collapsible state */
  collapsible?: boolean;
}

// ============================================================================
// Utility Types
// ============================================================================

/**
 * Result type for operations that can fail
 */
export type Result<T, E = Error> = 
  | { success: true; value: T }
  | { success: false; error: E };

/**
 * Async operation with cancellation support
 */
export interface CancellableOperation<T> {
  promise: Promise<T>;
  cancel: () => void;
}

/**
 * Disposable resource
 */
export interface Disposable {
  dispose(): void;
}

/**
 * Logger interface
 */
export interface Logger {
  info(message: string, ...args: unknown[]): void;
  warn(message: string, ...args: unknown[]): void;
  error(message: string, ...args: unknown[]): void;
  debug(message: string, ...args: unknown[]): void;
}
