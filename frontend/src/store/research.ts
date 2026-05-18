import { create } from 'zustand'
import type {
  Cluster,
  LiteratureReview,
  LiteratureReviewSummary,
  ResearchProfileEntry,
} from '../types'

interface ResearchStore {
  // ── Clusters ───────────────────────────────────────────────────────────────
  clusters: Cluster[] | null
  clustersLoading: boolean
  clustersError: string | null
  fetchClusters: (windowDays?: number) => Promise<void>

  // ── Researcher Profile ─────────────────────────────────────────────────────
  profile: ResearchProfileEntry[] | null
  profileLoading: boolean
  profileError: string | null
  fetchProfile: () => Promise<void>
  saveProfile: (entries: ResearchProfileEntry[]) => Promise<void>

  // ── Literature reviews (Story 3.4) ─────────────────────────────────────────
  reviews: LiteratureReviewSummary[] | null
  reviewsLoading: boolean
  reviewsError: string | null
  currentReview: LiteratureReview | null
  reviewGenerating: boolean
  reviewDetailLoading: boolean
  reviewError: string | null
  fetchReviewList: () => Promise<void>
  fetchReviewById: (id: number) => Promise<void>
  generateReview: (topic: string, windowDays: number, minRigor: number) => Promise<void>
  deleteReview: (id: number) => Promise<void>
}

export const useResearchStore = create<ResearchStore>((set) => ({
  // ── Clusters ───────────────────────────────────────────────────────────────
  clusters: null,
  clustersLoading: false,
  clustersError: null,

  fetchClusters: async (windowDays = 14) => {
    set({ clustersLoading: true, clustersError: null })
    try {
      const r = await fetch(`/api/research/clusters?window_days=${windowDays}`, {
        credentials: 'include',
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data: Cluster[] = await r.json()
      set({ clusters: data, clustersLoading: false })
    } catch (err) {
      set({
        clustersError: err instanceof Error ? err.message : 'Failed to load clusters',
        clustersLoading: false,
      })
    }
  },

  // ── Researcher Profile ─────────────────────────────────────────────────────
  profile: null,
  profileLoading: false,
  profileError: null,

  fetchProfile: async () => {
    set({ profileLoading: true, profileError: null })
    try {
      const r = await fetch('/api/research/profile', { credentials: 'include' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data: ResearchProfileEntry[] = await r.json()
      set({ profile: data, profileLoading: false })
    } catch (err) {
      set({
        profileError: err instanceof Error ? err.message : 'Failed to load profile',
        profileLoading: false,
      })
    }
  },

  saveProfile: async (entries: ResearchProfileEntry[]) => {
    set({ profileLoading: true, profileError: null })
    try {
      const r = await fetch('/api/research/profile', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entries }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data: ResearchProfileEntry[] = await r.json()
      set({ profile: data, profileLoading: false })
    } catch (err) {
      set({
        profileError: err instanceof Error ? err.message : 'Failed to save profile',
        profileLoading: false,
      })
    }
  },

  // ── Literature reviews ─────────────────────────────────────────────────────
  reviews: null,
  reviewsLoading: false,
  reviewsError: null,
  currentReview: null,
  reviewGenerating: false,
  reviewDetailLoading: false,
  reviewError: null,

  fetchReviewList: async () => {
    set({ reviewsLoading: true, reviewsError: null })
    try {
      const r = await fetch('/api/research/reviews', { credentials: 'include' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data: LiteratureReviewSummary[] = await r.json()
      set({ reviews: data, reviewsLoading: false })
    } catch (err) {
      set({
        reviewsError: err instanceof Error ? err.message : 'Failed to load reviews',
        reviewsLoading: false,
      })
    }
  },

  fetchReviewById: async (id: number) => {
    set({ reviewDetailLoading: true, reviewError: null })
    try {
      const r = await fetch(`/api/research/reviews/${id}`, { credentials: 'include' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data: LiteratureReview = await r.json()
      set({ currentReview: data, reviewDetailLoading: false })
    } catch (err) {
      set({
        reviewError: err instanceof Error ? err.message : 'Failed to load review',
        reviewDetailLoading: false,
      })
    }
  },

  generateReview: async (topic: string, windowDays: number, minRigor: number) => {
    set({ reviewGenerating: true, reviewError: null })
    try {
      const r = await fetch('/api/research/review', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, window_days: windowDays, min_rigor: minRigor }),
      })
      const bodyText = await r.text()
      if (!r.ok) {
        let msg = `HTTP ${r.status}`
        try {
          const j = JSON.parse(bodyText)
          if (typeof j.detail === 'string') msg = j.detail
          else if (Array.isArray(j.detail)) msg = j.detail.map((x: { msg?: string }) => x.msg || x).join(', ')
        } catch {
          if (bodyText) msg = bodyText.slice(0, 200)
        }
        throw new Error(msg)
      }
      const data = JSON.parse(bodyText) as LiteratureReview
      set({ currentReview: data, reviewGenerating: false })
      // refresh past list
      const lr = await fetch('/api/research/reviews', { credentials: 'include' })
      if (lr.ok) {
        const list: LiteratureReviewSummary[] = await lr.json()
        set({ reviews: list })
      }
    } catch (err) {
      set({
        reviewError: err instanceof Error ? err.message : 'Generation failed',
        reviewGenerating: false,
      })
    }
  },

  deleteReview: async (id: number) => {
    try {
      const r = await fetch(`/api/research/reviews/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      set(state => ({
        reviews: (state.reviews ?? []).filter(rv => rv.id !== id),
        currentReview: state.currentReview?.id === id ? null : state.currentReview,
      }))
    } catch (err) {
      set({ reviewError: err instanceof Error ? err.message : 'Delete failed' })
    }
  },
}))
