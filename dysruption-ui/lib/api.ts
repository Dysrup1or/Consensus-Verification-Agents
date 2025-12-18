import {
  RunResponse,
  StatusResponse,
  VerdictResponse,
  RunListResponse,
  Invariant,
  PromptResponse,
  VerdictsPayload,
  GitHubRepoListItem,
  GitHubBranchListItem,
} from './types';

// Always go through the Next.js server proxy. This keeps secrets (CVA_API_TOKEN)
// on the server and allows OAuth-gated access in production.
const API_BASE = '/api/cva';

export type RepoConnection = {
  id: string;
  user_id?: string | null;
  provider: 'github' | string;
  repo_full_name: string;
  default_branch: string;
  installation_id?: number | null;
  created_at?: string | null;
};

/**
 * Start a new verification run.
 */
export async function startRun(
  targetDir: string,
  specContent?: string,
  specPath?: string,
  options?: { generatePatches?: boolean; watchMode?: boolean }
): Promise<RunResponse> {
  const payload = {
    target_dir: targetDir,
    spec_path: specPath,
    spec_content: specContent,
    watch_mode: options?.watchMode ?? false,
    generate_patches: options?.generatePatches ?? true,
  };

  try {
    const res = await fetch(`${API_BASE}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to start run');
    }

    const data = await res.json();
    return data;
  } catch (error: any) {
    // Show alert for network errors (only in browser)
    if (typeof window !== 'undefined') {
      alert(`Backend connection failed: ${error.message}`);
    }
    throw error;
  }
}

/**
 * Get current status of a run.
 */
export async function fetchStatus(runId: string): Promise<StatusResponse> {
  const res = await fetch(`${API_BASE}/status/${runId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch status for run ${runId}`);
  }
  return res.json();
}

/**
 * Get the final verdict of a run.
 */
export async function fetchVerdict(runId: string): Promise<VerdictResponse> {
  const res = await fetch(`${API_BASE}/verdict/${runId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch verdict for run ${runId}`);
  }
  return res.json();
}

/**
 * Get the synthesized fix prompt for a failed run.
 */
export async function fetchPrompt(runId: string): Promise<PromptResponse> {
  const res = await fetch(`${API_BASE}/prompt/${runId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch prompt for run ${runId}`);
  }
  return res.json();
}

/**
 * Cancel a running verification.
 */
export async function cancelRun(runId: string): Promise<{ cancelled: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/run/${runId}`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error(`Failed to cancel run ${runId}`);
  }
  return res.json();
}

/**
 * List all verification runs.
 */
export async function fetchRuns(): Promise<RunListResponse> {
  const res = await fetch(`${API_BASE}/runs`);
  if (!res.ok) {
    throw new Error('Failed to fetch runs');
  }
  return res.json();
}

/**
 * List repo connections persisted in the backend DB.
 * Used to detect whether a GitHub App installation has been linked.
 */
export async function fetchRepoConnections(): Promise<RepoConnection[]> {
  const res = await fetch(`${API_BASE}/api/config/repo_connections`, { cache: 'no-store' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to fetch repo connections');
  }
  return res.json();
}

/**
 * Fetch the tribunal verdict payload (including telemetry) for a run.
 *
 * This is best-effort UI diagnostics: it should never crash the dashboard.
 */
export async function fetchVerdictsPayload(runId: string): Promise<VerdictsPayload> {
  try {
    const res = await fetch(`${API_BASE}/api/verdicts/${runId}`);
    if (!res.ok) {
      return {};
    }
    const data = await res.json();
    if (!data || typeof data !== 'object') return {};
    return data as VerdictsPayload;
  } catch {
    return {};
  }
}

// =============================================================================
// UI SERVER ROUTES (NEXT.JS API)
// =============================================================================

/**
 * Fetch a short-lived WebSocket token from the Next.js server.
 * Only used in production (dev does not require token).
 */
export async function fetchWsToken(runId: string): Promise<string | null> {
  if (process.env.NODE_ENV !== 'production') return null;

  try {
    const res = await fetch(`/api/ws-token?runId=${encodeURIComponent(runId)}`, { cache: 'no-store' });
    if (!res.ok) return null;
    const payload = (await res.json().catch(() => null as any)) as any;
    const token = payload?.ws_token;
    return typeof token === 'string' && token.length > 0 ? token : null;
  } catch {
    return null;
  }
}

export async function fetchGitHubRepos(): Promise<GitHubRepoListItem[]> {
  const resp = await fetch('/api/github/repos', { cache: 'no-store' });
  if (!resp.ok) {
    const payload = await resp.json().catch(() => null as any);
    const error = payload?.error ? String(payload.error) : `HTTP ${resp.status}`;
    throw new Error(`Failed to load repos (${error})`);
  }
  const data = (await resp.json().catch(() => null as any)) as { repos?: GitHubRepoListItem[] };
  return Array.isArray(data?.repos) ? data.repos : [];
}

export async function fetchGitHubBranches(repo: string): Promise<GitHubBranchListItem[]> {
  const resp = await fetch(`/api/github/branches?repo=${encodeURIComponent(repo)}`, { cache: 'no-store' });
  if (!resp.ok) {
    const payload = await resp.json().catch(() => null as any);
    const error = payload?.error ? String(payload.error) : `HTTP ${resp.status}`;
    throw new Error(`Failed to load branches (${error})`);
  }
  const data = (await resp.json().catch(() => null as any)) as { branches?: GitHubBranchListItem[] };
  return Array.isArray(data?.branches) ? data.branches : [];
}

export async function fetchGitHubInstallationId(repo: string): Promise<number | null> {
  try {
    const resp = await fetch(`/api/github/installations?repo=${encodeURIComponent(repo)}`, { cache: 'no-store' });
    if (!resp.ok) return null;
    const payload = (await resp.json().catch(() => null as any)) as any;
    const installationId = payload?.installation_id;
    return typeof installationId === 'number' && installationId > 0 ? installationId : null;
  } catch {
    return null;
  }
}

export async function importGitHubRepo(repo: string, ref: string): Promise<{
  targetPath: string;
  fileCount: number;
  repo: string;
  ref: string;
}> {
  const importResp = await fetch('/api/github/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo, ref }),
    cache: 'no-store',
  });

  if (!importResp.ok) {
    const payload = await importResp.json().catch(() => null as any);
    const error = payload?.error ? String(payload.error) : `HTTP ${importResp.status}`;
    throw new Error(`GitHub import failed (${error})`);
  }

  const imported = (await importResp.json().catch(() => null as any)) as any;
  return {
    targetPath: String(imported?.targetPath || ''),
    fileCount: Number(imported?.fileCount || 0),
    repo: String(imported?.repo || repo),
    ref: String(imported?.ref || ref),
  };
}

/**
 * Internal helper to upload a single batch of files.
 */
async function uploadBatch(
  files: File[],
  paths: string[],
  uploadId: string | null,
  onProgress?: (percent: number) => void
): Promise<{ path: string; count: number; upload_id: string }> {
  const formData = new FormData();

  files.forEach((file, index) => {
    formData.append('files', file);
    formData.append('paths', paths[index]);
  });

  if (uploadId) {
    formData.append('upload_id', uploadId);
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          resolve(response);
        } catch (e) {
          reject(new Error('Invalid response from server'));
        }
      } else {
        try {
          const error = JSON.parse(xhr.responseText);
          reject(new Error(error.detail || 'Upload failed'));
        } catch (e) {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    });

    xhr.addEventListener('error', () => {
      reject(new Error('Network error during upload'));
    });

    xhr.open('POST', `${API_BASE}/upload`);
    xhr.send(formData);
  });
}

/**
 * Upload files to the backend in batches to avoid browser/server limits.
 * 
 * @param files - List of File objects to upload
 * @param paths - Corresponding relative paths for each file
 * @param onProgress - Callback for overall upload progress (0-100)
 */
export async function uploadFilesBatched(
  files: File[],
  paths: string[],
  onProgress?: (percent: number) => void
): Promise<{ path: string; count: number }> {
  const BATCH_SIZE = 50; // Upload 50 files at a time
  const totalFiles = files.length;
  let uploadedCount = 0;
  let currentUploadId: string | null = null;
  let finalPath = '';

  for (let i = 0; i < totalFiles; i += BATCH_SIZE) {
    const batchFiles = files.slice(i, i + BATCH_SIZE);
    const batchPaths = paths.slice(i, i + BATCH_SIZE);

    // Calculate progress for this batch relative to total
    const batchProgressCallback = (batchPercent: number) => {
      if (onProgress) {
        // Weight of this batch in total
        const batchWeight = batchFiles.length / totalFiles;
        // Previous batches are 100% done
        const previousProgress = (uploadedCount / totalFiles) * 100;
        // Current batch contribution
        const currentProgress = batchPercent * batchWeight;

        onProgress(Math.round(previousProgress + currentProgress));
      }
    };

    const result = await uploadBatch(batchFiles, batchPaths, currentUploadId, batchProgressCallback);

    currentUploadId = result.upload_id;
    finalPath = result.path;
    uploadedCount += batchFiles.length;
  }

  return { path: finalPath, count: uploadedCount };
}
