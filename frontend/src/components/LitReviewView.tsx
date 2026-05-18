import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Download, Loader2, Trash2 } from 'lucide-react'
import { useResearchStore } from '../store/research'
import { useArticlesStore } from '../store/articles'
import type { LiteratureReview } from '../types'

const WINDOW_OPTIONS = [14, 30, 60, 90, 180] as const

export function buildMarkdownExport(review: LiteratureReview): string {
  const lines: string[] = []
  lines.push(`# Literature review: ${review.topic}`)
  lines.push('')
  lines.push(`Window: ${review.window_days}d · Min rigor: ${review.min_rigor} · Generated: ${review.created_at}`)
  lines.push('')
  for (const c of review.clusters) {
    lines.push(`## ${c.cluster_label}`)
    lines.push('')
    lines.push(c.synthesis)
    lines.push('')
    if (c.comparison_table.length > 0) {
      lines.push('| Work | Method | Dataset | Key result |')
      lines.push('| --- | --- | --- | --- |')
      for (const row of c.comparison_table) {
        const esc = (s: string) => s.replace(/\|/g, '\\|').replace(/\n/g, ' ')
        lines.push(`| ${esc(row.work)} | ${esc(row.method)} | ${esc(row.dataset)} | ${esc(row.key_result)} |`)
      }
      lines.push('')
    }
    if (c.gaps.length > 0) {
      lines.push('### Gaps')
      c.gaps.forEach(g => lines.push(`- ${g}`))
      lines.push('')
    }
    if (c.top_cite) {
      lines.push(`**Top cite:** ${c.top_cite}`)
      lines.push('')
    }
  }
  return lines.join('\n')
}

function slugTopic(topic: string): string {
  return topic
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 40) || 'review'
}

interface LitReviewViewProps {
  onSelectArticle?: (id: number) => void
}

