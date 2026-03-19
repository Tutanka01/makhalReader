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

  fetchArticles: (reset?: boolean) => Promise<void>
  fetchArticle: (id: number) => Promise<void>
  markRead: (id: number) => Promise<void>
  markUnread: (id: number) => Promise<void>
  toggleBookmark: (id: number) => Promise<void>
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
  },
  loading: false,
  hasMore: true,
  offset: 0,

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

      set(prev => ({
        articles: reset ? data : [...prev.articles, ...data],
        hasMore: data.length === PAGE_SIZE,
        offset: offset + data.length,
        loading: false,
      }))
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
    try {
      await fetch(`/api/articles/${id}/read`, { method: 'POST' })
      set(state => ({
        articles: state.articles.map(a =>
          a.id === id ? { ...a, read_at: new Date().toISOString() } : a
        ),
        selectedArticle:
          state.selectedArticle?.id === id
            ? { ...state.selectedArticle, read_at: new Date().toISOString() }
            : state.selectedArticle,
      }))
    } catch (err) {
      console.error('Failed to mark article as read:', err)
    }
  },

  markUnread: async (id: number) => {
    try {
      await fetch(`/api/articles/${id}/unread`, { method: 'POST' })
      set(state => ({
        articles: state.articles.map(a =>
          a.id === id ? { ...a, read_at: null } : a
        ),
        selectedArticle:
          state.selectedArticle?.id === id
            ? { ...state.selectedArticle, read_at: null }
            : state.selectedArticle,
      }))
    } catch (err) {
      console.error('Failed to mark article as unread:', err)
    }
  },

  toggleBookmark: async (id: number) => {
    try {
      const resp = await fetch(`/api/articles/${id}/bookmark`, { method: 'POST' })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      set(state => ({
        articles: state.articles.map(a =>
          a.id === id ? { ...a, bookmarked: data.bookmarked } : a
        ),
        selectedArticle:
          state.selectedArticle?.id === id
            ? { ...state.selectedArticle, bookmarked: data.bookmarked }
            : state.selectedArticle,
      }))
    } catch (err) {
      console.error('Failed to toggle bookmark:', err)
    }
  },

  setFilter: (partial: Partial<ArticleFilter>) => {
    set(state => ({
      filter: { ...state.filter, ...partial },
      articles: [],
      offset: 0,
      hasMore: true,
    }))
    // Trigger a fresh fetch after filter update
    get().fetchArticles(true)
  },

  prependArticle: (article: ArticleListItem) => {
    set(state => {
      // Don't prepend if it already exists
      if (state.articles.some(a => a.id === article.id)) return {}
      return { articles: [article, ...state.articles] }
    })
  },

  setSelectedId: (id: number | null) => {
    set({ selectedId: id })
    if (id !== null) {
      get().fetchArticle(id)
    }
  },
}))
