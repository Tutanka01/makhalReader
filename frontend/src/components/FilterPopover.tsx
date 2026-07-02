import { useEffect, useRef } from 'react'
import { ArrowUpDown, BookOpen, Clock, Clock3, Flame, MessageSquare, Radar, Star, Wrench, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { CategoryTabs } from './CategoryTabs'
import { useArticlesStore } from '../store/articles'
import type { Feed, ReadingLensKey } from '../types'
import { LENS_FILTERS, lensToneClass } from '../lenses'
import { Eyebrow } from './ui'

const LENS_ICONS: Record<ReadingLensKey, LucideIcon> = {
  all: Radar,
  latest: Clock3,
  opinions: MessageSquare,
  debates: Flame,
  practical: Wrench,
  deep: BookOpen,
}

interface FilterPopoverProps {
  feeds: Feed[]
  open: boolean
  onClose: () => void
  /** Element allowed to keep the popover open when clicked (its toggle button). */
  anchorRef: React.RefObject<HTMLElement | null>
}

export function FilterPopover({ feeds, open, onClose, anchorRef }: FilterPopoverProps) {
  const { filter, setFilter } = useArticlesStore()
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (panelRef.current?.contains(target)) return
      if (anchorRef.current?.contains(target)) return
      onClose()
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose, anchorRef])

  if (!open) return null

  const selectLens = (lens: ReadingLensKey) => {
    setFilter({
      lens,
      minScore: 0,
      sort: lens === 'latest' || lens === 'opinions' || lens === 'debates' ? 'date' : 'score',
    })
  }

  return (
    <div
      ref={panelRef}
      className="absolute right-2 top-full z-30 mt-1.5 w-[min(360px,calc(100vw-16px))] rounded-lg border border-border-default bg-bg-surface p-3 shadow-xl"
    >
      <div className="mb-3 flex items-center justify-between">
        <Eyebrow>Filtres</Eyebrow>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fermer les filtres"
          className="rounded p-0.5 text-text-muted transition-colors hover:text-text-primary"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="space-y-4">
        <section>
          <p className="mb-1.5 text-[11px] font-medium text-text-muted">Catégories</p>
          <CategoryTabs feeds={feeds} className="rounded-md border border-border-subtle bg-bg-base/65 p-1" />
        </section>

        <section>
          <p className="mb-1.5 text-[11px] font-medium text-text-muted">Statut, tri et score</p>
          <div className="flex flex-wrap items-center gap-1.5">
            <div className="flex rounded-md bg-bg-elevated/70 p-0.5 text-xs">
              {(['unread', 'all', 'read'] as const).map(status => (
                <button
                  key={status}
                  onClick={() => setFilter({ status, bookmarked: false })}
                  className={`rounded px-2 py-1 transition-colors ${
                    filter.status === status && !filter.bookmarked
                      ? 'bg-bg-surface text-text-primary shadow-sm'
                      : 'text-text-muted hover:bg-bg-hover hover:text-text-primary'
                  }`}
                >
                  {status === 'unread' ? 'Non lus' : status === 'read' ? 'Lus' : 'Tous'}
                </button>
              ))}
            </div>

            <button
              onClick={() => setFilter({ sort: filter.sort === 'score' ? 'date' : 'score' })}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
              title={filter.sort === 'score' ? 'Tri par score, cliquer pour date' : 'Tri par date, cliquer pour score'}
            >
              {filter.sort === 'score'
                ? <Star className="h-3 w-3" />
                : <Clock className="h-3 w-3" />
              }
              {filter.sort === 'score' ? 'Score' : 'Date'}
              <ArrowUpDown className="h-3 w-3 opacity-50" />
            </button>

            <div className="flex rounded-md bg-bg-elevated/70 p-0.5 text-xs">
              {([0, 6, 8] as const).map(s => (
                <button
                  key={s}
                  onClick={() => setFilter({ minScore: s })}
                  className={`rounded px-2 py-1 transition-colors ${
                    filter.minScore === s
                      ? s === 0 ? 'bg-bg-surface text-text-primary shadow-sm'
                        : s === 6 ? 'bg-accent-yellow/20 text-accent-yellow'
                        : 'bg-accent-green/20 text-accent-green'
                      : 'text-text-muted hover:bg-bg-hover hover:text-text-primary'
                  }`}
                  title={s === 0 ? 'Tous les scores' : `Score ≥ ${s}`}
                >
                  {s === 0 ? 'Tous' : `${s}+`}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section>
          <p className="mb-1.5 text-[11px] font-medium text-text-muted">Intention de lecture</p>
          <div className="flex flex-wrap gap-1">
            {LENS_FILTERS.map(lens => {
              const Icon = LENS_ICONS[lens.key]
              const active = filter.lens === lens.key
              return (
                <button
                  key={lens.key}
                  type="button"
                  onClick={() => selectLens(lens.key)}
                  title={lens.description}
                  className={`
                    inline-flex h-7 flex-shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs font-medium
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
        </section>
      </div>
    </div>
  )
}
