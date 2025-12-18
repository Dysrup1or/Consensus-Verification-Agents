/**
 * Toast Notification System
 * 
 * Lightweight toast notifications with animations and auto-dismiss.
 */

'use client';

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  type: ToastType;
  message: string;
  description?: string;
  duration?: number;
}

interface ToastContextValue {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

interface ToastProviderProps {
  children: ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  
  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const newToast = { ...toast, id };
    
    setToasts((prev) => [...prev, newToast]);
    
    // Auto-dismiss
    const duration = toast.duration ?? 5000;
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }
  }, []);
  
  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);
  
  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  );
}

// Helper functions for convenience
export function toast(message: string, type: ToastType = 'info', description?: string) {
  // This is a placeholder - in real usage, you'd need to call addToast from context
  console.log(`[${type.toUpperCase()}] ${message}`, description);
}

toast.success = (message: string, description?: string) => toast(message, 'success', description);
toast.error = (message: string, description?: string) => toast(message, 'error', description);
toast.warning = (message: string, description?: string) => toast(message, 'warning', description);
toast.info = (message: string, description?: string) => toast(message, 'info', description);

interface ToastContainerProps {
  toasts: Toast[];
  onRemove: (id: string) => void;
}

function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  if (toasts.length === 0) return null;
  
  return (
    <div className="fixed bottom-4 right-4 z-[var(--z-toast)] flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  );
}

interface ToastItemProps {
  toast: Toast;
  onRemove: (id: string) => void;
}

function ToastItem({ toast, onRemove }: ToastItemProps) {
  const iconMap: Record<ToastType, string> = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
  };
  
  const colorMap: Record<ToastType, string> = {
    success: 'bg-[var(--color-success)] text-[var(--color-bg)]',
    error: 'bg-[var(--color-danger)] text-white',
    warning: 'bg-[var(--color-warning)] text-[var(--color-bg)]',
    info: 'bg-[var(--color-primary)] text-white',
  };
  
  return (
    <div
      className={cn(
        'flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg',
        'animate-slide-in-right',
        'bg-[var(--color-surface-2)] border border-[var(--color-border)]'
      )}
      role="alert"
    >
      {/* Icon */}
      <div
        className={cn(
          'flex items-center justify-center w-6 h-6 rounded-full text-sm font-bold shrink-0',
          colorMap[toast.type]
        )}
      >
        {iconMap[toast.type]}
      </div>
      
      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-[var(--color-text)] font-medium">{toast.message}</p>
        {toast.description && (
          <p className="text-[var(--color-text-secondary)] text-sm mt-0.5">
            {toast.description}
          </p>
        )}
      </div>
      
      {/* Close button */}
      <button
        onClick={() => onRemove(toast.id)}
        className="shrink-0 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
        aria-label="Dismiss"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// Add animation styles
const style = `
  @keyframes slide-in-right {
    from {
      opacity: 0;
      transform: translateX(100%);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }
  
  .animate-slide-in-right {
    animation: slide-in-right 0.3s ease-out;
  }
`;

// Inject styles (only in browser)
if (typeof document !== 'undefined') {
  const styleEl = document.createElement('style');
  styleEl.textContent = style;
  document.head.appendChild(styleEl);
}
