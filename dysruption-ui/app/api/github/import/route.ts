import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';
import { Readable } from 'stream';

export const runtime = 'nodejs';

function resolveBackendBaseUrl(): string {
  const raw = (process.env.CVA_BACKEND_URL || '').trim();
  const fallback = process.env.NODE_ENV === 'production' ? '' : 'http://127.0.0.1:8001';
  const baseUrl = (raw || fallback).replace(/\/$/, '');

  if (!baseUrl) {
    throw new Error(
      'Missing CVA_BACKEND_URL. Set CVA_BACKEND_URL to the CVA backend origin (e.g. https://<api-service-domain>).'
    );
  }

  if (
    process.env.NODE_ENV === 'production' &&
    /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|::1)(:|\/|$)/i.test(baseUrl)
  ) {
    throw new Error(
      `Invalid CVA_BACKEND_URL in production (${baseUrl}). It cannot point to localhost; set it to your deployed CVA backend.`
    );
  }

  return baseUrl;
}

function getGitHubAccessToken(session: any): string | null {
  return (session as any)?.githubAccessToken ?? null;
}

function isValidRepoFullName(value: string): boolean {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value);
}

function sanitizeRelativePath(p: string): string {
  // Normalize separators, remove leading slashes, and strip traversal.
  const cleaned = p
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .replace(/\.\.(\/|$)/g, '');
  return cleaned
    .split('/')
    .filter((seg) => seg && seg !== '.' && seg !== '..')
    .join('/');
}

function stripZipballRootPrefix(zipPath: string): string {
  // GitHub zipballs include a single top-level folder like owner-repo-sha/...
  const parts = zipPath.replace(/\\/g, '/').split('/');
  if (parts.length <= 1) return zipPath;
  return parts.slice(1).join('/');
}

function shouldSkipPath(relPath: string): boolean {
  const p = relPath.toLowerCase();
  if (!p) return true;
  if (p.startsWith('.git/')) return true;
  if (p.includes('/.git/')) return true;
  if (p.startsWith('node_modules/')) return true;
  if (p.includes('/node_modules/')) return true;
  if (p.startsWith('.next/')) return true;
  if (p.includes('/.next/')) return true;
  if (p.startsWith('dist/')) return true;
  if (p.includes('/dist/')) return true;
  if (p.startsWith('build/')) return true;
  if (p.includes('/build/')) return true;
  if (p.startsWith('.venv/')) return true;
  if (p.includes('/.venv/')) return true;
  if (p.includes('/__pycache__/')) return true;
  if (p.endsWith('.ds_store')) return true;
  if (p.endsWith('thumbs.db')) return true;
  // Do not accept env files.
  if (p.endsWith('.env') || p.includes('/.env')) return true;
  return false;
}

function looksBinaryByExtension(relPath: string): boolean {
  const p = relPath.toLowerCase();
  return /\.(jpg|jpeg|png|gif|webp|mp4|mp3|avi|mov|pdf|zip|tar|gz|7z|exe|dll|bin|class|o|a)$/.test(p);
}

