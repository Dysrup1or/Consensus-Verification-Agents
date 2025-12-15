import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';

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

function shouldRequireUserSession(): boolean {
  // Require auth in production by default.
  // In development, allow running without OAuth configured.
  const requireAuth = process.env.CVA_REQUIRE_AUTH;
  if (typeof requireAuth === 'string' && requireAuth.toLowerCase() === 'true') return true;
  return process.env.NODE_ENV === 'production';
}

async function ensureSessionOrReject(): Promise<NextResponse | null> {
  if (!shouldRequireUserSession()) return null;
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  return null;
}

function buildBackendUrl(req: NextRequest, pathSegments: string[]): string {
  const pathname = pathSegments.join('/');
  const url = new URL(req.url);
  const qs = url.search ? url.search : '';
  const baseUrl = resolveBackendBaseUrl();
  return `${baseUrl}/${pathname}${qs}`;
}

function buildForwardHeaders(req: NextRequest): Headers {
  const headers = new Headers();

  // Copy through a safe subset.
  const contentType = req.headers.get('content-type');
  if (contentType) headers.set('content-type', contentType);
  const accept = req.headers.get('accept');
  if (accept) headers.set('accept', accept);

  // Attach backend token (kept server-side).
  const apiToken = process.env.CVA_API_TOKEN;
  if (apiToken) headers.set('authorization', `Bearer ${apiToken}`);

  return headers;
}

async function proxy(req: NextRequest, pathSegments: string[]) {
  const authReject = await ensureSessionOrReject();
  if (authReject) return authReject;

  let baseUrl: string;
  try {
    baseUrl = resolveBackendBaseUrl();
  } catch (err: any) {
    return NextResponse.json(
      { error: 'backend_not_configured', detail: err?.message || String(err) },
      { status: 500 }
    );
  }

  const backendUrl = buildBackendUrl(req, pathSegments);
  const headers = buildForwardHeaders(req);

  const method = req.method.toUpperCase();
  const hasBody = method !== 'GET' && method !== 'HEAD';
  const body = hasBody ? await req.arrayBuffer() : undefined;

  let resp: Response;
  try {
    resp = await fetch(backendUrl, {
      method,
      headers,
      body,
      // Avoid caching user-specific responses.
      cache: 'no-store',
    });
  } catch (err: any) {
    const msg = err?.cause?.message || err?.message || String(err);
    return NextResponse.json(
      {
        error: 'backend_unreachable',
        detail: `Failed to reach CVA backend (baseUrl=${baseUrl}). ${msg}`,
      },
      { status: 502 }
    );
  }

  const responseHeaders = new Headers();
  const respContentType = resp.headers.get('content-type');
  if (respContentType) responseHeaders.set('content-type', respContentType);

  return new NextResponse(resp.body, {
    status: resp.status,
    headers: responseHeaders,
  });
}

export async function GET(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxy(req, ctx.params.path);
}

export async function POST(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxy(req, ctx.params.path);
}

export async function DELETE(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxy(req, ctx.params.path);
}

export async function PUT(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxy(req, ctx.params.path);
}

export async function PATCH(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxy(req, ctx.params.path);
}
