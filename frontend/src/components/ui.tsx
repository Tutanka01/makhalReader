import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { ScoringStatus } from '../types'

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

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton({
  icon: Icon,
  label,
  tone = 'default',
  active = false,
  className = '',
  ...props
}, ref) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      aria-pressed={active || undefined}
      title={label}
      className={`
        inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border
        transition-colors duration-150 touch:h-10 touch:w-10
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
})

export type ScoreTier = 'high' | 'mid' | 'low'

/** Score bands shared by every score display: 8+ strong signal, 5+ worth a look. */
export function scoreTier(score: number): ScoreTier {
  if (score >= 8) return 'high'
  if (score >= 5) return 'mid'
  return 'low'
}

/** Lit bars on the 4-bar signal meter for a 0–10 score. */
export function signalBars(score: number): number {
  return Math.max(0, Math.min(4, Math.ceil(score / 2.5)))
}

const TIER_CLASS: Record<ScoreTier, string> = {
  high: 'text-score-high bg-score-high/10',
  mid: 'text-score-mid bg-score-mid/10',
  low: 'text-score-low bg-score-low/10',
}

const BAR_HEIGHTS = { compact: [4, 6, 8, 10], regular: [5, 8, 11, 14] }

export function SignalBars({ lit, compact, scanning = false }: { lit: number; compact: boolean; scanning?: boolean }) {
  const heights = compact ? BAR_HEIGHTS.compact : BAR_HEIGHTS.regular
  return (
    <span
      aria-hidden
      className={`inline-flex items-end gap-[2px] ${scanning ? 'signal-scan' : ''}`}
      style={{ height: heights[3] }}
    >
      {heights.map((h, i) => (
        <span
          key={i}
          className={`w-[3px] rounded-[1px] bg-current ${scanning || i >= lit ? 'opacity-25' : ''}`}
          style={{ height: h, ['--i' as string]: i }}
        />
      ))}
    </span>
  )
}

interface ScoreBadgeProps {
  score: number | null | undefined
  /** Scoring queue state; a missing score with a non-failed status reads as "in progress". */
  status?: ScoringStatus
  compact?: boolean
  className?: string
}

/**
 * The app's signal meter: four bars (like reception strength) plus the score.
 * While the LLM has not scored the article yet the bars sweep, so an empty
 * score reads as work in progress rather than missing data.
 */
export function ScoreBadge({ score, status, compact = false, className = '' }: ScoreBadgeProps) {
  const size = compact ? 'h-6 gap-1.5 px-1.5 text-[11px]' : 'h-7 gap-2 px-2 text-xs'

  if (score === null || score === undefined) {
    const failed = status === 'failed'
    return (
      <span
        role="img"
        aria-label={failed ? 'Score indisponible : le scoring a échoué' : 'Score en cours de calcul'}
        title={failed ? 'Le scoring IA a échoué pour cet article' : 'L’IA évalue cet article…'}
        className={`
          inline-flex flex-shrink-0 items-center rounded-md font-medium
          ${failed ? 'bg-bg-elevated text-text-muted' : 'bg-accent-blue/8 text-accent-blue'}
          ${size} ${className}
        `}
      >
        <SignalBars lit={0} compact={compact} scanning={!failed} />
        {failed ? <span>n/a</span> : !compact && <span>Analyse…</span>}
      </span>
    )
  }

  return (
    <span
      role="img"
      aria-label={`Score IA ${score.toFixed(1)} sur 10`}
      title={`Score IA : ${score.toFixed(1)}/10`}
      className={`
        inline-flex flex-shrink-0 items-center rounded-md font-semibold tabular-nums
        ${TIER_CLASS[scoreTier(score)]} ${size} ${className}
      `}
    >
      <SignalBars lit={signalBars(score)} compact={compact} />
      <span>{score.toFixed(1)}</span>
    </span>
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
