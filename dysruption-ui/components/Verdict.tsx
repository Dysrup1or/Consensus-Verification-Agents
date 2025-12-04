import { useState } from 'react';
import { JudgeVerdict, JudgeRole } from '@/lib/types';
import { clsx } from 'clsx';
import { ChevronDown, ChevronUp, ShieldAlert, CheckCircle, XCircle, AlertTriangle, Copy, Check } from 'lucide-react';
import CopyButton, { formatIssueForClipboard, formatIssuesForClipboard } from './CopyButton';

interface VerdictProps {
  verdicts: Record<string, JudgeVerdict>;
  vetoTriggered?: boolean;
}

export default function Verdict({ verdicts, vetoTriggered = false }: VerdictProps) {
  const judgeOrder: JudgeRole[] = ['architect', 'security', 'user_proxy'];
  
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {judgeOrder.map((role) => {
        const judge = verdicts[role];
        if (!judge) return null;
        return (
          <JudgeCard 
            key={role} 
            judge={judge} 
            isVeto={vetoTriggered && role === 'security'} 
          />
        );
      })}
    </div>
  );
}

function JudgeCard({ judge, isVeto }: { judge: JudgeVerdict; isVeto: boolean }) {
  const [expanded, setExpanded] = useState(false);
  
  const isPassing = judge.status === 'pass';
  const isFailing = judge.status === 'fail' || judge.status === 'error';
  
  const statusColor = isVeto
    ? 'text-danger border-danger/50'
    : isPassing
    ? 'text-success border-success/50'
    : isFailing
    ? 'text-danger border-danger/50'
    : 'text-warning border-warning/50';

  const Icon = isVeto
    ? ShieldAlert
    : isPassing
    ? CheckCircle
    : isFailing
    ? XCircle
    : AlertTriangle;

  const roleLabels: Record<JudgeRole, string> = {
    architect: 'Architect',
    security: 'Security',
    user_proxy: 'User Proxy',
  };

  // Format the full judge verdict for clipboard
  const getFullVerdictText = (): string => {
    const parts = [
      `## ${roleLabels[judge.judge_role]} Judge Verdict`,
      `Score: ${judge.score.toFixed(1)}/10 | Status: ${judge.status.toUpperCase()}`,
      `Confidence: ${(judge.confidence * 100).toFixed(0)}%`,
      '',
      '### Explanation',
      judge.explanation,
    ];
    
    if (judge.issues.length > 0) {
      parts.push('', '### Issues');
      judge.issues.forEach((issue, i) => {
        parts.push(`${i + 1}. ${issue.description}`);
        if (issue.file_path) {
          parts.push(`   Location: ${issue.file_path}${issue.line_number ? `:${issue.line_number}` : ''}`);
        }
        if (issue.suggestion) {
          parts.push(`   Fix: ${issue.suggestion}`);
        }
      });
    }
    
    if (judge.suggestions.length > 0) {
      parts.push('', '### Suggestions');
      judge.suggestions.forEach((s, i) => {
        parts.push(`${i + 1}. ${s}`);
      });
    }
    
    return parts.join('\n');
  };

  return (
    <div 
      className={clsx(
        "border rounded-lg p-4 bg-surface transition-all",
        statusColor,
        isVeto && "border-2 motion-safe:animate-pulse"
      )}
      data-testid={isVeto ? "veto" : undefined}
    >
      {/* Header - Clickable to expand */}
      <div 
        className="cursor-pointer hover:bg-panel/50 -m-4 p-4 rounded-t-lg"
        onClick={() => setExpanded(!expanded)}
        role="button"
        aria-expanded={expanded}
        tabIndex={0}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Icon className="w-6 h-6" />
            <span className="font-bold uppercase">{roleLabels[judge.judge_role]}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-textMuted">{judge.model_used}</span>
            {/* Copy full verdict button */}
            <div onClick={(e) => e.stopPropagation()}>
              <CopyButton 
                text={getFullVerdictText()}
                title="Copy full verdict"
                size="sm"
              />
            </div>
          </div>
        </div>
        
        <div className="flex justify-between items-center mb-2">
          <span className="font-mono text-sm">
            Score: {judge.score.toFixed(1)}/10 | Conf: {(judge.confidence * 100).toFixed(0)}%
          </span>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>

        <div className="text-xs uppercase tracking-wider">
          <span className={clsx(
            "px-2 py-0.5 rounded",
            isPassing ? "bg-success/20 text-success" : "bg-danger/20 text-danger"
          )}>
            {judge.status}
          </span>
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-border text-sm animate-in fade-in slide-in-from-top-2 space-y-4">
          {/* Explanation with copy button */}
          <div className="relative group">
            <div className="flex items-start justify-between gap-2">
              <p className="font-mono whitespace-pre-wrap text-textMuted flex-1">{judge.explanation}</p>
              <CopyButton 
                text={judge.explanation}
                title="Copy explanation"
                size="sm"
                className="opacity-0 group-hover:opacity-100 flex-shrink-0"
              />
            </div>
          </div>
          
          {/* Issues with individual copy buttons */}
          {judge.issues.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-textMuted uppercase tracking-wider">Issues ({judge.issues.length})</span>
                {judge.issues.length > 1 && (
                  <CopyButton 
                    text={formatIssuesForClipboard(judge.issues)}
                    label="Copy All"
                    variant="both"
                    size="sm"
                    title="Copy all issues"
                  />
                )}
              </div>
              <ul className="space-y-2">
                {judge.issues.map((issue, i) => (
                  <li key={i} className="flex items-start gap-2 group bg-danger/5 p-2 rounded-lg">
                    <span className="text-xs text-danger flex-1">
                      <span className="font-semibold">#{i + 1}</span> {issue.description}
                      {issue.file_path && (
                        <span className="text-textMuted block text-[10px] mt-0.5">
                          {issue.file_path}{issue.line_number ? `:${issue.line_number}` : ''}
                        </span>
                      )}
                      {issue.suggestion && (
                        <span className="text-primary block text-[10px] mt-0.5">
                          💡 {issue.suggestion}
                        </span>
                      )}
                    </span>
                    <CopyButton 
                      text={formatIssueForClipboard(issue)}
                      size="sm"
                      className="opacity-0 group-hover:opacity-100 flex-shrink-0"
                      title="Copy this issue"
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggestions with copy buttons */}
          {judge.suggestions.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-textMuted uppercase tracking-wider">Suggestions ({judge.suggestions.length})</span>
                {judge.suggestions.length > 1 && (
                  <CopyButton 
                    text={judge.suggestions.map((s, i) => `${i + 1}. ${s}`).join('\n')}
                    label="Copy All"
                    variant="both"
                    size="sm"
                    title="Copy all suggestions"
                  />
                )}
              </div>
              <ul className="space-y-1">
                {judge.suggestions.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 group">
                    <span className="text-xs text-primary flex-1">• {s}</span>
                    <CopyButton 
                      text={s}
                      size="sm"
                      className="opacity-0 group-hover:opacity-100 flex-shrink-0"
                      title="Copy this suggestion"
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      
      {isVeto && (
        <div className="sr-only" role="alert">
          Security judge vetoed this change.
        </div>
      )}
    </div>
  );
}
