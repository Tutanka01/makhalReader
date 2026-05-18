import type { REDocType } from '../types'

const ARISE_TYPES = new Set<REDocType>(['elicitation', 'extraction', 'method'])

const RE_LABELS: Partial<Record<REDocType, string>> = {
  elicitation: 'ELIX',
  extraction:  'EXTR',
  method:      'RE-M',
}

interface ReDocTypeBadgeProps {
  type: REDocType | null | undefined
  className?: string
}

export function ReDocTypeBadge({ type, className = '' }: ReDocTypeBadgeProps) {
  if (!type || !ARISE_TYPES.has(type)) return null
  const label = RE_LABELS[type]
  if (!label) return null
  return (
    <span
      className={`inline-flex items-center px-1.5 py-[1px] rounded-[4px] text-[10px] font-medium tracking-wide bg-warning-bg text-warning ${className}`}
      title={`RE document type: ${type} (ARISE-relevant)`}
    >
      {label}
    </span>
  )
}
