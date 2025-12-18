/**
 * Badge Component with CVA Variants
 * 
 * A small status indicator component for labels, tags, and status indicators.
 * Specifically designed for verdict display and status badges.
 */

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  // Base styles
  [
    'inline-flex items-center justify-center gap-1',
    'font-medium rounded-full transition-colors',
    'whitespace-nowrap',
  ].join(' '),
  {
    variants: {
      variant: {
        default: [
          'bg-[var(--color-surface-2)] text-[var(--color-text-secondary)]',
          'border border-[var(--color-border)]',
        ].join(' '),
        primary: [
          'bg-[var(--color-primary-muted)] text-[var(--color-primary)]',
          'border border-[var(--color-primary)]',
        ].join(' '),
        success: [
          'bg-emerald-500/15 text-[var(--color-success)]',
          'border border-[var(--color-success)]',
        ].join(' '),
        warning: [
          'bg-amber-500/15 text-[var(--color-warning)]',
          'border border-[var(--color-warning)]',
        ].join(' '),
        danger: [
          'bg-red-500/15 text-[var(--color-danger)]',
          'border border-[var(--color-danger)]',
        ].join(' '),
        info: [
          'bg-blue-500/15 text-[var(--color-info)]',
          'border border-[var(--color-info)]',
        ].join(' '),
        
        // Verdict-specific variants
        pass: [
          'bg-emerald-500/20 text-[var(--color-verdict-pass)]',
          'border border-[var(--color-verdict-pass)]',
        ].join(' '),
        fail: [
          'bg-red-500/20 text-[var(--color-verdict-fail)]',
          'border border-[var(--color-verdict-fail)]',
        ].join(' '),
        veto: [
          'bg-red-600/30 text-[var(--color-verdict-veto)]',
          'border border-[var(--color-verdict-veto)]',
          'font-bold',
        ].join(' '),
        partial: [
          'bg-amber-500/20 text-[var(--color-verdict-partial)]',
          'border border-[var(--color-verdict-partial)]',
        ].join(' '),
        pending: [
          'bg-zinc-500/20 text-[var(--color-verdict-pending)]',
          'border border-[var(--color-verdict-pending)]',
        ].join(' '),
        
        // Judge-specific variants
        architect: [
          'bg-violet-500/15 text-[var(--color-judge-architect)]',
          'border border-[var(--color-judge-architect)]',
        ].join(' '),
        security: [
          'bg-red-500/15 text-[var(--color-judge-security)]',
          'border border-[var(--color-judge-security)]',
        ].join(' '),
        'user-proxy': [
          'bg-blue-500/15 text-[var(--color-judge-user-proxy)]',
          'border border-[var(--color-judge-user-proxy)]',
        ].join(' '),
      },
      size: {
        sm: 'h-5 px-2 text-xs',
        md: 'h-6 px-2.5 text-xs',
        lg: 'h-7 px-3 text-sm',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  icon?: React.ReactNode;
}

/**
 * Badge component for status display
 * 
 * @example
 * <Badge variant="success">PASS</Badge>
 * <Badge variant="fail" icon={<XIcon />}>FAIL</Badge>
 * <Badge variant="architect" size="lg">🏛️ Architect</Badge>
 */
export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, size, icon, children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(badgeVariants({ variant, size }), className)}
        {...props}
      >
        {icon}
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

export { badgeVariants };
