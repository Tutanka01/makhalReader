import { useState, useEffect, useCallback } from 'react'
import { Filter, Layers, Loader2, ExternalLink } from 'lucide-react'
import type { HighlightManagerItem } from '../types'
import { VALID_THESIS_SECTIONS } from '../types'

export default function HighlightManager() {
  const [items, setItems] = useState<HighlightManagerItem[]>([])
  const [loading, setLoading] = useState(true)
  const [filterSection, setFilterSection] = useState<string | null>(null)
  const [filterOpen, setFilterOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkSection, setBulkSection] = useState<string | null>(null)
  const [updating, setUpdating] = useState(false)

  const fetchHighlights = useCallback(async () => {
    setLoading(true)
    try {
      const params = filterSection ? `?thesis_section=${encodeURIComponent(filterSection)}` : ''
      const res = await fetch(`/api/research/highlights/all${params}`, { credentials: 'include' })
      if (res.ok) {
        setItems(await res.json())
      }
    } catch {
    } finally {
      setLoading(false)
    }
  }, [filterSection])

  useEffect(() => {
    fetchHighlights()
  }, [fetchHighlights])

  const handleBulkUpdate = async () => {
    if (!bulkSection || selectedIds.size < 1) return
    setUpdating(true)
    try {
      await fetch('/api/research/highlights/bulk-update', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          highlight_ids: Array.from(selectedIds),
          thesis_section: bulkSection,
        }),
      })
      setSelectedIds(new Set())
      setBulkSection(null)
      await fetchHighlights()
    } catch {
    } finally {
      setUpdating(false)
    }
  }

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const unassigned = items.filter(h => !h.thesis_section)
  const assigned = items.filter(h => h.thesis_section)

  return (
    <div className="h-full flex flex-col bg-bg-base">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-default">
        <div className="flex items-center gap-2.5">
          <Layers className="w-4 h-4 text-accent" />
          <h1 className="text-sm font-semibold text-text-primary">Highlight Manager</h1>
          {loading && <Loader2 className="w-3 h-3 animate-spin text-text-muted" />}
        </div>
        <div className="flex items-center gap-2">
          {/* Filter */}
          <div className="relative">
            <button
              onClick={() => setFilterOpen(v => !v)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg bg-bg-surface border border-border-default text-text-secondary hover:border-border-strong transition-colors"
            >
              <Filter size={12} />
              {filterSection || 'All sections'}
            </button>
            {filterOpen && (
              <div className="absolute right-0 mt-1 w-48 bg-bg-surface border border-border-default rounded-lg shadow-xl z-10 max-h-60 overflow-y-auto">
                <button
                  onClick={() => { setFilterSection(null); setFilterOpen(false) }}
                  className={`w-full text-left text-xs px-3 py-2 transition-colors ${!filterSection ? 'bg-accent/5 text-accent font-medium' : 'text-text-secondary hover:bg-bg-hover'}`}
                >
                  All sections
                </button>
                <button
                  onClick={() => { setFilterSection('__unassigned__'); setFilterOpen(false) }}
                  className={`w-full text-left text-xs px-3 py-2 transition-colors ${filterSection === '__unassigned__' ? 'bg-accent/5 text-accent font-medium' : 'text-text-secondary hover:bg-bg-hover'}`}
                >
                  Unassigned
                </button>
                {VALID_THESIS_SECTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => { setFilterSection(s); setFilterOpen(false) }}
                    className={`w-full text-left text-xs px-3 py-2 transition-colors ${filterSection === s ? 'bg-accent/5 text-accent font-medium' : 'text-text-secondary hover:bg-bg-hover'}`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Bulk action bar */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-accent/5 border border-accent/20">
            <span className="text-xs text-text-secondary">{selectedIds.size} selected</span>
            <select
              value={bulkSection ?? ''}
              onChange={e => setBulkSection(e.target.value || null)}
              className="text-xs bg-bg-surface border border-border-default rounded px-2 py-1 text-text-primary"
            >
              <option value="">Move to section…</option>
              {VALID_THESIS_SECTIONS.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button
              onClick={handleBulkUpdate}
              disabled={!bulkSection || updating}
              className="text-xs px-2.5 py-1 rounded bg-accent text-white font-semibold disabled:opacity-40 hover:bg-accent-strong transition-colors"
            >
              {updating ? 'Moving…' : 'Move'}
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-xs px-2 py-1 text-text-muted hover:text-text-secondary transition-colors"
            >
              Cancel
            </button>
          </div>
        )}

        {/* Highlights list */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-text-muted">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-20 text-text-muted text-sm">
            No highlights found.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map(h => (
              <div
                key={h.id}
                onClick={() => toggleSelect(h.id)}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedIds.has(h.id)
                    ? 'bg-accent/5 border-accent/30'
                    : 'bg-bg-surface border-border-default hover:border-border-strong'
                }`}
              >
                <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 mt-0.5 ${
                  selectedIds.has(h.id) ? 'bg-accent border-accent' : 'border-border-strong'
                }`}>
                  {selectedIds.has(h.id) && <span className="text-[10px] text-white leading-none">✓</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                      h.thesis_section
                        ? 'bg-accent/10 text-accent'
                        : 'bg-warning/10 text-warning'
                    }`}>
                      {h.thesis_section || 'Unassigned'}
                    </span>
                    {h.article_score != null && (
                      <span className="text-[10px] font-mono text-text-muted">Score {h.article_score.toFixed(1)}</span>
                    )}
                    <span className="text-[10px] text-text-muted">{new Date(h.created_at).toLocaleDateString()}</span>
                  </div>
                  <p className="text-xs text-text-primary leading-relaxed line-clamp-2 mb-1">
                    "{h.selected_text}"
                  </p>
                  <a
                    href={h.article_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                    className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
                  >
                    <ExternalLink size={10} />
                    {h.article_title}
                  </a>
                  {h.note && (
                    <p className="text-[11px] text-text-muted mt-1 italic">{h.note}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
