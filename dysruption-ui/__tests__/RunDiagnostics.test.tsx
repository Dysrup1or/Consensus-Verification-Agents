import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import RunDiagnostics from '@/components/RunDiagnostics';
import type { RunTelemetry } from '@/lib/types';

describe('RunDiagnostics', () => {
  it('renders placeholder when telemetry missing', () => {
    render(<RunDiagnostics telemetry={null} />);
    expect(screen.getByText('Run Diagnostics')).toBeInTheDocument();
    expect(screen.getByText(/Diagnostics unavailable/i)).toBeInTheDocument();
  });

  it('renders key telemetry fields and batch stats', () => {
    const telemetry: RunTelemetry = {
      coverage: {
        fully_covered_percent_of_changed: 87.1,
        changed_files_total: 10,
        changed_files_fully_covered_count: 7,
        header_covered_count: 22,
        forced_files_count: 3,
        skip_reasons: {
          'src/a.ts': 'skipped_external',
        },
      },
      router: {
        lane_used: 'lane2',
        provider: 'open',
        model: 'gpt-oss',
        fallback_chain: [{ provider: 'frontier', model: 'gpt-5' }],
      },
      cache: {
        cached_vs_uncached: 'unknown',
        intent: 'stable_prefix_split',
        provider_cache_signal: null,
      },
      latency: {
        lane2_llm_batch_size: 3,
        lane2_llm_batch_mode: 'concurrent',
        lane2_llm_per_item_latency_ms: [10, 20, 30],
      },
    };

    render(<RunDiagnostics telemetry={telemetry} />);

    expect(screen.getByText(/87%/)).toBeInTheDocument();
    expect(screen.getByText(/7\/10 changed files fully covered/i)).toBeInTheDocument();

    expect(screen.getByText('lane2')).toBeInTheDocument();
    expect(screen.getByText('open')).toBeInTheDocument();
    expect(screen.getByText('gpt-oss')).toBeInTheDocument();
    expect(screen.getByText(/Fallback used/i)).toBeInTheDocument();

    expect(screen.getByText(/stable_prefix_split/i)).toBeInTheDocument();
    expect(screen.getByText(/concurrent/i)).toBeInTheDocument();

    expect(screen.getByText(/min 10, median 20, max 30/i)).toBeInTheDocument();
  });
});
