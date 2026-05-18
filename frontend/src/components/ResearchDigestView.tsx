import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { useResearchStore } from '../store/research'
import { useArticlesStore } from '../store/articles'
import { ContribTypeBadge } from './ContribTypeBadge'

interface ResearchDigestViewProps {
  onSelect: (id: number) => void
}

const WINDOW_OPTIONS = [14, 30, 60] as const

export default function ResearchDigestView({ onSelect }: ResearchDigestViewProps) {
  const { clusters, clustersLoading, clustersError, fetchClusters } = useResearchStore()
  const { articles } = useArticlesStore()
  const [windowDays, setWindowDays] = useState<number>(14)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    fetchClusters(windowDays)
  }, [windowDays])

  // Map article ID → list item for title resolution
  const articleMap = useMemo(
    () => new Map(articles.map(a => [a.id, a])),
    [articles]
  )

  return (
    <div className="flex flex-col h-full bg-bg-base overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border-subtle flex-shrink-0 flex items-center justify-between">
        <span className="text-xs font-semibold text-text-muted uppercase tracking-widest">
          Topic Clusters
        </span>
        <select
          value={windowDays}
          onChange={e => setWindowDays(Number(e.target.value))}
          className="text-xs bg-bg-elevated border border-border-subtle rounded px-1.5 py-0.5 text-text-secondary focus:outline-none"
          title="Time window"
        >
          {WINDOW_OPTIONS.map(d => (
            <option key={d} value={d}>{d}d</option>
          ))}
        </select>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Loading */}
        {clustersLoading && (
          <div className="flex flex-col gap-3 px-3 py-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="rounded-xl bg-bg-elevated p-3 animate-pulse">
                <div className="h-3.5 bg-bg-hover rounded w-3/4 mb-2" />
                <div className="h-2.5 bg-bg-hover rounded w-1/2 mb-2" />
                <div className="flex gap-1">
                  <div className="h-5 bg-bg-hover rounded-full w-12" />
                  <div className="h-5 bg-bg-hover rounded-full w-16" />
                  <div className="h-5 bg-bg-hover rounded-full w-10" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {!clustersLoading && clustersError && (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-warning">Cluster index unavailable</p>
            <p className="text-xs text-text-muted mt-1">
              Ensure <code className="text-purple">nomic-embed-text</code> is running in Ollama.
            </p>
            <button
              onClick={() => fetchClusters(windowDays)}
              className="mt-3 text-xs text-accent hover:underline"
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty */}
        {!clustersLoading && !clustersError && clusters !== null && clusters.length === 0 && (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-text-muted">No clusters yet</p>
            <p className="text-xs text-text-muted mt-1 leading-relaxed">
              Articles are embedded automatically after scoring.
              Come back when more articles are indexed.
            </p>
            <p className="text-xs text-text-muted mt-2 opacity-60">
              Try extending the window to {windowDays < 60 ? '60' : '90'} days.
            </p>
          </div>
        )}

        {/* Cluster cards */}
        {!clustersLoading && !clustersError && clusters && clusters.length > 0 && (
          <div className="py-2 space-y-1">
            {clusters.map(cluster => {
              const isExpanded = expandedId === cluster.cluster_id
              return (
                <div key={cluster.cluster_id} className="mx-2 rounded-xl overflow-hidden border border-border-subtle bg-bg-surface">
                  {/* Card header — click to expand */}
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : cluster.cluster_id)}
                    className="w-full text-left px-3 py-2.5 hover:bg-bg-elevated transition-colors group"
                  >
                    <div className="flex items-start gap-2">
                      <span className="mt-0.5 flex-shrink-0 text-text-muted group-hover:text-text-secondary transition-colors">
                        {isExpanded
                          ? <ChevronDown className="w-3.5 h-3.5" />
                          : <ChevronRight className="w-3.5 h-3.5" />
                        }
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-text-primary line-clamp-2 leading-snug font-medium">
                          {cluster.centroid_title}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-text-muted tabular-nums">
                            {cluster.size} article{cluster.size !== 1 ? 's' : ''}
                          </span>
                        </div>
                        {cluster.top_tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {cluster.top_tags.map(tag => (
                              <span
                                key={tag}
                                className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-bg-elevated text-text-muted border border-border-subtle"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </button>

                  {/* Expanded article list */}
                  {isExpanded && (
                    <div className="border-t border-border-subtle bg-bg-base divide-y divide-border-subtle/50">
                      {cluster.article_ids.map(id => {
                        const article = articleMap.get(id)
                        return (
                          <button
                            key={id}
                            onClick={() => onSelect(id)}
                            className="w-full text-left px-4 py-2 hover:bg-bg-elevated transition-colors group/item"
                          >
                            <p className="text-xs text-text-secondary group-hover/item:text-text-primary line-clamp-2 leading-snug">
                              {article ? article.title : `Article #${id}`}
                            </p>
                            {article && (
                              <div className="flex items-center gap-1.5 mt-0.5">
                                {article.score != null && (
                                  <span className="text-[10px] text-text-muted tabular-nums">
                                    ★ {article.score.toFixed(1)}
                                  </span>
                                )}
                                {article.contribution_type && (
                                  <ContribTypeBadge type={article.contribution_type} />
                                )}
                              </div>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
