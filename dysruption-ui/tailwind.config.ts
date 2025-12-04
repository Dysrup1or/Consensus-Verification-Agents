import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: 'class',
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        // Professional dark palette
        bg: '#09090b',        // zinc-950
        surface: '#18181b',   // zinc-900
        panel: '#27272a',     // zinc-800
        border: '#3f3f46',    // zinc-700
        muted: '#71717a',     // zinc-500
        // Accent colors - refined
        primary: '#6366f1',   // indigo-500
        primaryHover: '#818cf8', // indigo-400
        accent: '#22d3ee',    // cyan-400
        success: '#10b981',   // emerald-500
        warning: '#f59e0b',   // amber-500
        danger: '#ef4444',    // red-500
        // Text colors
        textPrimary: '#fafafa',  // zinc-50
        textSecondary: '#a1a1aa', // zinc-400
        textMuted: '#71717a',    // zinc-500
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'glow': '0 0 20px rgba(99, 102, 241, 0.15)',
        'glow-lg': '0 0 40px rgba(99, 102, 241, 0.2)',
      }
    },
  },
  plugins: [],
};
export default config;
