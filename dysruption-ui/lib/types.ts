// =============================================================================
// ENUMS (match backend schemas.py)
// =============================================================================

export type VerdictStatus = 'pass' | 'fail' | 'partial' | 'error' | 'skipped' | 'veto';

export type JudgeRole = 'architect' | 'security' | 'user_proxy';

export type PipelineStatus =
  | 'idle'
  | 'watching'
  | 'scanning'
  | 'parsing'
  | 'static_analysis'
  | 'judging'
  | 'patching'
  | 'complete'
  | 'error';

export type InvariantCategory =
  | 'security'
  | 'functionality'
  | 'style'
  | 'performance'
  | 'architecture'
  | 'documentation';

export type InvariantSeverity = 'critical' | 'high' | 'medium' | 'low';

// =============================================================================
// JUDGE & VERDICT MODELS
// =============================================================================

export interface IssueDetail {
  description: string;
  file_path?: string;
  line_number?: number;
  suggestion?: string;
  invariant_id?: number;
}

export interface JudgeVerdict {
  judge_role: JudgeRole;
  model_used: string;
  status: VerdictStatus;
  score: number; // 0-10
  confidence: number; // 0-1
  explanation: string;
  issues: IssueDetail[];
  suggestions: string[];
  invariants_checked: number[];
  execution_time_ms: number;
}

export interface StaticAnalysisResult {
  tool: string;
  passed: boolean;
  critical_issues: number;
  total_issues: number;
  issues: Record<string, any>[];
  execution_time_ms: number;
  aborted_pipeline: boolean;
}

export interface ConsensusResult {
  timestamp: string;
  overall_status: VerdictStatus;
  weighted_score: number; // 0-10
  confidence: number; // 0-1
  verdicts: Record<string, JudgeVerdict>;
  veto_triggered: boolean;
  veto_reason?: string | null;
  static_analysis: StaticAnalysisResult[];
  static_analysis_aborted: boolean;
  total_invariants: number;
  invariants_passed: number;
  execution_time_ms: number;
  files_analyzed: number;
}

// =============================================================================
// PATCH MODELS
// =============================================================================

export interface Patch {
  file_path: string;
  original_content: string;
  patched_content: string;
  unified_diff: string;
  issues_addressed: number[];
  confidence: number;
  requires_review: boolean;
  generated_by: string;
  generation_time_ms: number;
}

export interface PatchSet {
  patches: Patch[];
  total_issues_addressed: number;
  generation_timestamp: string;
  estimated_fix_coverage: number;
}

// =============================================================================
// PIPELINE MODELS
// =============================================================================

export interface PipelineState {
  status: PipelineStatus;
  current_phase: string;
  progress_percent: number;
  message: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

// =============================================================================
// API RESPONSE MODELS
// =============================================================================

export interface RunResponse {
  run_id: string;
  status: PipelineStatus;
  message: string;
}

export interface StatusResponse {
  run_id: string;
  state: PipelineState;
}

export interface VerdictResponse {
  run_id: string;
  consensus: ConsensusResult | null;
  patches: PatchSet | null;
  ready: boolean;
  // NEW: Raw content for downloads
  report_markdown?: string | null;
  patch_diff?: string | null;
}

export interface RunListItem {
  run_id: string;
  status: string;
  progress: number;
  started_at: string | null;
  target_dir: string;
}

export interface RunListResponse {
  runs: RunListItem[];
  total: number;
}

// =============================================================================
// WEBSOCKET MODELS
// =============================================================================

export interface WSProgressData {
  status: PipelineStatus;
  phase: string;
  progress: number;
  message: string;
}

export interface WSVerdictData {
  overall_verdict: string;
  overall_score: number;
  passed: number;
  failed: number;
  total: number;
  veto_triggered: boolean;
  veto_reason?: string | null;
  execution_time: number;
}

export interface WSMessage {
  type: 'status' | 'progress' | 'verdict' | 'error' | 'ping' | 'pong';
  run_id: string;
  timestamp?: string;
  data: WSProgressData | WSVerdictData | { error: string; aborted?: boolean } | Record<string, any>;
}

// =============================================================================
// INVARIANT (for SpecView)
// =============================================================================

export interface Invariant {
  id: number;
  description: string;
  category: InvariantCategory;
  severity: InvariantSeverity;
  keywords?: string[];
  source_line?: string | null;
}

// =============================================================================
// PROMPT RECOMMENDATION MODELS
// =============================================================================

export interface PriorityIssue {
  severity: string;
  category: string;
  description: string;
  file_path?: string;
  line_number?: number;
  judge_source?: string;
  suggestion?: string;
}

export interface PromptRecommendation {
  primary_prompt: string;
  priority_issues: PriorityIssue[];
  strategy: string;
  complexity: string;
  alternative_prompts: string[];
  context_files: string[];
  estimated_tokens: number;
  generation_time_ms: number;
  veto_addressed: boolean;
}

export interface PromptResponse {
  run_id: string;
  ready: boolean;
  message: string;
  prompt: PromptRecommendation | null;
}

// =============================================================================
// TRIBUNAL VERDICTS PAYLOAD (Phase 6 UI diagnostics)
// =============================================================================

export interface TelemetryCoverage {
  fully_covered_percent_of_changed: number;
  changed_files_total: number;
  changed_files_fully_covered_count: number;
  header_covered_count: number;
  forced_files_count: number;
  skip_reasons: Record<string, string>;
}

export interface TelemetryRouter {
  lane_used: string;
  provider: string;
  model: string;
  fallback_chain: Array<Record<string, string>>;
}

export interface TelemetryCache {
  cached_vs_uncached: 'unknown' | 'cached' | 'uncached' | string;
  intent?: string | null;
  provider_cache_signal?: string | null;
}

export interface TelemetryLatency {
  lane2_llm_batch_size?: number | null;
  lane2_llm_batch_mode?: string | null;
  lane2_llm_per_item_latency_ms?: number[] | null;
}

export interface TelemetryCost {
  lane1_deterministic_tokens: number;
  lane2_llm_input_tokens_est: number;
  lane2_llm_stable_prefix_tokens_est: number;
  lane2_llm_variable_suffix_tokens_est: number;
}

export interface RunTelemetry {
  coverage: TelemetryCoverage;
  cost?: TelemetryCost;
  router?: TelemetryRouter | null;
  cache: TelemetryCache;
  latency: TelemetryLatency;
}

export interface VerdictsPayload {
  telemetry?: RunTelemetry | null;
  [key: string]: any;
}
