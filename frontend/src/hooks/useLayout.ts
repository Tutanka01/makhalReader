import { useEffect, useState } from 'react'

/**
 * Three layouts, picked by available width rather than device:
 * - `compact` (< 768px): phones. One pane at a time, bottom tab bar.
 * - `medium` (768–1023px): iPad portrait, Split View, small windows. Navigation
 *   rail; the list fills the screen and the reader takes over when an article
 *   opens, with the list available as a slide-over.
 * - `wide` (≥ 1024px): iPad landscape and desktop. Persistent list + reader.
 */
export type Layout = 'compact' | 'medium' | 'wide'

const MEDIUM_QUERY = '(min-width: 768px)'
const WIDE_QUERY = '(min-width: 1024px)'

function currentLayout(): Layout {
  if (typeof window === 'undefined' || !window.matchMedia) return 'wide'
  if (window.matchMedia(WIDE_QUERY).matches) return 'wide'
  if (window.matchMedia(MEDIUM_QUERY).matches) return 'medium'
  return 'compact'
}

export function useLayout(): Layout {
  const [layout, setLayout] = useState<Layout>(currentLayout)

  useEffect(() => {
    if (!window.matchMedia) return
    const queries = [window.matchMedia(MEDIUM_QUERY), window.matchMedia(WIDE_QUERY)]
    const update = () => setLayout(currentLayout())
    queries.forEach(q => q.addEventListener('change', update))
    update()
    return () => queries.forEach(q => q.removeEventListener('change', update))
  }, [])

  return layout
}
