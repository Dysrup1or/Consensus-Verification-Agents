import {
  RunResponse,
  StatusResponse,
  VerdictResponse,
  RunListResponse,
  Invariant,
  PromptResponse,
  VerdictsPayload,
} from './types';

// Always go through the Next.js server proxy. This keeps secrets (CVA_API_TOKEN)
// on the server and allows OAuth-gated access in production.
const API_BASE = '/api/cva';

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
