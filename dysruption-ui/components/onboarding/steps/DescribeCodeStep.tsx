/**
 * Describe Code Step
 * 
 * Third step of onboarding - provide context about the project.
 */

'use client';

import { useState } from 'react';
import { useOnboardingStore } from '@/lib/stores';
import { Input, Badge, Button } from '@/components/ui';
import { cn } from '@/lib/utils';

const FRAMEWORK_SUGGESTIONS = [
  { id: 'react', label: 'React', icon: '⚛️' },
  { id: 'nextjs', label: 'Next.js', icon: '▲' },
  { id: 'vue', label: 'Vue.js', icon: '💚' },
  { id: 'angular', label: 'Angular', icon: '🅰️' },
  { id: 'express', label: 'Express', icon: '🚂' },
  { id: 'fastapi', label: 'FastAPI', icon: '⚡' },
  { id: 'django', label: 'Django', icon: '🐍' },
  { id: 'flask', label: 'Flask', icon: '🌶️' },
  { id: 'typescript', label: 'TypeScript', icon: '📘' },
  { id: 'graphql', label: 'GraphQL', icon: '◈' },
  { id: 'rest', label: 'REST API', icon: '🔗' },
  { id: 'postgres', label: 'PostgreSQL', icon: '🐘' },
  { id: 'mongodb', label: 'MongoDB', icon: '🍃' },
  { id: 'redis', label: 'Redis', icon: '🔴' },
];

const DESCRIPTION_EXAMPLES = [
  "E-commerce platform with shopping cart, payments, and order management",
  "SaaS dashboard for analytics with real-time data visualization",
  "REST API backend for a mobile app with user authentication",
  "Internal tool for managing customer support tickets",
];

export function DescribeCodeStep() {
  const { 
    selectedRepository,
    codeDescription, 
    setCodeDescription, 
    frameworkHints, 
    addFrameworkHint, 
    removeFrameworkHint 
  } = useOnboardingStore();
  
  const [charCount, setCharCount] = useState(codeDescription.length);
  
  const handleDescriptionChange = (value: string) => {
    setCodeDescription(value);
    setCharCount(value.length);
  };
  
  const handleFrameworkToggle = (frameworkId: string) => {
    if (frameworkHints.includes(frameworkId)) {
      removeFrameworkHint(frameworkId);
    } else {
      addFrameworkHint(frameworkId);
    }
  };
  
  const handleExampleClick = (example: string) => {
    handleDescriptionChange(example);
  };
  
  return (
    <div className="space-y-6">
      {/* Selected repo reminder */}
      {selectedRepository && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--color-surface-2)] border border-[var(--color-border)]">
          <span className="text-[var(--color-text-muted)]">Configuring:</span>
          <span className="font-mono text-[var(--color-primary)]">{selectedRepository.fullName}</span>
        </div>
      )}
      
      {/* Description textarea */}
      <div className="space-y-2">
        <label 
          htmlFor="description" 
          className="block text-sm font-medium text-[var(--color-text-primary)]"
        >
          What does this project do?
        </label>
        <textarea
          id="description"
          value={codeDescription}
          onChange={(e) => handleDescriptionChange(e.target.value)}
          placeholder="Describe your project's main purpose and key features..."
          rows={4}
          className={cn(
            'w-full px-4 py-3 rounded-lg border resize-none',
            'bg-[var(--color-surface-1)] border-[var(--color-border)]',
            'text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]',
            'focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-[var(--color-primary)]',
            'transition-all duration-200'
          )}
        />
        <div className="flex items-center justify-between text-xs">
          <span className="text-[var(--color-text-muted)]">
            {charCount} characters
          </span>
          <span className="text-[var(--color-text-muted)]">
            {charCount < 20 ? 'Add more detail for better results' : '✓ Good description'}
          </span>
        </div>
      </div>
      
      {/* Example descriptions */}
      <div className="space-y-2">
        <p className="text-xs text-[var(--color-text-muted)]">Need inspiration? Try one of these:</p>
        <div className="flex flex-wrap gap-2">
          {DESCRIPTION_EXAMPLES.map((example, i) => (
            <button
              key={i}
              onClick={() => handleExampleClick(example)}
              className={cn(
                'text-xs px-2 py-1 rounded-md',
                'bg-[var(--color-surface-2)] text-[var(--color-text-secondary)]',
                'hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text-primary)]',
                'transition-colors truncate max-w-[200px]'
              )}
            >
              &ldquo;{example.slice(0, 30)}...&rdquo;
            </button>
          ))}
        </div>
      </div>
      
      {/* Framework hints */}
      <div className="space-y-3">
        <label className="block text-sm font-medium text-[var(--color-text-primary)]">
          Tech Stack (optional)
        </label>
        <p className="text-xs text-[var(--color-text-muted)]">
          Select the technologies used in your project for better verification rules.
        </p>
        <div className="flex flex-wrap gap-2">
          {FRAMEWORK_SUGGESTIONS.map((framework) => {
            const isSelected = frameworkHints.includes(framework.id);
            return (
              <button
                key={framework.id}
                onClick={() => handleFrameworkToggle(framework.id)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full',
                  'text-sm font-medium transition-all',
                  'border',
                  isSelected
                    ? 'bg-[var(--color-primary-muted)] border-[var(--color-primary)] text-[var(--color-primary)]'
                    : 'bg-[var(--color-surface-2)] border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-text-muted)]'
                )}
              >
                <span>{framework.icon}</span>
                <span>{framework.label}</span>
                {isSelected && (
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      </div>
      
      {/* Summary */}
      {(codeDescription || frameworkHints.length > 0) && (
        <div className="p-4 rounded-lg bg-[var(--color-surface-2)] border border-[var(--color-border)] space-y-2">
          <p className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider">
            Verification Context
          </p>
          {codeDescription && (
            <p className="text-sm text-[var(--color-text-secondary)]">
              {codeDescription}
            </p>
          )}
          {frameworkHints.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {frameworkHints.map((hint) => {
                const framework = FRAMEWORK_SUGGESTIONS.find((f) => f.id === hint);
                return framework ? (
                  <Badge key={hint} variant="primary" size="sm">
                    {framework.icon} {framework.label}
                  </Badge>
                ) : null;
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
