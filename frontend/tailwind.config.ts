import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{ts,tsx,js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        'bg-base': 'var(--bg)',
        'bg-surface': 'var(--bg-secondary)',
        'bg-elevated': 'var(--bg-active)',
        'bg-hover': 'var(--bg-hover)',
        'border-subtle': 'var(--border)',
        'border-default': 'var(--border-strong)',
        'text-primary': 'var(--text)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted': 'var(--text-muted)',
        'accent-blue': 'var(--accent)',
        'accent-green': 'var(--success)',
        'accent-yellow': 'var(--warning)',
        'accent-red': 'var(--danger)',
        'score-high': 'var(--success)',
        'score-mid': 'var(--warning)',
        'score-low': 'var(--danger)',
        
        // Add additional ProjectOS specific colors to be used natively via tailwind
        'accent': 'var(--accent)',
        'accent-light': 'var(--accent-light)',
        'success': 'var(--success)',
        'success-bg': 'var(--success-bg)',
        'warning': 'var(--warning)',
        'warning-bg': 'var(--warning-bg)',
        'danger': 'var(--danger)',
        'danger-bg': 'var(--danger-bg)',
        'purple': 'var(--purple)',
        'purple-bg': 'var(--purple-bg)',
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"DM Mono"', 'monospace'],
        serif: ['Lora', 'Georgia', 'serif'],
      },
      fontSize: {
        'reader-body': ['17px', { lineHeight: '1.75' }],
      },
    },
  },
  plugins: [],
}

export default config
