import '@testing-library/jest-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import Verdict from '@/components/Verdict';
import { JudgeVerdict, JudgeRole } from '@/lib/types';

const mockVerdicts: Record<string, JudgeVerdict> = {
  architect: {
    judge_role: 'architect' as JudgeRole,
    model_used: 'claude-4-sonnet',
    status: 'fail',
    score: 6.5,
    confidence: 0.9,
    explanation: 'Architecture issues found',
    issues: [],
    suggestions: ['Refactor the module structure'],
    invariants_checked: [1, 2],
    execution_time_ms: 1500,
  },
  security: {
    judge_role: 'security' as JudgeRole,
    model_used: 'deepseek-v3',
    status: 'fail',
    score: 3.0,
    confidence: 0.95,
    explanation: 'Security risk detected!',
    issues: [{ description: 'Use of eval() on user input', file_path: 'main.py', line_number: 42 }],
    suggestions: ['Use ast.literal_eval instead'],
    invariants_checked: [3],
    execution_time_ms: 2000,
  },
  user_proxy: {
    judge_role: 'user_proxy' as JudgeRole,
    model_used: 'gemini-2.5-pro',
    status: 'pass',
    score: 8.0,
    confidence: 0.6,
    explanation: 'Looks good from user perspective',
    issues: [],
    suggestions: [],
    invariants_checked: [4, 5],
    execution_time_ms: 1200,
  },
};

describe('Verdict Component', () => {
  it('renders 3 judge cards', () => {
    render(<Verdict verdicts={mockVerdicts} />);
    expect(screen.getByText('Architect')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('User Proxy')).toBeInTheDocument();
  });

  it('toggles explanation visibility on click', () => {
    render(<Verdict verdicts={mockVerdicts} />);
    const card = screen.getByText('Architect').closest('div[role="button"]');
    expect(screen.queryByText('Architecture issues found')).not.toBeInTheDocument();
    
    fireEvent.click(card!);
    expect(screen.getByText('Architecture issues found')).toBeInTheDocument();
    
    fireEvent.click(card!);
    expect(screen.queryByText('Architecture issues found')).not.toBeInTheDocument();
  });

  it('applies veto styling correctly when vetoTriggered is true', () => {
    render(<Verdict verdicts={mockVerdicts} vetoTriggered={true} />);
    const vetoCard = screen.getByTestId('veto');
    expect(vetoCard).toHaveClass('motion-safe:animate-pulse');
    expect(vetoCard).toHaveClass('border-danger/50');
    expect(vetoCard).toHaveClass('text-danger');
  });
});
