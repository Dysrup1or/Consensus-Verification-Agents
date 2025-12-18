/**
 * Select Component with CVA Variants
 * 
 * A styled select/dropdown component with custom styling.
 */

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type SelectHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const selectVariants = cva(
  // Base styles
  [
    'flex w-full rounded-lg border appearance-none cursor-pointer',
    'bg-[var(--color-surface-1)]',
    'text-[var(--color-text-primary)]',
    'transition-all duration-200',
    'focus:outline-none focus:ring-2 focus:ring-offset-1',
    'focus:ring-offset-[var(--color-bg)]',
    'disabled:cursor-not-allowed disabled:opacity-50',
    // Arrow icon via background
    'bg-no-repeat bg-[length:16px_16px]',
    'bg-[position:right_12px_center]',
    'pr-10',
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
      },
      selectSize: {
        sm: 'h-8 px-3 text-sm',
        md: 'h-10 px-4 text-sm',
        lg: 'h-12 px-4 text-base',
      },
    },
    defaultVariants: {
      variant: 'default',
      selectSize: 'md',
    },
  }
);

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'>,
    VariantProps<typeof selectVariants> {
  options: SelectOption[];
  placeholder?: string;
  error?: string;
}

/**
 * Select dropdown component
 * 
 * @example
 * <Select
 *   options={[
 *     { value: 'gpt4', label: 'GPT-4' },
 *     { value: 'claude', label: 'Claude 3.5' },
 *   ]}
 *   placeholder="Select a model"
 * />
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, variant, selectSize, options, placeholder, error, ...props }, ref) => {
    const hasError = !!error || variant === 'error';
    
    // SVG arrow as data URL (chevron down icon)
    const arrowDataUrl = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`;
    
    return (
      <div className="relative w-full">
        <select
          ref={ref}
          className={cn(
            selectVariants({ variant: hasError ? 'error' : variant, selectSize }),
            className
          )}
          style={{ backgroundImage: arrowDataUrl }}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((option) => (
            <option
              key={option.value}
              value={option.value}
              disabled={option.disabled}
            >
              {option.label}
            </option>
          ))}
        </select>
        {error && (
          <p className="mt-1 text-xs text-[var(--color-danger)]">{error}</p>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';

export { selectVariants };
