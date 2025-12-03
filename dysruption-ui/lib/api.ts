import { VerdictPayload, Invariant } from './types';
import { MOCK_VERDICT, MOCK_INVARIANTS } from './mock';

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === 'true';
const API_BASE = 'http://localhost:8000';

export async function fetchLatestVerdict(): Promise<VerdictPayload | null> {
  if (USE_MOCK) return MOCK_VERDICT;
  try {
    const res = await fetch(`${API_BASE}/api/verdicts/latest`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function fetchInvariants(): Promise<{ invariants: Invariant[] }> {
  if (USE_MOCK) return { invariants: MOCK_INVARIANTS };
  try {
    const res = await fetch(`${API_BASE}/api/invariants`);
    if (!res.ok) return { invariants: [] };
    return await res.json();
  } catch (e) {
    console.error(e);
    return { invariants: [] };
  }
}

export async function fetchRun(runId: string): Promise<VerdictPayload | null> {
  if (USE_MOCK) return MOCK_VERDICT;
  try {
    const res = await fetch(`${API_BASE}/api/runs/${runId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}
