/**
 * Verify Page
 * 
 * Main verification experience with real-time progress,
 * tribunal panel, and remediation suggestions.
 * 
 * Integrates new UX components with existing backend via useCvaRunController.
 */

'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useSession } from 'next-auth/react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, Button, Badge, Progress, Skeleton } from '@/components/ui';
import { Celebration, triggerConfetti } from '@/components/effects';
import { useCvaRunController } from '@/components/dashboard/useCvaRunController';
import { cn } from '@/lib/utils';

// Constitution examples for vibecoders
const CONSTITUTION_EXAMPLES = [
  'No hardcoded API keys or secrets in code',
  'All user inputs must be validated',
  'Database queries must use parameterized statements',
  'All public functions need error handling',
  'Tests required for new features',
];

// Loading fallback for Suspense
function VerifyPageLoading() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <Skeleton className="h-8 w-48 mb-4" />
        <Skeleton className="h-12 w-96 mb-8" />
        <div className="grid gap-8 lg:grid-cols-2">
          <Skeleton className="h-96 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      </div>
    </div>
  );
}

// Inner component that uses useSearchParams
function VerifyPageContent() {
  const { data: session } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  
  const projectId = searchParams.get('project');
  
  // Core CVA run controller (existing backend integration)
  const cva = useCvaRunController();
  const {
    status,
    message,
    isRunning,
    stageLabel,
    displayProgress,
    consensus,
    patches,
    reportMarkdown,
    patchDiff,
    wsStatus,
    activityEvents,
    startVerification,
    handleCancelRun,
    downloadReport,
    downloadPatches,
    startNewAnalysis,
  } = cva;
  
  // Local state for constitution input
  const [constitution, setConstitution] = useState<string>('');
  const [targetPath, setTargetPath] = useState<string>('');
  const [showCelebration, setShowCelebration] = useState(false);
  
  // Get overall verdict status
  const overallStatus = consensus?.overall_status;
  const isPass = overallStatus === 'pass';
  const isFail = overallStatus === 'fail' || overallStatus === 'veto';
  
  // Trigger celebration on pass verdict
  useEffect(() => {
    if (status === 'complete' && isPass) {
      setShowCelebration(true);
      triggerConfetti();
      
      // Hide after animation
      setTimeout(() => setShowCelebration(false), 3000);
    }
  }, [status, isPass]);
  
  // Determine if we can start verification
  const canStart = constitution.trim().length > 0 && !isRunning;
  
  // Start verification with constitution
  const handleStartVerification = useCallback(() => {
    if (!canStart) return;
    
    startVerification({
      constitution,
      targetPath: targetPath || '',
      allowAutoFix: true,
    });
  }, [canStart, constitution, targetPath, startVerification]);
  
  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* Celebration effect */}
      <Celebration trigger={showCelebration} />
      
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-2">
            <Button 
              intent="ghost" 
              size="sm"
              onClick={() => router.push('/dashboard')}
            >
              ← Back to Projects
            </Button>
            <Badge 
              variant={wsStatus === 'connected' ? 'pass' : 'pending'}
            >
              {wsStatus === 'connected' ? '● Connected' : '○ Disconnected'}
            </Badge>
          </div>
          <h1 className="text-3xl font-bold text-[var(--color-text-primary)]">
            Verify Your Code
          </h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            Define your rules and let the AI tribunal judge your code
          </p>
        </div>
        
        <div className="grid gap-8 lg:grid-cols-2">
          {/* Left Column - Input */}
          <div className="space-y-6">
            {/* Constitution Input */}
            <Card variant="elevated" padding="lg">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                    📜 Constitution
                  </h2>
                  <span className="text-sm text-[var(--color-text-muted)]">
                    {constitution.split('\n').filter(l => l.trim()).length} rules
                  </span>
                </div>
                
                <p className="text-sm text-[var(--color-text-secondary)]">
                  Write the rules your code must follow. Be specific and checkable.
                </p>
                
                <textarea
                  value={constitution}
                  onChange={(e) => setConstitution(e.target.value)}
                  placeholder="Example:
