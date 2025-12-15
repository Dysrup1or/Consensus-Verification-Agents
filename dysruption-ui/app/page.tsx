"use client";

import { useEffect, useState, useRef, useCallback } from 'react';
import { CVAWebSocket, ConnectionStatus } from '@/lib/ws';
import { startRun, fetchVerdict, fetchRuns, fetchStatus, fetchPrompt, fetchVerdictsPayload, cancelRun } from '@/lib/api';
import {
  PipelineStatus,
  ConsensusResult,
  PatchSet,
  WSMessage,
  WSProgressData,
  WSVerdictData,
  RunListItem,
  PromptRecommendation as PromptData,
  RunTelemetry,
} from '@/lib/types';
import StatusBadge from '@/components/StatusBadge';
import Verdict from '@/components/Verdict';
import PatchDiff from '@/components/PatchDiff';
import Toast from '@/components/Toast';
import FileDropZone from '@/components/FileDropZone';
import ConstitutionInput from '@/components/ConstitutionInput';
import PromptRecommendation from '@/components/PromptRecommendation';
import RunDiagnostics from '@/components/RunDiagnostics';
import CoverageNotesStrip from '@/components/CoverageNotesStrip';
import { 
  Activity, 
  Shield, 
  Play, 
  Clock,
  Zap
} from 'lucide-react';
import { clsx } from 'clsx';

