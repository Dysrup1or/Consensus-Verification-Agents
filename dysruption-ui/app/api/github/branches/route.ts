import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';

export const runtime = 'nodejs';

type GitHubBranch = {
  name: string;
  protected: boolean;
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
  const repo = url.searchParams.get('repo') || '';

  if (!isValidRepoFullName(repo)) {
    return NextResponse.json({ error: 'invalid_repo' }, { status: 400 });
  }

  const resp = await fetch(`https://api.github.com/repos/${repo}/branches?per_page=100`, {
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

  const data = (await resp.json()) as GitHubBranch[];
  const branches = data.map((b) => ({ name: b.name, protected: b.protected }));

  return NextResponse.json({ branches });
}
