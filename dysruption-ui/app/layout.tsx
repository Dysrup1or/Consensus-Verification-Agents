import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from '@/lib/theme';

export const metadata: Metadata = {
  title: "Invariant - Verification Coach",
  description: "Invariant dashboard for verification and remediation coaching.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
