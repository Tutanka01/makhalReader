import type { BriefingArticle, BriefingSection as Section } from '../../types'

interface Props {
  section: Section
  articles: Record<string, BriefingArticle>
  index: number
  onOpen: (id: number) => void
}

export function BriefingSection({ section, articles, index, onOpen }: Props) {
  const linked = section.article_ids.map(id => articles[String(id)]).filter(Boolean)

  return (
    <section className="briefing-rise" style={{ animationDelay: `${160 + index * 70}ms` }}>
      <h2 className="text-lg font-bold tracking-tight text-text-primary">{section.title}</h2>
      <p className="reader-content mt-2 text-[17px] leading-relaxed text-text-secondary">{section.synthesis}</p>
      {section.why_it_matters && (
        <p className="mt-3 border-l-2 border-accent-yellow/60 pl-3 text-sm italic text-text-muted">
          {section.why_it_matters}
        </p>
      )}
      <ul className="mt-4 space-y-1.5">
        {linked.map(a => (
          <li key={a.id}>
            <button
              onClick={() => onOpen(a.id)}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-bg-hover ${a.read_at ? 'opacity-60' : ''}`}
            >
              <span className="text-xs font-bold tabular-nums text-text-muted">{(a.score ?? 0).toFixed(0)}</span>
              <span className="flex-1 truncate text-sm text-text-primary">{a.title}</span>
              <span className="flex-shrink-0 text-[11px] text-text-muted">{a.feed_name}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
