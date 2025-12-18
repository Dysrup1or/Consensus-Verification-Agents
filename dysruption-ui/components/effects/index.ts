/**
 * Effects Components Index
 * 
 * Central export for all animation and micro-interaction components.
 */

// Celebration effects
export { Celebration, triggerConfetti, triggerFireworks } from './Celebration';

// Animated counters
export { AnimatedCounter, PercentageCounter } from './AnimatedCounter';

// Loading states
export {
  Spinner,
  PulseDots,
  LoadingOverlay,
  ProgressRing,
  TypingIndicator,
} from './LoadingStates';

// Transitions
export {
  FadeIn,
  SlideIn,
  ScaleIn,
  StaggeredList,
  Collapse,
  Flip,
} from './Transitions';

// Toast notifications
export { ToastProvider, useToast, toast } from './Toast';
