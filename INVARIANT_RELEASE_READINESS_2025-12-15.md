# Invariant Release Readiness Report (2025-12-15)

## Scope (what was evaluated)
- Invariant UI (Next.js App Router) in `dysruption-ui`
- CVA preflight checks in `preflight.py`
- GitHub-native import pipeline (GitHub OAuth token → repo/branch selection → zipball import → backend `/upload` → `/run`)

## Change Summary
- Removed local-path / drag-drop workflow from the Invariant dashboard and replaced it with a strict GitHub-native workflow.
- Added server routes to list GitHub repos/branches and to import a repo zipball server-side (no client-side file paths).
- Fixed build + lint + security audit issues introduced during the GitHub import work.

## Security Review
### Controls present
- **Backend token isolation**: backend token (`CVA_API_TOKEN`) is only used server-side (Next.js route uploads to backend).
- **GitHub token usage**: GitHub access token is stored in NextAuth JWT/session and only used server-side in `/api/github/*`.
- **Import hardening** (repo zipball → upload):
  - Path sanitization (normalizes separators, strips traversal, removes zipball root folder).
  - Skips `.env` files and common build/cache directories (`node_modules`, `.git`, `.next`, etc.).
  - File and size limits: max files, max total bytes, max per-file bytes, plus batching.
  - GitHub API URL is fixed to `https://api.github.com/...` (no user-controlled host).

### Dependency risk
- `npm audit`: **0 vulnerabilities** after pinning `glob@10.5.0` via npm `overrides`.

### Deployment security requirements (must be set)
- `NEXTAUTH_SECRET` must be set in Railway.
- `NEXTAUTH_URL` must match the public canonical domain.
- In production: set `CVA_REQUIRE_AUTH=true` (or rely on `NODE_ENV=production`) to enforce auth.
- GitHub OAuth app must request `repo` scope if private repos are supported.

## Stability Review
- UI unit tests: `npm test` **PASS**.
- UI lint: `npm run lint` **PASS** (no warnings).
- UI build: `npm run build` **PASS**.
- Backend preflight: `python preflight.py` **PASS WITH WARNINGS**
  - Warning: `.env` missing locally (expected if using Railway env vars)
  - Warning: git working tree dirty (expected while changes uncommitted)
  - Note: LiteLLM Redis cache logs an error if Redis isn’t reachable; this did not fail imports.

## Efficiency Review
- GitHub import route batches uploads and enforces strict limits to reduce memory and prevent runaway imports.
- Server-side import avoids client-side zip handling and avoids pushing large payloads over WebSockets.

## Known Limitations / Follow-ups
- If users sign in with Google only, dashboard will require a GitHub connect step before import.
- Repo imports are capped (by design); very large repos may be rejected until limits are tuned.
- LiteLLM Redis cache warning suggests Redis should be configured/disabled explicitly for production.

## Launch Verdict
**Conditional GO** for real-user launch **provided** production configuration is complete:
- Railway env vars set (`CVA_BACKEND_URL`, `CVA_API_TOKEN`, `NEXTAUTH_SECRET`, `NEXTAUTH_URL`, OAuth creds).
- Auth enforced in production (`CVA_REQUIRE_AUTH=true` recommended).
- Custom domain + OAuth callback URLs verified end-to-end.

If those deployment requirements are not set, the product should be treated as **NO-GO** until they are.
