import { useCallback, useEffect, useRef, useState } from 'react'
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso'
import {
  CheckCheck,
  Inbox,
  ListFilter,
  Loader2,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'
import { ArticleCard } from './ArticleCard'
import { FilterPopover } from './FilterPopover'
import { MissionSelect, filterForMission, missionFromFilter, type MissionKey } from './MissionSelect'
import { isScorePending, useArticlesStore } from '../store/articles'
import type { Feed } from '../types'
import { IconButton, SignalBars } from './ui'
import { LENS_FILTERS } from '../lenses'

interface ArticleListProps {
  feeds: Feed[]
  onSelect: (id: number) => void
  selectedId: number | null
}

export function ArticleList({ feeds, onSelect, selectedId }: ArticleListProps) {
  const { articles, loading, hasMore, fetchArticles, filter, setFilter, markAllRead, searchArticles, clearSearch, searchResults, isSearching } = useArticlesStore()

  const [refreshing, setRefreshing] = useState(false)
  const [confirmingReadAll, setConfirmingReadAll] = useState(false)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const filterButtonRef = useRef<HTMLDivElement>(null)

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
  const virtuosoRef = useRef<VirtuosoHandle>(null)

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

  const activeLens = LENS_FILTERS.find(lens => lens.key === filter.lens) || LENS_FILTERS[0]
  const activeMission = missionFromFilter(filter)
  const selectMission = (mission: MissionKey) => {
    setFilter(filterForMission(mission))
  }

  const isSearchActive = Boolean(searchQuery.trim())
  const displayedArticles = isSearchActive ? searchResults : articles
  const pendingCount = displayedArticles.filter(isScorePending).length

  // Keep the selected card on screen when j/k moves the selection.
  useEffect(() => {
    if (selectedId === null) return
    const index = displayedArticles.findIndex(a => a.id === selectedId)
    if (index >= 0) virtuosoRef.current?.scrollIntoView({ index, behavior: 'smooth' })
  }, [selectedId]) // only on selection change, not when the page grows

  // Filters diverging from the plain mission presets (category scope, read-status
  // override) are only visible inside the popover — surface them on the trigger.
  const hasCustomFilters = Boolean(filter.category) || (!filter.bookmarked && filter.status !== 'unread')

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

      {/* Toolbar — mission selector + list actions */}
      <div className="relative z-10 flex h-[52px] flex-shrink-0 items-center gap-1 border-b border-border-subtle bg-bg-surface px-2">
        <MissionSelect
          value={activeMission}
          count={displayedArticles.length}
          onChange={selectMission}
        />
        <div className="flex flex-shrink-0 items-center gap-0.5">
          <IconButton
            onClick={openSearch}
            icon={Search}
            label="Rechercher  /"
            active={searchOpen}
          />
          <IconButton
            onClick={() => fetchArticles(true)}
            icon={RefreshCw}
            label="Actualiser"
          />
          {filter.status !== 'read' && (
            <button
              onClick={handleMarkAllRead}
              className={`inline-flex h-8 items-center justify-center rounded-md border text-xs font-medium transition-all duration-150 touch:h-10 ${
                confirmingReadAll
                  ? 'w-auto gap-1 border-accent-red/40 bg-accent-red/12 px-2 text-accent-red'
                  : 'w-8 border-transparent bg-transparent text-text-muted hover:bg-bg-hover hover:text-text-primary touch:w-10'
              }`}
              title={confirmingReadAll ? 'Confirmer : tout marquer comme lu' : 'Tout marquer comme lu'}
              aria-label={confirmingReadAll ? 'Confirmer : tout marquer comme lu' : 'Tout marquer comme lu'}
            >
              <CheckCheck className="h-4 w-4 flex-shrink-0" />
              {confirmingReadAll && <span>Tout lire ?</span>}
            </button>
          )}
          <div ref={filterButtonRef} className="relative">
            <IconButton
              onClick={() => setFiltersOpen(v => !v)}
              icon={ListFilter}
              label={filtersOpen ? 'Masquer les filtres' : 'Afficher les filtres'}
              active={filtersOpen || hasCustomFilters}
            />
            {hasCustomFilters && !filtersOpen && (
              <span className="pointer-events-none absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-accent-blue" />
            )}
          </div>
        </div>

        <FilterPopover
          feeds={feeds}
          open={filtersOpen}
          onClose={() => setFiltersOpen(false)}
          anchorRef={filterButtonRef}
        />
      </div>

      {/* Search bar */}
      {searchOpen && (
        <div className="flex flex-shrink-0 items-center gap-2 border-b border-border-subtle bg-bg-base px-3 py-2">
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md bg-bg-elevated px-2.5 focus-within:ring-1 focus-within:ring-accent-blue/40">
            <Search className="h-3.5 w-3.5 flex-shrink-0 text-text-muted" />
            <input
              ref={searchInputRef}
              type="search"
              enterKeyHint="search"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') closeSearch() }}
              placeholder="Titre, source, tag…"
              aria-label="Rechercher dans les articles"
              className="h-8 min-w-0 flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted outline-none touch:h-10 [&::-webkit-search-cancel-button]:hidden"
            />
            {isSearchActive && (
              <span className="flex-shrink-0 text-xs tabular-nums text-text-muted">
                {isSearching ? '…' : `${searchResults.length}`}
              </span>
            )}
          </div>
          <IconButton onClick={closeSearch} icon={X} label="Fermer la recherche" />
        </div>
      )}

      {/* Scoring progress — explains the sweeping meters on pending cards */}
      {pendingCount > 0 && !isSearching && (
        <div
          className="flex flex-shrink-0 items-center gap-2 border-b border-border-subtle bg-accent-blue/[0.04] px-4 py-1.5 text-[11px] text-text-muted"
          role="status"
        >
          <span className="text-accent-blue"><SignalBars lit={0} compact scanning /></span>
          <span className="truncate" title="Les scores s’affichent dès qu’ils arrivent, sans recharger.">
            {pendingCount} article{pendingCount > 1 ? 's' : ''} en cours d’évaluation par l’IA
          </span>
        </div>
      )}

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
          ref={virtuosoRef}
          className="flex-1 overscroll-contain"
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
    </div>
  )
}
