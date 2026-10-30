import { useEffect, useRef, useState } from 'react'
import { ALargeSmall, Minus, Plus } from 'lucide-react'
import { IconButton } from './ui'

export type ReaderFont = 'serif' | 'sans'

export const FONT_SIZE_MIN = 14
export const FONT_SIZE_MAX = 24
export const FONT_SIZE_DEFAULT = 18

const FONT_SIZE_KEY = 'makhal_reader_font_size'
const FONT_FAMILY_KEY = 'makhal_reader_font_family'

export function getSavedFontSize(): number {
  try {
    const n = parseInt(localStorage.getItem(FONT_SIZE_KEY) || '', 10)
    if (n >= FONT_SIZE_MIN && n <= FONT_SIZE_MAX) return n
  } catch {}
  return FONT_SIZE_DEFAULT
}

export function saveFontSize(size: number) {
  try { localStorage.setItem(FONT_SIZE_KEY, String(size)) } catch {}
}

export function getSavedFont(): ReaderFont {
  try {
    return localStorage.getItem(FONT_FAMILY_KEY) === 'sans' ? 'sans' : 'serif'
  } catch {
    return 'serif'
  }
}

export function saveFont(font: ReaderFont) {
  try { localStorage.setItem(FONT_FAMILY_KEY, font) } catch {}
}

interface ReadingSettingsProps {
  fontSize: number
  onFontSize: (size: number) => void
  font: ReaderFont
  onFont: (font: ReaderFont) => void
}

/** "Aa" popover: text size and typeface for the reader, remembered per device. */
export function ReadingSettings({ fontSize, onFontSize, font, onFont }: ReadingSettingsProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); setOpen(false) }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown, true)
    }
  }, [open])

  const step = (delta: number) => onFontSize(Math.max(FONT_SIZE_MIN, Math.min(FONT_SIZE_MAX, fontSize + delta)))

  return (
    <div ref={rootRef} className="relative">
      <IconButton
        onClick={() => setOpen(v => !v)}
        icon={ALargeSmall}
        label="Affichage du texte"
        active={open}
        aria-expanded={open}
        aria-haspopup="dialog"
      />
      {open && (
        <div
          role="dialog"
          aria-label="Affichage du texte"
          className="animate-pop-in absolute right-0 top-full z-40 mt-2 w-64 rounded-xl border border-border-default bg-bg-surface p-3 shadow-elevated"
        >
          <p className="mb-2 text-xs font-medium text-text-muted">Taille du texte</p>
          <div className="flex items-center gap-2">
            <IconButton
              icon={Minus}
              label="Réduire le texte"
              onClick={() => step(-1)}
              disabled={fontSize <= FONT_SIZE_MIN}
              className="bg-bg-elevated"
            />
            <div className="relative h-1.5 flex-1 rounded-full bg-bg-elevated">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-accent-blue"
                style={{ width: `${((fontSize - FONT_SIZE_MIN) / (FONT_SIZE_MAX - FONT_SIZE_MIN)) * 100}%` }}
              />
            </div>
            <IconButton
              icon={Plus}
              label="Agrandir le texte"
              onClick={() => step(1)}
              disabled={fontSize >= FONT_SIZE_MAX}
              className="bg-bg-elevated"
            />
          </div>
          <p className="mt-1.5 text-center text-[11px] tabular-nums text-text-muted">{fontSize} px</p>

          <p className="mb-2 mt-3 text-xs font-medium text-text-muted">Police</p>
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-bg-elevated p-1" role="radiogroup" aria-label="Police">
            {([
              ['serif', 'Lora', 'font-serif'],
              ['sans', 'Inter', 'font-sans'],
            ] as const).map(([value, name, cls]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={font === value}
                onClick={() => onFont(value)}
                className={`
                  flex h-9 items-center justify-center gap-2 rounded-md text-sm transition-colors touch:h-11
                  ${font === value ? 'bg-bg-surface text-text-primary shadow-sm' : 'text-text-muted hover:text-text-primary'}
                `}
              >
                <span className={`${cls} text-base`}>Aa</span>
                <span className="text-xs">{name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
