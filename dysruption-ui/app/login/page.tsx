'use client';

import { signIn } from 'next-auth/react';

export default function LoginPage() {
  return (
    <main className="min-h-screen bg-bg text-textPrimary font-sans flex items-center justify-center px-6">
      <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6">
        <h1 className="text-xl font-bold tracking-tight">Sign in</h1>
        <p className="mt-2 text-sm text-textMuted">Use Google or GitHub to access the CVA dashboard.</p>

        <div className="mt-6 space-y-3">
          <button
            className="w-full rounded-lg bg-primary text-white px-4 py-2 text-sm font-medium"
            onClick={() => signIn('google', { callbackUrl: '/' })}
          >
            Continue with Google
          </button>

          <button
            className="w-full rounded-lg border border-border bg-bg px-4 py-2 text-sm font-medium"
            onClick={() => signIn('github', { callbackUrl: '/' })}
          >
            Continue with GitHub
          </button>
        </div>

        <p className="mt-6 text-xs text-textMuted">
          If buttons don’t work, OAuth providers may not be configured yet.
        </p>
      </div>
    </main>
  );
}
