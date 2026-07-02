import { ArrowUpRight, Check, Hash, Lightbulb } from 'lucide-react'
import type { BriefingArticle, BriefingSection as Section } from '../../types'
import { topTags } from './format'
import { ScoreBadge } from '../ui'

interface Props {
  section: Section
  articles: Record<string, BriefingArticle>
  index: number
  onOpen: (id: number) => void
}

export function BriefingSection({ section, articles, index, onOpen }: Props) {
  const linked = section.article_ids.map((id) => articles[String(id)]).filter(Boolean)
  const tags = topTags(linked)

  return (
    <section
      className="briefing-rise rounded-md bg-bg-surface/80"
      style={{ animationDelay: `${130 + index * 60}ms` }}
    >
      <div className="border-b border-border-subtle px-4 py-4 sm:px-5">
        <div className="flex items-start gap-3">
          <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-bg-elevated font-mono text-xs font-semibold tabular-nums text-text-secondary">
            {String(index + 1).padStart(2, '0')}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <h2 className="text-xl font-semibold leading-snug text-text-primary">
                {section.title}
              </h2>
              {linked.length > 0 && (
                <span className="flex-shrink-0 text-xs text-text-muted">
                  {linked.length} source{linked.length > 1 ? 's' : ''}
                </span>
              )}
            </div>

            {tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 rounded bg-bg-elevated/80 px-1.5 py-0.5 text-[10px] text-text-muted"
                  >
                    <Hash className="h-2.5 w-2.5" />
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="px-4 py-4 sm:px-5">
        <p className="reader-content text-[17px] leading-relaxed text-text-secondary">
          {section.synthesis}
        </p>

        {section.why_it_matters && (
          <div className="mt-4 flex gap-3 rounded-md bg-accent-yellow/8 p-3">
            <Lightbulb className="mt-0.5 h-4 w-4 flex-shrink-0 text-accent-yellow" />
            <div>
              <div className="text-xs font-semibold text-accent-yellow">Pourquoi ça compte</div>
              <p className="mt-1 text-sm leading-relaxed text-text-secondary">{section.why_it_matters}</p>
            </div>
          </div>
        )}

        {linked.length > 0 && (
          <div className="mt-4 border-t border-border-subtle pt-2">
            <ul className="divide-y divide-border-subtle">
              {linked.map((a) => (
                <li key={a.id}>
                  <button
                    onClick={() => onOpen(a.id)}
                    className={`group grid w-full grid-cols-[52px_minmax(0,1fr)_auto] items-start gap-3 rounded-md px-2 py-3 text-left transition-colors hover:bg-bg-hover ${
                      a.read_at ? 'opacity-55' : ''
                    }`}
                  >
                    <ScoreBadge score={a.score} compact className="mt-0.5" />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium leading-snug text-text-primary transition-colors group-hover:text-accent-blue">
                        {a.title}
                      </span>
                      <span className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-text-muted">
                        <span className="max-w-full truncate">{a.feed_name}</span>
                        {a.reading_time ? (
                          <>
                            <span className="text-border-default">·</span>
                            <span>{a.reading_time} min</span>
                          </>
                        ) : null}
                        {a.read_at && (
                          <>
                            <span className="text-border-default">·</span>
                            <span className="inline-flex items-center gap-1 text-score-high">
                              <Check className="h-3 w-3" />
                              lu
                            </span>
                          </>
                        )}
                      </span>
                    </span>
                    <ArrowUpRight className="mt-1 h-4 w-4 flex-shrink-0 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}
