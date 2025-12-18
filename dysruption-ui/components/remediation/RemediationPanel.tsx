/**
 * Remediation Panel Component
 * 
 * Displays suggested fixes with one-click apply functionality.
 * Shows code diffs and allows applying fixes directly.
 */

'use client';

import { useState } from 'react';
import { Card, Button, Badge, Modal, ModalHeader, ModalBody, ModalFooter, ModalCloseButton } from '@/components/ui';
import { cn } from '@/lib/utils';

export interface RemediationSuggestion {
  id: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  category: 'security' | 'architecture' | 'performance' | 'style';
  filePath: string;
  lineStart: number;
  lineEnd: number;
  originalCode: string;
  suggestedCode: string;
  reasoning: string;
  judgeId: string;
}

interface RemediationPanelProps {
  suggestions: RemediationSuggestion[];
  onApply?: (id: string) => Promise<void>;
  onApplyAll?: () => Promise<void>;
  onDismiss?: (id: string) => void;
}

const SEVERITY_CONFIG = {
  critical: { label: 'Critical', variant: 'veto' as const, icon: '🚨' },
  high: { label: 'High', variant: 'danger' as const, icon: '⚠️' },
  medium: { label: 'Medium', variant: 'warning' as const, icon: '🔶' },
  low: { label: 'Low', variant: 'info' as const, icon: '💡' },
};

const CATEGORY_CONFIG = {
  security: { label: 'Security', icon: '🔒' },
  architecture: { label: 'Architecture', icon: '🏛️' },
  performance: { label: 'Performance', icon: '⚡' },
  style: { label: 'Code Style', icon: '✨' },
};

export function RemediationPanel({ suggestions, onApply, onApplyAll, onDismiss }: RemediationPanelProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [applyingAll, setApplyingAll] = useState(false);
  const [confirmModal, setConfirmModal] = useState<RemediationSuggestion | null>(null);
  
  const handleApply = async (suggestion: RemediationSuggestion) => {
    if (!onApply) return;
    
    setApplyingId(suggestion.id);
    try {
      await onApply(suggestion.id);
    } finally {
      setApplyingId(null);
      setConfirmModal(null);
    }
  };
  
  const handleApplyAll = async () => {
    if (!onApplyAll) return;
    
    setApplyingAll(true);
    try {
      await onApplyAll();
    } finally {
      setApplyingAll(false);
    }
  };
  
  if (suggestions.length === 0) {
    return (
      <Card variant="success" padding="lg" className="text-center">
        <div className="py-6 space-y-3">
          <div className="w-16 h-16 mx-auto rounded-full bg-[var(--color-success)]/20 flex items-center justify-center">
            <span className="text-3xl">✅</span>
          </div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
            All Clear!
          </h3>
          <p className="text-[var(--color-text-secondary)]">
            No remediation suggestions. Your code passed all checks.
          </p>
        </div>
      </Card>
    );
  }
  
  // Group by severity
  const grouped = {
    critical: suggestions.filter((s) => s.severity === 'critical'),
    high: suggestions.filter((s) => s.severity === 'high'),
    medium: suggestions.filter((s) => s.severity === 'medium'),
    low: suggestions.filter((s) => s.severity === 'low'),
  };
  
  return (
    <>
      <Card variant="default" padding="md" className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border-muted)]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[var(--color-warning)]/20 flex items-center justify-center text-xl">
              🔧
            </div>
            <div>
              <h3 className="font-semibold text-[var(--color-text-primary)]">
                Remediation Suggestions
              </h3>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {suggestions.length} issue{suggestions.length !== 1 ? 's' : ''} found
              </p>
            </div>
          </div>
          
          {onApplyAll && suggestions.length > 1 && (
            <Button
              intent="primary"
              size="sm"
              onClick={handleApplyAll}
              loading={applyingAll}
            >
              🚀 Apply All Fixes
            </Button>
          )}
        </div>
        
        {/* Severity summary */}
        <div className="flex items-center gap-4 text-sm">
          {Object.entries(grouped).map(([severity, items]) => {
            if (items.length === 0) return null;
            const config = SEVERITY_CONFIG[severity as keyof typeof SEVERITY_CONFIG];
            return (
              <div key={severity} className="flex items-center gap-1">
                <span>{config.icon}</span>
                <span className="font-medium">{items.length}</span>
                <span className="text-[var(--color-text-muted)]">{config.label}</span>
              </div>
            );
          })}
        </div>
        
        {/* Suggestions list */}
        <div className="space-y-2">
          {suggestions.map((suggestion) => (
            <SuggestionCard
              key={suggestion.id}
              suggestion={suggestion}
              isExpanded={expandedId === suggestion.id}
              isApplying={applyingId === suggestion.id}
              onToggle={() => setExpandedId(expandedId === suggestion.id ? null : suggestion.id)}
              onApply={() => setConfirmModal(suggestion)}
              onDismiss={() => onDismiss?.(suggestion.id)}
            />
          ))}
        </div>
      </Card>
      
      {/* Confirm modal */}
      <Modal
        open={confirmModal !== null}
        onClose={() => setConfirmModal(null)}
        size="lg"
      >
        {confirmModal && (
          <>
            <ModalHeader>
              <div className="flex items-center gap-2">
                <span>Apply Fix?</span>
                <ModalCloseButton onClose={() => setConfirmModal(null)} />
              </div>
            </ModalHeader>
            <ModalBody className="space-y-4">
              <p className="text-[var(--color-text-secondary)]">
                This will modify <code className="text-[var(--color-primary)]">{confirmModal.filePath}</code>
              </p>
              
              <div className="space-y-2">
                <p className="text-sm font-medium text-[var(--color-text-primary)]">Changes:</p>
                <CodeDiff
                  original={confirmModal.originalCode}
                  suggested={confirmModal.suggestedCode}
                />
              </div>
            </ModalBody>
            <ModalFooter>
              <Button intent="ghost" onClick={() => setConfirmModal(null)}>
                Cancel
              </Button>
              <Button
                intent="primary"
                onClick={() => handleApply(confirmModal)}
                loading={applyingId === confirmModal.id}
              >
                Apply Fix
              </Button>
            </ModalFooter>
          </>
        )}
      </Modal>
    </>
  );
}

