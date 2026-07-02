import { useCallback, useEffect, useRef, useState } from 'react'
import { Virtuoso } from 'react-virtuoso'
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
import { useArticlesStore } from '../store/articles'
import type { Feed } from '../types'
import { IconButton } from './ui'
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
      <div className="relative flex flex-shrink-0 items-center gap-1 border-b border-border-subtle bg-bg-surface/95 px-2 py-2">
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
              className={`inline-flex h-8 items-center justify-center rounded-md border text-xs font-medium transition-all duration-150 ${
                confirmingReadAll
                  ? 'w-auto gap-1 border-accent-red/40 bg-accent-red/12 px-2 text-accent-red'
                  : 'w-8 border-transparent bg-transparent text-text-muted hover:bg-bg-hover hover:text-text-primary'
              }`}
              title={confirmingReadAll ? 'Confirmer' : 'Tout marquer comme lu'}
            >
              <CheckCheck className="h-4 w-4 flex-shrink-0" />
              {confirmingReadAll && <span>Confirmer</span>}
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
    </div>
  )
}
