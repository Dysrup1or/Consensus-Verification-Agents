/**
 * Onboarding Layout
 * 
 * Layout for the onboarding wizard flow.
 * Provides a clean, focused UI for new user setup.
 */

import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Get Started | Invariant',
  description: 'Set up your first project with Invariant verification coaching.',
};

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] flex flex-col">
      {/* Header */}
      <header className="border-b border-[var(--color-border)] px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🧠</span>
            <span className="text-xl font-semibold text-[var(--color-text-primary)]">
              Invariant
            </span>
          </div>
          <a
            href="/"
            className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            Skip setup →
          </a>
        </div>
      </header>
      
      {/* Main content */}
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-2xl">
          {children}
        </div>
      </main>
      
      {/* Footer */}
      <footer className="border-t border-[var(--color-border)] px-6 py-4">
        <div className="max-w-4xl mx-auto text-center text-sm text-[var(--color-text-muted)]">
          Need help? Check out our{' '}
          <a
            href="/docs"
            className="text-[var(--color-primary)] hover:underline"
          >
            documentation
          </a>
        </div>
      </footer>
    </div>
  );
}