interface SuggestionCardProps {
  suggestion: RemediationSuggestion;
  isExpanded: boolean;
  isApplying: boolean;
  onToggle: () => void;
  onApply: () => void;
  onDismiss: () => void;
}

function SuggestionCard({ suggestion, isExpanded, isApplying, onToggle, onApply, onDismiss }: SuggestionCardProps) {
  const severityConfig = SEVERITY_CONFIG[suggestion.severity];
  const categoryConfig = CATEGORY_CONFIG[suggestion.category];
  
  return (
    <div
      className={cn(
        'rounded-lg border transition-all',
        'bg-[var(--color-surface-2)]',
        suggestion.severity === 'critical' && 'border-[var(--color-danger)]',
        suggestion.severity === 'high' && 'border-[var(--color-warning)]',
        suggestion.severity !== 'critical' && suggestion.severity !== 'high' && 'border-[var(--color-border)]'
      )}
    >
      {/* Header (always visible) */}
      <button
        className="w-full flex items-center gap-3 p-3 text-left"
        onClick={onToggle}
      >
        {/* Severity icon */}
        <span className="text-lg">{severityConfig.icon}</span>
        
        {/* Title and meta */}
        <div className="flex-1 min-w-0">
          <p className="font-medium text-[var(--color-text-primary)] truncate">
            {suggestion.title}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-[var(--color-text-muted)] font-mono">
              {suggestion.filePath}:{suggestion.lineStart}
            </span>
            <Badge variant={categoryConfig.label === 'Security' ? 'security' : 'default'} size="sm">
              {categoryConfig.icon} {categoryConfig.label}
            </Badge>
          </div>
        </div>
        
        {/* Expand icon */}
        <svg
          className={cn(
            'w-5 h-5 text-[var(--color-text-muted)] transition-transform',
            isExpanded && 'rotate-180'
          )}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      
      {/* Expanded content */}
      {isExpanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-[var(--color-border-muted)]">
          {/* Description */}
          <p className="text-sm text-[var(--color-text-secondary)] pt-3">
            {suggestion.description}
          </p>
          
          {/* Code diff */}
          <CodeDiff
            original={suggestion.originalCode}
            suggested={suggestion.suggestedCode}
          />
          
          {/* Reasoning */}
          <div className="p-2 rounded-lg bg-[var(--color-surface-3)] text-sm">
            <p className="text-[var(--color-text-muted)] mb-1">Why this matters:</p>
            <p className="text-[var(--color-text-secondary)]">{suggestion.reasoning}</p>
          </div>
          
          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-2">
            <Button intent="ghost" size="sm" onClick={onDismiss}>
              Dismiss
            </Button>
            <Button
              intent="primary"
              size="sm"
              onClick={onApply}
              loading={isApplying}
            >
              ✨ Apply Fix
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

interface CodeDiffProps {
  original: string;
  suggested: string;
}

function CodeDiff({ original, suggested }: CodeDiffProps) {
  return (
    <div className="grid grid-cols-2 gap-2 text-xs font-mono">
      {/* Original */}
      <div className="p-3 rounded-lg bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/30">
        <p className="text-[var(--color-danger)] font-medium mb-2">- Before</p>
        <pre className="whitespace-pre-wrap text-[var(--color-text-secondary)] overflow-x-auto">
          {original}
        </pre>
      </div>
      
      {/* Suggested */}
      <div className="p-3 rounded-lg bg-[var(--color-success)]/10 border border-[var(--color-success)]/30">
        <p className="text-[var(--color-success)] font-medium mb-2">+ After</p>
        <pre className="whitespace-pre-wrap text-[var(--color-text-secondary)] overflow-x-auto">
          {suggested}
        </pre>
      </div>
    </div>
  );
}