export default function LitReviewView({ onSelectArticle }: LitReviewViewProps) {
  const {
    reviews,
    reviewsLoading,
    reviewsError,
    currentReview,
    reviewGenerating,
    reviewDetailLoading,
    reviewError,
    fetchReviewList,
    fetchReviewById,
    generateReview,
    deleteReview,
  } = useResearchStore()
  const { articles } = useArticlesStore()

  const [topic, setTopic] = useState('')
  const [windowDays, setWindowDays] = useState(30)
  const [minRigor, setMinRigor] = useState(0)

  useEffect(() => {
    fetchReviewList()
  }, [fetchReviewList])

  const articleMap = useMemo(
    () => new Map(articles.map(a => [a.id, a])),
    [articles]
  )

  const handleExport = () => {
    if (!currentReview) return
    const md = buildMarkdownExport(currentReview)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const day = currentReview.created_at.slice(0, 10)
    a.href = url
    a.download = `${slugTopic(currentReview.topic)}-${day}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const showGenerateSkeleton = reviewGenerating

  return (
    <div className="flex flex-col md:flex-row h-full bg-bg-base overflow-hidden min-h-0">
      {/* Past reviews */}
      <aside className="w-full md:w-36 flex-shrink-0 border-b md:border-b-0 md:border-r border-border-subtle flex flex-col max-h-32 md:max-h-none">
        <div className="px-2 py-2 border-b border-border-subtle text-[10px] font-semibold text-text-muted uppercase tracking-wide">
          Past
        </div>
        <div className="flex-1 overflow-x-auto md:overflow-y-auto flex md:flex-col gap-1 p-1.5">
          {reviewsLoading && (
            <Loader2 className="w-4 h-4 animate-spin text-text-muted m-auto" />
          )}
          {reviewsError && (
            <p className="text-[10px] text-amber-500 px-1">{reviewsError}</p>
          )}
          {!reviewsLoading && reviews?.map(r => (
            <div
              key={r.id}
              className={`group flex items-start gap-0.5 rounded-md flex-shrink-0 md:w-full ${
                currentReview?.id === r.id ? 'bg-success/15' : 'hover:bg-bg-hover'
              }`}
            >
              <button
                type="button"
                onClick={() => fetchReviewById(r.id)}
                className={`flex-1 text-left text-[10px] px-1.5 py-1 truncate ${
                  currentReview?.id === r.id ? 'text-success' : 'text-text-muted'
                }`}
                title={r.topic}
              >
                <span className="block truncate">{r.topic}</span>
                <span className="block text-[9px] opacity-70">{r.created_at.slice(0, 10)}</span>
              </button>
              <button
                type="button"
                onClick={() => deleteReview(r.id)}
                className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-danger transition-opacity flex-shrink-0 mt-0.5"
                title="Delete review"
              >
                <Trash2 className="w-2.5 h-2.5" />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
        <div className="px-3 py-2 border-b border-border-subtle flex items-center gap-2 flex-shrink-0">
          <BookOpen className="w-3.5 h-3.5 text-success" />
          <span className="text-xs font-semibold text-text-muted uppercase tracking-widest">
            Lit Review
          </span>
        </div>

        <div className="p-3 space-y-3 overflow-y-auto flex-1">
          <div className="space-y-2">
            <label className="block text-[10px] text-text-muted uppercase">Topic</label>
            <input
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="e.g. LLM requirements extraction"
              className="w-full text-sm rounded-md border border-border-default bg-bg-surface px-2 py-1.5 text-text-primary placeholder-text-muted focus:outline-none focus:ring-1 focus:ring-success/50"
            />
          </div>

          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-[10px] text-text-muted uppercase mb-0.5">Window</label>
              <select
                value={windowDays}
                onChange={e => setWindowDays(Number(e.target.value))}
                className="text-xs bg-bg-elevated border border-border-subtle rounded px-1.5 py-1 text-text-secondary"
              >
                {WINDOW_OPTIONS.map(d => (
                  <option key={d} value={d}>{d}d</option>
                ))}
              </select>
            </div>
            <div className="flex-1 min-w-[140px]">
              <label className="block text-[10px] text-text-muted uppercase mb-0.5">
                Min rigor {minRigor.toFixed(2)}
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minRigor}
                onChange={e => setMinRigor(parseFloat(e.target.value))}
                className="w-full h-1.5 accent-success"
              />
            </div>
            <button
              type="button"
              disabled={reviewGenerating || !topic.trim()}
              onClick={() => generateReview(topic.trim(), windowDays, minRigor)}
              className="text-xs font-medium px-3 py-1.5 rounded-md bg-success text-white hover:bg-success/90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              {reviewGenerating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Generate
            </button>
          </div>

          {reviewError && (
            <p className="text-xs text-danger bg-danger/10 rounded-md px-2 py-1.5">{reviewError}</p>
          )}

          {reviewDetailLoading && (
            <div className="flex items-center gap-2 text-xs text-text-muted py-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading review…
            </div>
          )}

          {showGenerateSkeleton && (
            <div className="space-y-2 pt-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="rounded-xl bg-bg-elevated p-3 animate-pulse">
                  <div className="h-3 bg-bg-hover rounded w-1/3 mb-2" />
                  <div className="h-2 bg-bg-hover rounded w-full mb-1" />
                  <div className="h-2 bg-bg-hover rounded w-5/6" />
                </div>
              ))}
            </div>
          )}

          {currentReview && !showGenerateSkeleton && (
            <div className="space-y-3 pt-1">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-text-primary truncate">{currentReview.topic}</h2>
                <button
                  type="button"
                  onClick={handleExport}
                  className="flex-shrink-0 flex items-center gap-1 text-[11px] text-success hover:text-success/80 px-2 py-1 rounded-md border border-border-subtle"
                >
                  <Download className="w-3 h-3" />
                  Export Markdown
                </button>
              </div>

              {currentReview.clusters.map((c, idx) => (
                <article
                  key={`${c.cluster_label}-${idx}`}
                  className="rounded-xl border border-border-subtle bg-bg-surface/50 p-3 space-y-2"
                >
                  <h3 className="text-xs font-semibold text-success">{c.cluster_label}</h3>
                  <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">{c.synthesis}</p>

                  {c.comparison_table.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-[10px] text-left border-collapse">
                        <thead>
                          <tr className="text-text-muted border-b border-border-subtle">
                            <th className="py-1 pr-2 font-medium">Work</th>
                            <th className="py-1 pr-2 font-medium">Method</th>
                            <th className="py-1 pr-2 font-medium">Dataset</th>
                            <th className="py-1 font-medium">Key result</th>
                          </tr>
                        </thead>
                        <tbody>
                          {c.comparison_table.map((row, ri) => (
                            <tr key={ri} className="border-b border-border-subtle/60 text-text-secondary">
                              <td className="py-1 pr-2 align-top">{row.work}</td>
                              <td className="py-1 pr-2 align-top">{row.method}</td>
                              <td className="py-1 pr-2 align-top">{row.dataset}</td>
                              <td className="py-1 align-top">{row.key_result}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {c.gaps.length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold text-text-muted uppercase mb-1">Gaps</p>
                      <ul className="list-disc list-inside text-xs text-text-secondary space-y-0.5">
                        {c.gaps.map((g, gi) => (
                          <li key={gi}>{g}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {c.top_cite && (
                    <p className="text-xs">
                      <span className="text-text-muted">Top cite: </span>
                      <span className="text-text-primary">{c.top_cite}</span>
                    </p>
                  )}

                  {c.article_ids.length > 0 && onSelectArticle && (
                    <div className="pt-1 border-t border-border-subtle/60">
                      <p className="text-[10px] text-text-muted uppercase mb-1">Articles</p>
                      <ul className="space-y-0.5">
                        {c.article_ids.map((aid, i) => {
                          const storedTitle = c.article_titles?.[i]
                          const title = storedTitle || articleMap.get(aid)?.title || `Article #${aid}`
                          return (
                            <li key={aid}>
                              <button
                                type="button"
                                onClick={() => onSelectArticle(aid)}
                                className="text-[11px] text-left text-accent hover:underline truncate max-w-full"
                              >
                                {title}
                              </button>
                            </li>
                          )
                        })}
                      </ul>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
