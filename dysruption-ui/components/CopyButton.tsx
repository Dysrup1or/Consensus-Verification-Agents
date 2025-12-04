'use client';

import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import { clsx } from 'clsx';

interface CopyButtonProps {
  /** The text content to copy to clipboard */
  text: string;
  /** Optional label to show next to the icon */
  label?: string;
  /** Visual variant */
  variant?: 'icon' | 'text' | 'both';
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
  /** Callback fired after successful copy */
  onCopied?: () => void;
  /** Additional CSS classes */
  className?: string;
  /** Accessible title for the button */
  title?: string;
}

/**
 * Reusable copy-to-clipboard button with visual feedback.
 * 
 * Shows a checkmark and "Copied!" feedback for 2 seconds after copying.
 * Gracefully handles clipboard API failures with console warning.
 */
export default function CopyButton({
  text,
  label,
  variant = 'icon',
  size = 'sm',
  onCopied,
  className,
  title = 'Copy to clipboard',
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      onCopied?.();
      
      // Reset after 2 seconds
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn('Failed to copy to clipboard:', err);
      // Fallback for older browsers
      try {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        setCopied(true);
        onCopied?.();
        setTimeout(() => setCopied(false), 2000);
      } catch (fallbackErr) {
        console.error('Fallback copy also failed:', fallbackErr);
      }
    }
  }, [text, onCopied]);

  const sizeClasses = {
    sm: 'p-1 text-xs',
    md: 'p-1.5 text-sm',
    lg: 'p-2 text-base',
  };

  const iconSizes = {
    sm: 12,
    md: 14,
    lg: 16,
  };

  const baseClasses = clsx(
    'inline-flex items-center gap-1 rounded transition-all duration-200',
    'hover:bg-panel focus:outline-none focus:ring-2 focus:ring-primary/50',
    copied
      ? 'bg-success/20 text-success'
      : 'text-textMuted hover:text-textPrimary',
    sizeClasses[size],
    className
  );

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={baseClasses}
      title={copied ? 'Copied!' : title}
      aria-label={copied ? 'Copied to clipboard' : title}
    >
      {copied ? (
        <>
          <Check size={iconSizes[size]} className="text-success" />
          {(variant === 'text' || variant === 'both') && (
            <span className="text-success">Copied!</span>
          )}
        </>
      ) : (
        <>
          <Copy size={iconSizes[size]} />
          {(variant === 'text' || variant === 'both') && (
            <span>{label || 'Copy'}</span>
          )}
        </>
      )}
    </button>
  );
}

/**
 * Utility function to format an issue for clipboard.
 * Creates a clean, actionable text that can be pasted into AI assistants.
 */
export function formatIssueForClipboard(issue: {
  description: string;
  file_path?: string;
  line_number?: number;
  suggestion?: string;
  severity?: string;
  category?: string;
}): string {
  const parts: string[] = [];
  
  // Header with severity/category if available
  if (issue.severity || issue.category) {
    parts.push(`[${issue.severity?.toUpperCase() || 'ISSUE'}] ${issue.category || 'General'}`);
  }
  
  // Main description
  parts.push(issue.description);
  
  // File location
  if (issue.file_path) {
    const location = issue.line_number 
      ? `${issue.file_path}:${issue.line_number}`
      : issue.file_path;
    parts.push(`Location: ${location}`);
  }
  
  // Suggestion
  if (issue.suggestion) {
    parts.push(`Suggestion: ${issue.suggestion}`);
  }
  
  return parts.join('\n');
}

/**
 * Utility function to format multiple issues for clipboard.
 */
export function formatIssuesForClipboard(issues: Array<{
  description: string;
  file_path?: string;
  line_number?: number;
  suggestion?: string;
}>): string {
  return issues
    .map((issue, i) => `${i + 1}. ${formatIssueForClipboard(issue)}`)
    .join('\n\n');
}
