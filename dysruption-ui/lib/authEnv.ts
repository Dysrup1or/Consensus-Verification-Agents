export const IS_PROD = process.env.NODE_ENV === 'production';

function readTrimmedEnv(name: string): string {
  const raw = process.env[name];
  return typeof raw === 'string' ? raw.trim() : '';
}

/**
 * NextAuth requires a secret for JWT/session encryption.
 *
 * - In production, it must be explicitly configured via `NEXTAUTH_SECRET`.
 * - In local development, we fall back to a stable dev-only secret so the UI
 *   is usable for "ignorant vibecoder" workflows without setup friction.
 */
export function resolveNextAuthSecret(): string | undefined {
  const configured = readTrimmedEnv('NEXTAUTH_SECRET');
  if (configured) return configured;

  if (IS_PROD) return undefined;

  // Stable dev-only fallback. Do NOT rely on this in production.
  return 'invariant-dev-only-nextauth-secret';
}

/**
 * When NEXTAUTH_URL is not set in local dev, trust host headers.
 * This avoids hard-failing on callback URLs while still allowing explicit
 * configuration for production.
 */
export function resolveTrustHost(): boolean {
  if (IS_PROD) return false;
  const url = readTrimmedEnv('NEXTAUTH_URL');
  return !url;
}

export function hasOAuthProvidersConfigured(): boolean {
  const hasGoogle = Boolean(readTrimmedEnv('GOOGLE_CLIENT_ID') && readTrimmedEnv('GOOGLE_CLIENT_SECRET'));
  const hasGitHub = Boolean(readTrimmedEnv('GITHUB_ID') && readTrimmedEnv('GITHUB_SECRET'));
  return hasGoogle || hasGitHub;
}
