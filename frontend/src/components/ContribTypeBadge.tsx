import type { ContribType } from '../types'

const CONTRIB_COLORS: Record<ContribType, string> = {
  method:    'bg-accent-light text-accent',
  survey:    'bg-purple-bg text-purple',
  benchmark: 'bg-warning-bg text-warning',
  empirical: 'bg-success-bg text-success',
  theory:    'bg-accent-light text-accent',
  position:  'bg-warning-bg text-warning',
  tool:      'bg-success-bg text-success',
  incident:  'bg-danger-bg text-danger',
  tutorial:  'bg-bg-elevated text-text-muted',
  news:      'bg-bg-elevated text-text-muted',
  other:     'bg-bg-elevated text-text-muted',
}

const CONTRIB_LABELS: Record<ContribType, string> = {
  method:    'METHOD',
  survey:    'SURVEY',
  benchmark: 'BENCH',
  empirical: 'EMPIRICAL',
  theory:    'THEORY',
  position:  'POSITION',
  tool:      'TOOL',
  incident:  'INCIDENT',
  tutorial:  'TUTORIAL',
  news:      'NEWS',
  other:     'OTHER',
}

interface ContribTypeBadgeProps {
  type: ContribType | null | undefined
  className?: string
}

export function ContribTypeBadge({ type, className = '' }: ContribTypeBadgeProps) {
  if (!type) return null
  const colors = CONTRIB_COLORS[type] ?? CONTRIB_COLORS.other
  return (
    <span
      className={`inline-flex items-center px-1.5 py-[1px] rounded-[4px] text-[10px] font-medium tracking-wide ${colors} ${className}`}
      title={`Contribution type: ${type}`}
    >
      {CONTRIB_LABELS[type] ?? type.toUpperCase()}
    </span>
  )
}
