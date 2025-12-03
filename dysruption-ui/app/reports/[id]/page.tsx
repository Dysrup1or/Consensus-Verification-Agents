"use client";

import { useEffect, useState } from 'react';
import { fetchRun } from '@/lib/api';
import { VerdictPayload } from '@/lib/types';
import PatchDiff from '@/components/PatchDiff';
import Verdict from '@/components/Verdict';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function ReportPage({ params }: { params: { id: string } }) {
  const [verdict, setVerdict] = useState<VerdictPayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRun(params.id).then(v => {
      setVerdict(v);
      setLoading(false);
    });
  }, [params.id]);

  if (loading) return <div className="p-8">Loading report...</div>;
  if (!verdict) return <div className="p-8">Report not found</div>;

  return (
    <div className="min-h-screen bg-bg text-white p-8 font-mono">
      <Link href="/" className="inline-flex items-center gap-2 text-gray-400 hover:text-white mb-8 transition-colors">
        <ArrowLeft size={16} />
        Back to Dashboard
      </Link>

      <header className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Run Report: <span className="text-neonCyan">{verdict.runId}</span></h1>
        <div className="flex gap-4 text-sm opacity-70">
          <span>{new Date(verdict.timestamp || '').toLocaleString()}</span>
          <span>Files: {verdict.summary.filesScanned.join(', ')}</span>
        </div>
      </header>

      <div className="space-y-12">
        <section>
          <h2 className="text-xl font-bold mb-4 text-neonMagenta">JUDGE DECISIONS</h2>
          <Verdict judges={verdict.judges} />
        </section>

        {verdict.patches.length > 0 && (
          <section>
            <h2 className="text-xl font-bold mb-4 text-neonCyan">GENERATED PATCHES</h2>
            <div className="space-y-6">
              {verdict.patches.map((patch, i) => (
                <PatchDiff key={i} patch={patch} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
