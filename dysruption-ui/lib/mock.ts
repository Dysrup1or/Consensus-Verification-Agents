import { VerdictPayload, Invariant } from './types';

export const MOCK_VERDICT: VerdictPayload = {
  runId: "run_20251202_2002",
  result: "consensus_fail",
  summary: {
    filesScanned: ["trading/strategy.py"],
    pylintScore: 5.4,
    banditFindings: [{ "code": "B307", "line": 12, "message": "Use of eval()" }]
  },
  judges: [
    { "name": "architect", "model": "claude-4-sonnet", "vote": "fail", "confidence": 0.91, "notes": "Architecture issues detected in module structure." },
    { "name": "security", "model": "deepseek-v3", "vote": "veto", "confidence": 0.97, "notes": "RCE risk detected: direct use of eval() on user input." },
    { "name": "user_proxy", "model": "gemini-2.5-pro", "vote": "pass", "confidence": 0.55, "notes": "Spec matched functionality requirements." }
  ],
  patches: [
    {
      "file": "trading/strategy.py",
      "diffUnified": "@@ -10,7 +10,7 @@\n- result = eval(user_input)\n+ result = ast.literal_eval(user_input)\n",
      "generatedBy": "gpt-4o-mini"
    }
  ],
  timestamp: "2025-12-02T20:05:00Z"
};

export const MOCK_INVARIANTS: Invariant[] = [
  { id: "INV-001", description: "No use of eval()", matcher: "ast_visitor", severity: "critical" },
  { id: "INV-002", description: "All functions must have type hints", matcher: "regex", severity: "warning" },
  { id: "INV-003", description: "Max cyclomatic complexity < 10", matcher: "radon", severity: "info" }
];

export function getMockVerdict(): VerdictPayload {
  return MOCK_VERDICT;
}

export function startMockServer(wsHandler: (event: any) => void) {
  console.log("Starting mock server sequence...");
  
  // 1. Watcher update
  setTimeout(() => {
    wsHandler({
      type: "watcher:update",
      payload: {
        status: "watcher_detected",
        files: 12,
        lastChangeAt: new Date().toISOString()
      }
    });
  }, 1000);

  // 2. Verdict update (scanning)
  setTimeout(() => {
    wsHandler({
      type: "verdict:update",
      payload: {
        runId: "run_mock_1",
        stage: "static_analysis",
        percent: 30,
        partialVerdict: null
      }
    });
  }, 2000);

  // 3. Verdict update (judging)
  setTimeout(() => {
    wsHandler({
      type: "verdict:update",
      payload: {
        runId: "run_mock_1",
        stage: "llm_judges",
        percent: 75,
        partialVerdict: null
      }
    });
  }, 4000);

  // 4. Verdict complete
  setTimeout(() => {
    wsHandler({
      type: "verdict:complete",
      payload: MOCK_VERDICT
    });
  }, 6000);
}
