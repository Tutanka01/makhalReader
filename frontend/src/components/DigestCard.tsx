import { formatDistanceToNow } from 'date-fns'
import { fr } from 'date-fns/locale'
import { Bookmark, BookmarkCheck } from 'lucide-react'
import type { ArticleListItem } from '../types'

interface DigestCardProps {
  article: ArticleListItem
  onClick: () => void
}

function scoreColor(score: number) {
  if (score >= 9) return 'text-score-high bg-score-high/10 border-score-high/30'
  if (score >= 7) return 'text-accent-blue bg-accent-blue/10 border-accent-blue/30'
  return 'text-score-mid bg-score-mid/10 border-score-mid/30'
}

export function DigestCard({ article, onClick }: DigestCardProps) {
  const score = article.score ?? 0
  const timeAgo = article.published_at || article.created_at
    ? formatDistanceToNow(new Date(article.published_at || article.created_at), {
        addSuffix: true, locale: fr,
      })
    : ''

  return (
    <button
      onClick={onClick}
      className={`
        w-full text-left rounded-xl border bg-bg-surface p-4 transition-all duration-150
        hover:bg-bg-elevated hover:border-border-default hover:shadow-lg hover:-translate-y-0.5
        ${article.read_at ? 'border-border-subtle opacity-70' : 'border-border-default'}
      `}
    >
      {/* Top row: score badge + feed name */}
      <div className="flex items-center gap-2 mb-2.5">
        <span className={`inline-flex items-center justify-center w-9 h-9 rounded-full text-sm font-bold border flex-shrink-0 ${scoreColor(score)}`}>
          {score.toFixed(0)}
        </span>
        <span className="text-xs text-text-muted font-medium truncate flex-1">
          {article.feed_name}
        </span>
        {article.bookmarked && (
          <BookmarkCheck className="w-3.5 h-3.5 text-accent-blue flex-shrink-0" />
        )}
        {!article.bookmarked && article.read_at && (
          <Bookmark className="w-3.5 h-3.5 text-text-muted flex-shrink-0 opacity-40" />
        )}
      </div>

      {/* Title */}
      <h3 className={`text-sm font-semibold leading-snug mb-2 line-clamp-2 ${article.read_at ? 'text-text-secondary' : 'text-text-primary'}`}>
        {article.title}
      </h3>

      {/* First summary bullet */}
      {article.summary_bullets.length > 0 && (
        <p className="text-xs text-text-muted leading-relaxed line-clamp-2 mb-2.5">
          {article.summary_bullets[0]}
        </p>
      )}

      {/* Tags + time */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {article.tags.slice(0, 3).map(tag => (
          <span key={tag} className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-bg-elevated text-text-muted">
            {tag}
          </span>
        ))}
        {timeAgo && (
          <span className="ml-auto text-[10px] text-text-muted flex-shrink-0">{timeAgo}</span>
        )}
      </div>
    </button>
  )
}
