export type Judge = {
  name: 'architect' | 'security' | 'user_proxy';
  model: string;
  vote: 'pass' | 'fail' | 'veto';
  confidence: number; // 0..1
  notes: string;
};

export type Patch = {
  file: string;
  diffUnified: string;
  generatedBy: string;
};

export type VerdictPayload = {
  runId: string;
  result: 'consensus_pass' | 'consensus_fail';
  summary: { 
    filesScanned: string[]; 
    pylintScore?: number; 
    banditFindings?: any[] 
  };
  judges: Judge[];
  patches: Patch[];
  timestamp?: string;
};

export type WatcherUpdatePayload = {
  status: "idle" | "watcher_detected" | "scanning";
  files: number;
  lastChangeAt: string;
};

export type VerdictUpdatePayload = {
  runId: string;
  stage: "static_analysis" | "llm_judges" | "patch_generation";
  percent: number;
  partialVerdict: null | any;
};

export type Invariant = {
  id: string;
  description: string;
  matcher: string;
  severity: string;
};
