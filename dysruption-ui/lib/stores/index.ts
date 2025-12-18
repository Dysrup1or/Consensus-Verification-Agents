/**
 * Stores Index
 * 
 * Central export point for all Zustand stores.
 */

export { useOnboardingStore, type OnboardingState, type OnboardingStep, type Repository } from './onboarding-store';
export { useProjectsStore, type ProjectsState, type Project, type ProjectStatus, type VerdictStatus } from './projects-store';
export { 
  useVerificationStore, 
  type VerificationState, 
  type VerificationRun, 
  type VerificationPhase,
  type JudgeVerdict,
  type VerificationCriterion,
  type VerdictResult
} from './verification-store';
