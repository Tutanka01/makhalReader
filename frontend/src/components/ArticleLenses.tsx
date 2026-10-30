import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, BookOpen, Clock3, Flame, MessageSquare, Radar, Wrench } from 'lucide-react'
import type { Article, ArticleListItem } from '../types'
import { getArticleLenses, lensToneClass, type ArticleLens } from '../lenses'

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
        inline-flex min-w-0 items-center gap-1 rounded-md font-medium
        ${compact ? 'border-0 px-1.5 py-0.5 text-[11px]' : 'border px-2 py-1 text-xs'}
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
  skipFresh = false,
  className = '',
}: {
  article: Article | ArticleListItem
  max?: number
  compact?: boolean
  /** Leave out the "Nouveau" lens where a date is already shown next to it. */
  skipFresh?: boolean
  className?: string
}) {
  const lenses = getArticleLenses(article)
    .filter(lens => !(skipFresh && lens.key === 'latest' && lens.tone !== 'curiosity'))
    .slice(0, max)
  if (lenses.length === 0) return null
  return (
    <div className={`flex min-w-0 flex-wrap gap-1.5 ${className}`}>
      {lenses.map((lens) => (
        <LensBadge key={`${lens.key}-${lens.tone}`} lens={lens} compact={compact} />
      ))}
    </div>
  )
}
