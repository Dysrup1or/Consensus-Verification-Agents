/**
 * Card Component with CVA Variants
 * 
 * A flexible card component for content containers.
 * Supports different visual styles and padding options.
 */

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const cardVariants = cva(
  // Base styles
  [
    'rounded-xl border transition-all duration-200',
  ].join(' '),
  {
    variants: {
      variant: {
        default: [
          'bg-[var(--color-surface-1)] border-[var(--color-border)]',
        ].join(' '),
        elevated: [
          'bg-[var(--color-surface-2)] border-[var(--color-border)]',
          'shadow-lg',
        ].join(' '),
        ghost: [
          'bg-transparent border-transparent',
        ].join(' '),
        outline: [
          'bg-transparent border-[var(--color-border)]',
          'hover:border-[var(--color-text-muted)]',
        ].join(' '),
        success: [
          'bg-[var(--color-surface-1)] border-[var(--color-success)]',
          'shadow-[var(--shadow-glow-success)]',
        ].join(' '),
        danger: [
          'bg-[var(--color-surface-1)] border-[var(--color-danger)]',
          'shadow-[var(--shadow-glow-danger)]',
        ].join(' '),
      },
      padding: {
        none: 'p-0',
        sm: 'p-3',
        md: 'p-4',
        lg: 'p-6',
        xl: 'p-8',
      },
      interactive: {
        true: [
          'cursor-pointer',
          'hover:border-[var(--color-text-muted)]',
          'hover:shadow-[var(--shadow-glow)]',
        ].join(' '),
        false: '',
      },
    },
    defaultVariants: {
      variant: 'default',
      padding: 'md',
      interactive: false,
    },
  }
);

export interface CardProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

/**
 * Card container component
 * 
 * @example
 * <Card variant="elevated" padding="lg">
 *   <CardHeader>Title</CardHeader>
 *   <CardContent>Content goes here</CardContent>
 * </Card>
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, padding, interactive, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(cardVariants({ variant, padding, interactive }), className)}
        {...props}
      />
    );
  }
);

Card.displayName = 'Card';

/* Card Sub-components */

export const CardHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('flex flex-col space-y-1.5 pb-4', className)}
      {...props}
    />
  )
);

CardHeader.displayName = 'CardHeader';

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn(
        'text-lg font-semibold text-[var(--color-text-primary)] leading-none tracking-tight',
        className
      )}
      {...props}
    />
  )
);

CardTitle.displayName = 'CardTitle';

export const CardDescription = forwardRef<HTMLParagraphElement, HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn('text-sm text-[var(--color-text-secondary)]', className)}
      {...props}
    />
  )
);

CardDescription.displayName = 'CardDescription';

export const CardContent = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('', className)} {...props} />
  )
);

CardContent.displayName = 'CardContent';

export const CardFooter = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('flex items-center pt-4 border-t border-[var(--color-border-muted)]', className)}
      {...props}
    />
  )
);

CardFooter.displayName = 'CardFooter';

export { cardVariants };
