/**
 * Transition Components
 * 
 * Reusable enter/exit animations for UI elements.
 */

'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface FadeInProps {
  children: ReactNode;
  delay?: number;
  duration?: number;
  className?: string;
}

export function FadeIn({ children, delay = 0, duration = 300, className }: FadeInProps) {
  const [isVisible, setIsVisible] = useState(false);
  
  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  
  return (
    <div
      className={cn(
        'transition-all',
        isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2',
        className
      )}
      style={{ transitionDuration: `${duration}ms` }}
    >
      {children}
    </div>
  );
}

interface SlideInProps {
  children: ReactNode;
  direction?: 'left' | 'right' | 'up' | 'down';
  delay?: number;
  duration?: number;
  className?: string;
}

export function SlideIn({
  children,
  direction = 'up',
  delay = 0,
  duration = 300,
  className,
}: SlideInProps) {
  const [isVisible, setIsVisible] = useState(false);
  
  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  
  const transformMap = {
    left: 'translate-x-8',
    right: '-translate-x-8',
    up: 'translate-y-8',
    down: '-translate-y-8',
  };
  
  return (
    <div
      className={cn(
        'transition-all',
        isVisible ? 'opacity-100 translate-x-0 translate-y-0' : `opacity-0 ${transformMap[direction]}`,
        className
      )}
      style={{ transitionDuration: `${duration}ms` }}
    >
      {children}
    </div>
  );
}

interface ScaleInProps {
  children: ReactNode;
  delay?: number;
  duration?: number;
  className?: string;
}

export function ScaleIn({ children, delay = 0, duration = 300, className }: ScaleInProps) {
  const [isVisible, setIsVisible] = useState(false);
  
  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  
  return (
    <div
      className={cn(
        'transition-all',
        isVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95',
        className
      )}
      style={{ transitionDuration: `${duration}ms` }}
    >
      {children}
    </div>
  );
}

interface StaggeredListProps {
  children: ReactNode[];
  staggerDelay?: number;
  duration?: number;
  className?: string;
}

export function StaggeredList({
  children,
  staggerDelay = 50,
  duration = 300,
  className,
}: StaggeredListProps) {
  return (
    <div className={className}>
      {children.map((child, index) => (
        <FadeIn key={index} delay={index * staggerDelay} duration={duration}>
          {child}
        </FadeIn>
      ))}
    </div>
  );
}

interface CollapseProps {
  isOpen: boolean;
  children: ReactNode;
  duration?: number;
  className?: string;
}

export function Collapse({ isOpen, children, duration = 300, className }: CollapseProps) {
  const [height, setHeight] = useState<number | undefined>(isOpen ? undefined : 0);
  const [contentRef, setContentRef] = useState<HTMLDivElement | null>(null);
  
  useEffect(() => {
    if (!contentRef) return;
    
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (isOpen) {
          setHeight(entry.contentRect.height);
        } else {
          setHeight(0);
        }
      }
    });
    
    resizeObserver.observe(contentRef);
    
    // Initial height set
    if (isOpen) {
      setHeight(contentRef.scrollHeight);
    }
    
    return () => resizeObserver.disconnect();
  }, [contentRef, isOpen]);
  
  return (
    <div
      className={cn('overflow-hidden transition-all', className)}
      style={{
        height: height !== undefined ? `${height}px` : 'auto',
        transitionDuration: `${duration}ms`,
      }}
    >
      <div ref={setContentRef}>{children}</div>
    </div>
  );
}

interface FlipProps {
  isFlipped: boolean;
  front: ReactNode;
  back: ReactNode;
  duration?: number;
  className?: string;
}

export function Flip({ isFlipped, front, back, duration = 500, className }: FlipProps) {
  return (
    <div className={cn('relative perspective-1000', className)}>
      <div
        className="relative w-full h-full transition-transform preserve-3d"
        style={{
          transform: isFlipped ? 'rotateY(180deg)' : 'rotateY(0)',
          transitionDuration: `${duration}ms`,
        }}
      >
        {/* Front */}
        <div className="absolute w-full h-full backface-hidden">
          {front}
        </div>
        {/* Back */}
        <div
          className="absolute w-full h-full backface-hidden"
          style={{ transform: 'rotateY(180deg)' }}
        >
          {back}
        </div>
      </div>
    </div>
  );
}
