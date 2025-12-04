'use client';

import { useState } from 'react';
import { clsx } from 'clsx';
import { 
  Copy, 
  Check, 
  ChevronDown, 
  ChevronUp, 
  Sparkles, 
  AlertTriangle,
  Shield,
  Cog,
  Paintbrush,
  Clock,
  FileText,
  Zap,
  ArrowRight
} from 'lucide-react';

interface PriorityIssue {
  severity: string;
  category: string;
  description: string;
  file_path?: string;
  line_number?: number;
  judge_source?: string;
  suggestion?: string;
}

interface PromptData {
  primary_prompt: string;
  priority_issues: PriorityIssue[];
  strategy: string;
  complexity: string;
  alternative_prompts: string[];
  context_files: string[];
  estimated_tokens: number;
  generation_time_ms: number;
  veto_addressed: boolean;
}

interface PromptRecommendationProps {
  prompt: PromptData;
  runId: string;
}

export default function PromptRecommendation({ prompt, runId }: PromptRecommendationProps) {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'primary' | 'issues' | 'alternatives'>('primary');
  const [expandedIssue, setExpandedIssue] = useState<number | null>(null);

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const severityColors: Record<string, string> = {
    critical: 'text-danger bg-danger/10 border-danger/30',
    high: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
    medium: 'text-warning bg-warning/10 border-warning/30',
    low: 'text-success bg-success/10 border-success/30',
  };

  const categoryIcons: Record<string, React.ReactNode> = {
    security: <Shield className="w-4 h-4" />,
    functionality: <Cog className="w-4 h-4" />,
    style: <Paintbrush className="w-4 h-4" />,
  };

  const complexityColors: Record<string, string> = {
    low: 'text-success',
    medium: 'text-warning',
    high: 'text-danger',
  };

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-panel">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Sparkles className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-lg">AI Fix Prompt</h3>
              <p className="text-sm text-textMuted">
                Generated prompt to fix {prompt.priority_issues.length} issues
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2 text-textMuted">
              <Zap className="w-4 h-4" />
              <span className={complexityColors[prompt.complexity]}>
                {prompt.complexity.toUpperCase()}
              </span>
            </div>
            <div className="flex items-center gap-2 text-textMuted">
              <Clock className="w-4 h-4" />
              <span>{prompt.generation_time_ms}ms</span>
            </div>
          </div>
        </div>

        {prompt.veto_addressed && (
          <div className="mt-3 flex items-center gap-2 text-sm text-danger bg-danger/10 px-3 py-2 rounded-lg">
            <AlertTriangle className="w-4 h-4" />
            <span>Security veto addressed - prioritize these fixes first!</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('primary')}
          className={clsx(
            'px-6 py-3 text-sm font-medium transition-colors',
            activeTab === 'primary'
              ? 'text-primary border-b-2 border-primary bg-primary/5'
              : 'text-textMuted hover:text-text'
          )}
        >
          Primary Prompt
        </button>
        <button
          onClick={() => setActiveTab('issues')}
          className={clsx(
            'px-6 py-3 text-sm font-medium transition-colors',
            activeTab === 'issues'
              ? 'text-primary border-b-2 border-primary bg-primary/5'
              : 'text-textMuted hover:text-text'
          )}
        >
          Issues ({prompt.priority_issues.length})
        </button>
        <button
          onClick={() => setActiveTab('alternatives')}
          className={clsx(
            'px-6 py-3 text-sm font-medium transition-colors',
            activeTab === 'alternatives'
              ? 'text-primary border-b-2 border-primary bg-primary/5'
              : 'text-textMuted hover:text-text'
          )}
        >
          Alternatives ({prompt.alternative_prompts.length})
        </button>
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === 'primary' && (
          <div className="space-y-4">
            {/* Strategy */}
            <div className="bg-panel border border-border rounded-lg p-4">
              <div className="flex items-center gap-2 text-sm text-textMuted mb-2">
                <ArrowRight className="w-4 h-4" />
                <span className="uppercase tracking-wider text-xs">Strategy</span>
              </div>
              <p className="text-text">{prompt.strategy}</p>
            </div>

            {/* Context Files */}
            {prompt.context_files.length > 0 && (
              <div className="flex items-center gap-2 text-sm text-textMuted">
                <FileText className="w-4 h-4" />
                <span>Context files: </span>
                <div className="flex flex-wrap gap-1">
                  {prompt.context_files.map((file, i) => (
                    <code key={i} className="px-2 py-0.5 bg-panel rounded text-xs">
                      {file}
                    </code>
                  ))}
                </div>
              </div>
            )}

            {/* Main Prompt */}
            <div className="relative">
              <div className="absolute top-3 right-3 z-10">
                <button
                  onClick={() => copyToClipboard(prompt.primary_prompt)}
                  className={clsx(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors',
                    copied
                      ? 'bg-success/20 text-success'
                      : 'bg-panel hover:bg-border text-textMuted hover:text-text'
                  )}
                >
                  {copied ? (
                    <>
                      <Check className="w-4 h-4" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4" />
                      Copy Prompt
                    </>
                  )}
                </button>
              </div>

              <div className="bg-bg border border-border rounded-lg p-4 pr-32 max-h-[500px] overflow-y-auto">
                <pre className="whitespace-pre-wrap font-mono text-sm text-text leading-relaxed">
                  {prompt.primary_prompt}
                </pre>
              </div>

              <div className="mt-2 text-xs text-textMuted text-right">
                ~{prompt.estimated_tokens} tokens
              </div>
            </div>
          </div>
        )}

        {activeTab === 'issues' && (
          <div className="space-y-3">
            {prompt.priority_issues.map((issue, index) => (
              <div
                key={index}
                className={clsx(
                  'border rounded-lg overflow-hidden transition-all',
                  severityColors[issue.severity]
                )}
              >
                <button
                  onClick={() => setExpandedIssue(expandedIssue === index ? null : index)}
                  className="w-full px-4 py-3 flex items-center justify-between text-left"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-current">
                      {categoryIcons[issue.category] || <FileText className="w-4 h-4" />}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium uppercase tracking-wider opacity-70">
                          {issue.severity}
                        </span>
                        <span className="text-xs opacity-50">•</span>
                        <span className="text-xs opacity-70">{issue.category}</span>
                      </div>
                      <p className="text-sm mt-0.5 text-text">{issue.description}</p>
                    </div>
                  </div>
                  {expandedIssue === index ? (
                    <ChevronUp className="w-4 h-4 text-current flex-shrink-0" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-current flex-shrink-0" />
                  )}
                </button>

                {expandedIssue === index && (
                  <div className="px-4 pb-4 pt-0 border-t border-current/10 space-y-2 text-sm">
                    {issue.file_path && (
                      <div className="flex items-center gap-2">
                        <span className="text-textMuted">File:</span>
                        <code className="px-2 py-0.5 bg-black/20 rounded text-xs">
                          {issue.file_path}
                          {issue.line_number && `:${issue.line_number}`}
                        </code>
                      </div>
                    )}
                    {issue.judge_source && (
                      <div className="flex items-center gap-2">
                        <span className="text-textMuted">Source:</span>
                        <span>{issue.judge_source}</span>
                      </div>
                    )}
                    {issue.suggestion && (
                      <div className="mt-2 p-2 bg-black/10 rounded">
                        <span className="text-xs uppercase tracking-wider text-textMuted">Suggestion:</span>
                        <p className="mt-1">{issue.suggestion}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {activeTab === 'alternatives' && (
          <div className="space-y-4">
            {prompt.alternative_prompts.length === 0 ? (
              <p className="text-textMuted text-center py-8">
                No alternative prompts generated.
              </p>
            ) : (
              prompt.alternative_prompts.map((altPrompt, index) => (
                <div key={index} className="relative">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-textMuted">
                      Alternative #{index + 1}
                    </span>
                    <button
                      onClick={() => copyToClipboard(altPrompt)}
                      className="flex items-center gap-1 px-2 py-1 rounded text-xs hover:bg-panel transition-colors text-textMuted"
                    >
                      <Copy className="w-3 h-3" />
                      Copy
                    </button>
                  </div>
                  <div className="bg-bg border border-border rounded-lg p-4 max-h-[200px] overflow-y-auto">
                    <pre className="whitespace-pre-wrap font-mono text-xs text-textMuted leading-relaxed">
                      {altPrompt}
                    </pre>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
