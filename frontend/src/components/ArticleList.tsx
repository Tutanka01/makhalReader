import { useCallback, useEffect, useRef, useState } from 'react'
import { Virtuoso } from 'react-virtuoso'
import { Loader2, RefreshCw, ArrowUpDown, BarChart2, Clock, CheckCheck, Star, Search, X, Settings, Sparkles, LogOut, Network, UserCircle2, BookOpen } from 'lucide-react'
import { ArticleCard } from './ArticleCard'
import { CategoryTabs } from './CategoryTabs'
import { DigestView } from './DigestView'
import { StatsView } from './StatsView'
import ResearchDigestView from './ResearchDigestView'
import LitReviewView from './LitReviewView'
import { useArticlesStore } from '../store/articles'
import type { ContribType, Feed } from '../types'

interface ArticleListProps {
  feeds: Feed[]
  onSelect: (id: number) => void
  selectedId: number | null
  onOpenFeedManager: () => void
  onOpenProfile: () => void
  currentView: 'feed' | 'digest' | 'stats' | 'research' | 'litreview'
  onViewChange: (v: 'feed' | 'digest' | 'stats' | 'research' | 'litreview') => void
  onLogout: () => void
}

export function ArticleList({ feeds, onSelect, selectedId, onOpenFeedManager, onOpenProfile, currentView, onViewChange, onLogout }: ArticleListProps) {
  const { articles, loading, hasMore, fetchArticles, filter, setFilter, markAllRead, searchArticles, clearSearch, searchResults, isSearching } = useArticlesStore()

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
    clearSearch()
  }, [clearSearch])

  // Debounced backend search
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    if (!searchQuery.trim()) {
      clearSearch()
      return
    }
    searchTimer.current = setTimeout(() => searchArticles(searchQuery.trim()), 300)
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current) }
  }, [searchQuery])

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

  useEffect(() => {
    fetchArticles(true)
  }, [fetchArticles])

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

  const isSearchActive = Boolean(searchQuery.trim())
  const displayedArticles = isSearchActive ? searchResults : articles

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

      {/* Toolbar — feed filters */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle flex-shrink-0 bg-bg-surface/50 flex-wrap gap-2">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => fetchArticles(true)}
            className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          
          {filter.status !== 'read' && (
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

          <div className="w-[1px] h-4 bg-border-default mx-1" />

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
        </div>

        <div className="flex items-center gap-1.5">
          {/* Sort toggle */}
          <button
            onClick={() => {
              const order: Array<'score' | 'date' | 'cited_by_corpus'> = ['score', 'date', 'cited_by_corpus']
              const idx = order.indexOf(filter.sort as any)
              setFilter({ sort: order[(idx + 1) % order.length] })
            }}
            className="flex items-center gap-1 px-2 py-1 rounded-md border border-border-default text-xs text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
            title={
              filter.sort === 'score' ? 'Sorted by score' :
              filter.sort === 'cited_by_corpus' ? 'Sorted by most cited in corpus' :
              'Sorted by date'
            }
          >
            {filter.sort === 'score' ? <Star className="w-3 h-3" /> :
             filter.sort === 'cited_by_corpus' ? <Network className="w-3 h-3" /> :
             <Clock className="w-3 h-3" />
            }
            {filter.sort === 'score' ? 'Score' :
             filter.sort === 'cited_by_corpus' ? 'Most cited' :
             'Date'}
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
            <span className="ml-2 text-xs text-text-muted tabular-nums">
              {unreadCount}
            </span>
          )}
        </div>
      </div>

      {/* Research filters — only in feed view */}
      {currentView === 'feed' && <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border-subtle flex-shrink-0 flex-wrap bg-bg-surface/40">
        {/* Contribution type select */}
        <select
          value={filter.contributionType ?? ''}
          onChange={e => setFilter({ contributionType: (e.target.value || null) as ContribType | null })}
          className="text-xs px-2 py-1 rounded-md border border-border-default bg-bg-surface text-text-muted hover:text-text-primary focus:outline-none cursor-pointer"
          title="Filter by contribution type"
        >
          <option value="">All types</option>
          <option value="method">Method</option>
          <option value="survey">Survey</option>
          <option value="benchmark">Benchmark</option>
          <option value="empirical">Empirical</option>
          <option value="theory">Theory</option>
          <option value="position">Position</option>
          <option value="tool">Tool</option>
          <option value="tutorial">Tutorial</option>
          <option value="news">News</option>
          <option value="other">Other</option>
        </select>

        {/* ARISE toggle */}
        <button
          onClick={() => setFilter({ ariseOnly: !filter.ariseOnly })}
          className={`flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-medium transition-colors ${
            filter.ariseOnly
              ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
              : 'border-border-default text-text-muted hover:text-text-primary hover:bg-bg-hover'
          }`}
          title="Show only ARISE-relevant RE documents (elicitation, extraction, method)"
        >
          ARISE
        </button>

        {/* Clear research filters shortcut */}
        {(filter.contributionType || filter.ariseOnly) && (
          <button
            onClick={() => setFilter({ contributionType: null, ariseOnly: false })}
            className="ml-auto flex items-center gap-0.5 px-1.5 py-1 rounded-md text-xs text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
            title="Clear research filters"
          >
            <X className="w-3 h-3" />
            Clear
          </button>
        )}
      </div>}

      {/* Feed view: empty state + list */}
      {currentView === 'feed' && (
        <>
          {/* Empty state */}
          {!loading && !isSearching && displayedArticles.length === 0 && (
            <div className="flex flex-col items-center justify-center flex-1 text-center p-8">
              <div className="text-4xl mb-3 opacity-20">◎</div>
              <p className="text-sm font-medium text-text-secondary mb-1">
                {isSearchActive ? 'Aucun résultat' : 'Aucun article'}
              </p>
              <p className="text-xs text-text-muted leading-relaxed max-w-[200px]">
                {isSearchActive
                  ? `Aucun article ne correspond à "${searchQuery}"`
                  : filter.ariseOnly
                  ? 'No ARISE-relevant RE articles found. Papers are classified automatically after ingestion.'
                  : filter.contributionType
                  ? `No articles with contribution type "${filter.contributionType}" found.`
                  : filter.minScore > 0
                  ? `Aucun article avec score ≥ ${filter.minScore}`
                  : 'Les articles apparaîtront après le prochain poll.'}
              </p>
            </div>
          )}
          {isSearching && (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-text-muted" />
            </div>
          )}

          {/* Article list */}
          {!isSearching && displayedArticles.length > 0 && (
            <Virtuoso
              className="flex-1"
              data={displayedArticles}
              endReached={isSearchActive ? undefined : loadMore}
              overscan={200}
              itemContent={(_, article) => (
                <ArticleCard
                  key={article.id}
                  article={article}
                  selected={article.id === selectedId}
                  onClick={() => onSelect(article.id)}
                />
              )}
              components={{ Footer: isSearchActive ? () => null : Footer }}
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
