import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';

const BACKEND_BASE_URL = (process.env.CVA_BACKEND_URL || 'http://localhost:8001').replace(/\/$/, '');

function shouldRequireUserSession(): boolean {
  // Require auth in production by default.
  // In development, allow running without OAuth configured.
  if (process.env.CVA_REQUIRE_AUTH?.toLowerCase() === 'true') return true;
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
  return `${BACKEND_BASE_URL}/${pathname}${qs}`;
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

  const backendUrl = buildBackendUrl(req, pathSegments);
  const headers = buildForwardHeaders(req);

  const method = req.method.toUpperCase();
  const hasBody = method !== 'GET' && method !== 'HEAD';
  const body = hasBody ? await req.arrayBuffer() : undefined;

  const resp = await fetch(backendUrl, {
    method,
    headers,
    body,
    // Avoid caching user-specific responses.
    cache: 'no-store',
  });

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
