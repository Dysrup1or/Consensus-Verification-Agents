/**
 * Project Card Component
 * 
 * Individual project card showing status, last run, and quick actions.
 */

'use client';

import { useRouter } from 'next/navigation';
import { Card, Badge, Progress, Button } from '@/components/ui';
import type { Project } from '@/lib/stores';
import { cn, formatRelativeTime } from '@/lib/utils';

interface ProjectCardProps {
  project: Project;
}

const STATUS_CONFIG = {
  active: { label: 'Active', variant: 'success' as const, icon: '🟢' },
  paused: { label: 'Paused', variant: 'warning' as const, icon: '⏸️' },
  error: { label: 'Error', variant: 'danger' as const, icon: '❌' },
  setup: { label: 'Setup', variant: 'info' as const, icon: '⚙️' },
};

const VERDICT_CONFIG = {
  pass: { label: 'PASS', variant: 'pass' as const },
  fail: { label: 'FAIL', variant: 'fail' as const },
  partial: { label: 'PARTIAL', variant: 'partial' as const },
  pending: { label: 'PENDING', variant: 'pending' as const },
  veto: { label: 'VETO', variant: 'veto' as const },
};

export function ProjectCard({ project }: ProjectCardProps) {
  const router = useRouter();
  const statusConfig = STATUS_CONFIG[project.status];
  const verdictConfig = project.lastVerdict ? VERDICT_CONFIG[project.lastVerdict] : null;
  
  const handleClick = () => {
    router.push(`/project/${project.id}`);
  };
  
  const handleVerify = (e: React.MouseEvent) => {
    e.stopPropagation();
    router.push(`/project/${project.id}/verify`);
  };
  
  return (
    <Card
      variant="default"
      padding="lg"
      interactive
      onClick={handleClick}
      className="group"
    >
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Project name */}
            <h3 className="font-semibold text-[var(--color-text-primary)] truncate group-hover:text-[var(--color-primary)] transition-colors">
              {project.name}
            </h3>
            
            {/* Full name */}
            <p className="text-xs text-[var(--color-text-muted)] font-mono truncate mt-0.5">
              {project.fullName}
            </p>
          </div>
          
          {/* Status badge */}
          <Badge variant={statusConfig.variant} size="sm">
            {statusConfig.icon} {statusConfig.label}
          </Badge>
        </div>
        
        {/* Description */}
        {project.description && (
          <p className="text-sm text-[var(--color-text-secondary)] line-clamp-2">
            {project.description}
          </p>
        )}
        
        {/* Pass rate progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--color-text-muted)]">Pass Rate</span>
            <span className={cn(
              'font-mono font-medium',
              project.passRate >= 80 ? 'text-[var(--color-success)]' :
              project.passRate >= 50 ? 'text-[var(--color-warning)]' :
              'text-[var(--color-danger)]'
            )}>
              {project.passRate}%
            </span>
          </div>
          <Progress
            value={project.passRate}
            max={100}
            size="sm"
            variant={
              project.passRate >= 80 ? 'success' :
              project.passRate >= 50 ? 'warning' : 'danger'
            }
          />
        </div>
        
        {/* Last run info */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            {verdictConfig && (
              <Badge variant={verdictConfig.variant} size="sm">
                {verdictConfig.label}
              </Badge>
            )}
          </div>
          
          <span className="text-[var(--color-text-muted)]">
            {project.lastRunAt 
              ? formatRelativeTime(project.lastRunAt)
              : 'Never run'
            }
          </span>
        </div>
        
        {/* Actions */}
        <div className="flex items-center gap-2 pt-2 border-t border-[var(--color-border-muted)]">
          <Button
            intent="primary"
            size="sm"
            fullWidth
            onClick={handleVerify}
          >
            🚀 Verify Now
          </Button>
          
          <Button
            intent="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              router.push(`/project/${project.id}/settings`);
            }}
          >
            ⚙️
          </Button>
        </div>
      </div>
    </Card>
  );
}
