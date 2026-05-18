import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Download, ExternalLink, Loader2, Trash2 } from 'lucide-react'
import { useResearchStore } from '../store/research'
import { useArticlesStore } from '../store/articles'
import type { ExternalReview, LiteratureReview } from '../types'

const WINDOW_OPTIONS = [14, 30, 60, 90, 180] as const
const MIN_YEAR_OPTIONS = [2018, 2020, 2022, 2024] as const
const MAX_RESULTS_OPTIONS = [10, 20, 30] as const

type Mode = 'corpus' | 'external'

// ── Markdown export helpers ───────────────────────────────────────────────────

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

function buildExternalMarkdownExport(review: ExternalReview): string {
  const lines: string[] = []
  lines.push(`# State of the Art: ${review.topic}`)
  lines.push('')
  lines.push(`Source: ${review.source} · Generated: ${review.generated_at.slice(0, 10)} · Papers: ${review.papers.length}`)
  lines.push('')
  lines.push('## Synthesis')
  lines.push('')
  lines.push(review.synthesis)
  lines.push('')
  if (review.relevance_notes) {
    lines.push('## Relevance to thesis')
    lines.push('')
    lines.push(review.relevance_notes)
    lines.push('')
  }
  if (review.top_cite) {
    lines.push(`**Start here:** ${review.top_cite}`)
    lines.push('')
  }
  if (review.comparison_table.length > 0) {
    lines.push('## Comparison table (top 5)')
    lines.push('')
    lines.push('| Work | Method | Dataset | Key result |')
    lines.push('| --- | --- | --- | --- |')
    for (const row of review.comparison_table) {
      const esc = (s: string) => s.replace(/\|/g, '\\|').replace(/\n/g, ' ')
      lines.push(`| ${esc(row.work)} | ${esc(row.method)} | ${esc(row.dataset)} | ${esc(row.key_result)} |`)
    }
    lines.push('')
  }
  if (review.gaps.length > 0) {
    lines.push('## Research gaps')
    review.gaps.forEach(g => lines.push(`- ${g}`))
    lines.push('')
  }
  if (review.papers.length > 0) {
    lines.push('## Paper corpus')
    lines.push('')
    for (const p of review.papers) {
      const authors = p.authors.slice(0, 3).join(', ') + (p.authors.length > 3 ? ' et al.' : '')
      lines.push(`### ${p.title}`)
      lines.push(`${authors} · ${p.year ?? 'n/a'} · ${p.venue || 'n/a'} · ${p.citation_count} citations`)
      if (p.abstract) lines.push(`> ${p.abstract.slice(0, 300)}…`)
      if (p.url) lines.push(`[Read paper](${p.url})`)
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

function downloadMd(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ── Component ─────────────────────────────────────────────────────────────────

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
    externalReview,
    externalReviewGenerating,
    externalReviewError,
    generateExternalReview,
    clearExternalReview,
  } = useResearchStore()
  const { articles } = useArticlesStore()

  const [mode, setMode] = useState<Mode>('corpus')
  const [topic, setTopic] = useState('')
  const [windowDays, setWindowDays] = useState(30)
  const [minRigor, setMinRigor] = useState(0)
  const [minYear, setMinYear] = useState(2018)
  const [maxResults, setMaxResults] = useState(20)

  useEffect(() => { fetchReviewList() }, [fetchReviewList])

  const articleMap = useMemo(
    () => new Map(articles.map(a => [a.id, a])),
    [articles]
  )

  const handleCorpusExport = () => {
    if (!currentReview) return
    const day = currentReview.created_at.slice(0, 10)
    downloadMd(buildMarkdownExport(currentReview), `${slugTopic(currentReview.topic)}-${day}.md`)
  }

  const handleExternalExport = () => {
    if (!externalReview) return
    const day = externalReview.generated_at.slice(0, 10)
    downloadMd(buildExternalMarkdownExport(externalReview), `sota-${slugTopic(externalReview.topic)}-${day}.md`)
  }

  const switchMode = (m: Mode) => {
    setMode(m)
    if (m === 'corpus') clearExternalReview()
  }

  return (
    <div className="flex flex-col md:flex-row h-full bg-bg-base overflow-hidden min-h-0">

      {/* Past reviews sidebar — corpus mode only */}
      {mode === 'corpus' && (
        <aside className="w-full md:w-36 flex-shrink-0 border-b md:border-b-0 md:border-r border-border-subtle flex flex-col max-h-32 md:max-h-none">
          <div className="px-2 py-2 border-b border-border-subtle text-[10px] font-semibold text-text-muted uppercase tracking-wide">
            Past
          </div>
          <div className="flex-1 overflow-x-auto md:overflow-y-auto flex md:flex-col gap-1 p-1.5">
            {reviewsLoading && <Loader2 className="w-4 h-4 animate-spin text-text-muted m-auto" />}
            {reviewsError && <p className="text-[10px] text-amber-500 px-1">{reviewsError}</p>}
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
      )}

      {/* Main panel */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">

        {/* Header + mode tabs */}
        <div className="px-3 py-2 border-b border-border-subtle flex items-center gap-2 flex-shrink-0">
          <BookOpen className="w-3.5 h-3.5 text-success flex-shrink-0" />
          <span className="text-xs font-semibold text-text-muted uppercase tracking-widest flex-shrink-0">
            Lit Review
          </span>
          <div className="ml-auto flex rounded-lg overflow-hidden border border-border-default text-[10px]">
            <button
              onClick={() => switchMode('corpus')}
              className={`px-2.5 py-1 transition-colors ${
                mode === 'corpus'
                  ? 'bg-success text-white'
                  : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
              }`}
            >
              In corpus
            </button>
            <button
              onClick={() => switchMode('external')}
              className={`px-2.5 py-1 border-l border-border-default transition-colors ${
                mode === 'external'
                  ? 'bg-success text-white'
                  : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
              }`}
            >
              State of the art
            </button>
          </div>
        </div>

        {/* ── CORPUS MODE ────────────────────────────────────────────────── */}
        {mode === 'corpus' && (
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
                  {WINDOW_OPTIONS.map(d => <option key={d} value={d}>{d}d</option>)}
                </select>
              </div>
              <div className="flex-1 min-w-[140px]">
                <label className="block text-[10px] text-text-muted uppercase mb-0.5">
                  Min rigor {minRigor.toFixed(2)}
                </label>
                <input
                  type="range" min={0} max={1} step={0.05} value={minRigor}
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
                <Loader2 className="w-4 h-4 animate-spin" /> Loading review…
              </div>
            )}

            {reviewGenerating && (
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

            {currentReview && !reviewGenerating && (
              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold text-text-primary truncate">{currentReview.topic}</h2>
                  <button
                    type="button"
                    onClick={handleCorpusExport}
                    className="flex-shrink-0 flex items-center gap-1 text-[11px] text-success hover:text-success/80 px-2 py-1 rounded-md border border-border-subtle"
                  >
                    <Download className="w-3 h-3" /> Export Markdown
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
                          {c.gaps.map((g, gi) => <li key={gi}>{g}</li>)}
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
        )}

        {/* ── EXTERNAL MODE (State of the art) ───────────────────────────── */}
        {mode === 'external' && (
          <div className="p-3 space-y-3 overflow-y-auto flex-1">
            <div className="space-y-2">
              <label className="block text-[10px] text-text-muted uppercase">Research topic</label>
              <input
                value={topic}
                onChange={e => setTopic(e.target.value)}
                placeholder="e.g. AI agents for systems engineering"
                className="w-full text-sm rounded-md border border-border-default bg-bg-surface px-2 py-1.5 text-text-primary placeholder-text-muted focus:outline-none focus:ring-1 focus:ring-success/50"
              />
            </div>

            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-[10px] text-text-muted uppercase mb-0.5">From year</label>
                <select
                  value={minYear}
                  onChange={e => setMinYear(Number(e.target.value))}
                  className="text-xs bg-bg-elevated border border-border-subtle rounded px-1.5 py-1 text-text-secondary"
                >
                  {MIN_YEAR_OPTIONS.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-text-muted uppercase mb-0.5">Papers</label>
                <select
                  value={maxResults}
                  onChange={e => setMaxResults(Number(e.target.value))}
                  className="text-xs bg-bg-elevated border border-border-subtle rounded px-1.5 py-1 text-text-secondary"
                >
                  {MAX_RESULTS_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </div>
              <button
                type="button"
                disabled={externalReviewGenerating || !topic.trim()}
                onClick={() => generateExternalReview(topic.trim(), maxResults, minYear)}
                className="text-xs font-medium px-3 py-1.5 rounded-md bg-success text-white hover:bg-success/90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                {externalReviewGenerating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Search & synthesize
              </button>
            </div>

            {externalReviewGenerating && (
              <div className="space-y-2 pt-2">
                <p className="text-[10px] text-text-muted">Querying Semantic Scholar + synthesizing…</p>
                {[1, 2, 3, 4].map(i => (
                  <div key={i} className="rounded-xl bg-bg-elevated p-3 animate-pulse">
                    <div className="h-3 bg-bg-hover rounded w-2/5 mb-2" />
                    <div className="h-2 bg-bg-hover rounded w-full mb-1" />
                    <div className="h-2 bg-bg-hover rounded w-4/5" />
                  </div>
                ))}
              </div>
            )}

            {externalReviewError && (
              <p className="text-xs text-danger bg-danger/10 rounded-md px-2 py-1.5">{externalReviewError}</p>
            )}

            {externalReview && !externalReviewGenerating && (
              <div className="space-y-4 pt-1">
                {/* Header row */}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold text-text-primary">{externalReview.topic}</h2>
                    <p className="text-[10px] text-text-muted mt-0.5">
                      {externalReview.papers.length} papers · source: {externalReview.source} · {externalReview.generated_at.slice(0, 10)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleExternalExport}
                    className="flex-shrink-0 flex items-center gap-1 text-[11px] text-success hover:text-success/80 px-2 py-1 rounded-md border border-border-subtle"
                  >
                    <Download className="w-3 h-3" /> Export Markdown
                  </button>
                </div>

                {/* Synthesis */}
                <section className="rounded-xl border border-border-subtle bg-bg-surface/50 p-3 space-y-2">
                  <h3 className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">State of the art</h3>
                  <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">{externalReview.synthesis}</p>
                </section>

                {/* Relevance to thesis */}
                {externalReview.relevance_notes && (
                  <section className="rounded-xl border border-success/20 bg-success/5 p-3 space-y-1">
                    <h3 className="text-[10px] font-semibold text-success uppercase tracking-wide">Relevance to your thesis</h3>
                    <p className="text-xs text-text-secondary leading-relaxed">{externalReview.relevance_notes}</p>
                  </section>
                )}

                {/* Top cite */}
                {externalReview.top_cite && (
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wide flex-shrink-0">Start here:</span>
                    <span className="text-text-primary font-medium">{externalReview.top_cite}</span>
                  </div>
                )}

                {/* Comparison table */}
                {externalReview.comparison_table.length > 0 && (
                  <section className="space-y-1.5">
                    <h3 className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">Comparison — top 5</h3>
                    <div className="overflow-x-auto rounded-xl border border-border-subtle">
                      <table className="w-full text-[10px] text-left border-collapse">
                        <thead>
                          <tr className="text-text-muted border-b border-border-subtle bg-bg-elevated">
                            <th className="py-1.5 px-2 font-medium">Work</th>
                            <th className="py-1.5 px-2 font-medium">Method</th>
                            <th className="py-1.5 px-2 font-medium">Dataset</th>
                            <th className="py-1.5 px-2 font-medium">Key result</th>
                          </tr>
                        </thead>
                        <tbody>
                          {externalReview.comparison_table.map((row, ri) => (
                            <tr key={ri} className="border-b border-border-subtle/60 text-text-secondary hover:bg-bg-hover/40">
                              <td className="py-1.5 px-2 align-top font-medium">{row.work}</td>
                              <td className="py-1.5 px-2 align-top">{row.method}</td>
                              <td className="py-1.5 px-2 align-top">{row.dataset}</td>
                              <td className="py-1.5 px-2 align-top">{row.key_result}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}

                {/* Gaps */}
                {externalReview.gaps.length > 0 && (
                  <section className="space-y-1.5">
                    <h3 className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">Research gaps</h3>
                    <ul className="space-y-1">
                      {externalReview.gaps.map((g, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-xs text-text-secondary">
                          <span className="text-success mt-0.5 flex-shrink-0">▸</span>
                          {g}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {/* Paper corpus */}
                <section className="space-y-1.5">
                  <h3 className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">
                    Paper corpus ({externalReview.papers.length})
                  </h3>
                  <div className="space-y-1.5">
                    {externalReview.papers.map((p, i) => (
                      <div key={i} className="rounded-lg border border-border-subtle/60 bg-bg-surface/30 px-2.5 py-2 space-y-0.5">
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-xs font-medium text-text-primary leading-snug">{p.title}</span>
                          {p.url && (
                            <a
                              href={p.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-shrink-0 text-text-muted hover:text-success transition-colors mt-0.5"
                              title="Open paper"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                        <p className="text-[10px] text-text-muted">
                          {p.authors.slice(0, 3).join(', ')}{p.authors.length > 3 ? ' et al.' : ''}
                          {p.year ? ` · ${p.year}` : ''}
                          {p.venue ? ` · ${p.venue}` : ''}
                          {p.citation_count > 0 ? ` · ${p.citation_count} citations` : ''}
                        </p>
                        {p.abstract && (
                          <p className="text-[10px] text-text-muted/80 leading-relaxed line-clamp-2">{p.abstract}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
