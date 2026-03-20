import { create } from 'zustand'
import type { Article, ArticleFilter, ArticleListItem } from '../types'

interface ArticlesState {
  articles: ArticleListItem[]
  selectedId: number | null
  selectedArticle: Article | null
  filter: ArticleFilter
  loading: boolean
  hasMore: boolean
  offset: number
  searchResults: ArticleListItem[]
  isSearching: boolean

  fetchArticles: (reset?: boolean) => Promise<void>
  fetchArticle: (id: number) => Promise<void>
  markRead: (id: number) => Promise<void>
  markUnread: (id: number) => Promise<void>
  markAllRead: () => Promise<void>
  toggleBookmark: (id: number) => Promise<void>
  submitFeedback: (id: number, value: 1 | -1 | 0) => Promise<void>
  searchArticles: (query: string) => Promise<void>
  clearSearch: () => void
  setFilter: (partial: Partial<ArticleFilter>) => void
  prependArticle: (article: ArticleListItem) => void
  setSelectedId: (id: number | null) => void
}

const PAGE_SIZE = 50

function buildQueryParams(filter: ArticleFilter, limit: number, offset: number): string {
  const params = new URLSearchParams()
  params.set('status', filter.bookmarked ? 'all' : filter.status)
  params.set('sort', filter.sort)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  if (filter.category && filter.category !== 'All') {
    params.set('category', filter.category)
  }
  if (filter.bookmarked) {
    params.set('bookmarked', 'true')
  }
  if (filter.minScore > 0) {
    params.set('min_score', String(filter.minScore))
  }
  return params.toString()
}

