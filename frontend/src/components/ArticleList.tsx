import { useCallback, useRef, useState } from 'react'
import { Virtuoso } from 'react-virtuoso'
import { Loader2, RefreshCw, ArrowUpDown, Clock, CheckCheck, Star } from 'lucide-react'
import { ArticleCard } from './ArticleCard'
import { CategoryTabs } from './CategoryTabs'
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'

interface ArticleListProps {
  feeds: Feed[]
  onSelect: (id: number) => void
  selectedId: number | null
}

export function ArticleList({ feeds, onSelect, selectedId }: ArticleListProps) {
  const { articles, loading, hasMore, fetchArticles, filter, setFilter, markAllRead } = useArticlesStore()

  const [refreshing, setRefreshing] = useState(false)
  const touchStartY = useRef(0)
  const isPulling = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleTouchStart = (e: React.TouchEvent) => {
    const scroller = containerRef.current?.querySelector('[data-test-id="virtuoso-scroller"]') as HTMLElement | null
    if (scroller?.scrollTop === 0) {
      touchStartY.current = e.touches[0].clientY
      isPulling.current = true
    }
  }

  const handleTouchEnd = async (e: React.TouchEvent) => {
    if (!isPulling.current) return
    if (e.changedTouches[0].clientY - touchStartY.current > 80) {
      setRefreshing(true)
      await fetchArticles(true)
      setRefreshing(false)
    }
    isPulling.current = false
  }

  const loadMore = useCallback(() => {
    if (!loading && hasMore) fetchArticles(false)
  }, [loading, hasMore, fetchArticles])

  const Footer = useCallback(() => {
    if (loading) return (
      <div className="flex justify-center py-6">
        <Loader2 className="w-5 h-5 animate-spin text-text-muted" />
      </div>
    )
    if (!hasMore && articles.length > 0) return (
      <div className="text-center py-6 text-xs text-text-muted">
        {articles.length} articles chargés
      </div>
    )
    return null
  }, [loading, hasMore, articles.length])

  const unreadCount = filter.status === 'unread' ? articles.length : null

  return (
    <div
      ref={containerRef}
      className="flex flex-col h-full bg-bg-base"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {refreshing && (
        <div className="flex justify-center py-2 bg-bg-base border-b border-border-subtle">
          <RefreshCw className="w-4 h-4 animate-spin text-accent-blue" />
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle flex-shrink-0">
        <span className="text-xs font-semibold text-text-secondary tracking-wide">
          MakhalReader
        </span>
        <div className="flex items-center gap-0.5">
          {/* Refresh */}
          <button
            onClick={() => fetchArticles(true)}
            className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          {/* Mark all read */}
          {filter.status !== 'read' && (
            <button
              onClick={markAllRead}
              className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
              title="Mark all as read"
            >
              <CheckCheck className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Category tabs */}
      <CategoryTabs feeds={feeds} />

      {/* Toolbar */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border-subtle flex-shrink-0 flex-wrap">
        {/* Status toggle */}
        <div className="flex rounded-md overflow-hidden border border-border-default text-xs">
          <button
            onClick={() => setFilter({ status: 'unread', bookmarked: false })}
            className={`px-2 py-1 transition-colors ${
              filter.status === 'unread' && !filter.bookmarked
                ? 'bg-accent-blue text-white'
                : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
            }`}
          >
            Unread
          </button>
          <button
            onClick={() => setFilter({ status: 'all', bookmarked: false })}
            className={`px-2 py-1 border-l border-border-default transition-colors ${
              filter.status === 'all' && !filter.bookmarked
                ? 'bg-accent-blue text-white'
                : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
            }`}
          >
            All
          </button>
        </div>

        {/* Sort toggle */}
        <button
          onClick={() => setFilter({ sort: filter.sort === 'score' ? 'date' : 'score' })}
          className="flex items-center gap-1 px-2 py-1 rounded-md border border-border-default text-xs text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
          title={filter.sort === 'score' ? 'Sorted by score — click for date' : 'Sorted by date — click for score'}
        >
          {filter.sort === 'score'
            ? <Star className="w-3 h-3" />
            : <Clock className="w-3 h-3" />
          }
          {filter.sort === 'score' ? 'Score' : 'Date'}
          <ArrowUpDown className="w-3 h-3 opacity-50" />
        </button>

        {/* Min score filter */}
        <div className="flex rounded-md overflow-hidden border border-border-default text-xs">
          {([0, 6, 8] as const).map(s => (
            <button
              key={s}
              onClick={() => setFilter({ minScore: s })}
              className={`px-2 py-1 transition-colors ${s > 0 ? 'border-l border-border-default' : ''} ${
                filter.minScore === s
                  ? s === 0 ? 'bg-bg-elevated text-text-primary'
                    : s === 6 ? 'bg-accent-yellow/20 text-accent-yellow'
                    : 'bg-accent-green/20 text-accent-green'
                  : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
              }`}
              title={s === 0 ? 'All scores' : `Score ≥ ${s}`}
            >
              {s === 0 ? 'All' : `${s}+`}
            </button>
          ))}
        </div>

        {/* Unread count */}
        {unreadCount !== null && unreadCount > 0 && (
          <span className="ml-auto text-xs text-text-muted tabular-nums">
            {unreadCount}
          </span>
        )}
      </div>

      {/* Empty state */}
      {!loading && articles.length === 0 && (
        <div className="flex flex-col items-center justify-center flex-1 text-center p-8">
          <div className="text-4xl mb-3 opacity-20">◎</div>
          <p className="text-sm font-medium text-text-secondary mb-1">Aucun article</p>
          <p className="text-xs text-text-muted leading-relaxed max-w-[200px]">
            {filter.minScore > 0
              ? `Aucun article avec score ≥ ${filter.minScore}`
              : 'Les articles apparaîtront après le prochain poll.'}
          </p>
        </div>
      )}

      {/* Article list */}
      {articles.length > 0 && (
        <Virtuoso
          className="flex-1"
          data={articles}
          endReached={loadMore}
          overscan={200}
          itemContent={(_, article) => (
            <ArticleCard
              key={article.id}
              article={article}
              selected={article.id === selectedId}
              onClick={() => onSelect(article.id)}
            />
          )}
          components={{ Footer }}
        />
      )}

      {loading && articles.length === 0 && (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
        </div>
      )}
    </div>
  )
}
