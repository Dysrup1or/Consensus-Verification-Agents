/**
 * Modal Component with CVA Variants
 * 
 * A dialog component for overlays, confirmations, and focused interactions.
 * Includes accessibility features and animation support.
 */

'use client';

import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, useEffect, useCallback, type HTMLAttributes } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

const modalOverlayVariants = cva(
  [
    'fixed inset-0 z-[var(--z-overlay)]',
    'bg-black/60 backdrop-blur-sm',
    'transition-opacity duration-200',
  ].join(' '),
  {
    variants: {
      open: {
        true: 'opacity-100',
        false: 'opacity-0 pointer-events-none',
      },
    },
    defaultVariants: {
      open: false,
    },
  }
);

const modalContentVariants = cva(
  [
    'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
    'z-[var(--z-modal)]',
    'bg-[var(--color-surface-1)] border border-[var(--color-border)]',
    'rounded-xl shadow-xl',
    'transition-all duration-200',
    'max-h-[85vh] overflow-y-auto',
  ].join(' '),
  {
    variants: {
      open: {
        true: 'opacity-100 scale-100',
        false: 'opacity-0 scale-95 pointer-events-none',
      },
      size: {
        sm: 'w-full max-w-sm',
        md: 'w-full max-w-md',
        lg: 'w-full max-w-lg',
        xl: 'w-full max-w-xl',
        full: 'w-[calc(100%-2rem)] max-w-4xl',
      },
    },
    defaultVariants: {
      open: false,
      size: 'md',
    },
  }
);

export interface ModalProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof modalContentVariants> {
  open: boolean;
  onClose: () => void;
  closeOnOverlayClick?: boolean;
  closeOnEscape?: boolean;
}

/**
 * Modal dialog component
 * 
 * @example
 * <Modal open={isOpen} onClose={() => setIsOpen(false)} size="lg">
 *   <ModalHeader>Confirmation</ModalHeader>
 *   <ModalBody>Are you sure?</ModalBody>
 *   <ModalFooter>
 *     <Button onClick={() => setIsOpen(false)}>Cancel</Button>
 *     <Button intent="danger">Confirm</Button>
 *   </ModalFooter>
 * </Modal>
 */
export const Modal = forwardRef<HTMLDivElement, ModalProps>(
  ({ 
    className, 
    open, 
    onClose, 
    size, 
    closeOnOverlayClick = true,
    closeOnEscape = true,
    children, 
    ...props 
  }, ref) => {
    
    const handleEscape = useCallback((e: KeyboardEvent) => {
      if (closeOnEscape && e.key === 'Escape') {
        onClose();
      }
    }, [closeOnEscape, onClose]);

    useEffect(() => {
      if (open) {
        document.addEventListener('keydown', handleEscape);
        document.body.style.overflow = 'hidden';
      }
      
      return () => {
        document.removeEventListener('keydown', handleEscape);
        document.body.style.overflow = '';
      };
    }, [open, handleEscape]);

    if (typeof window === 'undefined') return null;

    return createPortal(
      <>
        {/* Overlay */}
        <div
          className={modalOverlayVariants({ open })}
          onClick={closeOnOverlayClick ? onClose : undefined}
          aria-hidden="true"
        />
        
        {/* Content */}
        <div
          ref={ref}
          role="dialog"
          aria-modal="true"
          className={cn(modalContentVariants({ open, size }), className)}
          {...props}
        >
          {children}
        </div>
      </>,
      document.body
    );
  }
);

Modal.displayName = 'Modal';

/* Modal Sub-components */

export const ModalHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex items-center justify-between p-4 pb-0',
        'text-lg font-semibold text-[var(--color-text-primary)]',
        className
      )}
      {...props}
    />
  )
);

ModalHeader.displayName = 'ModalHeader';

export const ModalBody = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('p-4 text-[var(--color-text-secondary)]', className)}
      {...props}
    />
  )
);

ModalBody.displayName = 'ModalBody';

export const ModalFooter = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex items-center justify-end gap-2 p-4 pt-0',
        className
      )}
      {...props}
    />
  )
);

ModalFooter.displayName = 'ModalFooter';

export const ModalCloseButton = forwardRef<HTMLButtonElement, HTMLAttributes<HTMLButtonElement> & { onClose: () => void }>(
  ({ className, onClose, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      onClick={onClose}
      className={cn(
        'rounded-lg p-1.5 text-[var(--color-text-muted)]',
        'hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]',
        'transition-colors',
        className
      )}
      aria-label="Close modal"
      {...props}
    >
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  )
);

ModalCloseButton.displayName = 'ModalCloseButton';

export { modalOverlayVariants, modalContentVariants };
