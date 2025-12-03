import { clsx } from 'clsx';

type Status = 'idle' | 'watcher_detected' | 'scanning' | 'consensus_pass' | 'consensus_fail';

interface StatusBadgeProps {
  status: Status;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = {
    idle: { text: 'READY', color: 'text-green-500 border-green-500', bg: 'bg-green-500/10' },
    watcher_detected: { text: 'THINKING', color: 'text-yellow-500 border-yellow-500', bg: 'bg-yellow-500/10' },
    scanning: { text: 'SCANNING', color: 'text-blue-500 border-blue-500', bg: 'bg-blue-500/10' },
    consensus_pass: { text: 'APPROVED', color: 'text-neonCyan border-neonCyan', bg: 'bg-neonCyan/10' },
    consensus_fail: { text: 'REJECTED', color: 'text-danger border-danger', bg: 'bg-danger/10' },
  };

  const current = config[status] || config.idle;

  return (
    <div 
      className={clsx(
        "flex items-center justify-center px-8 py-4 border-2 rounded-lg text-2xl font-bold tracking-widest transition-all duration-300",
        current.color,
        current.bg
      )}
      role="status"
      aria-live="polite"
    >
      {current.text}
    </div>
  );
}
