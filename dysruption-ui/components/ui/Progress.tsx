/**
 * Progress Component with CVA Variants
 * 
 * A progress bar component for displaying completion status.
 * Supports different visual styles and animated transitions.
 */

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const progressVariants = cva(
  // Base track styles
  [
    'relative w-full overflow-hidden rounded-full',
    'bg-[var(--color-surface-2)]',
  ].join(' '),
  {
    variants: {
      size: {
        sm: 'h-1.5',
        md: 'h-2.5',
        lg: 'h-4',
      },
    },
    defaultVariants: {
      size: 'md',
    },
  }
);

const progressBarVariants = cva(
  // Base bar styles
  [
    'h-full rounded-full transition-all duration-500 ease-out',
  ].join(' '),
  {
    variants: {
      variant: {
        default: 'bg-[var(--color-primary)]',
        success: 'bg-[var(--color-success)]',
        warning: 'bg-[var(--color-warning)]',
        danger: 'bg-[var(--color-danger)]',
        gradient: 'bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-accent)]',
      },
      animated: {
        true: 'animate-pulse',
        false: '',
      },
    },
    defaultVariants: {
      variant: 'default',
      animated: false,
    },
  }
);

export interface ProgressProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof progressVariants>,
    VariantProps<typeof progressBarVariants> {
  value: number;
  max?: number;
  showValue?: boolean;
  label?: string;
}

/**
 * Progress bar component
 * 
 * @example
 * <Progress value={75} />
 * <Progress value={3} max={5} variant="success" showValue />
 * <Progress value={50} variant="gradient" animated />
 */
export const Progress = forwardRef<HTMLDivElement, ProgressProps>(
  ({ 
    className, 
    size, 
    variant, 
    animated,
    value, 
    max = 100, 
    showValue = false,
    label,
    ...props 
  }, ref) => {
    const percentage = Math.min(100, Math.max(0, (value / max) * 100));
    
    return (
      <div className="w-full space-y-1.5">
        {(label || showValue) && (
          <div className="flex justify-between text-sm">
            {label && (
              <span className="text-[var(--color-text-secondary)]">{label}</span>
            )}
            {showValue && (
              <span className="text-[var(--color-text-muted)] font-mono">
                {value}/{max}
              </span>
            )}
          </div>
        )}
        <div
          ref={ref}
          role="progressbar"
          aria-valuenow={value}
          aria-valuemin={0}
          aria-valuemax={max}
          className={cn(progressVariants({ size }), className)}
          {...props}
        >
          <div
            className={cn(progressBarVariants({ variant, animated }))}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    );
  }
);

Progress.displayName = 'Progress';

export { progressVariants, progressBarVariants };
