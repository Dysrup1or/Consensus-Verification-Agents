'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { signIn } from 'next-auth/react';

type AuthDiagnostics = {
  env?: {
    hasNEXTAUTH_URL?: boolean;
    hasNEXTAUTH_SECRET?: boolean;
    usingDevFallbackSecret?: boolean;
    hasGITHUB_ID?: boolean;
    hasGITHUB_SECRET?: boolean;
    hasGOOGLE_CLIENT_ID?: boolean;
    hasGOOGLE_CLIENT_SECRET?: boolean;
  };
};

export default function LoginPage() {
  const [diag, setDiag] = useState<AuthDiagnostics | null>(null);
  const [diagError, setDiagError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch('/api/auth/diagnostics', { cache: 'no-store' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = (await resp.json().catch(() => null)) as AuthDiagnostics | null;
        if (!cancelled) setDiag(data);
      } catch (e: any) {
        if (!cancelled) setDiagError(e?.message || 'Failed to load auth diagnostics');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasGoogle = Boolean(diag?.env?.hasGOOGLE_CLIENT_ID && diag?.env?.hasGOOGLE_CLIENT_SECRET);
  const hasGitHub = Boolean(diag?.env?.hasGITHUB_ID && diag?.env?.hasGITHUB_SECRET);
  const missingAny = useMemo(() => {
    if (!diag) return false;
    return !hasGoogle && !hasGitHub;
  }, [diag, hasGoogle, hasGitHub]);

  return (
    <main className="min-h-screen bg-bg text-textPrimary font-sans flex items-center justify-center px-6">
      <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6">
        <h1 className="text-xl font-bold tracking-tight">Sign in</h1>
        <p className="mt-2 text-sm text-textMuted">Sign-in is optional right now. You can open the dashboard without it.</p>

        <div className="mt-4">
          <Link
            href="/"
            className="block w-full text-center rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium hover:border-primary/50 transition-colors"
          >
            Go to Dashboard
          </Link>
        </div>

        {diagError && <p className="mt-3 text-xs text-danger">Auth diagnostics unavailable: {diagError}</p>}

        {diag && missingAny && (
          <div className="mt-4 rounded-xl border border-border bg-bg p-4">
            <p className="text-sm font-medium">OAuth not configured yet</p>
            <p className="mt-1 text-xs text-textMuted">
              To enable sign-in buttons, copy <span className="font-mono">dysruption-ui/.env.example</span> to{' '}
              <span className="font-mono">dysruption-ui/.env.local</span> and set Google and/or GitHub credentials.
            </p>
            {diag.env?.usingDevFallbackSecret && (
              <p className="mt-2 text-xs text-textMuted">
                Dev note: a local-only NextAuth secret fallback is active.
              </p>
            )}
          </div>
        )}

        <div className="mt-6 space-y-3">
          <button
            className="w-full rounded-lg bg-primary text-white px-4 py-2 text-sm font-medium"
            onClick={() => signIn('google', { callbackUrl: '/' })}
            disabled={!hasGoogle}
            aria-disabled={!hasGoogle}
          >
            Continue with Google
          </button>

          <button
            className="w-full rounded-lg border border-border bg-bg px-4 py-2 text-sm font-medium"
            onClick={() => signIn('github', { callbackUrl: '/' })}
            disabled={!hasGitHub}
            aria-disabled={!hasGitHub}
          >
            Continue with GitHub
          </button>
        </div>

        <p className="mt-6 text-xs text-textMuted">
          If buttons are disabled, OAuth providers are not configured.
        </p>
      </div>
    </main>
  );
}
