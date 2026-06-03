import { create } from 'zustand'
import apiClient from '../apiClient'
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
  note?: string | null
  thesis_section?: string | null
}

interface HighlightsState {
  /** Highlights keyed by article_id */
  highlights: Record<number, Highlight[]>

  fetchHighlights: (articleId: number) => Promise<void>
  createHighlight: (articleId: number, data: HighlightCreate) => Promise<Highlight>
  updateHighlight: (articleId: number, id: number, data: HighlightUpdate) => Promise<void>
  deleteHighlight: (articleId: number, id: number) => Promise<void>
  patchHighlight: (id: number, data: HighlightUpdate) => Promise<void>
}

export const useHighlightsStore = create<HighlightsState>((set, get) => ({
  highlights: {},

  async fetchHighlights(articleId) {
    try {
      const data = await apiClient.get<Highlight[]>(`/api/articles/${articleId}/highlights`)
      set((s) => ({ highlights: { ...s.highlights, [articleId]: data } }))
    } catch {
      // Non-fatal: silently skip if article has no highlights or request fails
    }
  },

  async createHighlight(articleId, data) {
    const created = await apiClient.post<Highlight>(`/api/articles/${articleId}/highlights`, data)
    set((s) => ({
      highlights: {
        ...s.highlights,
        [articleId]: [...(s.highlights[articleId] ?? []), created],
      },
    }))
    return created
  },

  async updateHighlight(articleId, id, data) {
    try {
      const updated = await apiClient.put<Highlight>(`/api/articles/${articleId}/highlights/${id}`, data)
      set((s) => ({
        highlights: {
          ...s.highlights,
          [articleId]: (s.highlights[articleId] ?? []).map((h) =>
            h.id === id ? updated : h
          ),
        },
      }))
    } catch {
      // Non-fatal
    }
  },

  async deleteHighlight(articleId, id) {
    try {
      await apiClient.del(`/api/articles/${articleId}/highlights/${id}`)
      set((s) => ({
        highlights: {
          ...s.highlights,
          [articleId]: (s.highlights[articleId] ?? []).filter((h) => h.id !== id),
        },
      }))
    } catch {
      // Non-fatal
    }
  },

  async patchHighlight(id, data) {
    try {
      const updated = await apiClient.patch<Highlight>(`/api/highlights/${id}`, data)
      set((s) => {
        const next = { ...s.highlights }
        for (const aid of Object.keys(next)) {
          const aidNum = Number(aid)
          next[aidNum] = next[aidNum].map((h) => (h.id === id ? updated : h))
        }
        return { highlights: next }
      })
    } catch {
      // Non-fatal
    }
  },
}))
