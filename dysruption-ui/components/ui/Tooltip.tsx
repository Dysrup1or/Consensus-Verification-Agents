/**
 * Tooltip Component with CVA Variants
 * 
 * A lightweight tooltip component for contextual information.
 * Uses CSS-only approach for performance.
 */

'use client';

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, useState, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

const tooltipVariants = cva(
  [
    'absolute z-[var(--z-tooltip)]',
    'px-2.5 py-1.5 rounded-md',
    'text-xs font-medium whitespace-nowrap',
    'bg-[var(--color-surface-3)] text-[var(--color-text-primary)]',
    'border border-[var(--color-border)]',
    'shadow-lg',
    'transition-all duration-150',
    'pointer-events-none',
  ].join(' '),
  {
    variants: {
      position: {
        top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
        bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
        left: 'right-full top-1/2 -translate-y-1/2 mr-2',
        right: 'left-full top-1/2 -translate-y-1/2 ml-2',
      },
      visible: {
        true: 'opacity-100 scale-100',
        false: 'opacity-0 scale-95',
      },
    },
    defaultVariants: {
      position: 'top',
      visible: false,
    },
  }
);

export interface TooltipProps
  extends Omit<HTMLAttributes<HTMLDivElement>, 'content'>,
    Omit<VariantProps<typeof tooltipVariants>, 'visible'> {
  content: ReactNode;
  delay?: number;
}

/**
 * Tooltip component for contextual hints
 * 
 * @example
 * <Tooltip content="This is helpful info" position="top">
 *   <Button>Hover me</Button>
 * </Tooltip>
 */
export const Tooltip = forwardRef<HTMLDivElement, TooltipProps>(
  ({ className, content, position, delay = 200, children, ...props }, ref) => {
    const [visible, setVisible] = useState(false);
    const [timeoutId, setTimeoutId] = useState<NodeJS.Timeout | null>(null);

    const showTooltip = () => {
      const id = setTimeout(() => setVisible(true), delay);
      setTimeoutId(id);
    };

    const hideTooltip = () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
        setTimeoutId(null);
      }
      setVisible(false);
    };

    return (
      <div
        ref={ref}
        className={cn('relative inline-block', className)}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        {...props}
      >
        {children}
        <div
          role="tooltip"
          className={tooltipVariants({ position, visible })}
        >
          {content}
          {/* Arrow */}
          <div
            className={cn(
              'absolute w-2 h-2 rotate-45',
              'bg-[var(--color-surface-3)] border border-[var(--color-border)]',
              position === 'top' && 'bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 border-t-0 border-l-0',
              position === 'bottom' && 'top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 border-b-0 border-r-0',
              position === 'left' && 'right-0 top-1/2 -translate-y-1/2 translate-x-1/2 border-b-0 border-l-0',
              position === 'right' && 'left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 border-t-0 border-r-0',
            )}
          />
        </div>
      </div>
    );
  }
);

Tooltip.displayName = 'Tooltip';

export { tooltipVariants };
