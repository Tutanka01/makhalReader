import { useEffect, useRef, useState } from 'react'
import { X, ChevronDown } from 'lucide-react'
import type { Highlight } from '../types'
import { VALID_THESIS_SECTIONS } from '../types'

const COLORS = [
  { id: 'yellow', label: 'Jaune',  dot: '#B45309', bg: 'var(--warning-bg)', border: 'var(--warning)' },
  { id: 'green',  label: 'Vert',   dot: '#0F7B6C', bg: 'var(--success-bg)',  border: 'var(--success)' },
  { id: 'blue',   label: 'Bleu',   dot: '#2F6FED', bg: 'var(--accent-light)', border: 'var(--accent)' },
  { id: 'purple', label: 'Violet', dot: '#6B4FBB', bg: 'var(--purple-bg)', border: 'var(--purple)' },
] as const

interface HighlightPopoverProps {
  /** Viewport x-center, top and bottom of the selection */
  position: { x: number; top: number; bottom: number }
  selectedText: string
  /** If set, popover operates in edit mode for an existing highlight */
  highlight?: Highlight
  onSave: (color: string, note: string, thesisSection?: string | null) => void
  onClose: () => void
}

const WIDTH = 260
const MARGIN = 10
const GAP = 8

export function HighlightPopover({ position, selectedText, highlight, onSave, onClose }: HighlightPopoverProps) {
  const [color, setColor] = useState<string>(highlight?.color ?? 'yellow')
  const [note, setNote] = useState(highlight?.note ?? '')
  const [showNote, setShowNote] = useState(!!highlight?.note)
  const [thesisSection, setThesisSection] = useState<string | null>(highlight?.thesis_section ?? null)
  const [sectionOpen, setSectionOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const sectionRef = useRef<HTMLDivElement>(null)

  const isEdit = !!highlight

  // Compute height dynamically
  const baseHeight = isEdit ? 130 : 88
  const noteHeight = showNote ? 96 : 0
  const popoverHeight = baseHeight + noteHeight

  const vw = window.innerWidth
  const vh = window.innerHeight

  let left = position.x - WIDTH / 2
  left = Math.max(MARGIN, Math.min(left, vw - WIDTH - MARGIN))

  let top = position.top - popoverHeight - GAP
  let below = false
  if (top < MARGIN) {
    top = position.bottom + GAP
    below = true
  }
  top = Math.max(MARGIN, Math.min(top, vh - popoverHeight - MARGIN))

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [onClose])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { e.stopPropagation(); onClose() }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [onClose])

  // Close section dropdown on outside click
  useEffect(() => {
    if (!sectionOpen) return
    function handleClick(e: MouseEvent) {
      if (sectionRef.current && !sectionRef.current.contains(e.target as Node)) {
        setSectionOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [sectionOpen])

  const selectedColor = COLORS.find(c => c.id === color)!

  const sectionLabel = thesisSection ?? 'Assigner à une section…'

  return (
    <div
      ref={ref}
      className="fixed z-[60] select-none"
      style={{ left, top, width: WIDTH }}
      onMouseDown={e => e.stopPropagation()}
    >
      <div
        className="absolute left-1/2 -translate-x-1/2 w-0 h-0"
        style={
          below
            ? { top: -6, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderBottom: '6px solid var(--border)' }
            : { bottom: -6, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '6px solid var(--border)' }
        }
      />

      <div className="rounded-xl shadow-2xl overflow-hidden bg-bg-surface border border-border-default">
        <div className="px-3 pt-3 pb-2">
          <p className="text-[11px] text-text-muted line-clamp-1 italic">
            « {selectedText.slice(0, 60)}{selectedText.length > 60 ? '…' : ''} »
          </p>
        </div>

        {/* Thesis Section dropdown (edit mode) */}
        {isEdit && (
          <div className="px-3 pb-2" ref={sectionRef}>
            <button
              onClick={() => setSectionOpen(v => !v)}
              className="w-full flex items-center justify-between gap-1.5 text-[11px] bg-bg-base border border-border-default rounded-lg px-2.5 py-1.5 text-text-secondary hover:text-text-primary transition-colors"
            >
              <span className={thesisSection ? 'text-text-primary' : 'text-text-muted'}>
                {sectionLabel}
              </span>
              <ChevronDown size={12} className={`transition-transform ${sectionOpen ? 'rotate-180' : ''}`} />
            </button>
            {sectionOpen && (
              <div className="absolute left-3 right-3 mt-1 bg-bg-surface border border-border-default rounded-lg shadow-xl z-10 max-h-48 overflow-y-auto">
                <button
                  onClick={() => { setThesisSection(null); setSectionOpen(false) }}
                  className="w-full text-left text-[11px] px-2.5 py-1.5 text-text-muted hover:bg-bg-hover transition-colors"
                >
                  Aucune
                </button>
                {VALID_THESIS_SECTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => { setThesisSection(s); setSectionOpen(false) }}
                    className={`w-full text-left text-[11px] px-2.5 py-1.5 transition-colors ${
                      thesisSection === s ? 'text-accent font-medium bg-accent/5' : 'text-text-secondary hover:bg-bg-hover'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Color row */}
        <div className="flex items-center gap-2 px-3 pb-3">
          {COLORS.map((c) => (
            <button
              key={c.id}
              onClick={() => setColor(c.id)}
              title={c.label}
              className="relative w-7 h-7 rounded-full flex-shrink-0 transition-transform duration-150"
              style={{
                background: c.bg,
                border: `2px solid ${c.border}`,
                transform: color === c.id ? 'scale(1.2)' : 'scale(1)',
                boxShadow: color === c.id ? `0 0 0 2px ${c.dot}40` : 'none',
              }}
            >
              {color === c.id && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-2 h-2 rounded-full" style={{ background: c.dot }} />
                </div>
              )}
            </button>
          ))}

          <div className="flex-1" />

          {/* Note toggle */}
          <button
            onClick={() => setShowNote(v => !v)}
            className="text-[11px] text-text-muted hover:text-text-secondary transition-colors px-1.5 py-0.5 rounded"
          >
            {showNote ? '— Note' : '+ Note'}
          </button>

          <button
            onClick={onClose}
            className="p-0.5 rounded text-text-muted hover:text-text-secondary transition-colors"
          >
            <X className="w-3 h-3" />
          </button>
        </div>

        {/* Note field */}
        {showNote && (
          <div className="px-3 pb-2">
            <textarea
              autoFocus={!isEdit}
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Ajouter une note…"
              rows={3}
              className="w-full text-xs bg-bg-base border border-border-default rounded-lg px-2.5 py-2 text-text-primary placeholder-text-muted resize-none focus:outline-none focus:border-accent/50"
            />
          </div>
        )}

        {/* Save button */}
        <button
          onClick={() => onSave(color, note, thesisSection)}
          className="w-full py-2.5 text-xs font-semibold transition-colors"
          style={{
            background: selectedColor.bg,
            color: selectedColor.dot,
            borderTop: `1px solid ${selectedColor.border}`,
          }}
        >
          {isEdit ? 'Enregistrer' : 'Surligner'}
        </button>
      </div>
    </div>
  )
}