export const useArticlesStore = create<ArticlesState>((set, get) => ({
  articles: [],
  selectedId: null,
  selectedArticle: null,
  filter: {
    category: null,
    sort: 'score',
    status: 'unread',
    bookmarked: false,
    minScore: 0,
  },
  loading: false,
  hasMore: true,
  offset: 0,
  searchResults: [],
  isSearching: false,

  fetchArticles: async (reset = false) => {
    const state = get()
    if (state.loading) return

    const offset = reset ? 0 : state.offset
    set({ loading: true })

    try {
      const qs = buildQueryParams(state.filter, PAGE_SIZE, offset)
      const resp = await fetch(`/api/articles?${qs}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: ArticleListItem[] = await resp.json()

      set(prev => {
        // Deduplicate on append (score changes between pages can cause overlaps)
        const existingIds = reset ? new Set<number>() : new Set(prev.articles.map(a => a.id))
        const fresh = data.filter(a => !existingIds.has(a.id))
        return {
          articles: reset ? data : [...prev.articles, ...fresh],
          hasMore: data.length === PAGE_SIZE,
          offset: offset + data.length,
          loading: false,
        }
      })
    } catch (err) {
      console.error('Failed to fetch articles:', err)
      set({ loading: false })
    }
  },

  fetchArticle: async (id: number) => {
    set({ selectedId: id, selectedArticle: null })
    try {
      const resp = await fetch(`/api/articles/${id}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: Article = await resp.json()
      set({ selectedArticle: data })
    } catch (err) {
      console.error('Failed to fetch article:', err)
    }
  },

  markRead: async (id: number) => {
    const read_at = new Date().toISOString()

    set(state => {
      const article = state.articles.find(a => a.id === id)
      const updated = article ? { ...article, read_at } : null

      let articles: ArticleListItem[]
      if (!updated) {
        articles = state.articles
      } else if (updated.bookmarked) {
        // Bookmarked articles: gray out in place, never move
        articles = state.articles.map(a => a.id === id ? updated : a)
      } else {
        // Regular articles: gray out and sink to the bottom
        articles = [...state.articles.filter(a => a.id !== id), updated]
      }

      return {
        articles,
        selectedArticle: state.selectedArticle?.id === id
          ? { ...state.selectedArticle, read_at }
          : state.selectedArticle,
      }
    })

    try {
      await fetch(`/api/articles/${id}/read`, { method: 'POST' })
    } catch (err) {
      console.error('Failed to mark article as read:', err)
      get().fetchArticles(true)
    }
  },

  markUnread: async (id: number) => {
    set(state => ({
      articles: state.articles.map(a => a.id === id ? { ...a, read_at: null } : a),
      selectedArticle: state.selectedArticle?.id === id
        ? { ...state.selectedArticle, read_at: null }
        : state.selectedArticle,
    }))

    try {
      await fetch(`/api/articles/${id}/unread`, { method: 'POST' })
    } catch (err) {
      console.error('Failed to mark article as unread:', err)
      get().fetchArticles(true)
    }
  },

  markAllRead: async () => {
    const state = get()
    const params = new URLSearchParams()
    if (state.filter.category && state.filter.category !== 'All') {
      params.set('category', state.filter.category)
    }
    if (state.filter.minScore > 0) {
      params.set('min_score', String(state.filter.minScore))
    }
    try {
      await fetch(`/api/articles/read-all?${params}`, { method: 'POST' })
      get().fetchArticles(true)
    } catch (err) {
      console.error('Failed to mark all as read:', err)
    }
  },

  toggleBookmark: async (id: number) => {
    // Optimistic update first for instant feedback
    set(state => {
      const article = state.articles.find(a => a.id === id)
      if (!article) return {}
      const bookmarked = !article.bookmarked

      // Only remove from list when explicitly in bookmarks-only view and unbookmarking
      if (state.filter.bookmarked && !bookmarked) {
        return {
          articles: state.articles.filter(a => a.id !== id),
          selectedArticle: state.selectedArticle?.id === id
            ? { ...state.selectedArticle, bookmarked }
            : state.selectedArticle,
        }
      }

      return {
        articles: state.articles.map(a => a.id === id ? { ...a, bookmarked } : a),
        selectedArticle: state.selectedArticle?.id === id
          ? { ...state.selectedArticle, bookmarked }
          : state.selectedArticle,
      }
    })

    try {
      const resp = await fetch(`/api/articles/${id}/bookmark`, { method: 'POST' })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      // Server response confirms the new bookmarked state — sync it back
      const data = await resp.json()
      set(state => ({
        articles: state.articles.map(a => a.id === id ? { ...a, bookmarked: data.bookmarked } : a),
        selectedArticle: state.selectedArticle?.id === id
          ? { ...state.selectedArticle, bookmarked: data.bookmarked }
          : state.selectedArticle,
      }))
    } catch (err) {
      console.error('Failed to toggle bookmark:', err)
      // Revert optimistic update on error
      get().fetchArticles(true)
    }
  },

  submitFeedback: async (id: number, value: 1 | -1 | 0) => {
    // Optimistic update
    set(state => ({
      articles: state.articles.map(a => a.id === id ? { ...a, user_feedback: value === 0 ? null : value } : a),
      selectedArticle: state.selectedArticle?.id === id
        ? { ...state.selectedArticle, user_feedback: value === 0 ? null : value }
        : state.selectedArticle,
    }))
    try {
      await fetch(`/api/articles/${id}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      })
    } catch (err) {
      console.error('Failed to submit feedback:', err)
    }
  },

  searchArticles: async (query: string) => {
    if (!query.trim()) {
      set({ searchResults: [], isSearching: false })
      return
    }
    set({ isSearching: true })
    try {
      const params = new URLSearchParams({ search: query, limit: '50', sort: 'score' })
      const resp = await fetch(`/api/articles?${params}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: ArticleListItem[] = await resp.json()
      set({ searchResults: data, isSearching: false })
    } catch (err) {
      console.error('Search failed:', err)
      set({ isSearching: false })
    }
  },

  clearSearch: () => set({ searchResults: [], isSearching: false }),

  setFilter: (partial: Partial<ArticleFilter>) => {
    set(state => ({
      filter: { ...state.filter, ...partial },
      articles: [],
      offset: 0,
      hasMore: true,
    }))
    get().fetchArticles(true)
  },

  prependArticle: (article: ArticleListItem) => {
    set(state => {
      // Skip if already in list
      if (state.articles.some(a => a.id === article.id)) return {}

      const { filter } = state

      // Skip if doesn't match active filters
      if (filter.bookmarked && !article.bookmarked) return {}
      if (filter.minScore > 0 && (article.score ?? 0) < filter.minScore) return {}
      // New articles from SSE are always unread — skip only if filtering to read-only
      if (filter.status === 'read') return {}

      return { articles: [article, ...state.articles] }
    })
  },

  setSelectedId: (id: number | null) => {
    set({ selectedId: id })
  },
}))
