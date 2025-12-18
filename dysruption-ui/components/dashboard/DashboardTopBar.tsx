/**
 * Dashboard Top Bar Component
 * 
 * Top header bar for the new dashboard with search and quick actions.
 */

'use client';

import { useState } from 'react';
import { useVerificationStore } from '@/lib/stores';
import { Input, Badge } from '@/components/ui';

export function DashboardTopBar() {
  const [searchQuery, setSearchQuery] = useState('');
  const { isRunning, currentRun } = useVerificationStore();
  
  return (
    <header className="h-16 border-b border-[var(--color-border)] bg-[var(--color-surface-1)] px-6 flex items-center justify-between gap-4">
      {/* Search */}
      <div className="flex-1 max-w-md">
        <Input
          placeholder="Search projects..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          inputSize="sm"
          leftIcon={
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          }
        />
      </div>
      
      {/* Right side actions */}
      <div className="flex items-center gap-4">
        {/* Active run indicator */}
        {isRunning && currentRun && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--color-primary-muted)] border border-[var(--color-primary)]">
            <div className="w-2 h-2 rounded-full bg-[var(--color-primary)] animate-pulse" />
            <span className="text-sm font-medium text-[var(--color-primary)]">
              Verification Running
            </span>
          </div>
        )}
        
        {/* Connection status */}
        <div className="flex items-center gap-2">
          <Badge variant="success" size="sm">
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            Connected
          </Badge>
        </div>
        
        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          {/* Notification dot */}
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[var(--color-danger)]" />
        </button>
        
        {/* Help */}
        <button className="p-2 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
      </div>
    </header>
  );
}
