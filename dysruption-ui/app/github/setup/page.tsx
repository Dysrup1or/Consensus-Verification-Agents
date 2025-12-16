import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';
import { redirect } from 'next/navigation';

function decodeBase64Url(input: string): string {
  const normalized = input.replace(/-/g, '+').replace(/_/g, '/');
  const padLen = (4 - (normalized.length % 4)) % 4;
  const padded = normalized + '='.repeat(padLen);
  return Buffer.from(padded, 'base64').toString('utf-8');
}

function resolveBackendBaseUrl(): string {
  const raw = (process.env.CVA_BACKEND_URL || '').trim();
  const backendPort = (process.env.CVA_BACKEND_PORT || '').trim();
  let baseUrl = raw.replace(/\/$/, '');

  if (baseUrl && !/^https?:\/\//i.test(baseUrl)) {
    const shouldUseHttp = baseUrl.endsWith('.railway.internal') || !baseUrl.includes('.');
    baseUrl = `${shouldUseHttp ? 'http' : 'https'}://${baseUrl}`;
  }

  // For Railway internal domains, append port if not already present and we have one
  // This is CRITICAL: Railway private networking REQUIRES explicit port specification
  if (baseUrl.includes('.railway.internal')) {
    try {
      const url = new URL(baseUrl);
      if (!url.port && backendPort) {
        url.port = backendPort;
        baseUrl = url.toString().replace(/\/$/, '');
      }
    } catch {
      // URL parsing failed
    }
  }

  return baseUrl;
}

type SetupState = {
  repo_full_name: string;
  default_branch?: string;
};

export default async function GitHubSetupPage(props: {
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return (
      <main className="min-h-screen bg-bg text-textPrimary font-sans">
        <div className="max-w-2xl mx-auto px-6 py-10">
          <h1 className="text-xl font-semibold">GitHub App Setup</h1>
          <p className="mt-2 text-sm text-textSecondary">Sign in to link your GitHub App installation.</p>
          <a
            href="/login"
            className="inline-block mt-4 px-4 py-2 rounded-lg bg-primary text-white font-medium hover:bg-primaryHover transition-colors"
          >
            Go to login
          </a>
        </div>
      </main>
    );
  }

  const sp = props.searchParams || {};
  const installationIdRaw = sp.installation_id;
  const stateRaw = sp.state;

  const installationId = typeof installationIdRaw === 'string' ? Number(installationIdRaw) : NaN;
  const stateStr = typeof stateRaw === 'string' ? stateRaw : '';

  let parsedState: SetupState | null = null;
  let stateError: string | null = null;

  if (stateStr) {
    try {
      const decoded = decodeBase64Url(stateStr);
      const obj = JSON.parse(decoded) as SetupState;
      if (obj && typeof obj.repo_full_name === 'string' && obj.repo_full_name.includes('/')) {
        parsedState = obj;
      } else {
        stateError = 'Invalid state payload.';
      }
    } catch (e: any) {
      stateError = e?.message || 'Failed to decode state.';
    }
  }

  const backendUrl = resolveBackendBaseUrl();
  const apiToken = (process.env.CVA_API_TOKEN || '').trim();

  const userIdRaw =
    (session.user as any)?.email || (session.user as any)?.name || (session.user as any)?.id || 'user';
  const user_id = String(userIdRaw).slice(0, 64);

  let result: any = null;
  let error: string | null = null;

  if (!Number.isFinite(installationId) || installationId <= 0) {
    error = 'Missing or invalid installation_id.';
  } else if (!parsedState) {
    error = stateError || 'Missing state. Start from the dashboard install link so we know which repo to link.';
  } else if (!backendUrl) {
    error = 'Backend not configured (CVA_BACKEND_URL missing).';
  } else if (!apiToken) {
    error = 'Backend token not configured (CVA_API_TOKEN missing).';
  } else {
    try {
      const resp = await fetch(`${backendUrl}/api/config/repo_connections`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiToken}`,
          Accept: 'application/json',
        },
        body: JSON.stringify({
          provider: 'github',
          repo_full_name: parsedState.repo_full_name,
          default_branch: parsedState.default_branch || 'main',
          installation_id: installationId,
          user_id,
        }),
        cache: 'no-store',
      });

      const payload = await resp.json().catch(() => null as any);
      if (!resp.ok) {
        const detail = payload?.detail ? String(payload.detail) : `HTTP ${resp.status}`;
        throw new Error(detail);
      }

      result = payload;
    } catch (e: any) {
      const message = e?.message || 'Failed to link installation.';
      const cause = e?.cause?.message || e?.cause?.code || e?.cause;
      error = cause ? `${message} (cause: ${String(cause)})` : message;
    }
  }

  if (!error && result) {
    redirect('/');
  }

  return (
    <main className="min-h-screen bg-bg text-textPrimary font-sans">
      <div className="max-w-2xl mx-auto px-6 py-10">
        <h1 className="text-xl font-semibold">GitHub App Setup</h1>
        <p className="mt-2 text-sm text-textSecondary">
          Links your GitHub App installation to a monitored repository.
        </p>

        <div className="mt-6 p-4 rounded-xl bg-surface border border-border">
          <div className="text-sm text-textSecondary space-y-1">
            <div>
              Installation ID: <span className="font-mono text-textPrimary">{String(installationIdRaw || '—')}</span>
            </div>
            <div>
              Repo:{' '}
              <span className="font-mono text-textPrimary">
                {parsedState?.repo_full_name || '—'}
              </span>
            </div>
            <div>
              User:{' '}
              <span className="font-mono text-textPrimary">{user_id}</span>
            </div>
            <div>
              Backend:{' '}
              <span className="font-mono text-textPrimary">{backendUrl || '—'}</span>
            </div>
          </div>

          {error ? (
            <div className="mt-4 text-sm text-danger">Error: {error}</div>
          ) : (
            <div className="mt-4 text-sm text-success">Linked successfully.</div>
          )}

          {result ? (
            <pre className="mt-4 text-xs bg-bg border border-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          ) : null}

          <a
            href="/"
            className="inline-block mt-4 px-4 py-2 rounded-lg border border-border bg-bg text-textPrimary font-medium hover:border-primary/50 transition-colors"
          >
            Back to dashboard
          </a>

          <a
            href="/api/auth/signout?callbackUrl=/login"
            className="inline-block mt-3 px-4 py-2 rounded-lg bg-surface border border-border text-textPrimary font-medium hover:border-primary/50 transition-colors"
          >
            Sign out
          </a>
        </div>
      </div>
    </main>
  );
}
