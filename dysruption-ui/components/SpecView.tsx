import { Invariant } from '@/lib/types';
import { clsx } from 'clsx';

interface SpecViewProps {
  invariants: Invariant[];
  violatedIds?: string[];
}

export default function SpecView({ invariants, violatedIds = [] }: SpecViewProps) {
  // Virtualization would go here if invariants.length > 200
  // For now, standard list
  
  return (
    <div className="h-full overflow-y-auto pr-2">
      <h3 className="text-lg font-bold mb-4 text-neonMagenta">CONSTITUTION</h3>
      <div className="space-y-2">
        {invariants.map((inv) => {
          const isViolated = violatedIds.includes(inv.id);
          return (
            <div 
              key={inv.id}
              className={clsx(
                "p-3 rounded border text-sm transition-all",
                isViolated 
                  ? "border-danger bg-danger/10 text-danger" 
                  : "border-white/10 bg-white/5 text-gray-300"
              )}
            >
              <div className="flex justify-between items-start mb-1">
                <span className="font-mono text-xs opacity-50">{inv.id}</span>
                <span className={clsx(
                  "text-[10px] px-1.5 py-0.5 rounded uppercase",
                  inv.severity === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'
                )}>
                  {inv.severity}
                </span>
              </div>
              <p>{inv.description}</p>
              {isViolated && (
                <div className="mt-2 text-xs font-bold flex items-center gap-1">
                  <span>⚠️ VIOLATION DETECTED</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
