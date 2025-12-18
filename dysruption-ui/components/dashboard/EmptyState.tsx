/**
 * Empty State Component
 * 
 * Displayed when no projects are connected yet.
 */

'use client';

import { useRouter } from 'next/navigation';
import { Button, Card } from '@/components/ui';

export function EmptyState() {
  const router = useRouter();
  
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <Card variant="elevated" padding="xl" className="max-w-lg text-center">
        {/* Icon */}
        <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-[var(--color-primary-muted)] flex items-center justify-center">
          <span className="text-4xl">🚀</span>
        </div>
        
        {/* Title */}
        <h2 className="text-2xl font-semibold text-[var(--color-text-primary)] mb-2">
          No Projects Yet
        </h2>
        
        {/* Description */}
        <p className="text-[var(--color-text-secondary)] mb-6 max-w-sm mx-auto">
          Connect your first GitHub repository to start verifying your code with AI-powered analysis.
        </p>
        
        {/* Features list */}
        <div className="flex flex-col gap-3 mb-8 text-left">
          {[
            { icon: '🔍', text: 'Automatic code analysis on every PR' },
            { icon: '⚖️', text: 'AI tribunal with multiple judge perspectives' },
            { icon: '🛡️', text: 'Security and architecture verification' },
            { icon: '🔧', text: 'One-click remediation suggestions' },
          ].map((feature, i) => (
            <div key={i} className="flex items-center gap-3 text-sm text-[var(--color-text-secondary)]">
              <span className="text-lg">{feature.icon}</span>
              <span>{feature.text}</span>
            </div>
          ))}
        </div>
        
        {/* CTA */}
        <Button
          intent="primary"
          size="lg"
          onClick={() => router.push('/onboarding')}
          className="gap-2"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
          </svg>
          Connect GitHub Repository
        </Button>
        
        {/* Secondary action */}
        <p className="mt-4 text-sm text-[var(--color-text-muted)]">
          or{' '}
          <a href="/verify" className="text-[var(--color-primary)] hover:underline">
            run a quick verification
          </a>
        </p>
      </Card>
    </div>
  );
}
