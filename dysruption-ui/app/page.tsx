/**
 * Root Page - Smart Router
 * 
 * Routes users based on authentication and onboarding status:
 * - Unauthenticated → /login
 * - New user (no projects) → /onboarding  
 * - Existing user → /dashboard
 */

'use client';

import { useEffect, useState } from 'react';
import { useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import { Spinner } from '@/components/effects';

export default function RootPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    async function determineRoute() {
      // Wait for session to load
      if (status === 'loading') return;

      // Not authenticated → login
      if (!session) {
        router.replace('/login');
        return;
      }

      // Check if user has any projects (onboarding status)
      try {
        // Backend endpoint is /api/config/repo_connections
        const response = await fetch('/api/cva/api/config/repo_connections');
        
        if (response.ok) {
          const data = await response.json();
          // repos_connections returns { connections: [...] }
          const connections = data?.connections || data || [];
          const hasProjects = Array.isArray(connections) && connections.length > 0;
          
          if (hasProjects) {
            router.replace('/dashboard');
          } else {
            router.replace('/onboarding');
          }
        } else {
          // API error - default to onboarding for new experience
          router.replace('/onboarding');
        }
      } catch (error) {
        // Network error - still route to onboarding
        console.error('Failed to check projects:', error);
        router.replace('/onboarding');
      }
    }

    determineRoute();
  }, [session, status, router]);

  // Show loading while determining route
  return (
    <div className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <Spinner size="lg" />
        <p className="text-[var(--color-text-secondary)] animate-pulse">
          Loading Invariant...
        </p>
      </div>
    </div>
  );
}
