/**
 * Step Indicator Component
 * 
 * Visual indicator showing progress through the onboarding wizard.
 */

'use client';

import { cn } from '@/lib/utils';
import type { OnboardingStep } from '@/lib/stores';

interface Step {
  id: OnboardingStep;
  title: string;
  description: string;
}

interface StepIndicatorProps {
  steps: Step[];
  currentStep: OnboardingStep;
  completedSteps: OnboardingStep[];
}

export function StepIndicator({ steps, currentStep, completedSteps }: StepIndicatorProps) {
  return (
    <nav aria-label="Progress">
      <ol className="flex items-center justify-between">
        {steps.map((step, index) => {
          const isCurrent = step.id === currentStep;
          const isCompleted = completedSteps.includes(step.id);
          const isUpcoming = !isCurrent && !isCompleted;
          
          return (
            <li key={step.id} className="relative flex-1">
              {/* Connector line */}
              {index > 0 && (
                <div
                  className={cn(
                    'absolute left-0 top-4 -translate-x-1/2 w-full h-0.5',
                    isCompleted || isCurrent
                      ? 'bg-[var(--color-primary)]'
                      : 'bg-[var(--color-border)]'
                  )}
                  aria-hidden="true"
                />
              )}
              
              {/* Step circle and label */}
              <div className="relative flex flex-col items-center">
                {/* Circle */}
                <div
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center',
                    'text-sm font-medium transition-all duration-300',
                    'border-2',
                    isCompleted && [
                      'bg-[var(--color-primary)] border-[var(--color-primary)]',
                      'text-white',
                    ],
                    isCurrent && [
                      'bg-[var(--color-primary-muted)] border-[var(--color-primary)]',
                      'text-[var(--color-primary)]',
                      'ring-4 ring-[var(--color-primary-muted)]',
                    ],
                    isUpcoming && [
                      'bg-[var(--color-surface-2)] border-[var(--color-border)]',
                      'text-[var(--color-text-muted)]',
                    ]
                  )}
                >
                  {isCompleted ? (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    index + 1
                  )}
                </div>
                
                {/* Label */}
                <div className="mt-3 text-center">
                  <p
                    className={cn(
                      'text-sm font-medium',
                      isCurrent
                        ? 'text-[var(--color-text-primary)]'
                        : 'text-[var(--color-text-muted)]'
                    )}
                  >
                    {step.title}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
