"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CVAWebSocket, ConnectionStatus } from '@/lib/ws';
import {
  cancelRun,
  fetchPrompt,
  fetchRuns,
  fetchStatus,
  fetchVerdict,
  fetchVerdictsPayload,
  fetchWsToken,
  startRun,
} from '@/lib/api';
import type {
  ConsensusResult,
  PatchSet,
  PipelineStatus,
  PromptRecommendation as PromptData,
  RunListItem,
  RunTelemetry,
  WSMessage,
  WSProgressData,
  WSVerdictData,
} from '@/lib/types';
import type { LiveActivityEvent } from '@/components/LiveActivity';

type StartVerificationArgs = {
  targetPath: string;
  constitution: string;
  allowAutoFix: boolean;
};

type UseCvaRunControllerArgs = {
  onRequireWsTokenLog?: boolean;
};

export function useCvaRunController(_args: UseCvaRunControllerArgs = {}) {
  const [status, setStatus] = useState<PipelineStatus>('idle');
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string>('Ready to analyze');

  const [consensus, setConsensus] = useState<ConsensusResult | null>(null);
  const [patches, setPatches] = useState<PatchSet | null>(null);
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [patchDiff, setPatchDiff] = useState<string | null>(null);
  const [promptData, setPromptData] = useState<PromptData | null>(null);
  const [diagnosticsTelemetry, setDiagnosticsTelemetry] = useState<RunTelemetry | null>(null);

  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  const [wsStatus, setWsStatus] = useState<ConnectionStatus>('disconnected');
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const [activityEvents, setActivityEvents] = useState<LiveActivityEvent[]>([]);

  const wsRef = useRef<CVAWebSocket | null>(null);
  const lastActivityMessageRef = useRef<string>('');
  const pollingNotifiedRef = useRef<string | null>(null);

  const pushActivity = useCallback((kind: LiveActivityEvent['kind'], msg: string) => {
    const ts = Date.now();
    setActivityEvents((prev) => {
      const next: LiveActivityEvent[] = [
        {
          id: `${ts}-${Math.random().toString(16).slice(2)}`,
          ts,
          kind,
          message: msg,
        },
        ...prev,
      ];
      return next.slice(0, 60);
    });
  }, []);

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

  const downloadFile = useCallback((content: string, filename: string, mimeType: string = 'text/plain') => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  const downloadReport = useCallback(() => {
    if (!reportMarkdown) {
      setToastMsg('No report available to download');
      return;
    }
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
    const filename = `cva_report_${currentRunId || 'unknown'}_${timestamp}.md`;
    downloadFile(reportMarkdown, filename, 'text/markdown');
    setToastMsg('Report downloaded successfully');
  }, [currentRunId, downloadFile, reportMarkdown]);

  const downloadPatches = useCallback(() => {
    if (!patchDiff) {
      setToastMsg('No patches available to download');
      return;
    }
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
    const filename = `cva_patches_${currentRunId || 'unknown'}_${timestamp}.diff`;
    downloadFile(patchDiff, filename, 'text/x-diff');
    setToastMsg('Patches downloaded successfully');
  }, [currentRunId, downloadFile, patchDiff]);

  useEffect(() => {
    fetchRuns()
      .then((data) => setRuns(data.runs))
      .catch((e) => console.error('Failed to load runs:', e));
  }, []);

  const handleWsMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === 'status' || msg.type === 'progress') {
        const data = msg.data as WSProgressData;
        setStatus(data.status);
        setProgress(data.progress);
        setMessage(data.message);

        if (typeof data.message === 'string' && data.message && data.message !== lastActivityMessageRef.current) {
          lastActivityMessageRef.current = data.message;
          pushActivity(msg.type === 'progress' ? 'progress' : 'status', data.message);
        }
      }

      if (msg.type === 'verdict') {
        const data = msg.data as WSVerdictData;
        setStatus('complete');
        setProgress(100);
        setMessage(`Analysis complete: ${data.overall_verdict}${data.veto_triggered ? ' (Security Veto)' : ''}`);

        pushActivity(
          'verdict',
          `Verdict: ${data.overall_verdict}${data.veto_triggered ? ` (veto: ${data.veto_reason || 'triggered'})` : ''}`
        );

        if (currentRunId) {
          fetchVerdict(currentRunId)
            .then((resp) => {
              if (resp.ready && resp.consensus) {
                setConsensus(resp.consensus);
                setPatches(resp.patches);
                setReportMarkdown(resp.report_markdown || null);
                setPatchDiff(resp.patch_diff || null);

                fetchDiagnostics(currentRunId);

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
        pushActivity('error', data.error);
      }
    },
    [currentRunId, fetchDiagnostics, pushActivity]
  );

  const stopWs = useCallback(() => {
    wsRef.current?.stop();
    wsRef.current = null;
  }, []);

  useEffect(() => {
    return () => stopWs();
  }, [stopWs]);

  const handleCancelRun = useCallback(async () => {
    if (!currentRunId) return;
    try {
      await cancelRun(currentRunId);
      stopWs();
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
      pushActivity('system', 'Run cancelled');
      setToastMsg('Cancelled run');
    } catch (e: any) {
      setToastMsg(`Failed to cancel: ${e.message}`);
      pushActivity('error', `Cancel failed: ${e.message}`);
    }
  }, [currentRunId, pushActivity, stopWs]);

  const startVerification = useCallback(
    async ({ targetPath, constitution, allowAutoFix }: StartVerificationArgs) => {
      setStatus('scanning');
      setProgress(0);
      setMessage('Starting verification...');
      setConsensus(null);
      setPatches(null);
      setReportMarkdown(null);
      setPatchDiff(null);
      setPromptData(null);
      setDiagnosticsTelemetry(null);
      setActivityEvents([]);
      lastActivityMessageRef.current = '';
      pollingNotifiedRef.current = null;
      pushActivity('system', 'Starting run');

      const specContent = constitution.trim() || undefined;
      const resp = await startRun(targetPath, specContent, undefined, { generatePatches: allowAutoFix });

      setCurrentRunId(resp.run_id);
      setToastMsg('Verification started');
      pushActivity('system', `Run created: ${resp.run_id}`);

      stopWs();
      const ws = new CVAWebSocket();
      ws.onMessage(handleWsMessage);
      ws.onStatusChange((s, detail) => {
        setWsStatus(s);
        if (s === 'reconnecting') setToastMsg(`Reconnecting: ${detail}`);
        pushActivity('system', `WebSocket: ${s}${detail ? ` (${detail})` : ''}`);
      });

      if (process.env.NODE_ENV === 'production') {
        pushActivity('system', 'Requesting WebSocket token');
      }
      const wsToken = await fetchWsToken(resp.run_id);
      if (process.env.NODE_ENV === 'production' && !wsToken) {
        pushActivity('system', 'WebSocket token unavailable; using polling fallback');
      }
      ws.start(resp.run_id, { wsToken: wsToken ?? undefined });
      wsRef.current = ws;

      const runsData = await fetchRuns();
      setRuns(runsData.runs);

      return resp.run_id;
    },
    [handleWsMessage, pushActivity, stopWs]
  );

  const loadRun = useCallback(
    async (runId: string) => {
      try {
        stopWs();
        setWsStatus('disconnected');

        setCurrentRunId(runId);
        setActivityEvents([]);
        lastActivityMessageRef.current = '';
        pollingNotifiedRef.current = null;
        pushActivity('system', `Loading run: ${runId}`);

        const resp = await fetchVerdict(runId);
        if (resp.ready && resp.consensus) {
          setConsensus(resp.consensus);
          setPatches(resp.patches);
          setReportMarkdown(resp.report_markdown || null);
          setPatchDiff(resp.patch_diff || null);
          fetchDiagnostics(runId);
          setStatus('complete');
          setProgress(100);
          setMessage(`Loaded run ${runId}`);
          pushActivity('system', `Loaded completed run: ${runId}`);

          if (resp.consensus.overall_status !== 'pass') {
            const promptResp = await fetchPrompt(runId);
            if (promptResp.ready && promptResp.prompt) {
              setPromptData(promptResp.prompt);
            }
          } else {
            setPromptData(null);
          }
        } else {
          const ws = new CVAWebSocket();
          ws.onMessage(handleWsMessage);
          ws.onStatusChange((s, detail) => {
            setWsStatus(s);
            pushActivity('system', `WebSocket: ${s}${detail ? ` (${detail})` : ''}`);
          });

          if (process.env.NODE_ENV === 'production') {
            pushActivity('system', 'Requesting WebSocket token');
          }
          const wsToken = await fetchWsToken(runId);
          if (process.env.NODE_ENV === 'production' && !wsToken) {
            pushActivity('system', 'WebSocket token unavailable; using polling fallback');
          }
          ws.start(runId, { wsToken: wsToken ?? undefined });
          wsRef.current = ws;
        }

        setShowHistory(false);
      } catch (e: any) {
        setToastMsg(`Failed to load: ${e.message}`);
        pushActivity('error', `Load failed: ${e.message}`);
      }
    },
    [fetchDiagnostics, handleWsMessage, pushActivity, stopWs]
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const runId = new URLSearchParams(window.location.search).get('run');
    if (!runId) return;
    if (currentRunId === runId) return;

    loadRun(runId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRunId]);

  const isRunning = status !== 'idle' && status !== 'complete' && status !== 'error';

  const stageLabel = useMemo(() => {
    const stages: Record<string, string> = {
      scanning: '📁 Scanning files...',
      extracting: '📋 Extracting requirements...',
      parsing: '🔍 Parsing code...',
      analyzing: '🧠 AI Judges analyzing...',
      judging: '⚖️ Deliberating verdicts...',
      deliberating: '🤝 Building consensus...',
      remediating: '🔧 Generating fixes...',
      patching: '📝 Creating patches...',
      static_analysis: '🔬 Running static analysis...',
      complete: '✅ Analysis complete!',
      error: '❌ Error occurred',
    };
    return stages[status] || '⏳ Processing...';
  }, [status]);

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

    const estimatedDuration = 210000;
    const interval = setInterval(() => {
      const elapsed = Date.now() - runStartTime;
      const synthetic = Math.min(95, (elapsed / estimatedDuration) * 100);
      setSyntheticProgress(synthetic);
    }, 500);

    return () => clearInterval(interval);
  }, [isRunning, runStartTime]);

  const displayProgress = Math.max(progress, syntheticProgress);

  useEffect(() => {
    if (!consensus) return;

    setTimeout(() => {
      document.getElementById('results-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);
  }, [consensus]);

  useEffect(() => {
    if (!currentRunId || !isRunning) return;
    if (wsStatus === 'connected') return;

    if (pollingNotifiedRef.current !== currentRunId) {
      pollingNotifiedRef.current = currentRunId;
      pushActivity('system', 'Polling for status (WebSocket disconnected)');
    }

    const pollInterval = setInterval(async () => {
      try {
        const statusResp = await fetchStatus(currentRunId);
        const state = statusResp.state;

        setProgress(state.progress_percent);
        setMessage(state.message);

        if (state.message && state.message !== lastActivityMessageRef.current) {
          lastActivityMessageRef.current = state.message;
          pushActivity('progress', state.message);
        }

        if (state.status === 'complete') {
          setStatus('complete');
          clearInterval(pollInterval);

          try {
            const verdictResp = await fetchVerdict(currentRunId);
            if (verdictResp.ready && verdictResp.consensus) {
              setConsensus(verdictResp.consensus);
              setPatches(verdictResp.patches);
              setReportMarkdown(verdictResp.report_markdown || null);
              setPatchDiff(verdictResp.patch_diff || null);
              fetchDiagnostics(currentRunId);

              if (verdictResp.consensus.overall_status !== 'pass') {
                const promptResp = await fetchPrompt(currentRunId);
                if (promptResp.ready && promptResp.prompt) {
                  setPromptData(promptResp.prompt);
                }
              }
            }
            setToastMsg(`Analysis complete: ${state.message}`);
            pushActivity('verdict', `Complete: ${state.message}`);
          } catch (e) {
            console.error('Failed to fetch verdict:', e);
          }
        } else if (state.status === 'error') {
          setStatus('error');
          clearInterval(pollInterval);
          setToastMsg(`Error: ${state.message}`);
          pushActivity('error', state.message);
        } else {
          const statusMap: Record<string, PipelineStatus> = {
            scanning: 'scanning',
            extracting: 'parsing',
            analyzing: 'judging',
            deliberating: 'judging',
            remediating: 'patching',
            static_analysis: 'static_analysis',
          };
          setStatus(statusMap[state.status] || 'scanning');
        }
      } catch (e) {
        console.error('Polling error:', e);
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [currentRunId, fetchDiagnostics, isRunning, pushActivity, wsStatus]);

  const startNewAnalysis = useCallback(() => {
    setConsensus(null);
    setPatches(null);
    setReportMarkdown(null);
    setPatchDiff(null);
    setPromptData(null);
    setStatus('idle');
    setProgress(0);
    setMessage('Ready to analyze');
    setCurrentRunId(null);
    setDiagnosticsTelemetry(null);
    setActivityEvents([]);
    lastActivityMessageRef.current = '';
    pollingNotifiedRef.current = null;
    stopWs();
    setWsStatus('disconnected');
  }, [stopWs]);

  return {
    // core state
    status,
    progress,
    message,
    isRunning,
    stageLabel,
    displayProgress,

    // results
    consensus,
    patches,
    reportMarkdown,
    patchDiff,
    promptData,
    diagnosticsTelemetry,

    // runs/history
    currentRunId,
    runs,
    showHistory,
    setShowHistory,

    // realtime + UX
    wsStatus,
    activityEvents,
    toastMsg,
    setToastMsg,

    // actions
    startVerification,
    loadRun,
    handleCancelRun,
    downloadReport,
    downloadPatches,
    startNewAnalysis,

    // internals (rarely needed)
    setRuns,
    setCurrentRunId,
    setMessage,
    setStatus,
    setProgress,
  };
}
