import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

type Tone = 'default' | 'active' | 'success' | 'warning' | 'danger'

function toneClass(tone: Tone) {
  switch (tone) {
    case 'active':
      return 'border-transparent bg-accent-blue/12 text-accent-blue'
    case 'success':
      return 'border-transparent bg-accent-green/12 text-accent-green'
    case 'warning':
      return 'border-transparent bg-accent-yellow/12 text-accent-yellow'
    case 'danger':
      return 'border-transparent bg-accent-red/12 text-accent-red'
    default:
      return 'border-transparent bg-transparent text-text-muted'
  }
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon
  label: string
  tone?: Tone
  active?: boolean
}

export function IconButton({
  icon: Icon,
  label,
  tone = 'default',
  active = false,
  className = '',
  ...props
}: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`
        inline-flex h-8 w-8 items-center justify-center rounded-md border
        transition-colors duration-150
        hover:border-transparent hover:bg-bg-hover hover:text-text-primary
        disabled:pointer-events-none disabled:opacity-40
        ${toneClass(active && tone === 'default' ? 'active' : tone)}
        ${className}
      `}
      {...props}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}

interface ScoreBadgeProps {
  score: number | null | undefined
  compact?: boolean
  className?: string
}

export function ScoreBadge({ score, compact = false, className = '' }: ScoreBadgeProps) {
  if (score === null || score === undefined) {
    return (
      <span className={`inline-flex items-center rounded-md bg-bg-elevated px-2 py-1 font-mono text-xs text-text-muted ${className}`}>
        --
      </span>
    )
  }

  const tone =
    score >= 8 ? 'text-score-high bg-score-high/10'
    : score >= 5 ? 'text-score-mid bg-score-mid/10'
    : 'text-score-low bg-score-low/10'

  return (
    <span
      className={`
        inline-flex items-baseline justify-center rounded-md font-mono font-semibold tabular-nums
        ${compact ? 'min-w-10 px-1.5 py-0.5 text-[11px]' : 'min-w-12 px-2 py-1 text-xs'}
        ${tone}
        ${className}
      `}
      title={`Score IA : ${score.toFixed(1)}/10`}
    >
      {score.toFixed(1)}
    </span>
  )
}

interface SegmentedControlProps<T extends string> {
  value: T
  options: Array<{ value: T; label: string; icon?: LucideIcon }>
  onChange: (value: T) => void
  className?: string
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  className = '',
}: SegmentedControlProps<T>) {
  return (
    <div className={`inline-flex rounded-md bg-bg-elevated/70 p-0.5 ${className}`}>
      {options.map(option => {
        const Icon = option.icon
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`
              inline-flex min-h-7 flex-1 items-center justify-center gap-1.5 rounded px-2 text-xs font-medium
              transition-colors duration-150
              ${active
                ? 'bg-bg-surface text-text-primary shadow-sm'
                : 'text-text-muted hover:text-text-primary'
              }
            `}
          >
            {Icon && <Icon className="h-3.5 w-3.5" />}
            <span>{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}

export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <p className={`text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted ${className}`}>
      {children}
    </p>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded bg-bg-elevated px-1.5 py-0.5 font-mono text-[11px] text-text-secondary">
      {children}
    </kbd>
  )
}
