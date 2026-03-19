import { useEffect, useRef } from 'react'
import type { ArticleListItem } from '../types'
import { useArticlesStore } from '../store/articles'

export function useSSE() {
  const prependArticle = useArticlesStore(state => state.prependArticle)
  const esRef = useRef<EventSource | null>(null)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCountRef = useRef(0)

  const connect = () => {
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

      // Exponential backoff reconnect
      const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000)
      retryCountRef.current += 1

      retryTimerRef.current = setTimeout(() => {
        connect()
      }, delay)
    }
  }

  useEffect(() => {
    connect()

    return () => {
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
