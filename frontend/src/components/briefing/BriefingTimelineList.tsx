import { Archive, Loader2 } from 'lucide-react'
import { format, isToday, isYesterday } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { BriefingSummary } from '../../types'
import { BriefingTimelineItem } from './BriefingTimelineItem'

interface Props {
  summaries: BriefingSummary[]
  summariesStatus: 'loading' | 'ready' | 'error'
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
  selectedId: number | null
  onSelect: (id: number) => void
}

function dayLabel(isoDate: string): string {
  const d = new Date(isoDate)
  if (isToday(d)) return "Aujourd'hui"
  if (isYesterday(d)) return 'Hier'
  return format(d, 'EEEE d MMMM yyyy', { locale: fr })
}

function groupByDay(summaries: BriefingSummary[]): Array<[string, BriefingSummary[]]> {
  const groups: Array<[string, BriefingSummary[]]> = []
  for (const s of summaries) {
    const label = dayLabel(s.generated_at)
    const last = groups[groups.length - 1]
    if (last && last[0] === label) last[1].push(s)
    else groups.push([label, [s]])
  }
  return groups
}

export function BriefingTimelineList({
  summaries,
  summariesStatus,
  hasMore,
  loadingMore,
  onLoadMore,
  selectedId,
  onSelect,
}: Props) {
  const groups = groupByDay(summaries)

  return (
    <div className="flex h-full flex-col overflow-hidden border-border-subtle lg:border-r">
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {summariesStatus === 'loading' && (
          <div className="space-y-3" aria-hidden>
            {[0, 1, 2, 3].map(i => (
              <div key={i} className="briefing-shimmer h-20 rounded-md" />
            ))}
          </div>
        )}

        {summariesStatus === 'error' && (
          <p className="px-1 py-6 text-center text-xs text-text-muted">
            Impossible de charger l'historique.
          </p>
        )}

        {summariesStatus === 'ready' && summaries.length === 0 && (
          <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-md bg-bg-surface text-text-muted">
              <Archive className="h-4 w-4" />
            </div>
            <p className="text-xs leading-relaxed text-text-muted">
              Aucun briefing archivé pour l'instant.
            </p>
          </div>
        )}

        {summariesStatus === 'ready' && groups.map(([label, items]) => (
          <div key={label} className="mb-4">
            <h3 className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              {label}
            </h3>
            <ul className="space-y-1">
              {items.map(s => (
                <BriefingTimelineItem
                  key={s.id}
                  summary={s}
                  selected={s.id === selectedId}
                  onSelect={() => onSelect(s.id)}
                />
              ))}
            </ul>
          </div>
        ))}

        {summariesStatus === 'ready' && hasMore && (
          <button
            onClick={onLoadMore}
            disabled={loadingMore}
            className="flex w-full items-center justify-center gap-1.5 rounded-md py-2 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
          >
            {loadingMore ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            Charger plus
          </button>
        )}
      </div>
    </div>
  )
}
