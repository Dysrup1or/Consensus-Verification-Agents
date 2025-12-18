/**
 * Skeleton Component
 * 
 * A loading placeholder component for content that's being fetched.
 * Provides visual feedback during loading states.
 */

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const skeletonVariants = cva(
  [
    'animate-pulse rounded-md',
    'bg-[var(--color-surface-2)]',
  ].join(' '),
  {
    variants: {
      variant: {
        default: '',
        text: 'h-4 w-full',
        title: 'h-6 w-3/4',
        avatar: 'rounded-full',
        button: 'h-10 w-24',
        card: 'h-32 w-full',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface SkeletonProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof skeletonVariants> {}

/**
 * Skeleton loader component
 * 
 * @example
 * <Skeleton variant="text" />
 * <Skeleton variant="avatar" className="h-12 w-12" />
 * <Skeleton className="h-40 w-full" />
 */
export const Skeleton = forwardRef<HTMLDivElement, SkeletonProps>(
  ({ className, variant, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(skeletonVariants({ variant }), className)}
        {...props}
      />
    );
  }
);

Skeleton.displayName = 'Skeleton';

/* Skeleton Compound Components for Common Patterns */

export const SkeletonCard = () => (
  <div className="space-y-3 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-1)]">
    <Skeleton variant="title" />
    <Skeleton variant="text" />
    <Skeleton variant="text" className="w-4/5" />
    <div className="flex gap-2 pt-2">
      <Skeleton variant="button" />
      <Skeleton variant="button" />
    </div>
  </div>
);

export const SkeletonVerdictRow = () => (
  <div className="flex items-center gap-4 p-3 rounded-lg border border-[var(--color-border)]">
    <Skeleton className="h-6 w-16 rounded-full" />
    <Skeleton variant="text" className="flex-1" />
    <Skeleton className="h-8 w-20" />
  </div>
);

export const SkeletonProjectCard = () => (
  <div className="space-y-4 p-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-1)]">
    <div className="flex items-center gap-3">
      <Skeleton variant="avatar" className="h-10 w-10" />
      <div className="flex-1 space-y-2">
        <Skeleton variant="title" className="w-1/2" />
        <Skeleton variant="text" className="w-1/3" />
      </div>
    </div>
    <Skeleton className="h-2 w-full rounded-full" />
    <div className="flex gap-2">
      <Skeleton className="h-5 w-16 rounded-full" />
      <Skeleton className="h-5 w-20 rounded-full" />
    </div>
  </div>
);

export { skeletonVariants };
