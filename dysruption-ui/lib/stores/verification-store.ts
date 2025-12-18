/**
 * Verification Store
 * 
 * Zustand store for managing the current verification run state.
 * Tracks real-time progress and tribunal verdicts.
 */

import { create } from 'zustand';

export type VerificationPhase = 
  | 'idle'
  | 'analyzing'
  | 'coverage-plan'
  | 'test-generation'
  | 'test-execution'
  | 'tribunal'
  | 'complete';

export type VerdictResult = 'pass' | 'fail' | 'partial' | 'veto' | 'pending';

export interface JudgeVerdict {
  judgeId: string;
  judgeName: string;
  judgeEmoji: string;
  verdict: VerdictResult;
  confidence: number;
  reasoning: string;
  criteria: string[];
  vetoReason?: string;
}

export interface VerificationCriterion {
  id: string;
  description: string;
  status: VerdictResult;
  judgeId?: string;
}

export interface VerificationRun {
  id: string;
  projectId: string;
  startedAt: string;
  completedAt?: string;
  phase: VerificationPhase;
  progress: number; // 0-100
  
  // Coverage
  filesAnalyzed: number;
  totalFiles: number;
  testsGenerated: number;
  testsExecuted: number;
  testsPassed: number;
  testsFailed: number;
  
  // Tribunal
  judgeVerdicts: JudgeVerdict[];
  criteria: VerificationCriterion[];
  finalVerdict: VerdictResult;
  
  // Logs
  logs: Array<{ timestamp: string; level: 'info' | 'warn' | 'error'; message: string }>;
}

export interface VerificationState {
  // Current run
  currentRun: VerificationRun | null;
  isRunning: boolean;
  
  // History
  recentRuns: VerificationRun[];
  
  // WebSocket connection
  wsConnected: boolean;
  
  // Actions
  startRun: (projectId: string) => void;
  updatePhase: (phase: VerificationPhase) => void;
  updateProgress: (progress: number) => void;
  updateTestStats: (stats: Partial<Pick<VerificationRun, 'testsGenerated' | 'testsExecuted' | 'testsPassed' | 'testsFailed'>>) => void;
  addJudgeVerdict: (verdict: JudgeVerdict) => void;
  addCriterion: (criterion: VerificationCriterion) => void;
  updateCriterion: (id: string, status: VerdictResult) => void;
  setFinalVerdict: (verdict: VerdictResult) => void;
  completeRun: () => void;
  cancelRun: () => void;
  addLog: (level: 'info' | 'warn' | 'error', message: string) => void;
  setWsConnected: (connected: boolean) => void;
  reset: () => void;
}

const createEmptyRun = (projectId: string): VerificationRun => ({
  id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2),
  projectId,
  startedAt: new Date().toISOString(),
  phase: 'analyzing',
  progress: 0,
  filesAnalyzed: 0,
  totalFiles: 0,
  testsGenerated: 0,
  testsExecuted: 0,
  testsPassed: 0,
  testsFailed: 0,
  judgeVerdicts: [],
  criteria: [],
  finalVerdict: 'pending',
  logs: [],
});

export const useVerificationStore = create<VerificationState>((set, get) => ({
  // Initial state
  currentRun: null,
  isRunning: false,
  recentRuns: [],
  wsConnected: false,

  // Actions
  startRun: (projectId) => {
    const newRun = createEmptyRun(projectId);
    set({
      currentRun: newRun,
      isRunning: true,
    });
  },

  updatePhase: (phase) => set((state) => ({
    currentRun: state.currentRun
      ? { ...state.currentRun, phase }
      : null,
  })),

  updateProgress: (progress) => set((state) => ({
    currentRun: state.currentRun
      ? { ...state.currentRun, progress: Math.min(100, Math.max(0, progress)) }
      : null,
  })),

  updateTestStats: (stats) => set((state) => ({
    currentRun: state.currentRun
      ? { ...state.currentRun, ...stats }
      : null,
  })),

  addJudgeVerdict: (verdict) => set((state) => ({
    currentRun: state.currentRun
      ? {
          ...state.currentRun,
          judgeVerdicts: [...state.currentRun.judgeVerdicts, verdict],
        }
      : null,
  })),

  addCriterion: (criterion) => set((state) => ({
    currentRun: state.currentRun
      ? {
          ...state.currentRun,
          criteria: [...state.currentRun.criteria, criterion],
        }
      : null,
  })),

  updateCriterion: (id, status) => set((state) => ({
    currentRun: state.currentRun
      ? {
          ...state.currentRun,
          criteria: state.currentRun.criteria.map((c) =>
            c.id === id ? { ...c, status } : c
          ),
        }
      : null,
  })),

  setFinalVerdict: (verdict) => set((state) => ({
    currentRun: state.currentRun
      ? { ...state.currentRun, finalVerdict: verdict }
      : null,
  })),

  completeRun: () => {
    const { currentRun, recentRuns } = get();
    if (currentRun) {
      const completedRun: VerificationRun = {
        ...currentRun,
        phase: 'complete',
        progress: 100,
        completedAt: new Date().toISOString(),
      };
      set({
        currentRun: completedRun,
        isRunning: false,
        recentRuns: [completedRun, ...recentRuns].slice(0, 10),
      });
    }
  },

  cancelRun: () => set({
    currentRun: null,
    isRunning: false,
  }),

  addLog: (level, message) => set((state) => ({
    currentRun: state.currentRun
      ? {
          ...state.currentRun,
          logs: [
            ...state.currentRun.logs,
            { timestamp: new Date().toISOString(), level, message },
          ],
        }
      : null,
  })),

  setWsConnected: (connected) => set({ wsConnected: connected }),

  reset: () => set({
    currentRun: null,
    isRunning: false,
    recentRuns: [],
    wsConnected: false,
  }),
}));