async function uploadBatchToBackend(args: {
  files: Array<{ relPath: string; content: Uint8Array }>;
  uploadId: string | null;
}): Promise<{ upload_id: string; path: string; count: number }> {
  const baseUrl = resolveBackendBaseUrl();
  const apiToken = process.env.CVA_API_TOKEN;

  const form = new FormData();
  for (const f of args.files) {
    const filename = f.relPath.split('/').pop() || 'file';
    form.append('files', new Blob([f.content as any]), filename);
    form.append('paths', f.relPath);
  }
  if (args.uploadId) {
    form.append('upload_id', args.uploadId);
  }

  let resp: Response;
  try {
    resp = await fetch(`${baseUrl}/upload`, {
      method: 'POST',
      headers: apiToken ? { Authorization: `Bearer ${apiToken}` } : undefined,
      body: form,
      cache: 'no-store',
    });
  } catch (err: any) {
    const msg = err?.cause?.message || err?.message || String(err);
    throw new Error(
      `Backend upload request failed (baseUrl=${baseUrl}). Ensure the CVA backend is running and reachable, and CVA_BACKEND_URL is correct. ${msg}`
    );
  }

  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Backend upload failed (${resp.status}): ${text.slice(0, 300)}`);
  }

  return (await resp.json()) as { upload_id: string; path: string; count: number };
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  const token = getGitHubAccessToken(session);

  if (!session || !token) {
    return NextResponse.json({ error: 'github_auth_required' }, { status: 401 });
  }

  const body = (await req.json().catch(() => null)) as null | { repo: string; ref?: string };
  const repo = body?.repo || '';
  const ref = (body?.ref || '').trim() || 'HEAD';

  if (!isValidRepoFullName(repo)) {
    return NextResponse.json({ error: 'invalid_repo' }, { status: 400 });
  }

  // Download zipball
  const zipResp = await fetch(`https://api.github.com/repos/${repo}/zipball/${encodeURIComponent(ref)}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'invariant-ui',
    },
    cache: 'no-store',
  });

  if (!zipResp.ok || !zipResp.body) {
    const text = await zipResp.text().catch(() => '');
    return NextResponse.json(
      { error: 'github_zipball_error', status: zipResp.status, detail: text.slice(0, 500) },
      { status: 502 }
    );
  }

  // Lazy-load unzipper's parser only (avoids optional deps from the package entrypoint).
  const parseMod = (await import('unzipper/lib/parse')) as any;
  const Parse = parseMod?.default ?? parseMod;

  // Limits (strict safety)
  const MAX_FILES = 2500;
  const MAX_TOTAL_BYTES = 50 * 1024 * 1024; // 50MB
  const MAX_FILE_BYTES = 2 * 1024 * 1024; // 2MB per file
  const BATCH_SIZE = 50;

  let totalBytes = 0;
  let uploadedTotal = 0;
  let uploadId: string | null = null;
  let targetPath = '';

  const batch: Array<{ relPath: string; content: Uint8Array }> = [];

  const nodeStream = Readable.fromWeb(zipResp.body as any);
  const parser = nodeStream.pipe(Parse({ forceStream: true }));

  for await (const entry of parser) {
    const entryPath: string = entry.path || '';
    const isDirectory: boolean = entry.type === 'Directory' || entryPath.endsWith('/');

    if (isDirectory) {
      entry.autodrain();
      continue;
    }

    if (uploadedTotal >= MAX_FILES) {
      entry.autodrain();
      break;
    }

    let relPath = sanitizeRelativePath(stripZipballRootPrefix(entryPath));
    if (shouldSkipPath(relPath) || looksBinaryByExtension(relPath)) {
      entry.autodrain();
      continue;
    }

    const chunks: Buffer[] = [];
    let fileBytes = 0;

    for await (const chunk of entry) {
      const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      fileBytes += buf.length;
      totalBytes += buf.length;

      if (fileBytes > MAX_FILE_BYTES || totalBytes > MAX_TOTAL_BYTES) {
        // Stop reading this file and drop it.
        chunks.length = 0;
        break;
      }

      chunks.push(buf);
    }

    if (chunks.length === 0) {
      continue;
    }

    const content = Buffer.concat(chunks);
    batch.push({ relPath, content });

    if (batch.length >= BATCH_SIZE) {
      const uploaded = await uploadBatchToBackend({ files: batch.splice(0, batch.length), uploadId });
      uploadId = uploaded.upload_id;
      targetPath = uploaded.path;
      uploadedTotal += uploaded.count;
    }
  }

  if (batch.length > 0) {
    const uploaded = await uploadBatchToBackend({ files: batch, uploadId });
    uploadId = uploaded.upload_id;
    targetPath = uploaded.path;
    uploadedTotal += uploaded.count;
  }

  if (!targetPath) {
    return NextResponse.json(
      { error: 'no_files_imported', detail: 'No eligible source files were imported from the selected repo.' },
      { status: 400 }
    );
  }

  return NextResponse.json({ targetPath, fileCount: uploadedTotal, repo, ref });
}
