import { useEffect, useState } from 'react';
import { clsx } from 'clsx';

interface ToastProps {
  message: string | null;
}

export default function Toast({ message }: ToastProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (message) {
      setVisible(true);
      const timer = setTimeout(() => setVisible(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [message]);

  if (!visible || !message) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 animate-in slide-in-from-bottom-5 fade-in">
      <div className="bg-gray-800 border border-white/20 text-white px-4 py-3 rounded shadow-lg flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-neonCyan animate-pulse" />
        <span className="font-mono text-sm">{message}</span>
      </div>
    </div>
  );
}
