/**
 * Criteria Checklist Component
 * 
 * Displays success criteria with progressive completion states.
 * Shows real-time updates as criteria are evaluated.
 */

'use client';

import { useVerificationStore, type VerdictResult } from '@/lib/stores';
import { Card, Badge } from '@/components/ui';
import { cn } from '@/lib/utils';

interface CriteriaChecklistProps {
  projectId?: string;
}

const STATUS_ICONS: Record<VerdictResult, { icon: string; color: string }> = {
  pass: { icon: '✓', color: 'var(--color-success)' },
  fail: { icon: '✗', color: 'var(--color-danger)' },
  partial: { icon: '◐', color: 'var(--color-warning)' },
  pending: { icon: '○', color: 'var(--color-text-muted)' },
  veto: { icon: '⚠', color: 'var(--color-danger)' },
};

export function CriteriaChecklist({ projectId }: CriteriaChecklistProps) {
  const { currentRun } = useVerificationStore();
  const criteria = currentRun?.criteria || [];
  
  // Group criteria by status
  const passed = criteria.filter((c) => c.status === 'pass').length;
  const failed = criteria.filter((c) => c.status === 'fail' || c.status === 'veto').length;
  const pending = criteria.filter((c) => c.status === 'pending').length;
  
  if (criteria.length === 0) {
    return (
      <Card variant="default" padding="md">
        <div className="text-center py-6 text-[var(--color-text-muted)]">
          <p>No criteria defined yet</p>
          <p className="text-sm mt-1">Criteria will appear during verification</p>
        </div>
      </Card>
    );
  }
  
  return (
    <Card variant="default" padding="md" className="space-y-4">
      {/* Header with stats */}
      <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border-muted)]">
        <h4 className="font-medium text-[var(--color-text-primary)]">
          Success Criteria
        </h4>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-[var(--color-success)]">{passed} passed</span>
          <span className="text-[var(--color-text-muted)]">•</span>
          <span className="text-[var(--color-danger)]">{failed} failed</span>
          {pending > 0 && (
            <>
              <span className="text-[var(--color-text-muted)]">•</span>
              <span className="text-[var(--color-text-muted)]">{pending} pending</span>
            </>
          )}
        </div>
      </div>
      
      {/* Criteria list */}
      <div className="space-y-2">
        {criteria.map((criterion, index) => {
          const statusConfig = STATUS_ICONS[criterion.status];
          
          return (
            <div
              key={criterion.id}
              className={cn(
                'flex items-start gap-3 p-3 rounded-lg transition-all',
                'bg-[var(--color-surface-2)]',
                criterion.status === 'pass' && 'bg-[var(--color-success)]/5',
                criterion.status === 'fail' && 'bg-[var(--color-danger)]/5',
                criterion.status === 'veto' && 'bg-[var(--color-danger)]/10 ring-1 ring-[var(--color-danger)]',
                criterion.status === 'pending' && 'opacity-60'
              )}
            >
              {/* Status icon */}
              <div
                className={cn(
                  'w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0',
                  'border-2 font-bold text-sm',
                  criterion.status === 'pending' && 'border-dashed'
                )}
                style={{ 
                  borderColor: statusConfig.color,
                  color: statusConfig.color,
                }}
              >
                {statusConfig.icon}
              </div>
              
              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className={cn(
                  'text-sm',
                  criterion.status === 'pass' && 'text-[var(--color-text-primary)]',
                  criterion.status === 'fail' && 'text-[var(--color-text-primary)]',
                  criterion.status === 'pending' && 'text-[var(--color-text-muted)]'
                )}>
                  {criterion.description}
                </p>
                
                {/* Judge attribution */}
                {criterion.judgeId && (
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">
                    Evaluated by {criterion.judgeId.replace('-', ' ')} judge
                  </p>
                )}
              </div>
              
              {/* Index badge */}
              <Badge variant="default" size="sm">
                #{index + 1}
              </Badge>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
