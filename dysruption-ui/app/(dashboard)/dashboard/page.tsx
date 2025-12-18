/**
 * Dashboard Home Page
 * 
 * Main dashboard view showing project cards grid.
 */

'use client';

import { useState } from 'react';
import { useProjects } from '@/lib/hooks';
import { useProjectsStore } from '@/lib/stores';
import { ProjectCardGrid } from '@/components/dashboard/ProjectCardGrid';
import { ProjectFilters } from '@/components/dashboard/ProjectFilters';
import { EmptyState } from '@/components/dashboard/EmptyState';
import { Button, SkeletonProjectCard } from '@/components/ui';

export default function DashboardPage() {
  const { data: projects, isLoading, error, refetch } = useProjects();
  const { setProjects } = useProjectsStore();
  
  // Sync with store when data loads
  if (projects && projects.length > 0) {
    setProjects(projects);
  }
  
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="h-8 w-32 bg-[var(--color-surface-2)] rounded animate-pulse" />
          <div className="h-10 w-40 bg-[var(--color-surface-2)] rounded animate-pulse" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <SkeletonProjectCard key={i} />
          ))}
        </div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <div className="w-16 h-16 rounded-full bg-[var(--color-danger)]/20 flex items-center justify-center">
          <svg className="w-8 h-8 text-[var(--color-danger)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <p className="text-[var(--color-text-primary)] font-medium">Failed to load projects</p>
        <p className="text-[var(--color-text-secondary)] text-sm">{error.message}</p>
        <Button intent="secondary" onClick={() => refetch()}>
          Try Again
        </Button>
      </div>
    );
  }
  
  if (!projects || projects.length === 0) {
    return <EmptyState />;
  }
  
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
            Projects
          </h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            {projects.length} project{projects.length !== 1 ? 's' : ''} connected
          </p>
        </div>
        
        <Button intent="primary" onClick={() => window.location.href = '/onboarding'}>
          + Add Project
        </Button>
      </div>
      
      {/* Filters */}
      <ProjectFilters />
      
      {/* Project grid */}
      <ProjectCardGrid />
    </div>
  );
}
