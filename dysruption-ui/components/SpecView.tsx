import { Invariant, InvariantSeverity } from '@/lib/types';
import { clsx } from 'clsx';
import { useState, useMemo } from 'react';
import { Search, X } from 'lucide-react';

interface SpecViewProps {
  invariants: Invariant[];
  violatedIds?: number[];
}

const severityOrder: InvariantSeverity[] = ['critical', 'high', 'medium', 'low'];

const severityStyles: Record<InvariantSeverity, string> = {
  critical: 'bg-red-500/20 text-red-400',
  high: 'bg-orange-500/20 text-orange-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low: 'bg-blue-500/20 text-blue-400',
};

export default function SpecView({ invariants, violatedIds = [] }: SpecViewProps) {
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState<InvariantSeverity | 'all'>('all');

  const filteredInvariants = useMemo(() => {
    return invariants.filter((inv) => {
      const matchesSearch =
        search === '' ||
        inv.description.toLowerCase().includes(search.toLowerCase()) ||
        inv.id.toString().includes(search);
      const matchesSeverity =
        severityFilter === 'all' || inv.severity === severityFilter;
      return matchesSearch && matchesSeverity;
    });
  }, [invariants, search, severityFilter]);

  return (
    <div className="h-full flex flex-col">
      <h3 className="text-lg font-bold mb-4 text-neonMagenta">CONSTITUTION</h3>
      
      {/* Search and filter */}
      <div className="mb-4 space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-textMuted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search invariants..."
            className="w-full pl-10 pr-8 py-2 rounded bg-white/5 border border-white/10 text-sm focus:outline-none focus:ring-2 focus:ring-accent/60"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-white/10 rounded"
            >
              <X size={14} />
            </button>
          )}
        </div>
        
        <div className="flex gap-1 flex-wrap">
          <button
            onClick={() => setSeverityFilter('all')}
            className={clsx(
              "text-[10px] px-2 py-1 rounded uppercase transition-colors",
              severityFilter === 'all' ? 'bg-white/20 text-white' : 'bg-white/5 text-textMuted hover:bg-white/10'
            )}
          >
            All
          </button>
          {severityOrder.map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={clsx(
                "text-[10px] px-2 py-1 rounded uppercase transition-colors",
                severityFilter === sev ? severityStyles[sev] : 'bg-white/5 text-textMuted hover:bg-white/10'
              )}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Invariants list */}
      <div className="flex-1 overflow-y-auto pr-2 space-y-2">
        {filteredInvariants.length === 0 ? (
          <p className="text-sm text-textMuted">No invariants found.</p>
        ) : (
          filteredInvariants.map((inv) => {
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
                  <span className="font-mono text-xs opacity-50">INV-{inv.id}</span>
                  <span className={clsx("text-[10px] px-1.5 py-0.5 rounded uppercase", severityStyles[inv.severity])}>
                    {inv.severity}
                  </span>
                </div>
                <p className={clsx(isViolated && "line-through")}>{inv.description}</p>
                {inv.category && (
                  <span className="text-[10px] text-textMuted uppercase mt-1 inline-block">
                    {inv.category}
                  </span>
                )}
                {isViolated && (
                  <div className="mt-2 text-xs font-bold flex items-center gap-1 text-danger">
                    <span>⚠️ VIOLATION DETECTED</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
      
      <div className="mt-2 text-xs text-textMuted">
        Showing {filteredInvariants.length} of {invariants.length} invariants
      </div>
    </div>
  );
}
