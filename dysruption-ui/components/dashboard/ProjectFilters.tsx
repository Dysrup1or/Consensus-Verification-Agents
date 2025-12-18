/**
 * Project Filters Component
 * 
 * Filter controls for the project list.
 */

'use client';

import { useProjectsStore, type ProjectStatus } from '@/lib/stores';
import { Input, Button } from '@/components/ui';
import { cn } from '@/lib/utils';

const STATUS_FILTERS: { value: ProjectStatus | 'all'; label: string; icon: string }[] = [
  { value: 'all', label: 'All', icon: '📋' },
  { value: 'active', label: 'Active', icon: '🟢' },
  { value: 'paused', label: 'Paused', icon: '⏸️' },
  { value: 'error', label: 'Error', icon: '❌' },
  { value: 'setup', label: 'Setup', icon: '⚙️' },
];

const SORT_OPTIONS = [
  { value: 'lastRunAt', label: 'Last Run' },
  { value: 'name', label: 'Name' },
  { value: 'passRate', label: 'Pass Rate' },
] as const;

export function ProjectFilters() {
  const {
    statusFilter,
    searchQuery,
    sortBy,
    sortOrder,
    setStatusFilter,
    setSearchQuery,
    setSortBy,
    toggleSortOrder,
  } = useProjectsStore();
  
  return (
    <div className="flex flex-col sm:flex-row gap-4">
      {/* Status filter tabs */}
      <div className="flex items-center gap-1 p-1 rounded-lg bg-[var(--color-surface-1)] border border-[var(--color-border)]">
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setStatusFilter(filter.value)}
            className={cn(
              'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
              statusFilter === filter.value
                ? 'bg-[var(--color-primary)] text-white'
                : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]'
            )}
          >
            <span className="mr-1">{filter.icon}</span>
            <span className="hidden sm:inline">{filter.label}</span>
          </button>
        ))}
      </div>
      
      {/* Search */}
      <div className="flex-1">
        <Input
          placeholder="Filter projects..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          inputSize="sm"
          leftIcon={
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
          }
        />
      </div>
      
      {/* Sort controls */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-[var(--color-text-muted)]">Sort:</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          className={cn(
            'h-9 px-3 rounded-lg border text-sm',
            'bg-[var(--color-surface-1)] border-[var(--color-border)]',
            'text-[var(--color-text-primary)]',
            'focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]'
          )}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        
        <button
          onClick={toggleSortOrder}
          className={cn(
            'h-9 w-9 flex items-center justify-center rounded-lg border',
            'bg-[var(--color-surface-1)] border-[var(--color-border)]',
            'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
            'hover:bg-[var(--color-surface-2)] transition-colors'
          )}
          title={sortOrder === 'asc' ? 'Ascending' : 'Descending'}
        >
          {sortOrder === 'asc' ? (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
