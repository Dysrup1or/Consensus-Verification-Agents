/**
 * Animated Counter Component
 * 
 * Smoothly animates number changes for statistics.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

interface AnimatedCounterProps {
  value: number;
  duration?: number;
  className?: string;
  prefix?: string;
  suffix?: string;
  formatter?: (value: number) => string;
}

export function AnimatedCounter({
  value,
  duration = 500,
  className,
  prefix = '',
  suffix = '',
  formatter = (v) => v.toLocaleString(),
}: AnimatedCounterProps) {
  const [displayValue, setDisplayValue] = useState(0);
  const previousValue = useRef(0);
  const animationRef = useRef<number>();
  
  useEffect(() => {
    const startValue = previousValue.current;
    const endValue = value;
    const startTime = performance.now();
    
    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function (ease-out-cubic)
      const eased = 1 - Math.pow(1 - progress, 3);
      
      const current = startValue + (endValue - startValue) * eased;
      setDisplayValue(Math.round(current));
      
      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      } else {
        previousValue.current = endValue;
      }
    };
    
    animationRef.current = requestAnimationFrame(animate);
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [value, duration]);
  
  return (
    <span className={cn('font-mono tabular-nums', className)}>
      {prefix}{formatter(displayValue)}{suffix}
    </span>
  );
}

/**
 * Percentage counter with color coding
 */
interface PercentageCounterProps {
  value: number;
  duration?: number;
  className?: string;
  thresholds?: { danger: number; warning: number };
}

export function PercentageCounter({
  value,
  duration = 500,
  className,
  thresholds = { danger: 50, warning: 80 },
}: PercentageCounterProps) {
  const colorClass = 
    value < thresholds.danger ? 'text-[var(--color-danger)]' :
    value < thresholds.warning ? 'text-[var(--color-warning)]' :
    'text-[var(--color-success)]';
  
  return (
    <AnimatedCounter
      value={value}
      duration={duration}
      suffix="%"
      className={cn(colorClass, className)}
    />
  );
}
