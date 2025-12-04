import React from 'react';
import { CheckCircle, Loader2, Shield, XCircle, AlertTriangle, Eye, Zap, FileCode } from 'lucide-react';
import { clsx } from 'clsx';
import { PipelineStatus } from '@/lib/types';

interface StatusBadgeProps {
  status: PipelineStatus;
  size?: 'lg' | 'md' | 'sm';
  compact?: boolean;
}

const sizeMap: Record<string, string> = {
  lg: 'px-10 py-6 text-3xl',
  md: 'px-8 py-4 text-2xl',
  sm: 'px-4 py-2 text-lg'
};

interface StatusMeta {
  label: string;
  icon: React.ElementType;
  colorClass: string;
  emoji: string;
  animate?: boolean;
}

const statusMeta: Record<PipelineStatus, StatusMeta> = {
  idle: { label: 'Ready', icon: CheckCircle, colorClass: 'text-success', emoji: '' },
  watching: { label: 'Watching', icon: Eye, colorClass: 'text-primary', emoji: '', animate: true },
  scanning: { label: 'Scanning', icon: Loader2, colorClass: 'text-warning', emoji: '', animate: true },
  parsing: { label: 'Parsing', icon: FileCode, colorClass: 'text-warning', emoji: '', animate: true },
  static_analysis: { label: 'Analyzing', icon: Zap, colorClass: 'text-warning', emoji: '', animate: true },
  judging: { label: 'Judging', icon: Shield, colorClass: 'text-primary', emoji: '', animate: true },
  patching: { label: 'Patching', icon: FileCode, colorClass: 'text-accent', emoji: '', animate: true },
  complete: { label: 'Complete', icon: CheckCircle, colorClass: 'text-success', emoji: '' },
  error: { label: 'Error', icon: XCircle, colorClass: 'text-danger', emoji: '' }
};

export default function StatusBadge({ status, size = 'lg', compact = false }: StatusBadgeProps) {
  const item = statusMeta[status] ?? statusMeta.idle;
  const Icon = item.icon;

  return (
    <div
      aria-live="polite"
      role="status"
      tabIndex={0}
      aria-label={`System status: ${item.label}`}
      className={clsx(
        'inline-flex items-center gap-4 rounded-xl bg-surface border border-border',
        sizeMap[size],
        'transition-all duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-primary/40'
      )}
    >
      <div className={clsx(
        'rounded-full flex items-center justify-center bg-panel',
        compact ? 'w-10 h-10' : 'w-12 h-12'
      )}>
        <Icon 
          className={clsx(
            compact ? 'w-5 h-5' : 'w-6 h-6',
            item.colorClass,
            item.animate && 'motion-safe:animate-spin'
          )} 
          aria-hidden 
        />
      </div>

      <div>
        <div className="text-xs text-textMuted uppercase tracking-wider">Status</div>
        <div className="font-medium">{item.label}</div>
      </div>
    </div>
  );
}
