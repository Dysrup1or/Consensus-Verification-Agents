import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';

export const runtime = 'nodejs';

type GitHubRepo = {
  id: number;
  full_name: string;
  private: boolean;
  default_branch: string;
  archived: boolean;
  disabled: boolean;
  fork: boolean;
};

function getGitHubAccessToken(session: any): string | null {
  return (session as any)?.githubAccessToken ?? null;
}

function parseNextLink(linkHeader: string | null): string | null {
  if (!linkHeader) return null;
  // Example: <https://api.github.com/user/repos?page=2>; rel="next", <...>; rel="last"
  const parts = linkHeader.split(',').map((p) => p.trim());
  for (const part of parts) {
    const match = part.match(/^<([^>]+)>;\s*rel="([^"]+)"$/);
    if (match && match[2] === 'next') return match[1];
  }
  return null;
}

export async function GET() {
  const session = await getServerSession(authOptions);
  const token = getGitHubAccessToken(session);

  if (!session || !token) {
    return NextResponse.json({ error: 'github_auth_required' }, { status: 401 });
  }

  const repos: Array<{
    id: number;
    full_name: string;
    private: boolean;
    default_branch: string;
  }> = [];

  let url: string | null =
    'https://api.github.com/user/repos?per_page=100&sort=updated&direction=desc&affiliation=owner,collaborator,organization_member';

  // Cap pagination to avoid runaway requests.
  const MAX_PAGES = 10;
  let pages = 0;

  while (url && pages < MAX_PAGES) {
    pages += 1;
    const resp = await fetch(url, {
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

    const data = (await resp.json()) as GitHubRepo[];
    for (const r of data) {
      // Strict: only repos you can actually analyze.
      if (r.archived || r.disabled) continue;
      repos.push({ id: r.id, full_name: r.full_name, private: r.private, default_branch: r.default_branch });
    }

    url = parseNextLink(resp.headers.get('link'));
  }

  return NextResponse.json({ repos });
}
