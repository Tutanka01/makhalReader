import { Clock } from 'lucide-react'

interface ReadTimeBadgeProps {
  minutes: number | null | undefined
  className?: string
}

export function ReadTimeBadge({ minutes, className = '' }: ReadTimeBadgeProps) {
  if (minutes === null || minutes === undefined || minutes <= 0) return null

  const label = minutes === 1 ? '1 min' : `${minutes} min`

  return (
    <span
      className={`
        inline-flex items-center gap-1 text-xs text-text-muted
        ${className}
      `}
      title={`Temps de lecture estimé : ${minutes} minute${minutes > 1 ? 's' : ''}`}
    >
      <Clock className="w-3 h-3" strokeWidth={2.5} />
      {label}
    </span>
  )
}
