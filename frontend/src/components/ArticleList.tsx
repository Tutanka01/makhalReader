import { useCallback, useRef, useState } from 'react'
import { Virtuoso } from 'react-virtuoso'
import { Loader2, RefreshCw } from 'lucide-react'
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
  const { articles, loading, hasMore, fetchArticles } = useArticlesStore()

  // Pull-to-refresh state
  const [refreshing, setRefreshing] = useState(false)
  const touchStartY = useRef(0)
  const isPulling = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleTouchStart = (e: React.TouchEvent) => {
    const scrollTop = containerRef.current?.querySelector('[data-test-id="virtuoso-scroller"]')
    if ((scrollTop as HTMLElement)?.scrollTop === 0) {
      touchStartY.current = e.touches[0].clientY
      isPulling.current = true
    }
  }

  const handleTouchEnd = async (e: React.TouchEvent) => {
    if (!isPulling.current) return
    const dy = e.changedTouches[0].clientY - touchStartY.current
    if (dy > 80) {
      setRefreshing(true)
      await fetchArticles(true)
      setRefreshing(false)
    }
    isPulling.current = false
  }

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      fetchArticles(false)
    }
  }, [loading, hasMore, fetchArticles])

  const Footer = useCallback(() => {
    if (loading) {
      return (
        <div className="flex justify-center py-6">
          <Loader2 className="w-5 h-5 animate-spin text-text-muted" />
        </div>
      )
    }
    if (!hasMore && articles.length > 0) {
      return (
        <div className="text-center py-6 text-xs text-text-muted">
          All articles loaded
        </div>
      )
    }
    return null
  }, [loading, hasMore, articles.length])

  return (
    <div
      ref={containerRef}
      className="flex flex-col h-full bg-bg-base"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Pull-to-refresh indicator */}
      {refreshing && (
        <div className="flex justify-center py-2 bg-bg-base border-b border-border-subtle">
          <RefreshCw className="w-4 h-4 animate-spin text-accent-blue" />
        </div>
      )}

      {/* Category tabs */}
      <CategoryTabs feeds={feeds} />

      {/* Article count */}
      <div className="px-3 py-1.5 border-b border-border-subtle">
        <span className="text-xs text-text-muted">
          {articles.length} article{articles.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Empty state */}
      {!loading && articles.length === 0 && (
        <div className="flex flex-col items-center justify-center flex-1 text-center p-8">
          <div className="text-4xl mb-3">📭</div>
          <p className="text-text-secondary font-medium mb-1">No articles</p>
          <p className="text-xs text-text-muted">
            Articles will appear here once feeds are polled.
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

      {/* Initial loading state */}
      {loading && articles.length === 0 && (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
        </div>
      )}
    </div>
  )
}
