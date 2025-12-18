import type { NextAuthOptions } from 'next-auth';
import GoogleProvider from 'next-auth/providers/google';
import GitHubProvider from 'next-auth/providers/github';
import { resolveNextAuthSecret } from './authEnv';

const providers = [];

if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
  providers.push(
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    })
  );
}

if (process.env.GITHUB_ID && process.env.GITHUB_SECRET) {
  providers.push(
    GitHubProvider({
      clientId: process.env.GITHUB_ID,
      clientSecret: process.env.GITHUB_SECRET,
      authorization: {
        params: {
          // Minimal set to list repos/branches and download zipballs.
          // Includes private repos if the user chooses them.
          scope: 'read:user user:email repo',
        },
      },
    })
  );
}

export const authOptions: NextAuthOptions = {
  providers,
  secret: resolveNextAuthSecret(),
  debug: process.env.NEXTAUTH_DEBUG?.toLowerCase() === 'true',
  session: { strategy: 'jwt' },
  pages: {
    signIn: '/login',
  },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.provider === 'github' && account.access_token) {
        (token as any).githubAccessToken = account.access_token;
      }
      return token;
    },
    async session({ session, token }) {
      (session as any).githubAccessToken = (token as any).githubAccessToken;
      return session;
    },
  },
};
