/**
 * Verification Runner Component
 * 
 * Real-time verification progress display with streaming updates.
 * Shows current phase, progress bar, and live logs.
 */

'use client';

import { useEffect, useRef } from 'react';
import { useVerificationStore, type VerificationPhase } from '@/lib/stores';
import { Card, Badge, Progress, Button } from '@/components/ui';
import { cn } from '@/lib/utils';

interface VerificationRunnerProps {
  projectId: string;
  onComplete?: () => void;
  onCancel?: () => void;
}

const PHASE_CONFIG: Record<VerificationPhase, { label: string; icon: string; description: string }> = {
  idle: { label: 'Ready', icon: '⏳', description: 'Waiting to start...' },
  analyzing: { label: 'Analyzing', icon: '🔍', description: 'Scanning codebase and dependencies...' },
  'coverage-plan': { label: 'Planning', icon: '📋', description: 'Creating verification coverage plan...' },
  'test-generation': { label: 'Generating', icon: '🔧', description: 'Generating test cases...' },
  'test-execution': { label: 'Executing', icon: '🚀', description: 'Running tests...' },
  tribunal: { label: 'Tribunal', icon: '⚖️', description: 'Judges are deliberating...' },
  complete: { label: 'Complete', icon: '✅', description: 'Verification finished!' },
};

export function VerificationRunner({ projectId, onComplete, onCancel }: VerificationRunnerProps) {
  const { 
    currentRun, 
    isRunning, 
    wsConnected,
    cancelRun,
    addLog 
  } = useVerificationStore();
  
  const logsEndRef = useRef<HTMLDivElement>(null);
  
  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentRun?.logs]);
  
  // Handle completion
  useEffect(() => {
    if (currentRun?.phase === 'complete' && onComplete) {
      onComplete();
    }
  }, [currentRun?.phase, onComplete]);
  
  if (!currentRun) {
    return (
      <Card variant="elevated" padding="lg" className="text-center">
        <div className="py-8 space-y-4">
          <div className="w-16 h-16 mx-auto rounded-full bg-[var(--color-surface-3)] flex items-center justify-center">
            <span className="text-3xl">🚀</span>
          </div>
          <p className="text-[var(--color-text-secondary)]">
            Ready to start verification
          </p>
        </div>
      </Card>
    );
  }
  
  const phaseConfig = PHASE_CONFIG[currentRun.phase];
  
  return (
    <Card variant="elevated" padding="lg" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={cn(
            'w-12 h-12 rounded-xl flex items-center justify-center text-2xl',
            currentRun.phase === 'complete' 
              ? 'bg-[var(--color-success)]/20' 
              : 'bg-[var(--color-primary-muted)]'
          )}>
            {phaseConfig.icon}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
              {phaseConfig.label}
            </h3>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {phaseConfig.description}
            </p>
          </div>
        </div>
        
        {/* Connection indicator */}
        <Badge variant={wsConnected ? 'success' : 'warning'} size="sm">
          <span className={cn(
            'w-1.5 h-1.5 rounded-full',
            wsConnected ? 'bg-current' : 'bg-current animate-pulse'
          )} />
          {wsConnected ? 'Connected' : 'Connecting...'}
        </Badge>
      </div>
      
      {/* Main progress */}
      <Progress
        value={currentRun.progress}
        max={100}
        size="lg"
        variant="gradient"
        animated={isRunning}
        showValue
        label="Overall Progress"
      />
      
      {/* Phase progress */}
      <div className="grid grid-cols-6 gap-2">
        {Object.entries(PHASE_CONFIG).map(([phase, config]) => {
          if (phase === 'idle') return null;
          
          const isActive = currentRun.phase === phase;
          const isComplete = getPhaseIndex(currentRun.phase) > getPhaseIndex(phase as VerificationPhase);
          
          return (
            <div
              key={phase}
              className={cn(
                'text-center p-2 rounded-lg transition-all',
                isActive && 'bg-[var(--color-primary-muted)] ring-1 ring-[var(--color-primary)]',
                isComplete && 'bg-[var(--color-success)]/10',
                !isActive && !isComplete && 'bg-[var(--color-surface-2)]'
              )}
            >
              <div className={cn(
                'text-lg mb-1',
                isComplete && 'opacity-50'
              )}>
                {isComplete ? '✓' : config.icon}
              </div>
              <div className={cn(
                'text-xs font-medium',
                isActive ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-muted)]'
              )}>
                {config.label}
              </div>
            </div>
          );
        })}
      </div>
      
      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatBox label="Files Analyzed" value={currentRun.filesAnalyzed} />
        <StatBox label="Tests Generated" value={currentRun.testsGenerated} />
        <StatBox label="Tests Passed" value={currentRun.testsPassed} variant="success" />
        <StatBox label="Tests Failed" value={currentRun.testsFailed} variant="danger" />
      </div>
      
      {/* Live logs */}
      <div className="space-y-2">
        <h4 className="text-sm font-medium text-[var(--color-text-secondary)]">
          Live Logs
        </h4>
        <div className="h-48 overflow-y-auto bg-[var(--color-bg)] rounded-lg p-3 font-mono text-xs">
          {currentRun.logs.length === 0 ? (
            <p className="text-[var(--color-text-muted)]">Waiting for logs...</p>
          ) : (
            currentRun.logs.map((log, i) => (
              <div key={i} className="flex gap-2">
                <span className="text-[var(--color-text-muted)] shrink-0">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className={cn(
                  log.level === 'error' && 'text-[var(--color-danger)]',
                  log.level === 'warn' && 'text-[var(--color-warning)]',
                  log.level === 'info' && 'text-[var(--color-text-secondary)]'
                )}>
                  {log.message}
                </span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
      
      {/* Actions */}
      {isRunning && (
        <div className="flex justify-end">
          <Button
            intent="danger"
            size="sm"
            onClick={() => {
              cancelRun();
              onCancel?.();
            }}
          >
            Cancel Verification
          </Button>
        </div>
      )}
    </Card>
  );
}

interface StatBoxProps {
  label: string;
  value: number;
  variant?: 'default' | 'success' | 'danger';
}

function StatBox({ label, value, variant = 'default' }: StatBoxProps) {
  return (
    <div className="p-3 rounded-lg bg-[var(--color-surface-2)] text-center">
      <div className={cn(
        'text-2xl font-bold font-mono',
        variant === 'success' && 'text-[var(--color-success)]',
        variant === 'danger' && value > 0 && 'text-[var(--color-danger)]',
        variant === 'default' && 'text-[var(--color-text-primary)]'
      )}>
        {value}
      </div>
      <div className="text-xs text-[var(--color-text-muted)]">{label}</div>
    </div>
  );
}

function getPhaseIndex(phase: VerificationPhase): number {
  const order: VerificationPhase[] = ['idle', 'analyzing', 'coverage-plan', 'test-generation', 'test-execution', 'tribunal', 'complete'];
  return order.indexOf(phase);
}
