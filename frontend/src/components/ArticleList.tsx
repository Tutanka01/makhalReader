import { useCallback, useEffect, useRef, useState } from 'react'
import { Virtuoso } from 'react-virtuoso'
import { Loader2, RefreshCw, ArrowUpDown, Clock, CheckCheck, Star, Search, X, Settings, Sparkles, LogOut } from 'lucide-react'
import { ArticleCard } from './ArticleCard'
import { CategoryTabs } from './CategoryTabs'
import { DigestView } from './DigestView'
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'

interface ArticleListProps {
  feeds: Feed[]
  onSelect: (id: number) => void
  selectedId: number | null
  onOpenFeedManager: () => void
  currentView: 'feed' | 'digest'
  onViewChange: (v: 'feed' | 'digest') => void
  onLogout: () => void
}

export function ArticleList({ feeds, onSelect, selectedId, onOpenFeedManager, currentView, onViewChange, onLogout }: ArticleListProps) {
  const { articles, loading, hasMore, fetchArticles, filter, setFilter, markAllRead } = useArticlesStore()

  const [refreshing, setRefreshing] = useState(false)
  const [confirmingReadAll, setConfirmingReadAll] = useState(false)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const handleMarkAllRead = useCallback(() => {
    if (!confirmingReadAll) {
      setConfirmingReadAll(true)
      confirmTimerRef.current = setTimeout(() => setConfirmingReadAll(false), 3000)
    } else {
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
      setConfirmingReadAll(false)
      markAllRead()
    }
  }, [confirmingReadAll, markAllRead])

  useEffect(() => () => {
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
  }, [])

  const openSearch = useCallback(() => {
    setSearchOpen(true)
    setTimeout(() => searchInputRef.current?.focus(), 50)
  }, [])

  const closeSearch = useCallback(() => {
    setSearchOpen(false)
    setSearchQuery('')
  }, [])

  // `/` key opens search (when not in an input)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key === '/') {
        e.preventDefault()
        openSearch()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [openSearch])

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

  const q = searchQuery.toLowerCase().trim()
  const displayedArticles = q
    ? articles.filter(a =>
        a.title.toLowerCase().includes(q) ||
        a.feed_name.toLowerCase().includes(q) ||
        a.tags.some(t => t.toLowerCase().includes(q))
      )
    : articles

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
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-text-secondary tracking-wide">
            MakhalReader
          </span>
          {/* Digest toggle */}
          <button
            onClick={() => onViewChange(currentView === 'digest' ? 'feed' : 'digest')}
            className={`flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[11px] font-medium transition-colors ${
              currentView === 'digest'
                ? 'bg-accent-blue/15 text-accent-blue'
                : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
            }`}
            title="Digest du jour"
          >
            <Sparkles className="w-3 h-3" />
            Digest
          </button>
        </div>
        <div className="flex items-center gap-0.5">
          {/* Search — hidden in digest */}
          {currentView === 'feed' && (
            <button
              onClick={openSearch}
              className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
              title="Search  /"
            >
              <Search className="w-3.5 h-3.5" />
            </button>
          )}
          {/* Refresh — hidden in digest */}
          {currentView === 'feed' && (
            <button
              onClick={() => fetchArticles(true)}
              className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
              title="Refresh"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          )}
          {/* Mark all read */}
          {currentView === 'feed' && filter.status !== 'read' && (
            <button
              onClick={handleMarkAllRead}
              className={`flex items-center gap-1 rounded-md transition-all duration-150 text-xs font-medium ${
                confirmingReadAll
                  ? 'px-2 py-1 bg-red-500/15 text-red-400 hover:bg-red-500/25 ring-1 ring-red-500/40'
                  : 'p-1.5 text-text-muted hover:bg-bg-hover hover:text-text-primary'
              }`}
              title={confirmingReadAll ? 'Tap again to confirm' : 'Mark all as read'}
            >
              <CheckCheck className="w-3.5 h-3.5 flex-shrink-0" />
              {confirmingReadAll && <span>Confirm?</span>}
            </button>
          )}
          {/* Feed manager */}
          <button
            onClick={onOpenFeedManager}
            className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
            title="Gérer les feeds"
          >
            <Settings className="w-3.5 h-3.5" />
          </button>
          {/* Logout */}
          <button
            onClick={async () => {
              await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
              onLogout()
            }}
            className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-red-400"
            title="Se déconnecter"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Digest view — replaces list when active */}
      {currentView === 'digest' && (
        <DigestView onSelect={onSelect} />
      )}

      {/* Search bar */}
      {currentView === 'feed' && searchOpen && (
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle bg-bg-surface flex-shrink-0">
          <Search className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') closeSearch() }}
            placeholder="Search title, feed, tag…"
            className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted outline-none"
          />
          {searchQuery && (
            <span className="text-xs text-text-muted tabular-nums flex-shrink-0">
              {displayedArticles.length}
            </span>
          )}
          <button onClick={closeSearch} className="p-0.5 rounded text-text-muted hover:text-text-primary">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Category tabs — only in feed view */}
      {currentView === 'feed' && <CategoryTabs feeds={feeds} />}

      {/* Toolbar — only in feed view */}
      {currentView === 'feed' && <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border-subtle flex-shrink-0 flex-wrap">
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
      </div>}

      {/* Feed view: empty state + list */}
      {currentView === 'feed' && (
        <>
          {/* Empty state */}
          {!loading && displayedArticles.length === 0 && (
            <div className="flex flex-col items-center justify-center flex-1 text-center p-8">
              <div className="text-4xl mb-3 opacity-20">◎</div>
              <p className="text-sm font-medium text-text-secondary mb-1">
                {q ? 'Aucun résultat' : 'Aucun article'}
              </p>
              <p className="text-xs text-text-muted leading-relaxed max-w-[200px]">
                {q
                  ? `Aucun article ne correspond à "${searchQuery}"`
                  : filter.minScore > 0
                  ? `Aucun article avec score ≥ ${filter.minScore}`
                  : 'Les articles apparaîtront après le prochain poll.'}
              </p>
            </div>
          )}

          {/* Article list */}
          {displayedArticles.length > 0 && (
            <Virtuoso
              className="flex-1"
              data={displayedArticles}
              endReached={q ? undefined : loadMore}
              overscan={200}
              itemContent={(_, article) => (
                <ArticleCard
                  key={article.id}
                  article={article}
                  selected={article.id === selectedId}
                  onClick={() => onSelect(article.id)}
                />
              )}
              components={{ Footer: q ? () => null : Footer }}
            />
          )}

          {loading && articles.length === 0 && (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
            </div>
          )}
        </>
      )}
    </div>
  )
}
