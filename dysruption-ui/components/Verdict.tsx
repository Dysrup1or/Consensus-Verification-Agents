import { useState } from 'react';
import { Judge } from '@/lib/types';
import { clsx } from 'clsx';
import { ChevronDown, ChevronUp, ShieldAlert, CheckCircle, XCircle } from 'lucide-react';

interface VerdictProps {
  judges: Judge[];
}

export default function Verdict({ judges }: VerdictProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {judges.map((judge) => (
        <JudgeCard key={judge.name} judge={judge} />
      ))}
    </div>
  );
}

function JudgeCard({ judge }: { judge: Judge }) {
  const [expanded, setExpanded] = useState(false);
  const isVeto = judge.vote === 'veto';
  
  const statusColor = {
    pass: 'text-success border-success',
    fail: 'text-danger border-danger',
    veto: 'text-danger border-danger pulsing-border'
  }[judge.vote];

  const Icon = {
    pass: CheckCircle,
    fail: XCircle,
    veto: ShieldAlert
  }[judge.vote];

  return (
    <div 
      className={clsx(
        "border rounded-lg p-4 bg-bg transition-all cursor-pointer hover:bg-white/5",
        statusColor,
        isVeto && "border-2"
      )}
      onClick={() => setExpanded(!expanded)}
      role="button"
      aria-expanded={expanded}
      tabIndex={0}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setExpanded(!expanded)}
      data-testid={isVeto ? "veto" : undefined}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon className="w-6 h-6" />
          <span className="font-bold uppercase">{judge.name}</span>
        </div>
        <span className="text-xs opacity-70">{judge.model}</span>
      </div>
      
      <div className="flex justify-between items-center mb-2">
        <span className="font-mono text-sm">CONFIDENCE: {(judge.confidence * 100).toFixed(0)}%</span>
        {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-white/10 text-sm opacity-90 animate-in fade-in slide-in-from-top-2">
          <p className="font-mono whitespace-pre-wrap">{judge.notes}</p>
        </div>
      )}
      
      {isVeto && (
        <div className="sr-only" role="alert">
          Security judge vetoed this change.
        </div>
      )}
    </div>
  );
}