1. No hardcoded secrets (keys/passwords/tokens)
2. All endpoints require auth (unless explicitly public)
3. Input validation on every request boundary
4. Tests required for new features"
                  className={cn(
                    'w-full h-48 px-4 py-3 rounded-lg resize-none',
                    'bg-[var(--color-surface-2)] border border-[var(--color-border)]',
                    'text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]',
                    'focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent',
                    'font-mono text-sm'
                  )}
                  disabled={isRunning}
                />
                
                {/* Quick add examples */}
                <div className="space-y-2">
                  <p className="text-xs text-[var(--color-text-muted)]">Quick add:</p>
                  <div className="flex flex-wrap gap-2">
                    {CONSTITUTION_EXAMPLES.map((example, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          const existing = constitution.trim();
                          const ruleNumber = constitution.split('\n').filter(l => l.trim()).length + 1;
                          const newRule = `${existing ? existing + '\n' : ''}${ruleNumber}. ${example}`;
                          setConstitution(newRule);
                        }}
                        className={cn(
                          'px-2 py-1 text-xs rounded-md',
                          'bg-[var(--color-surface-3)] text-[var(--color-text-secondary)]',
                          'hover:bg-[var(--color-primary)]/20 hover:text-[var(--color-primary)]',
                          'transition-colors'
                        )}
                        disabled={isRunning}
                      >
                        + {example.slice(0, 25)}...
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
            
            {/* Start Button */}
            <Button
              intent="primary"
              size="lg"
              className="w-full"
              onClick={handleStartVerification}
              disabled={!canStart}
            >
              {isRunning ? (
                <>
                  <span className="animate-spin mr-2">⟳</span>
                  Running Verification...
                </>
              ) : (
                <>
                  ▶ Start Verification
                </>
              )}
            </Button>
            
            {isRunning && (
              <Button
                intent="danger"
                className="w-full"
                onClick={handleCancelRun}
              >
                Cancel Run
              </Button>
            )}
          </div>
          
          {/* Right Column - Results */}
          <div className="space-y-6">
            {/* Progress Panel */}
            <Card variant="elevated" padding="lg">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                    Progress
                  </h2>
                  {status === 'complete' && consensus && (
                    <Badge 
                      variant={isPass ? 'pass' : isFail ? 'fail' : 'partial'}
                      size="lg"
                    >
                      {overallStatus?.toUpperCase()}
                    </Badge>
                  )}
                </div>
                
                {/* Progress bar */}
                <Progress 
                  value={displayProgress} 
                  max={100}
                  variant={
                    status === 'complete' && isPass ? 'success' :
                    status === 'complete' && isFail ? 'danger' :
                    'default'
                  }
                />
                
                {/* Status message */}
                <div className="flex items-center justify-between text-sm">
                  <span className="text-[var(--color-text-secondary)]">
                    {stageLabel || message || 'Ready to analyze'}
                  </span>
                  <span className="text-[var(--color-text-muted)]">
                    {displayProgress}%
                  </span>
                </div>
                
                {/* Live activity log */}
                {activityEvents.length > 0 && (
                  <div className="mt-4 p-3 bg-[var(--color-surface-2)] rounded-lg max-h-40 overflow-y-auto">
                    <p className="text-xs font-medium text-[var(--color-text-muted)] mb-2">
                      Live Activity
                    </p>
                    <div className="space-y-1 font-mono text-xs">
                      {activityEvents.slice(0, 10).map((event) => (
                        <div 
                          key={event.id}
                          className="text-[var(--color-text-secondary)] truncate"
                        >
                          {event.message}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
            
            {/* Verdict Panel */}
            {status === 'complete' && consensus && (
              <Card 
                variant={isPass ? 'success' : 'danger'}
                padding="lg"
              >
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      'w-12 h-12 rounded-full flex items-center justify-center text-2xl',
                      isPass 
                        ? 'bg-[var(--color-success)]/20' 
                        : 'bg-[var(--color-danger)]/20'
                    )}>
                      {isPass ? '✓' : '✕'}
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-[var(--color-text-primary)]">
                        {isPass ? 'All Checks Passed!' : 'Issues Found'}
                      </h3>
                      <p className="text-[var(--color-text-secondary)]">
                        {consensus.invariants_passed} of {consensus.total_invariants} invariants passed
                        {consensus.veto_triggered && ` (Veto: ${consensus.veto_reason})`}
                      </p>
                    </div>
                  </div>
                  
                  {/* Score display */}
                  <div className="flex items-center gap-4 pt-2 border-t border-[var(--color-border-muted)]">
                    <div className="text-center">
                      <p className="text-2xl font-bold text-[var(--color-text-primary)]">
                        {consensus.weighted_score.toFixed(1)}
                      </p>
                      <p className="text-xs text-[var(--color-text-muted)]">Score</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-[var(--color-text-primary)]">
                        {(consensus.confidence * 100).toFixed(0)}%
                      </p>
                      <p className="text-xs text-[var(--color-text-muted)]">Confidence</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-[var(--color-text-primary)]">
                        {consensus.files_analyzed}
                      </p>
                      <p className="text-xs text-[var(--color-text-muted)]">Files</p>
                    </div>
                  </div>
                  
                  {/* Actions */}
                  <div className="flex flex-wrap gap-2 pt-2">
                    <Button 
                      intent="secondary" 
                      size="sm"
                      onClick={downloadReport}
                    >
                      📄 Download Report
                    </Button>
                    {patches && patches.patches && patches.patches.length > 0 && (
                      <Button 
                        intent="secondary" 
                        size="sm"
                        onClick={downloadPatches}
                      >
                        🔧 Download Patches
                      </Button>
                    )}
                    <Button 
                      intent="ghost" 
                      size="sm"
                      onClick={startNewAnalysis}
                    >
                      ↻ New Analysis
                    </Button>
                  </div>
                </div>
              </Card>
            )}
            
            {/* Patches info */}
            {status === 'complete' && patches && patches.patches && patches.patches.length > 0 && (
              <Card variant="elevated" padding="lg">
                <div className="space-y-3">
                  <h3 className="text-lg font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                    🔧 Available Fixes
                  </h3>
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    {patches.patches.length} patch{patches.patches.length !== 1 ? 'es' : ''} available 
                    addressing {patches.total_issues_addressed} issue{patches.total_issues_addressed !== 1 ? 's' : ''}.
                  </p>
                  <Button 
                    intent="primary" 
                    size="sm"
                    onClick={downloadPatches}
                  >
                    Download All Patches
                  </Button>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Default export wraps content in Suspense for useSearchParams
export default function VerifyPage() {
  return (
    <Suspense fallback={<VerifyPageLoading />}>
      <VerifyPageContent />
    </Suspense>
  );
}