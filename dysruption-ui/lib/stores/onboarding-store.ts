/**
 * Onboarding Store
 * 
 * Zustand store for managing the onboarding wizard state.
 * Persists to localStorage for session continuity.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type OnboardingStep = 'connect-github' | 'select-repo' | 'describe-code';

export interface Repository {
  id: string;
  name: string;
  fullName: string;
  description: string | null;
  defaultBranch: string;
  isPrivate: boolean;
  language: string | null;
  stargazersCount: number;
  pushedAt: string;
}

export interface OnboardingState {
  // Current step
  currentStep: OnboardingStep;
  completedSteps: OnboardingStep[];
  
  // Step 1: GitHub connection
  githubConnected: boolean;
  githubUsername: string | null;
  
  // Step 2: Repository selection
  selectedRepository: Repository | null;
  availableRepositories: Repository[];
  
  // Step 3: Code description
  codeDescription: string;
  frameworkHints: string[];
  
  // Actions
  setStep: (step: OnboardingStep) => void;
  completeStep: (step: OnboardingStep) => void;
  connectGitHub: (username: string) => void;
  disconnectGitHub: () => void;
  setRepositories: (repos: Repository[]) => void;
  selectRepository: (repo: Repository | null) => void;
  setCodeDescription: (description: string) => void;
  addFrameworkHint: (hint: string) => void;
  removeFrameworkHint: (hint: string) => void;
  reset: () => void;
}

const initialState = {
  currentStep: 'connect-github' as OnboardingStep,
  completedSteps: [] as OnboardingStep[],
  githubConnected: false,
  githubUsername: null,
  selectedRepository: null,
  availableRepositories: [],
  codeDescription: '',
  frameworkHints: [],
};

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setStep: (step) => set({ currentStep: step }),
      
      completeStep: (step) => {
        const { completedSteps } = get();
        if (!completedSteps.includes(step)) {
          set({ completedSteps: [...completedSteps, step] });
        }
      },
      
      connectGitHub: (username) => set({
        githubConnected: true,
        githubUsername: username,
      }),
      
      disconnectGitHub: () => set({
        githubConnected: false,
        githubUsername: null,
        selectedRepository: null,
        availableRepositories: [],
      }),
      
      setRepositories: (repos) => set({ availableRepositories: repos }),
      
      selectRepository: (repo) => set({ selectedRepository: repo }),
      
      setCodeDescription: (description) => set({ codeDescription: description }),
      
      addFrameworkHint: (hint) => {
        const { frameworkHints } = get();
        if (!frameworkHints.includes(hint)) {
          set({ frameworkHints: [...frameworkHints, hint] });
        }
      },
      
      removeFrameworkHint: (hint) => {
        const { frameworkHints } = get();
        set({ frameworkHints: frameworkHints.filter((h) => h !== hint) });
      },
      
      reset: () => set(initialState),
    }),
    {
      name: 'invariant-onboarding',
      partialize: (state) => ({
        currentStep: state.currentStep,
        completedSteps: state.completedSteps,
        githubConnected: state.githubConnected,
        githubUsername: state.githubUsername,
        selectedRepository: state.selectedRepository,
        codeDescription: state.codeDescription,
        frameworkHints: state.frameworkHints,
      }),
    }
  )
);
