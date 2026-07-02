import { useCallback, useEffect, useRef, useState } from 'react'
import { Virtuoso } from 'react-virtuoso'
import { Loader2, RefreshCw, ArrowUpDown, BarChart2, Clock, Clock3, CheckCheck, Star, Search, X, Settings2, Sparkles, LogOut, Newspaper, Inbox, SlidersHorizontal, Radar, MessageSquare, Flame, Wrench, BookOpen } from 'lucide-react'
import { ArticleCard } from './ArticleCard'
import { CategoryTabs } from './CategoryTabs'
import { StatsView } from './StatsView'
import { useArticlesStore } from '../store/articles'
import type { Feed, ReadingLensKey } from '../types'
import type { Theme } from '../theme'
import { IconButton, SegmentedControl } from './ui'
import { ThemeToggle } from './ThemeToggle'
import { LENS_FILTERS, lensToneClass } from '../lenses'

interface ArticleListProps {
  feeds: Feed[]
  onSelect: (id: number) => void
  selectedId: number | null
  onOpenFeedManager: () => void
  currentView: 'briefing' | 'feed' | 'stats'
  onViewChange: (v: 'briefing' | 'feed' | 'stats') => void
  onLogout: () => void
  theme: Theme
  onToggleTheme: () => void
}

export function ArticleList({ feeds, onSelect, selectedId, onOpenFeedManager, currentView, onViewChange, onLogout, theme, onToggleTheme }: ArticleListProps) {
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
  const activeLens = LENS_FILTERS.find(lens => lens.key === filter.lens) || LENS_FILTERS[0]
  const lensIcons = {
    all: Radar,
    latest: Clock3,
    opinions: MessageSquare,
    debates: Flame,
    practical: Wrench,
    deep: BookOpen,
  }
  const selectLens = (lens: ReadingLensKey) => {
    setFilter({
      lens,
      minScore: 0,
      sort: lens === 'latest' || lens === 'opinions' || lens === 'debates' ? 'date' : 'score',
    })
  }
  const viewOptions = [
    { value: 'briefing' as const, label: 'Briefing', icon: Sparkles },
    { value: 'feed' as const, label: 'Articles', icon: Newspaper },
    { value: 'stats' as const, label: 'Stats', icon: BarChart2 },
  ]

  const isSearchActive = Boolean(searchQuery.trim())
  const displayedArticles = isSearchActive ? searchResults : articles
  // The article list is the persistent sidebar navigation — it stays visible for both
  // the feed and the briefing tabs, and only steps aside for the dedicated Stats view.
  const showArticleList = currentView !== 'stats'

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
      <div className="border-b border-border-subtle bg-bg-surface/95 px-3 py-3 flex-shrink-0">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent-blue/12 text-accent-blue">
                <Inbox className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-sm font-semibold leading-5 text-text-primary">MakhalReader</h1>
                <p className="truncate text-[11px] text-text-muted">Moins lire. Plus savoir.</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
          {/* Search — hidden only in Stats */}
          {showArticleList && (
            <IconButton
              onClick={openSearch}
              icon={Search}
              label="Rechercher  /"
            />
          )}
          {/* Refresh — hidden only in Stats */}
          {showArticleList && (
            <IconButton
              onClick={() => fetchArticles(true)}
              icon={RefreshCw}
              label="Actualiser"
            />
          )}
          {/* Mark all read */}
          {showArticleList && filter.status !== 'read' && (
            <button
              onClick={handleMarkAllRead}
              className={`flex items-center gap-1 rounded-md transition-all duration-150 text-xs font-medium ${
                confirmingReadAll
                  ? 'h-8 px-2 border border-accent-red/40 bg-accent-red/12 text-accent-red'
                  : 'h-8 w-8 justify-center border border-transparent bg-transparent text-text-muted hover:bg-bg-hover hover:text-text-primary'
              }`}
              title={confirmingReadAll ? 'Confirmer' : 'Tout marquer comme lu'}
            >
              <CheckCheck className="w-4 h-4 flex-shrink-0" />
              {confirmingReadAll && <span>Confirmer</span>}
            </button>
          )}
          {/* Feed manager */}
          <IconButton
            onClick={onOpenFeedManager}
            icon={Settings2}
            label="Gérer les feeds"
          />
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          {/* Logout */}
          <IconButton
            onClick={async () => {
              await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
              onLogout()
            }}
            icon={LogOut}
            label="Se déconnecter"
            className="hover:text-accent-red"
          />
          </div>
        </div>

        <SegmentedControl
          value={currentView}
          options={viewOptions}
          onChange={onViewChange}
          className="grid w-full grid-cols-3"
        />
      </div>

      {/* Stats view — replaces list when active */}
      {currentView === 'stats' && (
        <StatsView onClose={() => onViewChange('feed')} />
      )}

      {/* Search bar */}
      {showArticleList && searchOpen && (
        <div className="flex items-center gap-2 border-b border-border-subtle bg-bg-base px-3 py-2.5 flex-shrink-0">
          <Search className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') closeSearch() }}
            placeholder="Titre, source, tag..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted outline-none"
          />
          {isSearchActive && (
            <span className="text-xs text-text-muted tabular-nums flex-shrink-0">
              {isSearching ? '…' : `${searchResults.length}`}
            </span>
          )}
          <button onClick={closeSearch} className="p-0.5 rounded text-text-muted hover:text-text-primary">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Category tabs — hidden only in Stats */}
      {showArticleList && <CategoryTabs feeds={feeds} />}

      {/* Reading lenses */}
      {showArticleList && (
        <div className="border-b border-border-subtle bg-bg-base/88 px-3 py-2.5 flex-shrink-0">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">
              <Radar className="h-3.5 w-3.5" />
              Radar
            </div>
            <span className="max-w-[150px] truncate text-[11px] text-text-muted" title={activeLens.description}>
              {activeLens.shortLabel}
            </span>
          </div>
          <div className="scrollbar-hide flex gap-1.5 overflow-x-auto">
            {LENS_FILTERS.map(lens => {
              const Icon = lensIcons[lens.key]
              const active = filter.lens === lens.key
              return (
                <button
                  key={lens.key}
                  type="button"
                  onClick={() => selectLens(lens.key)}
                  title={lens.description}
                  className={`
                    inline-flex h-8 flex-shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs font-medium
                    transition-colors duration-150
                    ${active
                      ? lensToneClass(lens.tone)
                      : 'border-transparent bg-transparent text-text-muted hover:bg-bg-hover hover:text-text-primary'
                    }
                  `}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{lens.shortLabel}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Toolbar — hidden only in Stats */}
      {showArticleList && <div className="flex flex-col gap-2 border-b border-border-subtle bg-bg-base/70 px-3 py-2.5 flex-shrink-0">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Triage
          </div>
          {unreadCount !== null && unreadCount > 0 && (
          <span className="rounded bg-bg-elevated px-2 py-0.5 text-[11px] text-text-muted tabular-nums">
              {unreadCount} à lire
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
        {/* Status toggle */}
        <div className="flex rounded-md overflow-hidden bg-bg-elevated/70 p-0.5 text-xs">
          <button
            onClick={() => setFilter({ status: 'unread', bookmarked: false })}
            className={`rounded px-2 py-1 transition-colors ${
              filter.status === 'unread' && !filter.bookmarked
                ? 'bg-accent-blue text-bg-base font-semibold'
                : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
            }`}
          >
            Non lus
          </button>
          <button
            onClick={() => setFilter({ status: 'all', bookmarked: false })}
            className={`rounded px-2 py-1 transition-colors ${
              filter.status === 'all' && !filter.bookmarked
                ? 'bg-accent-blue text-bg-base font-semibold'
                : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
            }`}
          >
            Tous
          </button>
        </div>

        {/* Sort toggle */}
        <button
          onClick={() => setFilter({ sort: filter.sort === 'score' ? 'date' : 'score' })}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
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
        <div className="flex rounded-md overflow-hidden bg-bg-elevated/70 p-0.5 text-xs">
          {([0, 6, 8] as const).map(s => (
            <button
              key={s}
              onClick={() => setFilter({ minScore: s })}
              className={`rounded px-2 py-1 transition-colors ${
                filter.minScore === s
                  ? s === 0 ? 'bg-bg-elevated text-text-primary'
                    : s === 6 ? 'bg-accent-yellow/20 text-accent-yellow'
                    : 'bg-accent-green/20 text-accent-green'
                  : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
              }`}
              title={s === 0 ? 'All scores' : `Score ≥ ${s}`}
            >
              {s === 0 ? 'Tous' : `${s}+`}
            </button>
          ))}
        </div>
        </div>
      </div>}

      {/* Article list — empty state + list, hidden only in Stats */}
      {showArticleList && (
        <>
          {/* Empty state */}
          {!loading && !isSearching && displayedArticles.length === 0 && (
            <div className="flex flex-col items-center justify-center flex-1 text-center p-8">
              <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-md bg-bg-surface text-text-muted">
                <Inbox className="h-5 w-5" />
              </div>
              <p className="text-sm font-medium text-text-secondary mb-1">
                {isSearchActive ? 'Aucun résultat' : 'Aucun article'}
              </p>
              <p className="text-xs text-text-muted leading-relaxed max-w-[200px]">
                {isSearchActive
                  ? `Aucun article ne correspond à "${searchQuery}"`
                  : filter.lens !== 'all'
                  ? `Aucun article dans ${activeLens.label.toLowerCase()}`
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
