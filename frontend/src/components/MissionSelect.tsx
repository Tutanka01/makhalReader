import { useEffect, useRef, useState } from 'react'
import {
  BookOpen,
  Bookmark,
  Check,
  ChevronDown,
  Clock3,
  Flame,
  Inbox,
  Star,
  Target,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ArticleFilter } from '../types'

export type MissionKey =
  | 'inbox'
  | 'priority'
  | 'decide'
  | 'latest'
  | 'debates'
  | 'practical'
  | 'deep'
  | 'saved'

type MissionTone = 'blue' | 'green' | 'yellow' | 'red' | 'neutral'

export interface MissionOption {
  key: MissionKey
  label: string
  description: string
  icon: LucideIcon
  tone: MissionTone
}

export const MISSION_OPTIONS: MissionOption[] = [
  { key: 'inbox', label: 'Inbox', description: 'Tout ce qui reste à trier', icon: Inbox, tone: 'blue' },
  { key: 'priority', label: 'Signal fort', description: 'Score 8+ à lire en premier', icon: Target, tone: 'green' },
  { key: 'decide', label: 'À décider', description: 'Score 6+ qui mérite un coup d’œil', icon: Star, tone: 'yellow' },
  { key: 'latest', label: 'Nouveau', description: 'Fraîcheur avant scoring sévère', icon: Clock3, tone: 'blue' },
  { key: 'debates', label: 'Débats', description: 'Angles tranchés et backlash', icon: Flame, tone: 'red' },
  { key: 'practical', label: 'Pratique', description: 'Tutos, retours terrain, postmortems', icon: Wrench, tone: 'green' },
  { key: 'deep', label: 'Deep', description: 'Papiers, architecture, technique dense', icon: BookOpen, tone: 'neutral' },
  { key: 'saved', label: 'Favoris', description: 'Articles gardés sous la main', icon: Bookmark, tone: 'blue' },
]

/** Filter preset applied when a mission is selected. */
export function filterForMission(mission: MissionKey): Partial<ArticleFilter> {
  const base = { category: null, bookmarked: false, status: 'unread' as const }
  switch (mission) {
    case 'inbox':
      return { ...base, lens: 'all', minScore: 0, sort: 'score' }
    case 'priority':
      return { ...base, lens: 'all', minScore: 8, sort: 'score' }
    case 'decide':
      return { ...base, lens: 'all', minScore: 6, sort: 'score' }
    case 'latest':
      return { ...base, lens: 'latest', minScore: 0, sort: 'date' }
    case 'debates':
      return { ...base, lens: 'debates', minScore: 0, sort: 'date' }
    case 'practical':
      return { ...base, lens: 'practical', minScore: 0, sort: 'score' }
    case 'deep':
      return { ...base, lens: 'deep', minScore: 0, sort: 'score' }
    case 'saved':
      return { category: null, bookmarked: true, status: 'all', lens: 'all', minScore: 0, sort: 'score' }
  }
}

/** Reverse mapping: which mission best describes the current filter state. */
export function missionFromFilter(filter: ArticleFilter): MissionKey {
  if (filter.bookmarked) return 'saved'
  if (filter.lens === 'latest') return 'latest'
  if (filter.lens === 'debates') return 'debates'
  if (filter.lens === 'practical') return 'practical'
  if (filter.lens === 'deep') return 'deep'
  if (filter.minScore >= 8) return 'priority'
  if (filter.minScore >= 6) return 'decide'
  return 'inbox'
}

function toneTextClass(tone: MissionTone) {
  switch (tone) {
    case 'green': return 'text-accent-green'
    case 'yellow': return 'text-accent-yellow'
    case 'red': return 'text-accent-red'
    case 'neutral': return 'text-text-secondary'
    default: return 'text-accent-blue'
  }
}

interface MissionSelectProps {
  value: MissionKey
  count: number
  onChange: (mission: MissionKey) => void
}

export function MissionSelect({ value, count, onChange }: MissionSelectProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const active = MISSION_OPTIONS.find(m => m.key === value) ?? MISSION_OPTIONS[0]
  const ActiveIcon = active.icon

  return (
    <div ref={rootRef} className="relative min-w-0 flex-1">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={active.description}
        className={`
          flex h-9 w-full min-w-0 items-center gap-2 rounded-md px-2 text-left
          transition-colors duration-150
          ${open ? 'bg-bg-hover' : 'hover:bg-bg-hover'}
        `}
      >
        <span className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-bg-elevated ${toneTextClass(active.tone)}`}>
          <ActiveIcon className="h-3.5 w-3.5" />
        </span>
        <span className="truncate text-sm font-semibold text-text-primary">{active.label}</span>
        <span className="flex-shrink-0 text-xs tabular-nums text-text-muted">{count}</span>
        <ChevronDown
          className={`ml-auto h-3.5 w-3.5 flex-shrink-0 text-text-muted transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Mission de lecture"
          className="absolute left-0 top-full z-30 mt-1.5 w-72 rounded-lg border border-border-default bg-bg-surface p-1 shadow-xl"
        >
          {MISSION_OPTIONS.map(mission => {
            const Icon = mission.icon
            const selected = mission.key === value
            return (
              <button
                key={mission.key}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => { onChange(mission.key); setOpen(false) }}
                className={`
                  flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left
                  transition-colors duration-150
                  ${selected ? 'bg-bg-elevated' : 'hover:bg-bg-hover'}
                `}
              >
                <span className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-bg-elevated ${toneTextClass(mission.tone)}`}>
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold text-text-primary">{mission.label}</span>
                  <span className="block truncate text-[11px] text-text-muted">{mission.description}</span>
                </span>
                {selected && <Check className="h-3.5 w-3.5 flex-shrink-0 text-accent-blue" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
