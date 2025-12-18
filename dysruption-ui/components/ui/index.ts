/**
 * UI Components Index
 * 
 * Central export point for all atomic UI components.
 * Import components from '@/components/ui' for cleaner imports.
 */

// Button
export { Button, buttonVariants, type ButtonProps } from './Button';

// Card
export { 
  Card, 
  CardHeader, 
  CardTitle, 
  CardDescription, 
  CardContent, 
  CardFooter,
  cardVariants,
  type CardProps 
} from './Card';

// Input
export { Input, inputVariants, type InputProps } from './Input';

// Select
export { Select, selectVariants, type SelectProps, type SelectOption } from './Select';

// Badge
export { Badge, badgeVariants, type BadgeProps } from './Badge';

// Progress
export { Progress, progressVariants, progressBarVariants, type ProgressProps } from './Progress';

// Modal
export { 
  Modal, 
  ModalHeader, 
  ModalBody, 
  ModalFooter, 
  ModalCloseButton,
  modalOverlayVariants,
  modalContentVariants,
  type ModalProps 
} from './Modal';

// Tooltip
export { Tooltip, tooltipVariants, type TooltipProps } from './Tooltip';

// Skeleton
export { 
  Skeleton, 
  SkeletonCard, 
  SkeletonVerdictRow, 
  SkeletonProjectCard,
  skeletonVariants,
  type SkeletonProps 
} from './Skeleton';
