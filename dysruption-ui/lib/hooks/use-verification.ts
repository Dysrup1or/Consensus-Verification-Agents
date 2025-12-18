/**
 * React Query Hooks for Verification
 * 
 * TanStack Query hooks for verification runs and tribunal verdicts.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { VerificationRun, JudgeVerdict } from '../stores';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Query keys
export const verificationKeys = {
  all: ['verifications'] as const,
  runs: (projectId: string) => [...verificationKeys.all, 'runs', projectId] as const,
  run: (runId: string) => [...verificationKeys.all, 'run', runId] as const,
  verdicts: (runId: string) => [...verificationKeys.run(runId), 'verdicts'] as const,
  criteria: (runId: string) => [...verificationKeys.run(runId), 'criteria'] as const,
};

// Types
export interface StartVerificationParams {
  projectId: string;
  branch?: string;
  commitSha?: string;
  criteria?: string[];
}

export interface VerificationRunSummary {
  id: string;
  projectId: string;
  startedAt: string;
  completedAt?: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  finalVerdict: 'pass' | 'fail' | 'partial' | 'veto' | 'pending';
  passRate: number;
}

// API functions
async function fetchRunHistory(projectId: string): Promise<VerificationRunSummary[]> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/runs`);
  if (!response.ok) {
    throw new Error('Failed to fetch run history');
  }
  return response.json();
}

async function fetchRunDetails(runId: string): Promise<VerificationRun> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch run details');
  }
  return response.json();
}

async function startVerification(params: StartVerificationParams): Promise<{ runId: string }> {
  const response = await fetch(`${API_BASE}/api/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    throw new Error('Failed to start verification');
  }
  return response.json();
}

async function cancelVerification(runId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to cancel verification');
  }
}

async function fetchJudgeVerdicts(runId: string): Promise<JudgeVerdict[]> {
  const response = await fetch(`${API_BASE}/api/runs/${runId}/verdicts`);
  if (!response.ok) {
    throw new Error('Failed to fetch verdicts');
  }
  return response.json();
}

// Hooks

/**
 * Fetch run history for a project
 */
export function useRunHistory(projectId: string | null) {
  return useQuery({
    queryKey: verificationKeys.runs(projectId || ''),
    queryFn: () => fetchRunHistory(projectId!),
    enabled: !!projectId,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Fetch details for a specific run
 */
export function useRunDetails(runId: string | null) {
  return useQuery({
    queryKey: verificationKeys.run(runId || ''),
    queryFn: () => fetchRunDetails(runId!),
    enabled: !!runId,
    staleTime: 5 * 1000, // 5 seconds for active runs
    refetchInterval: (query) => {
      // Poll while running
      const data = query.state.data;
      if (data?.phase && data.phase !== 'complete') {
        return 2000;
      }
      return false;
    },
  });
}

/**
 * Start a new verification run
 */
export function useStartVerification() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: startVerification,
    onSuccess: (data, params) => {
      // Invalidate run history
      queryClient.invalidateQueries({
        queryKey: verificationKeys.runs(params.projectId),
      });
    },
  });
}

/**
 * Cancel an active verification run
 */
export function useCancelVerification() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: cancelVerification,
    onSuccess: (_, runId) => {
      queryClient.invalidateQueries({
        queryKey: verificationKeys.run(runId),
      });
    },
  });
}

/**
 * Fetch judge verdicts for a run
 */
export function useJudgeVerdicts(runId: string | null) {
  return useQuery({
    queryKey: verificationKeys.verdicts(runId || ''),
    queryFn: () => fetchJudgeVerdicts(runId!),
    enabled: !!runId,
    staleTime: 30 * 1000,
  });
}
