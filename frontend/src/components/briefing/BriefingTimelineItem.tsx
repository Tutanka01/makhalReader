import { Hash, Layers3 } from 'lucide-react'
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { BriefingSummary } from '../../types'

interface Props {
  summary: BriefingSummary
  selected: boolean
  onSelect: () => void
}

export function BriefingTimelineItem({ summary, selected, onSelect }: Props) {
  const stamp = format(new Date(summary.generated_at), 'HH:mm', { locale: fr })

  return (
    <li>
      <button
        onClick={onSelect}
        className={`group flex w-full flex-col items-start gap-1.5 rounded-md border px-3 py-2.5 text-left transition-colors ${
          selected
            ? 'border-accent-blue/30 bg-accent-blue/15 text-accent-blue'
            : 'border-transparent hover:bg-bg-hover'
        }`}
      >
        <div className="flex w-full items-center justify-between gap-2">
          <span className={`flex items-center gap-1.5 text-xs font-semibold tabular-nums ${selected ? 'text-accent-blue' : 'text-text-secondary'}`}>
            <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${selected ? 'bg-accent-blue' : 'bg-border-default'}`} />
            {stamp}
          </span>
          <span className="flex flex-shrink-0 items-center gap-1 text-[11px] text-text-muted">
            <Layers3 className="h-3 w-3" />
            {summary.sections_count}
          </span>
        </div>

        {summary.intro && (
          <p className={`line-clamp-2 text-xs leading-relaxed ${selected ? 'text-accent-blue/90' : 'text-text-muted'}`}>
            {summary.intro}
          </p>
        )}

        {summary.top_tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {summary.top_tags.map(t => (
              <span
                key={t}
                className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] ${
                  selected ? 'bg-accent-blue/10 text-accent-blue' : 'bg-bg-elevated text-text-muted'
                }`}
              >
                <Hash className="h-2.5 w-2.5" />
                {t}
              </span>
            ))}
          </div>
        )}
      </button>
    </li>
  )
}
