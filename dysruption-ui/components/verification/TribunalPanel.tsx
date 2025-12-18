/**
 * Tribunal Panel Component
 * 
 * Displays the AI tribunal with judge avatars and their verdicts.
 * Shows animated deliberation and final verdict reveal.
 */

'use client';

import { useState, useEffect, useMemo } from 'react';
import { useVerificationStore, type JudgeVerdict, type VerdictResult } from '@/lib/stores';
import { Card, Badge, Progress } from '@/components/ui';
import { cn } from '@/lib/utils';

interface TribunalPanelProps {
  runId?: string;
  showAnimation?: boolean;
}

const JUDGE_CONFIG = {
  architect: {
    name: 'Architecture Judge',
    emoji: '🏛️',
    color: 'var(--color-judge-architect)',
    description: 'Evaluates code structure, patterns, and maintainability',
  },
  security: {
    name: 'Security Judge',
    emoji: '🔒',
    color: 'var(--color-judge-security)',
    description: 'Analyzes vulnerabilities, auth flows, and data handling',
  },
  'user-proxy': {
    name: 'User Proxy Judge',
    emoji: '👤',
    color: 'var(--color-judge-user-proxy)',
    description: 'Represents end-user experience and requirements',
  },
};

const VERDICT_LABELS: Record<VerdictResult, { label: string; variant: string }> = {
  pass: { label: 'PASS', variant: 'pass' },
  fail: { label: 'FAIL', variant: 'fail' },
  partial: { label: 'PARTIAL', variant: 'partial' },
  pending: { label: 'PENDING', variant: 'pending' },
  veto: { label: 'VETO', variant: 'veto' },
};

export function TribunalPanel({ runId, showAnimation = true }: TribunalPanelProps) {
  const { currentRun } = useVerificationStore();
  const [revealedJudges, setRevealedJudges] = useState<string[]>([]);
  const [isDeliberating, setIsDeliberating] = useState(false);
  
  const verdicts = useMemo(
    () => currentRun?.judgeVerdicts || [],
    [currentRun?.judgeVerdicts]
  );
  const finalVerdict = currentRun?.finalVerdict || 'pending';
  
  // Animate judge reveal
  useEffect(() => {
    if (!showAnimation || verdicts.length === 0) {
      setRevealedJudges(verdicts.map((v) => v.judgeId));
      return;
    }
    
    setIsDeliberating(true);
    const revealed: string[] = [];
    
    verdicts.forEach((verdict, index) => {
      setTimeout(() => {
        revealed.push(verdict.judgeId);
        setRevealedJudges([...revealed]);
        
        if (index === verdicts.length - 1) {
          setTimeout(() => setIsDeliberating(false), 500);
        }
      }, 1000 * (index + 1));
    });
    
    return () => setRevealedJudges([]);
  }, [verdicts, showAnimation]);
  
  return (
    <Card variant="elevated" padding="lg" className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-[var(--color-surface-3)] flex items-center justify-center text-2xl">
            ⚖️
          </div>
          <div>
            <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
              AI Tribunal
            </h3>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {isDeliberating ? 'Judges are deliberating...' : 'Verdict rendered'}
            </p>
          </div>
        </div>
        
        {/* Final verdict badge */}
        {finalVerdict !== 'pending' && !isDeliberating && (
          <Badge
            variant={VERDICT_LABELS[finalVerdict].variant as VerdictResult}
            size="lg"
            className="text-base px-4 py-2"
          >
            {VERDICT_LABELS[finalVerdict].label}
          </Badge>
        )}
      </div>
      
      {/* Judge cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(JUDGE_CONFIG).map(([judgeId, config]) => {
          const verdict = verdicts.find((v) => v.judgeId === judgeId);
          const isRevealed = revealedJudges.includes(judgeId);
          
          return (
            <JudgeCard
              key={judgeId}
              judgeId={judgeId}
              config={config}
              verdict={verdict}
              isRevealed={isRevealed}
              isDeliberating={isDeliberating && !isRevealed}
            />
          );
        })}
      </div>
      
      {/* Criteria breakdown */}
      {currentRun?.criteria && currentRun.criteria.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-[var(--color-text-secondary)]">
            Criteria Breakdown
          </h4>
          <div className="space-y-2">
            {currentRun.criteria.map((criterion) => (
              <div
                key={criterion.id}
                className="flex items-center justify-between p-3 rounded-lg bg-[var(--color-surface-2)]"
              >
                <span className="text-sm text-[var(--color-text-primary)]">
                  {criterion.description}
                </span>
                <Badge
                  variant={VERDICT_LABELS[criterion.status].variant as VerdictResult}
                  size="sm"
                >
                  {VERDICT_LABELS[criterion.status].label}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

interface JudgeCardProps {
  judgeId: string;
  config: typeof JUDGE_CONFIG[keyof typeof JUDGE_CONFIG];
  verdict?: JudgeVerdict;
  isRevealed: boolean;
  isDeliberating: boolean;
}

function JudgeCard({ judgeId, config, verdict, isRevealed, isDeliberating }: JudgeCardProps) {
  return (
    <div
      className={cn(
        'p-4 rounded-xl border transition-all duration-500',
        'bg-[var(--color-surface-1)]',
        isRevealed
          ? 'border-[color:var(--judge-color)] shadow-[0_0_20px_rgba(var(--judge-color-rgb),0.15)]'
          : 'border-[var(--color-border)]',
        isDeliberating && 'animate-pulse'
      )}
      style={{
        '--judge-color': config.color,
      } as React.CSSProperties}
    >
      {/* Judge avatar */}
      <div className="flex items-center gap-3 mb-3">
        <div
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center text-xl',
            isRevealed ? 'bg-[color:var(--judge-color)]/20' : 'bg-[var(--color-surface-3)]'
          )}
        >
          {config.emoji}
        </div>
        <div>
          <h4 className="font-medium text-[var(--color-text-primary)]">
            {config.name}
          </h4>
          {verdict && isRevealed && (
            <Badge
              variant={VERDICT_LABELS[verdict.verdict].variant as VerdictResult}
              size="sm"
            >
              {VERDICT_LABELS[verdict.verdict].label}
            </Badge>
          )}
        </div>
      </div>
      
      {/* Description or verdict */}
      {isRevealed && verdict ? (
        <div className="space-y-3">
          {/* Confidence */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-[var(--color-text-muted)]">Confidence</span>
              <span className="font-mono">{Math.round(verdict.confidence * 100)}%</span>
            </div>
            <Progress value={verdict.confidence * 100} size="sm" variant="default" />
          </div>
          
          {/* Reasoning */}
          <p className="text-sm text-[var(--color-text-secondary)] line-clamp-3">
            {verdict.reasoning}
          </p>
          
          {/* Veto reason */}
          {verdict.vetoReason && (
            <div className="p-2 rounded-lg bg-[var(--color-danger)]/10 border border-[var(--color-danger)]">
              <p className="text-xs font-medium text-[var(--color-danger)]">
                🚨 VETO: {verdict.vetoReason}
              </p>
            </div>
          )}
        </div>
      ) : (
        <p className="text-sm text-[var(--color-text-muted)]">
          {isDeliberating ? 'Analyzing...' : config.description}
        </p>
      )}
    </div>
  );
}
