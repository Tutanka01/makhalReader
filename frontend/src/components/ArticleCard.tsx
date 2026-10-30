import { useRef, useState } from 'react'
import { AlertTriangle, BookmarkCheck, BookmarkMinus, Check, ThumbsDown, ThumbsUp } from 'lucide-react'
import type { ArticleListItem } from '../types'
import { useArticlesStore } from '../store/articles'
import { ScoreBadge } from './ui'
import { ArticleLensStrip } from './ArticleLenses'
import { articleDate, longDate, shortAgo } from '../format'

interface ArticleCardProps {
  article: ArticleListItem
  selected: boolean
  onClick: () => void
}

/** Horizontal travel needed to commit a swipe action. */
const SWIPE_THRESHOLD = 72
/** Movement before deciding whether the gesture is a swipe or a scroll. */
const INTENT_SLOP = 8

export function ArticleCard({ article, selected, onClick }: ArticleCardProps) {
  const markRead = useArticlesStore(s => s.markRead)
  const toggleBookmark = useArticlesStore(s => s.toggleBookmark)

  const start = useRef({ x: 0, y: 0 })
  const intent = useRef<'undecided' | 'swipe' | 'scroll'>('undecided')
  const [offset, setOffset] = useState(0)
  const [dragging, setDragging] = useState(false)

  const handleTouchStart = (e: React.TouchEvent) => {
    start.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    intent.current = 'undecided'
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    const dx = e.touches[0].clientX - start.current.x
    const dy = e.touches[0].clientY - start.current.y
    if (intent.current === 'undecided') {
      if (Math.abs(dx) < INTENT_SLOP && Math.abs(dy) < INTENT_SLOP) return
      // Lock the gesture: a mostly vertical move belongs to the list scroll.
      intent.current = Math.abs(dx) > Math.abs(dy) * 1.4 ? 'swipe' : 'scroll'
      if (intent.current === 'swipe') setDragging(true)
    }
    if (intent.current === 'swipe') {
      // Resist past the threshold so the card never flies off screen.
      const limit = SWIPE_THRESHOLD * 1.6
      setOffset(Math.max(-limit, Math.min(limit, dx)))
    }
  }

  const handleTouchEnd = () => {
    if (intent.current === 'swipe') {
      if (offset <= -SWIPE_THRESHOLD && !article.read_at) markRead(article.id)
      else if (offset >= SWIPE_THRESHOLD) toggleBookmark(article.id)
    }
    intent.current = 'undecided'
    setDragging(false)
    setOffset(0)
  }

  const date = articleDate(article)
  const isRead = Boolean(article.read_at)
  const excerpt = article.summary_bullets[0]
  const tags = article.tags.slice(0, 2)
  const armed = Math.abs(offset) >= SWIPE_THRESHOLD

  return (
    <div className="relative overflow-hidden border-b border-border-subtle">
      {/* Action revealed behind the card while swiping */}
      {offset !== 0 && (
        <div
          aria-hidden
          className={`
            absolute inset-0 flex items-center px-5 text-xs font-semibold transition-colors
            ${offset > 0
              ? `justify-start ${armed ? 'bg-accent-blue/25' : 'bg-accent-blue/10'} text-accent-blue`
              : `justify-end ${armed ? 'bg-accent-green/25' : 'bg-accent-green/10'} text-accent-green`}
          `}
        >
          {offset > 0 ? (
            <span className="flex items-center gap-1.5">
              {article.bookmarked ? <BookmarkMinus className="h-4 w-4" /> : <BookmarkCheck className="h-4 w-4" />}
              {article.bookmarked ? 'Retirer des favoris' : 'Favori'}
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              {isRead ? 'Déjà lu' : 'Marquer lu'}
              <Check className="h-4 w-4" />
            </span>
          )}
        </div>
      )}

      <div
        role="button"
        tabIndex={0}
        aria-current={selected || undefined}
        onClick={onClick}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onClick()
          }
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onTouchCancel={handleTouchEnd}
        className={`
          group relative cursor-pointer select-none px-4 py-3.5 outline-offset-[-2px]
          ${selected ? 'bg-bg-surface' : 'bg-bg-base hover:bg-bg-surface'}
        `}
        style={{
          transform: offset ? `translateX(${offset}px)` : undefined,
          transition: dragging ? 'none' : 'transform 220ms cubic-bezier(0.16, 1, 0.3, 1), background-color 150ms',
        }}
      >
        {selected && (
          <span aria-hidden className="absolute inset-y-2 left-0 w-[3px] rounded-r-full bg-accent-blue" />
        )}

        <div className="mb-1.5 flex items-center gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2 text-xs leading-5">
            {!isRead && (
              <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent-blue" aria-label="Non lu" />
            )}
            <span className={`truncate font-medium ${isRead ? 'text-text-muted' : 'text-text-secondary'}`}>
              {article.feed_name}
            </span>
            <time
              dateTime={date.toISOString()}
              title={longDate(date)}
              className="flex-shrink-0 tabular-nums text-text-muted"
            >
              {shortAgo(date)}
            </time>
          </div>
          <ScoreBadge score={article.score} status={article.scoring_status} compact />
        </div>

        <h3
          className={`
            line-clamp-3 text-[15px] font-semibold leading-snug
            ${isRead ? 'text-text-muted' : 'text-text-primary'}
          `}
        >
          {article.title}
        </h3>

        {excerpt && (
          <p className={`mt-1.5 line-clamp-2 text-[13px] leading-relaxed ${isRead ? 'text-text-muted' : 'text-text-secondary'}`}>
            {excerpt}
          </p>
        )}

        <div className="mt-2.5 flex min-w-0 items-center gap-1.5">
          <ArticleLensStrip article={article} max={1} compact skipFresh className="flex-shrink-0" />
          <div className="flex min-w-0 flex-1 gap-1.5 overflow-hidden">
            {tags.map(tag => (
              <span
                key={tag}
                className="truncate rounded bg-bg-elevated px-1.5 py-0.5 text-[11px] text-text-muted"
              >
                {tag}
              </span>
            ))}
          </div>
          <div className="ml-auto flex flex-shrink-0 items-center gap-2 text-text-muted">
            {article.user_feedback === 1 && (
              <ThumbsUp className="h-3.5 w-3.5 text-accent-green" aria-label="Aimé" />
            )}
            {article.user_feedback === -1 && (
              <ThumbsDown className="h-3.5 w-3.5 text-accent-red" aria-label="Pas aimé" />
            )}
            {article.bookmarked && (
              <BookmarkCheck className="h-3.5 w-3.5 text-accent-blue" aria-label="Favori" />
            )}
            {article.extraction_failed && (
              <span title="Contenu non extrait : ouvre l’original">
                <AlertTriangle className="h-3.5 w-3.5 text-accent-yellow" aria-label="Extraction échouée" />
              </span>
            )}
            {article.reading_time ? (
              <span className="text-[11px] tabular-nums">{article.reading_time} min</span>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
