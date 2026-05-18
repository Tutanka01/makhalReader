import { useEffect, useState } from 'react'
import type { RelatedArticle } from '../types'
import { ContribTypeBadge } from './ContribTypeBadge'
import { ReDocTypeBadge } from './ReDocTypeBadge'

interface RelatedPanelProps {
  articleId: number
  onNavigate: (id: number) => void
}

export default function RelatedPanel({ articleId, onNavigate }: RelatedPanelProps) {
  const [related, setRelated] = useState<RelatedArticle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setRelated([])

    fetch(`/api/articles/${articleId}/related?n=8`, { credentials: 'include' })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<RelatedArticle[]>
      })
      .then(data => {
        if (!cancelled) {
          setRelated(data)
          setLoading(false)
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err.message ?? 'Failed to load related articles')
          setLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [articleId])

  return (
    <aside className="flex flex-col h-full bg-bg-surface border-l border-border-default">
      <div className="px-4 py-3 border-b border-border-subtle flex items-center gap-2">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-widest">
          Related
        </span>
        <span className="ml-auto text-xs text-text-muted">semantic similarity</span>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {loading && (
          <div className="px-4 py-8 text-center">
            <div className="inline-block w-5 h-5 border-2 border-purple border-t-transparent rounded-full animate-spin" />
            <p className="mt-2 text-xs text-text-muted">Searching embeddings…</p>
          </div>
        )}

        {!loading && error && (
          <div className="px-4 py-6 text-center">
            <p className="text-xs text-warning">Semantic index unavailable</p>
            <p className="text-xs text-text-muted mt-1">
              Pull <code className="text-purple">nomic-embed-text</code> in Ollama to enable.
            </p>
          </div>
        )}

        {!loading && !error && related.length === 0 && (
          <div className="px-4 py-6 text-center">
            <p className="text-xs text-text-muted">No similar articles indexed yet.</p>
            <p className="text-xs text-text-muted mt-1">
              New articles are embedded automatically after scoring.
            </p>
          </div>
        )}

        {!loading && !error && related.map(item => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className="w-full text-left px-4 py-3 hover:bg-bg-hover transition-colors border-b border-border-subtle group"
          >
            <div className="flex items-start justify-between gap-2 mb-1">
              <p className="text-sm text-text-secondary group-hover:text-text-primary line-clamp-2 leading-snug flex-1">
                {item.title}
              </p>
              <span
                className="shrink-0 text-xs font-mono text-purple mt-0.5"
                title={`${Math.round(item.similarity * 100)}% similar`}
              >
                {Math.round(item.similarity * 100)}%
              </span>
            </div>

            <div className="flex items-center gap-1.5 flex-wrap">
              {item.score != null && (
                <span className="text-xs text-text-muted font-mono">
                  ★ {item.score.toFixed(1)}
                </span>
              )}
              {item.contribution_type && (
                <ContribTypeBadge type={item.contribution_type} />
              )}
              {item.re_document_type && (
                <ReDocTypeBadge type={item.re_document_type} />
              )}
            </div>
          </button>
        ))}
      </div>
    </aside>
  )
}
