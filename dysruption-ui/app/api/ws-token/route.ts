import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';

export async function GET(req: NextRequest) {
  const runId = new URL(req.url).searchParams.get('runId');
  if (!runId) {
    return NextResponse.json({ error: 'missing_runId' }, { status: 400 });
  }

  // Go through the server-side proxy so the browser never needs CVA_API_TOKEN.
  const res = await fetch(`${req.nextUrl.origin}/api/cva/api/ws_token/${encodeURIComponent(runId)}`, {
    cache: 'no-store',
  });

  const body = await res.json().catch(() => ({}));
  return NextResponse.json(body, { status: res.status });
}
