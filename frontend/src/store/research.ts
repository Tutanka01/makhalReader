import { create } from 'zustand'
import apiClient from '../apiClient'
import type {
  Cluster,
  ExternalReview,
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

  // ── External review (State of the Art) ──────────────────────────────────
  externalReview: ExternalReview | null
  externalReviewGenerating: boolean
  externalReviewError: string | null
  generateExternalReview: (topic: string, maxResults: number, minYear: number) => Promise<void>
  clearExternalReview: () => void
}

export const useResearchStore = create<ResearchStore>((set) => ({
  // ── Clusters ───────────────────────────────────────────────────────────────
  clusters: null,
  clustersLoading: false,
  clustersError: null,

  fetchClusters: async (windowDays = 14) => {
    set({ clustersLoading: true, clustersError: null })
    try {
      const data = await apiClient.get<Cluster[]>(`/api/research/clusters?window_days=${windowDays}`)
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
      const data = await apiClient.get<ResearchProfileEntry[]>('/api/research/profile')
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
      const data = await apiClient.put<ResearchProfileEntry[]>('/api/research/profile', { entries })
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
      const data = await apiClient.get<LiteratureReviewSummary[]>('/api/research/reviews')
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
      const data = await apiClient.get<LiteratureReview>(`/api/research/reviews/${id}`)
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
      const data = await apiClient.post<LiteratureReview>('/api/research/review', {
        topic,
        window_days: windowDays,
        min_rigor: minRigor,
      })
      set({ currentReview: data, reviewGenerating: false })
      // refresh past list
      try {
        const list = await apiClient.get<LiteratureReviewSummary[]>('/api/research/reviews')
        set({ reviews: list })
      } catch {}
    } catch (err) {
      set({
        reviewError: err instanceof Error ? err.message : 'Generation failed',
        reviewGenerating: false,
      })
    }
  },

  deleteReview: async (id: number) => {
    try {
      await apiClient.del(`/api/research/reviews/${id}`)
      set(state => ({
        reviews: (state.reviews ?? []).filter(rv => rv.id !== id),
        currentReview: state.currentReview?.id === id ? null : state.currentReview,
      }))
    } catch (err) {
      set({ reviewError: err instanceof Error ? err.message : 'Delete failed' })
    }
  },

  // ── External review ──────────────────────────────────────────────────────
  externalReview: null,
  externalReviewGenerating: false,
  externalReviewError: null,

  generateExternalReview: async (topic, maxResults, minYear) => {
    set({ externalReviewGenerating: true, externalReviewError: null, externalReview: null })
    try {
      const data = await apiClient.post<ExternalReview>('/api/research/external-review', {
        topic,
        max_results: maxResults,
        min_year: minYear,
      })
      set({ externalReview: data, externalReviewGenerating: false })
    } catch (err) {
      set({
        externalReviewError: err instanceof Error ? err.message : 'Generation failed',
        externalReviewGenerating: false,
      })
    }
  },

  clearExternalReview: () => set({ externalReview: null, externalReviewError: null }),
}))
