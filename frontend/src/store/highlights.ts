import { create } from 'zustand'
import type { Highlight } from '../types'

interface HighlightCreate {
  selected_text: string
  prefix_context: string
  suffix_context: string
  color: string
  note?: string
}

interface HighlightUpdate {
  color?: string
  note?: string
}

interface HighlightsState {
  /** Highlights keyed by article_id */
  highlights: Record<number, Highlight[]>

  fetchHighlights: (articleId: number) => Promise<void>
  createHighlight: (articleId: number, data: HighlightCreate) => Promise<Highlight>
  updateHighlight: (articleId: number, id: number, data: HighlightUpdate) => Promise<void>
  deleteHighlight: (articleId: number, id: number) => Promise<void>
}

export const useHighlightsStore = create<HighlightsState>((set, get) => ({
  highlights: {},

  async fetchHighlights(articleId) {
    const res = await fetch(`/api/articles/${articleId}/highlights`, { credentials: 'include' })
    if (!res.ok) return
    const data: Highlight[] = await res.json()
    set((s) => ({ highlights: { ...s.highlights, [articleId]: data } }))
  },

  async createHighlight(articleId, data) {
    const res = await fetch(`/api/articles/${articleId}/highlights`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to create highlight')
    const created: Highlight = await res.json()
    set((s) => ({
      highlights: {
        ...s.highlights,
        [articleId]: [...(s.highlights[articleId] ?? []), created],
      },
    }))
    return created
  },

  async updateHighlight(articleId, id, data) {
    const res = await fetch(`/api/articles/${articleId}/highlights/${id}`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) return
    const updated: Highlight = await res.json()
    set((s) => ({
      highlights: {
        ...s.highlights,
        [articleId]: (s.highlights[articleId] ?? []).map((h) =>
          h.id === id ? updated : h
        ),
      },
    }))
  },

  async deleteHighlight(articleId, id) {
    const res = await fetch(`/api/articles/${articleId}/highlights/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    })
    if (!res.ok) return
    set((s) => ({
      highlights: {
        ...s.highlights,
        [articleId]: (s.highlights[articleId] ?? []).filter((h) => h.id !== id),
      },
    }))
  },
}))
