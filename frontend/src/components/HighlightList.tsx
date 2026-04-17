import { X, Trash2 } from 'lucide-react'
import type { Highlight } from '../types'

const COLOR_CLASSES: Record<string, string> = {
  yellow: 'bg-yellow-400/25 border-yellow-400/50',
  green:  'bg-green-400/20  border-green-400/45',
  blue:   'bg-blue-400/20   border-blue-400/50',
  purple: 'bg-purple-400/20 border-purple-400/45',
}

const SWATCH_CLASSES: Record<string, string> = {
  yellow: 'bg-yellow-400',
  green:  'bg-green-400',
  blue:   'bg-blue-400',
  purple: 'bg-purple-400',
}

interface HighlightListProps {
  highlights: Highlight[]
  onDelete: (id: number) => void
  onClose: () => void
  onScrollTo?: (highlight: Highlight) => void
}

export function HighlightList({ highlights, onDelete, onClose, onScrollTo }: HighlightListProps) {
  return (
    <div className="absolute inset-y-0 right-0 w-72 bg-bg-surface border-l border-border-subtle z-40 flex flex-col shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle flex-shrink-0">
        <h3 className="text-sm font-semibold text-text-primary">
          Surlignages{highlights.length > 0 ? ` (${highlights.length})` : ''}
        </h3>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-bg-hover text-text-muted hover:text-text-secondary transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-2">
        {highlights.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-text-muted text-sm px-4 text-center">
            <p>Aucun surlignage.</p>
            <p className="text-xs mt-1 text-text-muted">Sélectionnez du texte pour surligner.</p>
          </div>
        ) : (
          <ul className="space-y-2 px-3">
            {highlights.map((h) => (
              <li
                key={h.id}
                className={`group relative rounded-lg border px-3 py-2.5 cursor-pointer transition-opacity hover:opacity-90 ${COLOR_CLASSES[h.color] ?? ''}`}
                onClick={() => onScrollTo?.(h)}
              >
                {/* Color swatch + text */}
                <div className="flex items-start gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 mt-1 ${SWATCH_CLASSES[h.color] ?? 'bg-text-muted'}`} />
                  <p className="text-xs text-text-secondary leading-relaxed line-clamp-3">
                    {h.selected_text}
                  </p>
                </div>

                {/* Note if present */}
                {h.note && (
                  <p className="text-xs text-text-muted mt-1.5 pl-4 italic line-clamp-2">
                    {h.note}
                  </p>
                )}

                {/* Delete button */}
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(h.id) }}
                  className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-bg-elevated text-text-muted hover:text-accent-red transition-all"
                  title="Supprimer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
