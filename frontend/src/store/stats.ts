import { create } from 'zustand'
import type { Stats } from '../types'

interface StatsState {
  stats: Stats | null
  loading: boolean
  fetchStats: () => Promise<void>
}

export const useStatsStore = create<StatsState>((set) => ({
  stats: null,
  loading: false,

  async fetchStats() {
    set({ loading: true })
    try {
      const res = await fetch('/api/stats', { credentials: 'include' })
      if (!res.ok) return
      const data: Stats = await res.json()
      set({ stats: data })
    } finally {
      set({ loading: false })
    }
  },
}))
