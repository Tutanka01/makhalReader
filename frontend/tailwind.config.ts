import type { Config } from 'tailwindcss'
import plugin from 'tailwindcss/plugin'

/** A theme color backed by an RGB channel variable, so `/<opacity>` modifiers work. */
const channel = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`

const config: Config = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{ts,tsx,js,jsx}',
  ],
  future: {
    // `hover:` styles only apply on devices that can actually hover. On an
    // iPad a tap would otherwise leave the last touched row "stuck" hovered.
    hoverOnlyWhenSupported: true,
  },
  theme: {
    extend: {
      colors: {
        'bg-base': channel('bg-base'),
        'bg-surface': channel('bg-surface'),
        'bg-elevated': channel('bg-elevated'),
        'bg-hover': channel('bg-hover'),
        'border-subtle': 'var(--color-border-subtle)',
        'border-default': 'var(--color-border-default)',
        'text-primary': channel('text-primary'),
        'text-secondary': channel('text-secondary'),
        'text-muted': channel('text-muted'),
        'accent-blue': channel('accent-blue'),
        'accent-green': channel('accent-green'),
        'accent-yellow': channel('accent-yellow'),
        'accent-red': channel('accent-red'),
        'on-accent': channel('on-accent'),
        'score-high': channel('accent-green'),
        'score-mid': channel('accent-yellow'),
        'score-low': channel('accent-red'),
      },
      // A bare `border` uses the theme's hairline instead of Tailwind's #e5e7eb,
      // which reads as a stark white outline on the dark theme.
      borderColor: {
        DEFAULT: 'var(--color-border-default)',
      },
      opacity: {
        8: '0.08',
        12: '0.12',
        14: '0.14',
        18: '0.18',
        22: '0.22',
        28: '0.28',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['Lora', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      fontSize: {
        'reader-body': ['17px', { lineHeight: '1.75' }],
      },
      boxShadow: {
        elevated: 'var(--shadow-elevated)',
        pane: 'var(--shadow-pane)',
      },
    },
  },
  plugins: [
    plugin(({ addVariant }) => {
      // Primary input is a finger (iPad, phone): enlarge hit targets.
      addVariant('touch', '@media (pointer: coarse)')
      // Precise pointer that can hover: hover-revealed controls are safe here.
      addVariant('can-hover', '@media (hover: hover) and (pointer: fine)')
    }),
  ],
}

export default config
