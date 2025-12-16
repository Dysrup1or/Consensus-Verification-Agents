import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';

export const runtime = 'nodejs';

type GitHubInstallation = {
  id: number;
  app_slug?: string;
  account?: { login?: string };
};

type InstallationsResponse = {
  installations?: GitHubInstallation[];
};

function getGitHubAccessToken(session: any): string | null {
  return (session as any)?.githubAccessToken ?? null;
}

function isValidRepoFullName(value: string): boolean {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value);
}

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  const token = getGitHubAccessToken(session);

  if (!session || !token) {
    return NextResponse.json({ error: 'github_auth_required' }, { status: 401 });
  }

  const url = new URL(req.url);
  const repo = (url.searchParams.get('repo') || '').trim();

  if (repo && !isValidRepoFullName(repo)) {
    return NextResponse.json({ error: 'invalid_repo' }, { status: 400 });
  }

  const slug = (process.env.NEXT_PUBLIC_GITHUB_APP_SLUG || '').trim();
  if (!slug) {
    return NextResponse.json({ error: 'missing_app_slug' }, { status: 500 });
  }

  const resp = await fetch('https://api.github.com/user/installations?per_page=100', {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'invariant-ui',
    },
    cache: 'no-store',
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    return NextResponse.json(
      { error: 'github_api_error', status: resp.status, detail: text.slice(0, 500) },
      { status: 502 }
    );
  }

  const data = (await resp.json()) as InstallationsResponse;
  const installations = Array.isArray(data.installations) ? data.installations : [];

  const repoOwner = repo ? repo.split('/')[0] : '';
  const match = installations.find((inst) => {
    const instSlug = (inst.app_slug || '').toLowerCase();
    if (instSlug !== slug.toLowerCase()) return false;
    if (!repoOwner) return true;
    const login = (inst.account?.login || '').toLowerCase();
    return login === repoOwner.toLowerCase();
  });

  return NextResponse.json({
    slug,
    repo: repo || null,
    installation_id: match?.id ?? null,
  });
}
