import { ArrowUpRight } from 'lucide-react'
import type { BriefingArticle } from '../../types'

interface Props {
  ids: number[]
  articles: Record<string, BriefingArticle>
  onOpen: (id: number) => void
}

export function TopPicks({ ids, articles, onOpen }: Props) {
  const picks = ids.map(id => articles[String(id)]).filter(Boolean)
  if (picks.length === 0) return null

  return (
    <section className="briefing-rise" style={{ animationDelay: '80ms' }}>
      <h2 className="mb-3 text-sm font-semibold text-text-secondary">À ouvrir aujourd'hui</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        {picks.map(a => (
          <button
            key={a.id}
            onClick={() => onOpen(a.id)}
            className="group relative overflow-hidden rounded-xl border border-accent-blue/30 bg-gradient-to-b from-accent-blue/[0.08] to-transparent p-4 text-left transition-all hover:-translate-y-0.5 hover:border-accent-blue/60 hover:shadow-lg"
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-score-high/30 bg-score-high/10 text-xs font-bold text-score-high">
                {(a.score ?? 0).toFixed(0)}
              </span>
              <span className="truncate text-[11px] text-text-muted">{a.feed_name}</span>
              <ArrowUpRight className="ml-auto h-4 w-4 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
            </div>
            <h3 className="line-clamp-3 text-sm font-semibold leading-snug text-text-primary">{a.title}</h3>
          </button>
        ))}
      </div>
    </section>
  )
}
