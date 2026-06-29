import { ArrowUpRight, Clock, Star } from 'lucide-react'
import type { BriefingArticle } from '../../types'
import { fmtScore, scoreColor } from './format'

interface Props {
  ids: number[]
  articles: Record<string, BriefingArticle>
  onOpen: (id: number) => void
}

export function TopPicks({ ids, articles, onOpen }: Props) {
  const picks = ids.map((id) => articles[String(id)]).filter(Boolean)
  if (picks.length === 0) return null

  return (
    <section className="briefing-rise" style={{ animationDelay: '70ms' }}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
          <Star className="h-4 w-4 text-accent-blue" />
          Priorités de lecture
        </h2>
        <span className="text-xs text-text-muted">{picks.length} articles</span>
      </div>

      <ol className="grid gap-2 md:grid-cols-2">
        {picks.map((a, i) => {
          const bullet = a.summary_bullets?.[0]
          return (
            <li key={a.id}>
              <button
                onClick={() => onOpen(a.id)}
                className={`group flex h-full w-full items-start gap-3 rounded-md border border-border-subtle bg-bg-surface p-3 text-left transition-colors hover:border-border-default hover:bg-bg-hover ${
                  a.read_at ? 'opacity-55' : ''
                }`}
              >
                <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-bg-elevated font-mono text-xs font-semibold tabular-nums text-text-secondary">
                  {String(i + 1).padStart(2, '0')}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="mb-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-text-muted">
                    <span className={`font-semibold ${scoreColor(a.score)}`}>{fmtScore(a.score)}</span>
                    <span className="text-border-default">·</span>
                    <span className="max-w-full truncate">{a.feed_name}</span>
                    {a.reading_time ? (
                      <>
                        <span className="text-border-default">·</span>
                        <span className="inline-flex items-center gap-0.5">
                          <Clock className="h-3 w-3" /> {a.reading_time} min
                        </span>
                      </>
                    ) : null}
                  </span>

                  <h3 className="text-sm font-semibold leading-snug text-text-primary transition-colors group-hover:text-accent-blue">
                    {a.title}
                  </h3>

                  {bullet && (
                    <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-text-muted">
                      {bullet}
                    </p>
                  )}

                  {a.tags?.length > 0 && (
                    <span className="mt-2.5 flex flex-wrap gap-1.5">
                      {a.tags.slice(0, 4).map((t) => (
                        <span
                          key={t}
                          className="rounded bg-bg-elevated px-1.5 py-0.5 text-[10px] text-text-muted before:mr-px before:content-['#']"
                        >
                          {t}
                        </span>
                      ))}
                    </span>
                  )}
                </span>

                <ArrowUpRight className="mt-1 h-4 w-4 flex-shrink-0 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
