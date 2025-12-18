import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('*/api/cva/api/config/repo_connections', () => {
    return HttpResponse.json([]);
  }),

  http.get('*/api/github/repos', () => {
    return HttpResponse.json({
      repos: [
        {
          id: 1,
          full_name: 'acme/repo',
          private: false,
          default_branch: 'main',
        },
      ],
    });
  }),

  http.get('*/api/github/branches', ({ request }) => {
    const url = new URL(request.url);
    const repo = url.searchParams.get('repo');

    if (!repo) {
      return HttpResponse.json(
        { error: 'Missing repo query param' },
        { status: 400 }
      );
    }

    return HttpResponse.json({
      branches: [{ name: 'main', protected: false }],
    });
  }),

  http.get('*/api/github/installations', () => {
    return HttpResponse.json({ installation_id: 123 });
  }),

  http.post('*/api/github/import', async () => {
    return HttpResponse.json({
      targetPath: '/tmp/upload_123',
      fileCount: 3,
      repo: 'acme/repo',
      ref: 'main',
    });
  }),
];
