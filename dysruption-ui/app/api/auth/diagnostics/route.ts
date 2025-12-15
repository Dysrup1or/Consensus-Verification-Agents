import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';

function getHeader(req: NextRequest, name: string): string {
  return req.headers.get(name) || '';
}

function computeEffectiveBaseUrl(req: NextRequest): {
  effectiveBaseUrl: string;
  source: 'NEXTAUTH_URL' | 'x-forwarded-*' | 'req.nextUrl.origin';
} {
  const envUrl = (process.env.NEXTAUTH_URL || '').trim();
  if (envUrl) {
    return { effectiveBaseUrl: envUrl.replace(/\/$/, ''), source: 'NEXTAUTH_URL' };
  }

  const xfProto = getHeader(req, 'x-forwarded-proto');
  const xfHost = getHeader(req, 'x-forwarded-host');
  if (xfProto && xfHost) {
    return { effectiveBaseUrl: `${xfProto}://${xfHost}`.replace(/\/$/, ''), source: 'x-forwarded-*' };
  }

  return { effectiveBaseUrl: req.nextUrl.origin.replace(/\/$/, ''), source: 'req.nextUrl.origin' };
}

export async function GET(req: NextRequest) {
  const { effectiveBaseUrl, source } = computeEffectiveBaseUrl(req);

  const githubCallback = `${effectiveBaseUrl}/api/auth/callback/github`;
  const googleCallback = `${effectiveBaseUrl}/api/auth/callback/google`;

  return NextResponse.json(
    {
      now: new Date().toISOString(),
      effectiveBaseUrl,
      effectiveBaseUrlSource: source,
      expectedOAuthCallbacks: {
        github: githubCallback,
        google: googleCallback,
      },
      request: {
        url: req.url,
        nextUrlOrigin: req.nextUrl.origin,
        host: getHeader(req, 'host') || null,
        xForwardedHost: getHeader(req, 'x-forwarded-host') || null,
        xForwardedProto: getHeader(req, 'x-forwarded-proto') || null,
      },
      env: {
        hasNEXTAUTH_URL: Boolean((process.env.NEXTAUTH_URL || '').trim()),
        hasNEXTAUTH_SECRET: Boolean((process.env.NEXTAUTH_SECRET || '').trim()),
        hasGITHUB_ID: Boolean((process.env.GITHUB_ID || '').trim()),
        hasGITHUB_SECRET: Boolean((process.env.GITHUB_SECRET || '').trim()),
        hasGOOGLE_CLIENT_ID: Boolean((process.env.GOOGLE_CLIENT_ID || '').trim()),
        hasGOOGLE_CLIENT_SECRET: Boolean((process.env.GOOGLE_CLIENT_SECRET || '').trim()),
      },
    },
    { headers: { 'cache-control': 'no-store' } }
  );
}
