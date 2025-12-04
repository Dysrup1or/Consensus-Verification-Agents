import { useEffect, useState } from 'react';
import { clsx } from 'clsx';
import { X, AlertCircle, CheckCircle, Info } from 'lucide-react';

interface ToastProps {
  message: string | null;
  onDismiss?: () => void;
  duration?: number;
}

export default function Toast({ message, onDismiss, duration = 5000 }: ToastProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (message) {
      setVisible(true);
      const timer = setTimeout(() => {
        setVisible(false);
        onDismiss?.();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [message, duration, onDismiss]);

  if (!visible || !message) return null;

  // Determine toast type based on message content
  const isError = message.toLowerCase().includes('error') || message.toLowerCase().includes('failed');
  const isVeto = message.toLowerCase().includes('veto');
  const isSuccess = message.toLowerCase().includes('pass') || message.toLowerCase().includes('approved');

  const Icon = isError || isVeto ? AlertCircle : isSuccess ? CheckCircle : Info;
  const borderColor = isError || isVeto ? 'border-danger/50' : isSuccess ? 'border-success/50' : 'border-border';

  const handleDismiss = () => {
    setVisible(false);
    onDismiss?.();
  };

  return (
    <div 
      className="fixed bottom-4 right-4 z-50 animate-in slide-in-from-bottom-5 fade-in"
      role={isError || isVeto ? 'alert' : 'status'}
      aria-live={isVeto ? 'assertive' : 'polite'}
    >
      <div className={clsx(
        "bg-panel border text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 max-w-md",
        borderColor
      )}>
        <Icon className={clsx("w-5 h-5 flex-shrink-0", isError || isVeto ? 'text-danger' : isSuccess ? 'text-success' : 'text-primary')} />
        <span className="font-mono text-sm flex-1">{message}</span>
        <button
          onClick={handleDismiss}
          className="p-1 hover:bg-white/10 rounded transition-colors"
          aria-label="Dismiss"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
