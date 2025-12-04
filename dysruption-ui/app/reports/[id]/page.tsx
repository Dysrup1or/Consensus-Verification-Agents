"use client";

import { useEffect, useState } from 'react';
import { fetchVerdict } from '@/lib/api';
import { VerdictResponse, ConsensusResult, PatchSet } from '@/lib/types';
import PatchDiff from '@/components/PatchDiff';
import Verdict from '@/components/Verdict';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function ReportPage({ params }: { params: { id: string } }) {
  const [consensus, setConsensus] = useState<ConsensusResult | null>(null);
  const [patches, setPatches] = useState<PatchSet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVerdict(params.id)
      .then((resp: VerdictResponse) => {
        if (resp.ready && resp.consensus) {
          setConsensus(resp.consensus);
          setPatches(resp.patches);
        } else {
          setError('Verdict not ready yet');
        }
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [params.id]);

  if (loading) return <div className="p-8 bg-bg min-h-screen text-text">Loading report...</div>;
  if (error) return <div className="p-8 bg-bg min-h-screen text-text">Error: {error}</div>;
  if (!consensus) return <div className="p-8 bg-bg min-h-screen text-text">Report not found</div>;

  return (
    <div className="min-h-screen bg-bg text-text p-8">
      <Link href="/" className="inline-flex items-center gap-2 text-textMuted hover:text-text mb-8 transition-colors">
        <ArrowLeft size={16} />
        Back to Dashboard
      </Link>

      <header className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Run Report: <span className="text-primary">{params.id}</span></h1>
        <div className="flex gap-4 text-sm text-textMuted">
          <span>{new Date(consensus.timestamp).toLocaleString()}</span>
          <span>Files analyzed: {consensus.files_analyzed}</span>
          <span>Invariants: {consensus.invariants_passed}/{consensus.total_invariants}</span>
        </div>
        {consensus.veto_triggered && (
          <div className="mt-2 px-3 py-1 inline-block rounded bg-danger/20 text-danger text-sm">
            ⚠️ Security Veto: {consensus.veto_reason}
          </div>
        )}
      </header>

      <div className="space-y-12">
        {/* Summary stats */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-surface border border-border">
            <div className="text-xs text-textMuted uppercase tracking-wider">Status</div>
            <div className="text-xl font-semibold uppercase">{consensus.overall_status}</div>
          </div>
          <div className="p-4 rounded-lg bg-surface border border-border">
            <div className="text-xs text-textMuted uppercase tracking-wider">Score</div>
            <div className="text-xl font-semibold">{consensus.weighted_score.toFixed(1)}/10</div>
          </div>
          <div className="p-4 rounded-lg bg-surface border border-border">
            <div className="text-xs text-textMuted uppercase tracking-wider">Confidence</div>
            <div className="text-xl font-semibold">{(consensus.confidence * 100).toFixed(0)}%</div>
          </div>
          <div className="p-4 rounded-lg bg-surface border border-border">
            <div className="text-xs text-textMuted uppercase tracking-wider">Execution Time</div>
            <div className="text-xl font-semibold">{(consensus.execution_time_ms / 1000).toFixed(1)}s</div>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold mb-4 text-accent">Judge Decisions</h2>
          <Verdict verdicts={consensus.verdicts} vetoTriggered={consensus.veto_triggered} />
        </section>

        {patches && patches.patches.length > 0 && (
          <section>
            <h2 className="text-xl font-semibold mb-4 text-primary">Generated Patches</h2>
            <div className="space-y-6">
              {patches.patches.map((patch, i) => (
                <PatchDiff key={i} patch={patch} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
