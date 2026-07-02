import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, BookOpen, Clock3, Flame, MessageSquare, Radar, Wrench } from 'lucide-react'
import type { Article, ArticleListItem } from '../types'
import { getArticleLenses, lensToneClass, type ArticleLens } from '../lenses'
import { Eyebrow } from './ui'

const ICONS: Record<string, LucideIcon> = {
  all: Radar,
  latest: Clock3,
  opinions: MessageSquare,
  debates: Flame,
  practical: Wrench,
  deep: BookOpen,
  curiosity: AlertTriangle,
}

function LensBadge({ lens, compact = false }: { lens: ArticleLens; compact?: boolean }) {
  const Icon = lens.tone === 'curiosity' ? ICONS.curiosity : ICONS[lens.key]
  return (
    <span
      title={lens.reason}
      className={`
        inline-flex min-w-0 items-center gap-1 rounded-md border font-medium
        ${compact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs'}
        ${lensToneClass(lens.tone)}
      `}
    >
      <Icon className={compact ? 'h-3 w-3 flex-shrink-0' : 'h-3.5 w-3.5 flex-shrink-0'} />
      <span className="truncate">{lens.shortLabel}</span>
    </span>
  )
}

export function ArticleLensStrip({
  article,
  max = 3,
  compact = false,
  className = '',
}: {
  article: Article | ArticleListItem
  max?: number
  compact?: boolean
  className?: string
}) {
  const lenses = getArticleLenses(article).slice(0, max)
  if (lenses.length === 0) return null
  return (
    <div className={`flex min-w-0 flex-wrap gap-1.5 ${className}`}>
      {lenses.map((lens) => (
        <LensBadge key={`${lens.key}-${lens.tone}`} lens={lens} compact={compact} />
      ))}
    </div>
  )
}

export function ArticleLensPanel({ article }: { article: Article }) {
  const lenses = getArticleLenses(article)
  if (lenses.length === 0) return null

  return (
    <section className="mb-6 rounded-md bg-bg-elevated/40 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <Eyebrow>Dans ton radar</Eyebrow>
        <span className="text-[11px] text-text-muted">intention de lecture</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {lenses.map((lens) => (
          <LensBadge key={`${lens.key}-${lens.tone}`} lens={lens} />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5">
        {lenses.slice(0, 3).map((lens) => (
          <li key={`${lens.key}-${lens.reason}`} className="flex gap-2 text-xs leading-relaxed text-text-secondary">
            <span className="mt-[0.6em] h-1 w-1 flex-shrink-0 rounded-full bg-text-muted" />
            <span>
              <span className="font-medium text-text-primary">{lens.label}</span>
              <span className="text-text-muted"> — {lens.reason}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
