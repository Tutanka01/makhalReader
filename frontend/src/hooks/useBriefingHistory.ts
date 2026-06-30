import { useCallback, useEffect, useState } from 'react'
import type { Briefing, BriefingSummary } from '../types'

const PAGE_SIZE = 20

type SummariesStatus = 'loading' | 'ready' | 'error'
type DetailStatus = 'idle' | 'loading' | 'ready' | 'error'

export function useBriefingHistory() {
  const [summaries, setSummaries] = useState<BriefingSummary[]>([])
  const [summariesStatus, setSummariesStatus] = useState<SummariesStatus>('loading')
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Briefing | null>(null)
  const [detailStatus, setDetailStatus] = useState<DetailStatus>('idle')

  const loadPage = useCallback(async (offset: number) => {
    const res = await fetch(`/api/briefings?limit=${PAGE_SIZE}&offset=${offset}`, { credentials: 'include' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const page: BriefingSummary[] = await res.json()
    setHasMore(page.length === PAGE_SIZE)
    return page
  }, [])

  useEffect(() => {
    let cancelled = false
    setSummariesStatus('loading')
    loadPage(0)
      .then(page => { if (!cancelled) { setSummaries(page); setSummariesStatus('ready') } })
      .catch(() => { if (!cancelled) setSummariesStatus('error') })
    return () => { cancelled = true }
  }, [loadPage])

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return
    setLoadingMore(true)
    try {
      const page = await loadPage(summaries.length)
      setSummaries(prev => [...prev, ...page])
    } catch {
      // leave hasMore as-is; user can retry by scrolling/clicking again
    } finally {
      setLoadingMore(false)
    }
  }, [loadPage, loadingMore, hasMore, summaries.length])

  const selectBriefing = useCallback(async (id: number | null) => {
    setSelectedId(id)
    if (id === null) { setDetail(null); setDetailStatus('idle'); return }
    setDetailStatus('loading')
    try {
      const res = await fetch(`/api/briefings/${id}`, { credentials: 'include' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setDetail(await res.json())
      setDetailStatus('ready')
    } catch {
      setDetailStatus('error')
    }
  }, [])

  return {
    summaries,
    summariesStatus,
    hasMore,
    loadingMore,
    loadMore,
    selectedId,
    detail,
    detailStatus,
    selectBriefing,
  }
}