export default function Dashboard() {
  // Pipeline state
  const [status, setStatus] = useState<PipelineStatus>('idle');
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string>('Ready to analyze');
  
  // Results
  const [consensus, setConsensus] = useState<ConsensusResult | null>(null);
  const [patches, setPatches] = useState<PatchSet | null>(null);
  
  // NEW: Raw content for downloads
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [patchDiff, setPatchDiff] = useState<string | null>(null);
  
  // NEW: Prompt recommendation for AI-assisted fixing
  const [promptData, setPromptData] = useState<PromptData | null>(null);

  // Phase 6: diagnostics telemetry (best-effort)
  const [diagnosticsTelemetry, setDiagnosticsTelemetry] = useState<RunTelemetry | null>(null);
  
  // Inputs
  const [targetPath, setTargetPath] = useState<string>('');
  const [constitution, setConstitution] = useState<string>('');

  // Options
  const [allowAutoFix, setAllowAutoFix] = useState<boolean>(true);
  
  // Run management
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  
  // Connection state
  const [wsStatus, setWsStatus] = useState<ConnectionStatus>('disconnected');
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  
  const wsRef = useRef<CVAWebSocket | null>(null);

  const fetchDiagnostics = useCallback(async (runId: string) => {
    try {
      const payload = await fetchVerdictsPayload(runId);
      const telemetry = payload?.telemetry ?? null;
      if (!telemetry || typeof telemetry !== 'object') {
        setDiagnosticsTelemetry(null);
        return;
      }
      setDiagnosticsTelemetry(telemetry as RunTelemetry);
    } catch {
      setDiagnosticsTelemetry(null);
    }
  }, []);

  // Download helper function
  const downloadFile = (content: string, filename: string, mimeType: string = 'text/plain') => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Download Report as Markdown
  const downloadReport = () => {
    if (!reportMarkdown) {
      setToastMsg('No report available to download');
      return;
    }
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
    const filename = `cva_report_${currentRunId || 'unknown'}_${timestamp}.md`;
    downloadFile(reportMarkdown, filename, 'text/markdown');
    setToastMsg('Report downloaded successfully');
  };

  // Download Patches as Diff
  const downloadPatches = () => {
    if (!patchDiff) {
      setToastMsg('No patches available to download');
      return;
    }
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
    const filename = `cva_patches_${currentRunId || 'unknown'}_${timestamp}.diff`;
    downloadFile(patchDiff, filename, 'text/x-diff');
    setToastMsg('Patches downloaded successfully');
  };

  // Load previous runs on mount
  useEffect(() => {
    fetchRuns()
      .then((data) => setRuns(data.runs))
      .catch((e) => console.error('Failed to load runs:', e));
  }, []);

  // Handle WS messages
  const handleWsMessage = useCallback((msg: WSMessage) => {
    if (msg.type === 'status' || msg.type === 'progress') {
      const data = msg.data as WSProgressData;
      setStatus(data.status);
      setProgress(data.progress);
      setMessage(data.message);
    }
    
    if (msg.type === 'verdict') {
      const data = msg.data as WSVerdictData;
      setStatus('complete');
      setProgress(100);
      setMessage(`Analysis complete: ${data.overall_verdict}${data.veto_triggered ? ' (Security Veto)' : ''}`);
      
      if (currentRunId) {
        fetchVerdict(currentRunId)
          .then((resp) => {
            if (resp.ready && resp.consensus) {
              setConsensus(resp.consensus);
              setPatches(resp.patches);
              // NEW: Store raw content for downloads
              setReportMarkdown(resp.report_markdown || null);
              setPatchDiff(resp.patch_diff || null);

              // Phase 6 diagnostics (best-effort)
              fetchDiagnostics(currentRunId);
              
              // Fetch prompt recommendation if verification failed
              if (resp.consensus.overall_status !== 'pass') {
                fetchPrompt(currentRunId)
                  .then((promptResp) => {
                    if (promptResp.ready && promptResp.prompt) {
                      setPromptData(promptResp.prompt);
                    }
                  })
                  .catch((e) => console.error('Failed to fetch prompt:', e));
              } else {
                setPromptData(null);
              }
            }
          })
          .catch((e) => console.error('Failed to fetch verdict:', e));
      }
      
      if (data.veto_triggered) {
        setToastMsg(`Security Veto: ${data.veto_reason || 'Critical security issue detected'}`);
      } else {
        setToastMsg(`Analysis complete: ${data.overall_verdict.toUpperCase()}`);
      }
    }
    
    if (msg.type === 'error') {
      const data = msg.data as { error: string; aborted?: boolean };
      setStatus('error');
      setMessage(data.error);
      setToastMsg(`Error: ${data.error}`);
    }
  }, [currentRunId]);

  const handleCancelRun = async () => {
    if (!currentRunId) return;
    try {
      await cancelRun(currentRunId);
      wsRef.current?.stop();
      setWsStatus('disconnected');
      setStatus('idle');
      setProgress(0);
      setMessage('Run cancelled');
      setConsensus(null);
      setPatches(null);
      setReportMarkdown(null);
      setPatchDiff(null);
      setPromptData(null);
      setDiagnosticsTelemetry(null);
      setToastMsg('Cancelled run');
    } catch (e: any) {
      setToastMsg(`Failed to cancel: ${e.message}`);
    }
  };

  // Handle file selection
  const handleFilesSelected = (files: FileList | null, path?: string) => {
    if (path) {
      setTargetPath(path);
    } else if (files && files.length > 0) {
      const pathStr = `[${files.length} files selected]`;
      setTargetPath(pathStr);
    } else {
      // no-op
    }
  };

  // Path validation helper
  const validateTargetPath = (path: string): { valid: boolean; error?: string; resolvedPath?: string } => {
    // Check for empty
    if (!path || !path.trim()) {
      return { valid: false, error: 'Please enter a path to your project directory' };
    }
    
    const trimmedPath = path.trim();
    
    // Check for file picker placeholder (the dangerous case!)
    if (trimmedPath.startsWith('[') && trimmedPath.endsWith(']')) {
      return { 
        valid: false, 
        error: 'Browser file picker cannot provide the actual path. Please manually enter the absolute path to your project (e.g., C:\\Users\\you\\Projects\\my-app)' 
      };
    }
    
    // Check for relative paths
    if (trimmedPath === '.' || trimmedPath === '..' || trimmedPath.startsWith('./') || trimmedPath.startsWith('../')) {
      return { valid: false, error: 'Relative paths are not allowed. Please enter an absolute path (e.g., C:\\Users\\...)' };
    }
    
    // Check for absolute path (Windows or Unix)
    const isAbsoluteWindows = /^[A-Za-z]:\\/.test(trimmedPath);
    const isAbsoluteUnix = trimmedPath.startsWith('/');
    
    if (!isAbsoluteWindows && !isAbsoluteUnix) {
      return { valid: false, error: 'Please enter an absolute path starting with a drive letter (C:\\...) or forward slash (/...)' };
    }
    
    // Warn if trying to scan CVA itself - BUT allow temp_uploads (user uploaded files)
    const lowerPath = trimmedPath.toLowerCase();
    const isTempUpload = lowerPath.includes('temp_uploads');
    
    if (!isTempUpload) {
      if (lowerPath.includes('consensus verifier agent') || 
          lowerPath.includes('dysruption_cva') || 
          lowerPath.includes('dysruption-ui')) {
        return { valid: false, error: 'Cannot scan the CVA application itself. Please select your target project directory.' };
      }
    }
    
    return { valid: true, resolvedPath: trimmedPath };
  };

  // Start verification
  const handleStartRun = async () => {
    // Validate the path
    const validation = validateTargetPath(targetPath);
    if (!validation.valid) {
      setToastMsg(validation.error || 'Invalid path');
      return;
    }

    try {
      setStatus('scanning');
      setProgress(0);
      setMessage('Starting verification...');
      setConsensus(null);
      setPatches(null);
      setPromptData(null);
      setDiagnosticsTelemetry(null);
      
      const pathToUse = validation.resolvedPath!;
      // Pass constitution text if user provided any rules
      const specContent = constitution.trim() || undefined;
      const resp = await startRun(pathToUse, specContent, undefined, { generatePatches: allowAutoFix });
      
      setCurrentRunId(resp.run_id);
      setToastMsg(`Verification started`);
      
      if (wsRef.current) wsRef.current.stop();
      const ws = new CVAWebSocket();
      ws.onMessage(handleWsMessage);
      ws.onStatusChange((s, detail) => {
        setWsStatus(s);
        if (s === 'reconnecting') setToastMsg(`Reconnecting: ${detail}`);
      });
      ws.start(resp.run_id);
      wsRef.current = ws;
      
      const runsData = await fetchRuns();
      setRuns(runsData.runs);
    } catch (e: any) {
      setStatus('error');
      setMessage(e.message);
      setToastMsg(`Failed: ${e.message}`);
    }
  };

  // Load previous run
  const handleLoadRun = async (runId: string) => {
    try {
      setCurrentRunId(runId);
      const resp = await fetchVerdict(runId);
      if (resp.ready && resp.consensus) {
        setConsensus(resp.consensus);
        setPatches(resp.patches);
        // NEW: Store raw content for downloads
        setReportMarkdown(resp.report_markdown || null);
        setPatchDiff(resp.patch_diff || null);
        // Phase 6 diagnostics (best-effort)
        fetchDiagnostics(runId);
        setStatus('complete');
        setProgress(100);
        setMessage(`Loaded run ${runId}`);
        
        // Fetch prompt recommendation if verification failed
        if (resp.consensus.overall_status !== 'pass') {
          const promptResp = await fetchPrompt(runId);
          if (promptResp.ready && promptResp.prompt) {
            setPromptData(promptResp.prompt);
          }
        } else {
          setPromptData(null);
        }
      } else {
        if (wsRef.current) wsRef.current.stop();
        const ws = new CVAWebSocket();
        ws.onMessage(handleWsMessage);
        ws.onStatusChange((s) => setWsStatus(s));
        ws.start(runId);
        wsRef.current = ws;
      }
      setShowHistory(false);
    } catch (e: any) {
      setToastMsg(`Failed to load: ${e.message}`);
    }
  };

  // Deep link support: /?run=<run_id>
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const runId = new URLSearchParams(window.location.search).get('run');
    if (!runId) return;

    // Avoid re-loading if already on this run.
    if (currentRunId === runId) return;

    // Fire and forget; errors surface via toast.
    handleLoadRun(runId);
    // Intentionally *not* depending on handleLoadRun to avoid recreating effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRunId]);

  useEffect(() => {
    return () => wsRef.current?.stop();
  }, []);

  const isRunning = status !== 'idle' && status !== 'complete' && status !== 'error';

  // Stage labels for user feedback
  const getStageLabel = (status: string): string => {
    const stages: Record<string, string> = {
      'scanning': '📁 Scanning files...',
      'extracting': '📋 Extracting requirements...',
      'parsing': '🔍 Parsing code...',
      'analyzing': '🧠 AI Judges analyzing...',
      'judging': '⚖️ Deliberating verdicts...',
      'deliberating': '🤝 Building consensus...',
      'remediating': '🔧 Generating fixes...',
      'patching': '📝 Creating patches...',
      'static_analysis': '🔬 Running static analysis...',
      'complete': '✅ Analysis complete!',
      'error': '❌ Error occurred'
    };
    return stages[status] || '⏳ Processing...';
  };

  // Synthetic progress based on elapsed time (as backup)
  const [syntheticProgress, setSyntheticProgress] = useState(0);
  const [runStartTime, setRunStartTime] = useState<number | null>(null);

  useEffect(() => {
    if (isRunning && !runStartTime) {
      setRunStartTime(Date.now());
    }
    if (!isRunning) {
      setRunStartTime(null);
      setSyntheticProgress(0);
    }
  }, [isRunning, runStartTime]);

  useEffect(() => {
    if (!isRunning || !runStartTime) return;
    
    const estimatedDuration = 210000; // 3.5 minutes
    const interval = setInterval(() => {
      const elapsed = Date.now() - runStartTime;
      const synthetic = Math.min(95, (elapsed / estimatedDuration) * 100);
      setSyntheticProgress(synthetic);
    }, 500);
    
    return () => clearInterval(interval);
  }, [isRunning, runStartTime]);

  // Use the higher of actual progress or synthetic progress
  const displayProgress = Math.max(progress, syntheticProgress);

  // Auto-scroll to results when complete
  useEffect(() => {
    if (consensus) {
      setTimeout(() => {
        document.getElementById('results-section')?.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }, 300);
    }
  }, [consensus]);

  // HTTP Polling fallback when WebSocket is disconnected
  useEffect(() => {
    if (!currentRunId || !isRunning) return;
    if (wsStatus === 'connected') return; // WS is working, no need to poll

    const pollInterval = setInterval(async () => {
      try {
        const statusResp = await fetchStatus(currentRunId);
        const state = statusResp.state;
        
        setProgress(state.progress_percent);
        setMessage(state.message);
        
        if (state.status === 'complete') {
          setStatus('complete');
          clearInterval(pollInterval);
          
          // Fetch final verdict
          try {
            const verdictResp = await fetchVerdict(currentRunId);
            if (verdictResp.ready && verdictResp.consensus) {
              setConsensus(verdictResp.consensus);
              setPatches(verdictResp.patches);
              // NEW: Store raw content for downloads
              setReportMarkdown(verdictResp.report_markdown || null);
              setPatchDiff(verdictResp.patch_diff || null);

              // Phase 6 diagnostics (best-effort)
              fetchDiagnostics(currentRunId);
              
              // Fetch prompt recommendation if verification failed
              if (verdictResp.consensus.overall_status !== 'pass') {
                const promptResp = await fetchPrompt(currentRunId);
                if (promptResp.ready && promptResp.prompt) {
                  setPromptData(promptResp.prompt);
                }
              }
            }
            setToastMsg(`Analysis complete: ${state.message}`);
          } catch (e) {
            console.error('Failed to fetch verdict:', e);
          }
        } else if (state.status === 'error') {
          setStatus('error');
          clearInterval(pollInterval);
          setToastMsg(`Error: ${state.message}`);
        } else {
          // Map backend status to frontend status
          const statusMap: Record<string, PipelineStatus> = {
            'scanning': 'scanning',
            'extracting': 'parsing',
            'analyzing': 'judging',
            'deliberating': 'judging',
            'remediating': 'patching',
            'static_analysis': 'static_analysis',
          };
          setStatus(statusMap[state.status] || 'scanning');
        }
      } catch (e) {
        console.error('Polling error:', e);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(pollInterval);
  }, [currentRunId, isRunning, wsStatus]);

  const canStart = targetPath && !isRunning;

  return (
    <main className="min-h-screen bg-bg text-textPrimary font-sans">
      {/* Header */}
      <header className="border-b border-border bg-surface/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                <Shield className="w-6 h-6 text-primary" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight">Invariant</h1>
                <p className="text-xs text-textMuted">Invariant • Verification Coach</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface border border-border text-sm">
                <div className={clsx(
                  'w-2 h-2 rounded-full',
                  status === 'complete' ? 'bg-success' :
                  status === 'error' ? 'bg-danger' :
                  isRunning ? 'bg-warning animate-pulse' :
                  'bg-success'
                )} />
                <span className="text-textSecondary">
                  {status === 'idle' ? '🟢 Ready' :
                   status === 'complete' ? '✅ Complete' :
                   status === 'error' ? '❌ Error' :
                   '⏳ Analyzing...'}
                </span>
              </div>

              <button
                onClick={() => setShowHistory(!showHistory)}
                className={clsx(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-colors',
                  showHistory 
                    ? 'bg-primary text-white border-primary' 
                    : 'bg-surface border-border hover:border-primary/50'
                )}
              >
                <Clock size={14} />
                History
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* History Dropdown */}
        {showHistory && runs.length > 0 && (
          <div className="mb-6 p-4 rounded-xl bg-surface border border-border animate-in fade-in slide-in-from-top-2">
            <h3 className="text-sm font-medium text-textSecondary mb-3">Recent Runs</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {runs.slice(0, 12).map((run) => (
                <button
                  key={run.run_id}
                  onClick={() => handleLoadRun(run.run_id)}
                  className={clsx(
                    'text-left p-3 rounded-lg border transition-all text-sm',
                    currentRunId === run.run_id
                      ? 'border-primary bg-primary/10'
                      : 'border-border hover:border-primary/50 bg-bg'
                  )}
                >
                  <p className="font-mono text-xs text-textMuted">{run.run_id}</p>
                  <p className={clsx(
                    'text-xs capitalize mt-1',
                    run.status === 'complete' ? 'text-success' :
                    run.status === 'error' ? 'text-danger' : 'text-warning'
                  )}>
                    {run.status}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Top panels: Action + Progress */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          {/* Left: Primary Action Panel */}
          <section className="p-6 rounded-2xl bg-surface border border-border">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Shield className="w-5 h-5 text-primary" />
                <h2 className="text-lg font-semibold">Primary Action Panel</h2>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className={clsx(
                    'w-2.5 h-2.5 rounded-full',
                    wsStatus === 'connected'
                      ? 'bg-success'
                      : wsStatus === 'reconnecting'
                        ? 'bg-warning animate-pulse'
                        : 'bg-danger'
                  )}
                />
                <span className="text-xs text-textMuted">{wsStatus}</span>
              </div>
            </div>

            <button
              onClick={handleStartRun}
              disabled={!canStart}
              className={clsx(
                'w-full flex items-center justify-center gap-3 px-6 py-5 rounded-xl font-semibold text-lg transition-all',
                'shadow-glow hover:shadow-glow-lg',
                canStart
                  ? 'bg-primary hover:bg-primaryHover text-white'
                  : 'bg-panel text-textMuted cursor-not-allowed'
              )}
              aria-label="Verify Invariant"
            >
              {isRunning ? (
                <>
                  <Zap className="w-5 h-5 animate-pulse" />
                  Running Verification...
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  VERIFY INVARIANT
                </>
              )}
            </button>

            <div className="mt-4 p-4 rounded-xl bg-bg border border-border">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">Allow Auto-Fix (Safe Mode)</p>
                  <p className="text-xs text-textMuted mt-1">
                    When enabled, the run generates patch artifacts and a fix plan. You can review before applying.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setAllowAutoFix((v) => !v)}
                  disabled={isRunning}
                  className={clsx(
                    'relative inline-flex h-6 w-11 items-center rounded-full border transition-colors',
                    allowAutoFix ? 'bg-primary border-primary' : 'bg-panel border-border',
                    isRunning && 'opacity-50 cursor-not-allowed'
                  )}
                  aria-pressed={allowAutoFix}
                  aria-label="Toggle auto-fix"
                >
                  <span
                    className={clsx(
                      'inline-block h-5 w-5 transform rounded-full bg-white transition-transform',
                      allowAutoFix ? 'translate-x-5' : 'translate-x-0.5'
                    )}
                  />
                </button>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              <FileDropZone onFilesSelected={handleFilesSelected} disabled={isRunning} />
              <ConstitutionInput value={constitution} onChange={setConstitution} disabled={isRunning} />
            </div>
          </section>

          {/* Right: Progress + Results Panel */}
          <section className="p-6 rounded-2xl bg-surface border border-border">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Activity className="w-5 h-5 text-primary" />
                <h2 className="text-lg font-semibold">Progress & Results Panel</h2>
              </div>
              <StatusBadge status={status} size="md" />
            </div>

            {isRunning ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm font-medium text-primary">{getStageLabel(status)}</span>
                  {currentRunId && (
                    <button
                      onClick={handleCancelRun}
                      className="ml-auto px-3 py-1.5 rounded-lg border border-border bg-bg text-textPrimary text-xs hover:border-primary/50 transition-colors"
                    >
                      Cancel
                    </button>
                  )}
                </div>

                <div className="w-full h-3 bg-panel rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-primary to-accent transition-all duration-500 ease-out"
                    style={{ width: `${displayProgress}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-xs text-textMuted font-mono">
                  <span>{displayProgress.toFixed(0)}%</span>
                  <span className="text-textSecondary">{message}</span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-textSecondary">{message}</p>
            )}

            <div className="mt-6 grid grid-cols-2 gap-3">
              <div className="p-3 rounded-xl bg-bg border border-border">
                <p className="text-xs text-textMuted uppercase tracking-wider">Coverage</p>
                <p className="text-lg font-semibold">
                  {diagnosticsTelemetry?.coverage
                    ? `${Math.round(diagnosticsTelemetry.coverage.fully_covered_percent_of_changed)}%`
                    : '—'}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-bg border border-border">
                <p className="text-xs text-textMuted uppercase tracking-wider">Cost (tokens)</p>
                <p className="text-lg font-semibold">
                  {diagnosticsTelemetry?.cost
                    ? (
                        diagnosticsTelemetry.cost.lane1_deterministic_tokens +
                        diagnosticsTelemetry.cost.lane2_llm_input_tokens_est +
                        diagnosticsTelemetry.cost.lane2_llm_stable_prefix_tokens_est +
                        diagnosticsTelemetry.cost.lane2_llm_variable_suffix_tokens_est
                      ).toLocaleString()
                    : '—'}
                </p>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-between gap-3">
              <div className="text-xs text-textMuted">
                Run ID: <span className="font-mono">{currentRunId ?? '—'}</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => downloadReport()}
                  disabled={!reportMarkdown}
                  className="px-3 py-1.5 text-xs rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Report
                </button>
                <button
                  onClick={() => downloadPatches()}
                  disabled={!patchDiff}
                  className="px-3 py-1.5 text-xs rounded-lg bg-accent/10 text-accent hover:bg-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Patches
                </button>
              </div>
            </div>
          </section>
        </div>

        {/* Results */}
        {consensus && (
          <section id="results-section" className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Shield className="w-6 h-6 text-primary" />
                <h2 className="text-xl font-bold">Issues & Fix Panel</h2>
                {consensus.veto_triggered && (
                  <span className="px-3 py-1 text-xs rounded-full bg-danger/10 text-danger font-medium">
                    Security Veto
                  </span>
                )}
              </div>
              <div className="text-sm text-textMuted">
                Run ID: <span className="font-mono">{currentRunId}</span>
              </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-surface border border-border">
                <p className="text-xs text-textMuted uppercase tracking-wider mb-1">Score</p>
                <p className={clsx(
                  'text-3xl font-bold',
                  consensus.weighted_score >= 7 ? 'text-success' :
                  consensus.weighted_score >= 5 ? 'text-warning' : 'text-danger'
                )}>
                  {consensus.weighted_score.toFixed(1)}
                  <span className="text-lg text-textMuted">/10</span>
                </p>
              </div>
              <div className="p-4 rounded-xl bg-surface border border-border">
                <p className="text-xs text-textMuted uppercase tracking-wider mb-1">Invariants</p>
                <p className="text-3xl font-bold">
                  {consensus.invariants_passed}
                  <span className="text-lg text-textMuted">/{consensus.total_invariants}</span>
                </p>
              </div>
              <div className="p-4 rounded-xl bg-surface border border-border">
                <p className="text-xs text-textMuted uppercase tracking-wider mb-1">Files Analyzed</p>
                <p className="text-3xl font-bold">{consensus.files_analyzed}</p>
              </div>
              <div className="p-4 rounded-xl bg-surface border border-border">
                <p className="text-xs text-textMuted uppercase tracking-wider mb-1">Duration</p>
                <p className="text-3xl font-bold">
                  {(consensus.execution_time_ms / 1000).toFixed(1)}
                  <span className="text-lg text-textMuted">s</span>
                </p>
              </div>
            </div>

            {/* Phase 6: Coverage Notes + Diagnostics */}
            {diagnosticsTelemetry?.coverage && (
              <CoverageNotesStrip coverage={diagnosticsTelemetry.coverage} />
            )}
            <RunDiagnostics telemetry={diagnosticsTelemetry} />
            
            <div>
              <h3 className="text-lg font-semibold mb-4">Judge Verdicts</h3>
              <Verdict verdicts={consensus.verdicts} vetoTriggered={consensus.veto_triggered} />
            </div>

            {patches && patches.patches.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  Suggested Fixes
                  <span className="px-2 py-0.5 text-xs rounded-full bg-accent/10 text-accent">
                    {patches.patches.length} patches
                  </span>
                </h3>
                <div className="space-y-4">
                  {patches.patches.map((patch, i) => (
                    <PatchDiff key={i} patch={patch} />
                  ))}
                </div>
              </div>
            )}

            {/* AI Fix Prompt - Only shown when verification fails */}
            {promptData && currentRunId && (
              <div>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  AI-Assisted Fixes
                  <span className="px-2 py-0.5 text-xs rounded-full bg-primary/10 text-primary">
                    Copy & Paste
                  </span>
                </h3>
                <PromptRecommendation prompt={promptData} runId={currentRunId} />
              </div>
            )}

            {/* Next Steps CTA */}
            <div className="p-6 rounded-xl bg-gradient-to-r from-primary/10 to-accent/10 border border-primary/20">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold mb-1">What&apos;s Next?</h3>
                  <p className="text-sm text-textSecondary">
                    {consensus.overall_status === 'pass' 
                      ? 'Your code passed verification! Consider adding more requirements or testing different scenarios.'
                      : 'Download the report for detailed findings, or use the patches to fix issues automatically.'}
                  </p>
                </div>
                <div className="flex gap-3">
                  {reportMarkdown && (
                    <button
                      onClick={() => downloadReport()}
                      className="px-4 py-2 rounded-lg bg-primary text-white font-medium hover:bg-primaryHover transition-colors flex items-center gap-2"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                      Download Report
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setTargetPath('');
                      setConsensus(null);
                      setPatches(null);
                      setReportMarkdown(null);
                      setPatchDiff(null);
                      setPromptData(null);
                      setStatus('idle');
                      setProgress(0);
                      setMessage('Ready to analyze');
                      setCurrentRunId(null);
                    }}
                    className="px-4 py-2 rounded-lg border border-border bg-surface text-textPrimary font-medium hover:border-primary/50 transition-colors"
                  >
                    Start New Analysis
                  </button>
                </div>
              </div>
            </div>
          </section>
        )}
      </div>

      <Toast message={toastMsg} onDismiss={() => setToastMsg(null)} />
    </main>
  );
}
