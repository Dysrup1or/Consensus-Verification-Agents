"use client";

import React, { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'dark' | 'light' | 'system';
const KEY = 'cva:theme';

const ThemeContext = createContext({
  theme: 'dark' as Theme,
  setTheme: (t: Theme) => {},
  toggle: () => {}
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('dark');
  const [mounted, setMounted] = useState(false);

  // Load theme from localStorage after mount (client-side only)
  useEffect(() => {
    try {
      const stored = localStorage.getItem(KEY) as Theme | null;
      if (stored) setThemeState(stored);
    } catch (e) {
      // ignore
    }
    setMounted(true);
  }, []);

  useEffect(() => {
    // Only run after mount to avoid SSR mismatch
    if (!mounted) return;

    const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const applied = theme === 'system'
      ? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : theme;

    try {
      document.documentElement.classList.toggle('dark', applied === 'dark');
      localStorage.setItem(KEY, theme);
    } catch (e) {
      // ignore
    }

    // set reduced motion attribute
    if (prefersReduced) {
      document.documentElement.classList.add('reduce-motion');
    } else {
      document.documentElement.classList.remove('reduce-motion');
    }
  }, [theme, mounted]);

  const toggle = () => setThemeState(t => (t === 'dark' ? 'light' : 'dark'));

  return <ThemeContext.Provider value={{ theme, setTheme: setThemeState, toggle }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
