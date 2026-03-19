import { useEffect, useRef, useCallback } from 'react'
import { useArticlesStore } from '../store/articles'

export function useArticles() {
  const {
    articles,
    loading,
    hasMore,
    fetchArticles,
    selectedId,
    setSelectedId,
  } = useArticlesStore()

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const observerRef = useRef<IntersectionObserver | null>(null)

  // Initial fetch
  useEffect(() => {
    fetchArticles(true)
  }, [])

  const loadMore = useCallback(() => {
    if (!loading && hasMore) {
      fetchArticles(false)
    }
  }, [loading, hasMore, fetchArticles])

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect()
    }

    observerRef.current = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) {
          loadMore()
        }
      },
      { threshold: 0.1 }
    )

    if (sentinelRef.current) {
      observerRef.current.observe(sentinelRef.current)
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect()
      }
    }
  }, [loadMore])

  return {
    articles,
    loading,
    hasMore,
    sentinelRef,
    selectedId,
    setSelectedId,
    loadMore,
  }
}
