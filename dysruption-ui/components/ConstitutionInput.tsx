"use client";

import { useState } from 'react';
import { BookOpen, Sparkles, ChevronDown, ChevronUp, Info } from 'lucide-react';
import { clsx } from 'clsx';

interface ConstitutionInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

const EXAMPLE_PROMPTS = [
  {
    title: 'Security-First',
    content: `1. No use of eval(), exec(), or dynamic code execution on user input
2. All API endpoints must validate authentication tokens
3. Sensitive data must be encrypted at rest and in transit
4. No hardcoded secrets, API keys, or passwords in source code
5. SQL queries must use parameterized statements`
  },
  {
    title: 'Code Quality',
    content: `1. All functions must have type hints and docstrings
2. Maximum cyclomatic complexity of 10 per function
3. No functions longer than 50 lines
4. All public APIs must have unit test coverage > 80%
5. No TODO or FIXME comments in production code`
  },
  {
    title: 'Architecture',
    content: `1. Follow single responsibility principle - one concern per module
2. No circular dependencies between modules
3. Database access only through repository pattern
4. All external services accessed through interface abstractions
5. Configuration loaded from environment, not hardcoded`
  }
];

export default function ConstitutionInput({ value, onChange, disabled }: ConstitutionInputProps) {
  const [showExamples, setShowExamples] = useState(false);

  const applyExample = (content: string) => {
    onChange(content);
    setShowExamples(false);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-primary" />
          <h3 className="text-lg font-semibold text-textPrimary">Constitution</h3>
          <div className="group relative">
            <Info className="w-4 h-4 text-textMuted cursor-help" />
            <div className="absolute left-0 top-6 w-64 p-3 rounded-lg bg-panel border border-border text-xs text-textSecondary opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 shadow-lg">
              Define the rules and invariants your code must follow. The AI tribunal will verify compliance against these requirements.
            </div>
          </div>
        </div>
        <button
          onClick={() => setShowExamples(!showExamples)}
          className="flex items-center gap-1 text-sm text-primary hover:text-primaryHover transition-colors"
        >
          <Sparkles size={14} />
          Examples
          {showExamples ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Examples dropdown */}
      {showExamples && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 rounded-lg bg-surface border border-border animate-in fade-in slide-in-from-top-2 duration-200">
          {EXAMPLE_PROMPTS.map((example) => (
            <button
              key={example.title}
              onClick={() => applyExample(example.content)}
              className="text-left p-3 rounded-lg bg-bg hover:bg-panel border border-border hover:border-primary/50 transition-all group"
            >
              <p className="font-medium text-textPrimary group-hover:text-primary transition-colors mb-1">
                {example.title}
              </p>
              <p className="text-xs text-textMuted line-clamp-2">
                {example.content.split('\n')[0]}...
              </p>
            </button>
          ))}
        </div>
      )}

      {/* Main textarea */}
      <div className="relative">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder={`Enter your code requirements and invariants...

Example:
1. All functions must have type hints
2. No use of eval() or exec()
3. API endpoints must validate authentication
4. Maximum cyclomatic complexity of 10`}
          rows={8}
          className={clsx(
            'w-full px-4 py-3 rounded-lg bg-surface border border-border',
            'text-sm font-mono leading-relaxed',
            'placeholder:text-textMuted/50',
            'focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary',
            'resize-y min-h-[150px] max-h-[400px]',
            'transition-all duration-200',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        />
        <div className="absolute bottom-3 right-3 text-xs text-textMuted">
          {value.split('\n').filter(l => l.trim()).length} rules
        </div>
      </div>
    </div>
  );
}
