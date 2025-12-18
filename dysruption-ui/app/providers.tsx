"use client";

import { SessionProvider } from 'next-auth/react';
import { ThemeProvider } from '@/lib/theme';
import { QueryProvider } from '@/lib/providers/query-provider';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <QueryProvider>
        <ThemeProvider>{children}</ThemeProvider>
      </QueryProvider>
    </SessionProvider>
  );
}
