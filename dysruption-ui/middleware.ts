import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { withAuth } from 'next-auth/middleware';
import { resolveNextAuthSecret } from '@/lib/authEnv';

const requireAuth =
  process.env.CVA_REQUIRE_AUTH?.toLowerCase() === 'true' || process.env.NODE_ENV === 'production';

const middleware = requireAuth
  ? withAuth({
      secret: resolveNextAuthSecret(),
      pages: {
        signIn: '/login',
      },
      callbacks: {
        authorized: ({ token }: { token: any }) => {
          return !!token;
        },
      },
    })
  : (req: NextRequest) => NextResponse.next();

export default middleware;

export const config = {
  // Protect everything except NextAuth endpoints + the login page + Next.js internals.
  matcher: ['/((?!api/auth|login|_next/static|_next/image|favicon.ico).*)'],
};
