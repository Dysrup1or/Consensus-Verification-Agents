import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';

function resolveBackendBaseUrl(): { raw: string; resolved: string } {
  const raw = (process.env.CVA_BACKEND_URL || '').trim();
  const fallback = process.env.NODE_ENV === 'production' ? '' : 'http://127.0.0.1:8001';
  let baseUrl = (raw || fallback).trim();

  baseUrl = baseUrl.replace(/\/+$/, '');
  baseUrl = baseUrl.replace(/:(?:\$\{?PORT\}?|PORT)$/i, '');
  baseUrl = baseUrl.replace(/:$/, '');

  if (baseUrl && !/^https?:\/\//i.test(baseUrl)) {
    const shouldUseHttp = baseUrl.endsWith('.railway.internal') || !baseUrl.includes('.');
    baseUrl = `${shouldUseHttp ? 'http' : 'https'}://${baseUrl}`;
  }

  baseUrl = baseUrl.replace(/:(?:\$\{?PORT\}?|PORT)$/i, '');
  baseUrl = baseUrl.replace(/:$/, '');

  try {
    if (baseUrl) {
      // eslint-disable-next-line no-new
      new URL(baseUrl);
    }
  } catch {
    baseUrl = '';
  }

  return { raw, resolved: baseUrl };
}

async function probe(url: string): Promise<{ ok: boolean; status?: number; bodyPreview?: string; error?: string }> {
  try {
    const resp = await fetch(url, { method: 'GET', cache: 'no-store' });
    const text = await resp.text().catch(() => '');
    return {
      ok: resp.ok,
      status: resp.status,
      bodyPreview: text.slice(0, 500),
    };
  } catch (err: any) {
    const msg = err?.cause?.message || err?.message || String(err);
    return { ok: false, error: msg };
  }
}

export async function GET(req: NextRequest) {
  const { raw, resolved } = resolveBackendBaseUrl();
  const hasToken = typeof process.env.CVA_API_TOKEN === 'string' && process.env.CVA_API_TOKEN.trim().length > 0;

  if (!resolved) {
    return NextResponse.json(
      {
        ok: false,
        error: 'missing_CVA_BACKEND_URL',
        env: {
          NODE_ENV: process.env.NODE_ENV || null,
          CVA_BACKEND_URL_present: !!raw,
          CVA_API_TOKEN_present: hasToken,
        },
      },
      { status: 500 }
    );
  }

  const root = await probe(`${resolved}/`);
  const docs = await probe(`${resolved}/docs`);

  return NextResponse.json({
    ok: true,
    env: {
      NODE_ENV: process.env.NODE_ENV || null,
      CVA_BACKEND_URL_raw: raw || null,
      CVA_BACKEND_URL_resolved: resolved,
      CVA_API_TOKEN_present: hasToken,
    },
    probes: {
      root,
      docs,
    },
    request: {
      host: req.headers.get('host'),
      x_forwarded_host: req.headers.get('x-forwarded-host'),
      x_forwarded_proto: req.headers.get('x-forwarded-proto'),
    },
  });
}
