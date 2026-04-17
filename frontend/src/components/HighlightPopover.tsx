import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

const COLORS = [
  { id: 'yellow', label: 'Jaune',  dot: '#EAB308', bg: 'rgba(234,179,8,0.25)', border: 'rgba(234,179,8,0.6)' },
  { id: 'green',  label: 'Vert',   dot: '#22C55E', bg: 'rgba(34,197,94,0.2)',  border: 'rgba(34,197,94,0.5)' },
  { id: 'blue',   label: 'Bleu',   dot: '#60A5FA', bg: 'rgba(96,165,250,0.2)', border: 'rgba(96,165,250,0.5)' },
  { id: 'purple', label: 'Violet', dot: '#A855F7', bg: 'rgba(168,85,247,0.2)', border: 'rgba(168,85,247,0.5)' },
] as const

interface HighlightPopoverProps {
  /** Viewport x-center, top and bottom of the selection */
  position: { x: number; top: number; bottom: number }
  selectedText: string
  onSave: (color: string, note: string) => void
  onClose: () => void
}

const WIDTH = 260
const MARGIN = 10
const GAP = 8   // gap between selection and popover

export function HighlightPopover({ position, selectedText, onSave, onClose }: HighlightPopoverProps) {
  const [color, setColor] = useState<string>('yellow')
  const [note, setNote] = useState('')
  const [showNote, setShowNote] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Compute height dynamically
  const baseHeight = 88
  const noteHeight = showNote ? 96 : 0
  const popoverHeight = baseHeight + noteHeight

  const vw = window.innerWidth
  const vh = window.innerHeight

  // Horizontal: centered on selection, clamped to viewport
  let left = position.x - WIDTH / 2
  left = Math.max(MARGIN, Math.min(left, vw - WIDTH - MARGIN))

  // Vertical: prefer ABOVE the selection
  let top = position.top - popoverHeight - GAP
  let below = false
  if (top < MARGIN) {
    // Flip below the selection
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

  const selectedColor = COLORS.find(c => c.id === color)!

  return (
    <div
      ref={ref}
      className="fixed z-[60] select-none"
      style={{ left, top, width: WIDTH }}
      onMouseDown={e => e.stopPropagation()}
    >
      {/* Arrow indicator */}
      <div
        className="absolute left-1/2 -translate-x-1/2 w-0 h-0"
        style={
          below
            ? { top: -6, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderBottom: '6px solid #2A3341' }
            : { bottom: -6, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '6px solid #2A3341' }
        }
      />

      {/* Card */}
      <div className="rounded-xl shadow-2xl overflow-hidden" style={{ background: '#1E2430', border: '1px solid #2A3341' }}>
        {/* Selected text preview */}
        <div className="px-3 pt-3 pb-2">
          <p className="text-[11px] text-text-muted line-clamp-1 italic">
            « {selectedText.slice(0, 60)}{selectedText.length > 60 ? '…' : ''} »
          </p>
        </div>

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
              autoFocus
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Ajouter une note…"
              rows={3}
              className="w-full text-xs bg-[#161B22] border border-[#2A3341] rounded-lg px-2.5 py-2 text-text-primary placeholder-text-muted resize-none focus:outline-none focus:border-accent-blue/50"
            />
          </div>
        )}

        {/* Save button */}
        <button
          onClick={() => onSave(color, note)}
          className="w-full py-2.5 text-xs font-semibold transition-colors"
          style={{
            background: selectedColor.bg,
            color: selectedColor.dot,
            borderTop: `1px solid ${selectedColor.border}`,
          }}
        >
          Surligner
        </button>
      </div>
    </div>
  )
}
