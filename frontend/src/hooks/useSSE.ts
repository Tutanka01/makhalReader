import { useEffect, useRef } from 'react'
import type { ArticleListItem } from '../types'
import { useArticlesStore } from '../store/articles'

export function useSSE(onUnauthorized?: () => void) {
  const prependArticle = useArticlesStore(state => state.prependArticle)
  const esRef = useRef<EventSource | null>(null)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCountRef = useRef(0)
  const stoppedRef = useRef(false)

  const connect = () => {
    if (stoppedRef.current) return
    if (esRef.current) {
      esRef.current.close()
    }

    const es = new EventSource('/api/stream')
    esRef.current = es

    es.onopen = () => {
      retryCountRef.current = 0
    }

    es.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'new_article' && message.data) {
          const article = message.data as ArticleListItem
          prependArticle(article)
        }
      } catch (err) {
        console.error('Failed to parse SSE message:', err)
      }
    }

    es.onerror = () => {
      es.close()
      esRef.current = null
      if (stoppedRef.current) return

      // Check if we're still authenticated before retrying
      fetch('/auth/status', { credentials: 'include' }).then(r => {
        if (r.status === 401) {
          stoppedRef.current = true
          onUnauthorized?.()
          return
        }
        // Still authenticated — exponential backoff retry
        const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000)
        retryCountRef.current += 1
        retryTimerRef.current = setTimeout(connect, delay)
      }).catch(() => {
        const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000)
        retryCountRef.current += 1
        retryTimerRef.current = setTimeout(connect, delay)
      })
    }
  }

  useEffect(() => {
    stoppedRef.current = false
    connect()

    return () => {
      stoppedRef.current = true
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
      }
    }
  }, [])
}
