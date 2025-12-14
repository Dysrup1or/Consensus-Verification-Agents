import { withAuth } from 'next-auth/middleware';

const requireAuth =
  process.env.CVA_REQUIRE_AUTH?.toLowerCase() === 'true' || process.env.NODE_ENV === 'production';

export default withAuth({
  pages: {
    signIn: '/login',
  },
  callbacks: {
    authorized: ({ token }: { token: any }) => {
      if (!requireAuth) return true;
      return !!token;
    },
  },
});

export const config = {
  // Protect everything except NextAuth endpoints + the login page + Next.js internals.
  matcher: ['/((?!api/auth|login|_next/static|_next/image|favicon.ico).*)'],
};
