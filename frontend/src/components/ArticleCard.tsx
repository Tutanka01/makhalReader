import { useRef, useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Bookmark, BookmarkCheck } from 'lucide-react'
import type { ArticleListItem } from '../types'
import { ScoreBar } from './ScoreBar'
import { useArticlesStore } from '../store/articles'

interface ArticleCardProps {
  article: ArticleListItem
  selected: boolean
  onClick: () => void
}

const SWIPE_THRESHOLD = 60

export function ArticleCard({ article, selected, onClick }: ArticleCardProps) {
  const { markRead, toggleBookmark } = useArticlesStore()

  const touchStartX = useRef<number>(0)
  const touchStartY = useRef<number>(0)
  const [swipeOffset, setSwipeOffset] = useState(0)
  const [swiping, setSwiping] = useState(false)

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
    setSwiping(true)
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!swiping) return
    const dx = e.touches[0].clientX - touchStartX.current
    const dy = Math.abs(e.touches[0].clientY - touchStartY.current)
    if (dy > 20) {
      setSwiping(false)
      setSwipeOffset(0)
      return
    }
    setSwipeOffset(dx)
  }

  const handleTouchEnd = () => {
    if (swipeOffset < -SWIPE_THRESHOLD) {
      markRead(article.id)
    } else if (swipeOffset > SWIPE_THRESHOLD) {
      toggleBookmark(article.id)
    }
    setSwiping(false)
    setSwipeOffset(0)
  }

  const relativeDate = article.published_at
    ? formatDistanceToNow(new Date(article.published_at), { addSuffix: true })
    : formatDistanceToNow(new Date(article.created_at), { addSuffix: true })

  const isRead = Boolean(article.read_at)

  return (
    <div
      className={`
        relative overflow-hidden cursor-pointer select-none
        border-b border-border-subtle
        transition-colors duration-150
        ${selected
          ? 'bg-bg-elevated border-l-2 border-l-accent-blue'
          : 'hover:bg-bg-hover'
        }
        ${isRead ? 'opacity-60' : ''}
      `}
      style={{
        transform: swipeOffset !== 0 ? `translateX(${swipeOffset}px)` : undefined,
        transition: swiping ? 'none' : 'transform 0.2s ease',
      }}
      onClick={onClick}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Swipe left indicator (mark read) */}
      {swipeOffset < -20 && (
        <div className="absolute right-0 top-0 bottom-0 flex items-center px-4 bg-accent-green text-white text-xs font-medium">
          Read
        </div>
      )}
      {/* Swipe right indicator (bookmark) */}
      {swipeOffset > 20 && (
        <div className="absolute left-0 top-0 bottom-0 flex items-center px-4 bg-accent-blue text-white text-xs font-medium">
          <Bookmark className="w-4 h-4" />
        </div>
      )}

      <div className="p-3">
        <ScoreBar score={article.score} />

        {/* Tags */}
        {article.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {article.tags.slice(0, 3).map(tag => (
              <span
                key={tag}
                className="px-1.5 py-0.5 bg-bg-elevated rounded text-xs text-text-muted font-medium"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Title */}
        <h3
          className={`
            text-sm font-semibold leading-snug mb-1 line-clamp-2
            ${isRead ? 'text-text-secondary' : 'text-text-primary'}
          `}
        >
          {article.title}
        </h3>

        {/* Summary bullets */}
        {article.summary_bullets.length > 0 && (
          <ul className="mb-2 space-y-0.5">
            {article.summary_bullets.slice(0, 2).map((bullet, i) => (
              <li key={i} className="text-xs text-text-secondary leading-relaxed flex gap-1">
                <span className="text-text-muted flex-shrink-0">•</span>
                <span className="line-clamp-1">{bullet}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Meta */}
        <div className="flex items-center justify-between mt-1">
          <div className="flex items-center gap-2 text-xs text-text-muted min-w-0">
            <span className="truncate font-medium">{article.feed_name}</span>
            <span className="flex-shrink-0">·</span>
            <span className="flex-shrink-0">{relativeDate}</span>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0 ml-2">
            {article.bookmarked && (
              <BookmarkCheck className="w-3.5 h-3.5 text-accent-blue" />
            )}
            {article.extraction_failed && (
              <span className="text-xs text-accent-yellow" title="Extraction failed">⚠</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
