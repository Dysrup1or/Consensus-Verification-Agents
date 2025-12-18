/**
 * Button Component with CVA Variants
 * 
 * A type-safe button component using class-variance-authority for variant styling.
 * Supports multiple intents (primary, secondary, danger, ghost) and sizes.
 */

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  // Base styles applied to all variants
  [
    'inline-flex items-center justify-center gap-2',
    'font-medium transition-all',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
    'disabled:pointer-events-none disabled:opacity-50',
    'focus-visible:ring-offset-[var(--color-bg)]',
  ].join(' '),
  {
    variants: {
      intent: {
        primary: [
          'bg-[var(--color-primary)] text-white',
          'hover:bg-[var(--color-primary-hover)]',
          'focus-visible:ring-[var(--color-primary)]',
          'shadow-md hover:shadow-lg',
        ].join(' '),
        secondary: [
          'bg-[var(--color-surface-2)] text-[var(--color-text-primary)]',
          'border border-[var(--color-border)]',
          'hover:bg-[var(--color-surface-3)] hover:border-[var(--color-text-muted)]',
          'focus-visible:ring-[var(--color-border)]',
        ].join(' '),
        danger: [
          'bg-[var(--color-danger)] text-white',
          'hover:bg-red-600',
          'focus-visible:ring-[var(--color-danger)]',
          'shadow-md hover:shadow-lg',
        ].join(' '),
        ghost: [
          'text-[var(--color-text-secondary)]',
          'hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]',
          'focus-visible:ring-[var(--color-border)]',
        ].join(' '),
        success: [
          'bg-[var(--color-success)] text-white',
          'hover:bg-emerald-600',
          'focus-visible:ring-[var(--color-success)]',
          'shadow-md hover:shadow-lg',
        ].join(' '),
      },
      size: {
        sm: 'h-8 px-3 text-sm rounded-md',
        md: 'h-10 px-4 text-sm rounded-lg',
        lg: 'h-12 px-6 text-base rounded-lg',
        icon: 'h-10 w-10 rounded-lg',
      },
      fullWidth: {
        true: 'w-full',
        false: '',
      },
    },
    defaultVariants: {
      intent: 'primary',
      size: 'md',
      fullWidth: false,
    },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

/**
 * Button component with variant support
 * 
 * @example
 * <Button intent="primary" size="md">Click me</Button>
 * <Button intent="danger" size="sm" loading>Deleting...</Button>
 * <Button intent="ghost" size="icon"><Icon /></Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, intent, size, fullWidth, loading, children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ intent, size, fullWidth }), className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading && (
          <svg
            className="h-4 w-4 animate-spin"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';

export { buttonVariants };
