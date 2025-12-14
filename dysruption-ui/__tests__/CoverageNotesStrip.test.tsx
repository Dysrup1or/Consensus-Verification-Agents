import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import CoverageNotesStrip from '@/components/CoverageNotesStrip';
import type { TelemetryCoverage } from '@/lib/types';

describe('CoverageNotesStrip', () => {
  it('does not render when coverage complete and no skips', () => {
    const coverage: TelemetryCoverage = {
      fully_covered_percent_of_changed: 100,
      changed_files_total: 1,
      changed_files_fully_covered_count: 1,
      header_covered_count: 1,
      forced_files_count: 0,
      skip_reasons: {},
    };

    const { container } = render(<CoverageNotesStrip coverage={coverage} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders grouped skip reasons', () => {
    const coverage: TelemetryCoverage = {
      fully_covered_percent_of_changed: 90,
      changed_files_total: 10,
      changed_files_fully_covered_count: 9,
      header_covered_count: 5,
      forced_files_count: 0,
      skip_reasons: {
        'src/a.ts': 'skipped_external',
        'src/b.ts': 'skipped_external',
        'src/c.ts': 'skipped_missing',
      },
    };

    render(<CoverageNotesStrip coverage={coverage} />);

    expect(screen.getByText('Coverage Notes')).toBeInTheDocument();
    expect(screen.getByText(/skipped_external: 2/i)).toBeInTheDocument();
    expect(screen.getByText(/skipped_missing: 1/i)).toBeInTheDocument();
  });
});
