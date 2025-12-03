import { render, screen, fireEvent } from '@testing-library/react';
import Verdict from '@/components/Verdict';
import { Judge } from '@/lib/types';

const mockJudges: Judge[] = [
  { name: 'architect', model: 'claude', vote: 'fail', confidence: 0.9, notes: 'Arch notes' },
  { name: 'security', model: 'deepseek', vote: 'veto', confidence: 0.95, notes: 'Security risk!' },
  { name: 'user_proxy', model: 'gemini', vote: 'pass', confidence: 0.6, notes: 'Looks good' },
];

describe('Verdict Component', () => {
  it('renders 3 judge cards', () => {
    render(<Verdict judges={mockJudges} />);
    expect(screen.getByText('ARCHITECT')).toBeInTheDocument();
    expect(screen.getByText('SECURITY')).toBeInTheDocument();
    expect(screen.getByText('USER_PROXY')).toBeInTheDocument();
  });

  it('toggles notes visibility on click', () => {
    render(<Verdict judges={mockJudges} />);
    const card = screen.getByText('ARCHITECT').closest('div');
    expect(screen.queryByText('Arch notes')).not.toBeInTheDocument();
    
    fireEvent.click(card!);
    expect(screen.getByText('Arch notes')).toBeInTheDocument();
    
    fireEvent.click(card!);
    expect(screen.queryByText('Arch notes')).not.toBeInTheDocument();
  });

  it('applies veto styling correctly', () => {
    render(<Verdict judges={mockJudges} />);
    const vetoCard = screen.getByTestId('veto');
    expect(vetoCard).toHaveClass('pulsing-border');
    expect(vetoCard).toHaveClass('border-danger');
  });
});
