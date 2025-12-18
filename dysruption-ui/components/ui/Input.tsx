/**
 * Input Component with CVA Variants
 * 
 * A styled input component with validation states and icon support.
 */

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const inputVariants = cva(
  // Base styles
  [
    'flex w-full rounded-lg border bg-[var(--color-surface-1)]',
    'text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]',
    'transition-all duration-200',
    'focus:outline-none focus:ring-2 focus:ring-offset-1',
    'focus:ring-offset-[var(--color-bg)]',
    'disabled:cursor-not-allowed disabled:opacity-50',
    'font-mono',
  ].join(' '),
  {
    variants: {
      variant: {
        default: [
          'border-[var(--color-border)]',
          'focus:border-[var(--color-primary)] focus:ring-[var(--color-primary)]',
        ].join(' '),
        error: [
          'border-[var(--color-danger)]',
          'focus:border-[var(--color-danger)] focus:ring-[var(--color-danger)]',
        ].join(' '),
        success: [
          'border-[var(--color-success)]',
          'focus:border-[var(--color-success)] focus:ring-[var(--color-success)]',
        ].join(' '),
      },
      inputSize: {
        sm: 'h-8 px-3 text-sm',
        md: 'h-10 px-4 text-sm',
        lg: 'h-12 px-4 text-base',
      },
    },
    defaultVariants: {
      variant: 'default',
      inputSize: 'md',
    },
  }
);

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'>,
    VariantProps<typeof inputVariants> {
  error?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

/**
 * Input component with validation support
 * 
 * @example
 * <Input placeholder="Enter text" />
 * <Input variant="error" error="This field is required" />
 * <Input leftIcon={<SearchIcon />} placeholder="Search..." />
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, variant, inputSize, error, leftIcon, rightIcon, ...props }, ref) => {
    const hasError = !!error || variant === 'error';
    
    return (
      <div className="relative w-full">
        {leftIcon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
            {leftIcon}
          </div>
        )}
        <input
          ref={ref}
          className={cn(
            inputVariants({ variant: hasError ? 'error' : variant, inputSize }),
            leftIcon && 'pl-10',
            rightIcon && 'pr-10',
            className
          )}
          {...props}
        />
        {rightIcon && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
            {rightIcon}
          </div>
        )}
        {error && (
          <p className="mt-1 text-xs text-[var(--color-danger)]">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export { inputVariants };
