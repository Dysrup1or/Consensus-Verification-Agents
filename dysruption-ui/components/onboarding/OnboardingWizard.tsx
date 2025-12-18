/**
 * Onboarding Wizard Component
 * 
 * Multi-step wizard for new user onboarding.
 * Steps: Connect GitHub → Select Repo → Describe Code
 */

'use client';

import { useRouter } from 'next/navigation';
import { useOnboardingStore, type OnboardingStep } from '@/lib/stores';
import { Button } from '@/components/ui';
import { StepIndicator } from './StepIndicator';
import { ConnectGitHubStep } from './steps/ConnectGitHubStep';
import { SelectRepoStep } from './steps/SelectRepoStep';
import { DescribeCodeStep } from './steps/DescribeCodeStep';

const STEPS: { id: OnboardingStep; title: string; description: string }[] = [
  {
    id: 'connect-github',
    title: 'Connect GitHub',
    description: 'Link your GitHub account to import repositories',
  },
  {
    id: 'select-repo',
    title: 'Select Repository',
    description: 'Choose which project to verify',
  },
  {
    id: 'describe-code',
    title: 'Describe Your Code',
    description: 'Help us understand your project',
  },
];

export function OnboardingWizard() {
  const router = useRouter();
  const { currentStep, completedSteps, setStep, completeStep, selectedRepository, codeDescription } = 
    useOnboardingStore();
  
  const currentStepIndex = STEPS.findIndex((s) => s.id === currentStep);
  
  const handleNext = () => {
    // Complete current step
    completeStep(currentStep);
    
    // Move to next step or finish
    if (currentStepIndex < STEPS.length - 1) {
      setStep(STEPS[currentStepIndex + 1].id);
    } else {
      // All steps complete - redirect to dashboard
      router.push('/');
    }
  };
  
  const handleBack = () => {
    if (currentStepIndex > 0) {
      setStep(STEPS[currentStepIndex - 1].id);
    }
  };
  
  const canProceed = () => {
    switch (currentStep) {
      case 'connect-github':
        return useOnboardingStore.getState().githubConnected;
      case 'select-repo':
        return selectedRepository !== null;
      case 'describe-code':
        return codeDescription.trim().length > 0;
      default:
        return false;
    }
  };
  
  const renderStep = () => {
    switch (currentStep) {
      case 'connect-github':
        return <ConnectGitHubStep onComplete={handleNext} />;
      case 'select-repo':
        return <SelectRepoStep />;
      case 'describe-code':
        return <DescribeCodeStep />;
      default:
        return null;
    }
  };
  
  return (
    <div className="space-y-8">
      {/* Step Indicator */}
      <StepIndicator
        steps={STEPS}
        currentStep={currentStep}
        completedSteps={completedSteps}
      />
      
      {/* Step Content */}
      <div className="bg-[var(--color-surface-1)] border border-[var(--color-border)] rounded-xl p-6 md:p-8">
        <div className="space-y-6">
          {/* Step Header */}
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">
              {STEPS[currentStepIndex]?.title}
            </h1>
            <p className="text-[var(--color-text-secondary)]">
              {STEPS[currentStepIndex]?.description}
            </p>
          </div>
          
          {/* Step Component */}
          <div className="py-4">
            {renderStep()}
          </div>
          
          {/* Navigation */}
          <div className="flex items-center justify-between pt-4 border-t border-[var(--color-border-muted)]">
            <Button
              intent="ghost"
              onClick={handleBack}
              disabled={currentStepIndex === 0}
            >
              ← Back
            </Button>
            
            <Button
              intent="primary"
              onClick={handleNext}
              disabled={!canProceed()}
            >
              {currentStepIndex === STEPS.length - 1 ? 'Complete Setup' : 'Continue →'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
