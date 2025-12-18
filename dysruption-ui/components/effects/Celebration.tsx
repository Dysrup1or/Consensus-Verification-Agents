/**
 * Celebration Component
 * 
 * Confetti explosion and success animation for passing verdicts.
 */

'use client';

import { useEffect, useCallback } from 'react';
import confetti from 'canvas-confetti';

interface CelebrationProps {
  trigger: boolean;
  intensity?: 'low' | 'medium' | 'high';
}

export function Celebration({ trigger, intensity = 'medium' }: CelebrationProps) {
  const celebrate = useCallback(() => {
    const intensityConfig = {
      low: { particleCount: 50, spread: 55 },
      medium: { particleCount: 100, spread: 70 },
      high: { particleCount: 200, spread: 100 },
    };
    
    const config = intensityConfig[intensity];
    
    // Left side
    confetti({
      particleCount: config.particleCount,
      spread: config.spread,
      origin: { x: 0.2, y: 0.6 },
      colors: ['#10b981', '#6366f1', '#22d3ee', '#f59e0b'],
    });
    
    // Right side
    confetti({
      particleCount: config.particleCount,
      spread: config.spread,
      origin: { x: 0.8, y: 0.6 },
      colors: ['#10b981', '#6366f1', '#22d3ee', '#f59e0b'],
    });
    
    // Center burst for high intensity
    if (intensity === 'high') {
      setTimeout(() => {
        confetti({
          particleCount: 150,
          spread: 120,
          origin: { x: 0.5, y: 0.5 },
          colors: ['#10b981', '#6366f1', '#22d3ee', '#f59e0b', '#ec4899'],
        });
      }, 250);
    }
  }, [intensity]);
  
  useEffect(() => {
    if (trigger) {
      celebrate();
    }
  }, [trigger, celebrate]);
  
  return null; // This is a side-effect-only component
}

/**
 * Trigger confetti programmatically
 */
export function triggerConfetti(
  options: {
    particleCount?: number;
    spread?: number;
    origin?: { x: number; y: number };
    colors?: string[];
  } = {}
) {
  confetti({
    particleCount: options.particleCount || 100,
    spread: options.spread || 70,
    origin: options.origin || { x: 0.5, y: 0.6 },
    colors: options.colors || ['#10b981', '#6366f1', '#22d3ee', '#f59e0b'],
  });
}

/**
 * Trigger fireworks effect
 */
export function triggerFireworks() {
  const duration = 3000;
  const animationEnd = Date.now() + duration;
  const defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 0 };

  function randomInRange(min: number, max: number) {
    return Math.random() * (max - min) + min;
  }

  const interval: NodeJS.Timeout = setInterval(function() {
    const timeLeft = animationEnd - Date.now();

    if (timeLeft <= 0) {
      return clearInterval(interval);
    }

    const particleCount = 50 * (timeLeft / duration);
    
    confetti({
      ...defaults,
      particleCount,
      origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 },
      colors: ['#10b981', '#6366f1'],
    });
    confetti({
      ...defaults,
      particleCount,
      origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 },
      colors: ['#22d3ee', '#f59e0b'],
    });
  }, 250);
}
