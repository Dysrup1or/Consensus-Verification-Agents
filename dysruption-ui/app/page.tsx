"use client";

import { useEffect, useState, useRef } from 'react';
import { CVAWebSocket } from '@/lib/ws';
import { fetchLatestVerdict, fetchInvariants } from '@/lib/api';
import { startMockServer, getMockVerdict } from '@/lib/mock';
import { VerdictPayload, Invariant, WatcherUpdatePayload, VerdictUpdatePayload } from '@/lib/types';
import StatusBadge from '@/components/StatusBadge';
import Verdict from '@/components/Verdict';
import PatchDiff from '@/components/PatchDiff';
import SpecView from '@/components/SpecView';
import Toast from '@/components/Toast';
import { Activity, Terminal, Shield } from 'lucide-react';

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === 'true';

export default function Dashboard() {
  const [status, setStatus] = useState<'idle' | 'watcher_detected' | 'scanning' | 'consensus_pass' | 'consensus_fail'>('idle');
  const [verdict, setVerdict] = useState<VerdictPayload | null>(null);
  const [invariants, setInvariants] = useState<Invariant[]>([]);
  const [wsStatus, setWsStatus] = useState<string>('connecting...');
  const [progress, setProgress] = useState<number>(0);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  
  const wsRef = useRef<CVAWebSocket | null>(null);

  useEffect(() => {
    // Initial data fetch
    fetchInvariants().then(data => setInvariants(data.invariants));
    fetchLatestVerdict().then(v => {
      if (v) {
        setVerdict(v);
        setStatus(v.result);
      }
    });

    // WS Setup
    if (USE_MOCK) {
      startMockServer((event) => handleWsMessage(event));
      setWsStatus('connected (mock)');
    } else {
      const ws = new CVAWebSocket();
      ws.onMessage(handleWsMessage);
      ws.onStatusChange((s) => {
        setWsStatus(s);
        if (s.includes('reconnecting')) setToastMsg(s);
      });
      ws.start();
      wsRef.current = ws;
    }

    return () => wsRef.current?.stop();
  }, []);

  const handleWsMessage = (event: any) => {
    console.log('WS Event:', event);
    
    if (event.type === 'watcher:update') {
      const payload = event.payload as WatcherUpdatePayload;
      if (payload.status === 'watcher_detected') {
        setStatus('watcher_detected');
        setToastMsg(`Change detected in ${payload.files} files`);
      }
    }
    
    if (event.type === 'verdict:update') {
      const payload = event.payload as VerdictUpdatePayload;
      setStatus('scanning');
      setProgress(payload.percent);
    }
    
    if (event.type === 'verdict:complete') {
      const payload = event.payload as VerdictPayload;
      setVerdict(payload);
      setStatus(payload.result);
      setProgress(100);
      setToastMsg(`Verdict: ${payload.result === 'consensus_pass' ? 'APPROVED' : 'REJECTED'}`);
    }
  };

  return (
    <main className="min-h-screen bg-bg text-white p-6 font-mono selection:bg-neonCyan selection:text-black">
      <header className="flex justify-between items-center mb-8 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <Shield className="text-neonCyan w-8 h-8" />
          <h1 className="text-2xl font-bold tracking-tighter">
            DYS<span className="text-neonCyan">RUPTION</span> CVA
          </h1>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-2 px-3 py-1 rounded bg-white/5">
            <Terminal size={14} />
            <span>WS: {wsStatus}</span>
          </div>
          {status === 'scanning' && (
            <div className="w-32 h-2 bg-gray-800 rounded-full overflow-hidden">
              <div 
                className="h-full bg-neonCyan transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Status & Verdict */}
        <div className="lg:col-span-8 space-y-8">
          <section aria-label="Current Status">
            <StatusBadge status={status} />
          </section>

          {verdict && (
            <section className="space-y-6 animate-in fade-in slide-in-from-bottom-4">
              <div className="flex items-center gap-2 text-neonMagenta font-bold text-lg">
                <Activity />
                <h2>TRIBUNAL VERDICT</h2>
              </div>
              
              <Verdict judges={verdict.judges} />

              {verdict.patches.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-lg font-bold mb-4 text-neonCyan">REMEDIATION PATCHES</h3>
                  <div className="space-y-4">
                    {verdict.patches.map((patch, i) => (
                      <PatchDiff key={i} patch={patch} />
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}
        </div>

        {/* Right Column: Spec View */}
        <div className="lg:col-span-4 h-[calc(100vh-12rem)] sticky top-24">
          <div className="h-full border-l border-white/10 pl-6">
            <SpecView invariants={invariants} />
          </div>
        </div>
      </div>

      <Toast message={toastMsg} />
    </main>
  );
}
