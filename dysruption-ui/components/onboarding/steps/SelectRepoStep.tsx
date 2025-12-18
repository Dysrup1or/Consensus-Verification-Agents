/**
 * Select Repository Step
 * 
 * Second step of onboarding - select a repository to verify.
 */

'use client';

import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';
import { useOnboardingStore, type Repository } from '@/lib/stores';
import { Input, Badge, Skeleton } from '@/components/ui';
import { cn } from '@/lib/utils';

export function SelectRepoStep() {
  const { data: session } = useSession();
  const { 
    selectedRepository, 
    availableRepositories, 
    setRepositories, 
    selectRepository 
  } = useOnboardingStore();
  
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Fetch repositories on mount
  useEffect(() => {
    async function fetchRepos() {
      if (!session) {
        setIsLoading(false);
        return;
      }
      
      try {
        setIsLoading(true);
        setError(null);
        
        const response = await fetch('/api/github/repos');
        
        if (!response.ok) {
          throw new Error('Failed to fetch repositories');
        }
        
        const repos: Repository[] = await response.json();
        setRepositories(repos);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load repositories');
      } finally {
        setIsLoading(false);
      }
    }
    
    if (availableRepositories.length === 0) {
      fetchRepos();
    } else {
      setIsLoading(false);
    }
  }, [session, availableRepositories.length, setRepositories]);
  
  // Filter repositories by search
  const filteredRepos = availableRepositories.filter((repo) =>
    repo.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    repo.fullName.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (repo.description && repo.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );
  
  const handleSelect = (repo: Repository) => {
    if (selectedRepository?.id === repo.id) {
      selectRepository(null);
    } else {
      selectRepository(repo);
    }
  };
  
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="w-16 h-16 rounded-full bg-[var(--color-danger)]/20 flex items-center justify-center">
          <svg className="w-8 h-8 text-[var(--color-danger)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <p className="text-[var(--color-text-primary)] font-medium">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="text-sm text-[var(--color-primary)] hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }
  
  return (
    <div className="space-y-4">
      {/* Search */}
      <Input
        placeholder="Search repositories..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        leftIcon={
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        }
      />
      
      {/* Repository count */}
      <p className="text-sm text-[var(--color-text-muted)]">
        {filteredRepos.length} of {availableRepositories.length} repositories
      </p>
      
      {/* Repository list */}
      <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
        {filteredRepos.length === 0 ? (
          <div className="text-center py-8 text-[var(--color-text-muted)]">
            No repositories found matching &ldquo;{searchQuery}&rdquo;
          </div>
        ) : (
          filteredRepos.map((repo) => (
            <RepoCard
              key={repo.id}
              repo={repo}
              isSelected={selectedRepository?.id === repo.id}
              onSelect={() => handleSelect(repo)}
            />
          ))
        )}
      </div>
    </div>
  );
}

interface RepoCardProps {
  repo: Repository;
  isSelected: boolean;
  onSelect: () => void;
}

function RepoCard({ repo, isSelected, onSelect }: RepoCardProps) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        'w-full text-left p-4 rounded-lg border transition-all',
        'hover:border-[var(--color-text-muted)]',
        isSelected
          ? 'border-[var(--color-primary)] bg-[var(--color-primary-muted)]'
          : 'border-[var(--color-border)] bg-[var(--color-surface-2)]'
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Name */}
          <div className="flex items-center gap-2">
            <span className="font-mono font-medium text-[var(--color-text-primary)] truncate">
              {repo.name}
            </span>
            {repo.isPrivate && (
              <Badge size="sm" variant="default">
                🔒 Private
              </Badge>
            )}
          </div>
          
          {/* Full name */}
          <p className="text-xs text-[var(--color-text-muted)] truncate mt-0.5">
            {repo.fullName}
          </p>
          
          {/* Description */}
          {repo.description && (
            <p className="text-sm text-[var(--color-text-secondary)] mt-2 line-clamp-2">
              {repo.description}
            </p>
          )}
          
          {/* Metadata */}
          <div className="flex items-center gap-3 mt-3 text-xs text-[var(--color-text-muted)]">
            {repo.language && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[var(--color-primary)]" />
                {repo.language}
              </span>
            )}
            <span className="flex items-center gap-1">
              ⭐ {repo.stargazersCount}
            </span>
            <span className="flex items-center gap-1">
              🌿 {repo.defaultBranch}
            </span>
          </div>
        </div>
        
        {/* Selection indicator */}
        <div
          className={cn(
            'w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0',
            isSelected
              ? 'border-[var(--color-primary)] bg-[var(--color-primary)]'
              : 'border-[var(--color-border)]'
          )}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </div>
      </div>
    </button>
  );
}
