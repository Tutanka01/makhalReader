import { useState } from 'react'
import { BookMarked, Download, Loader2 } from 'lucide-react'
import type { ContribType } from '../types'

const CONTRIB_TYPES: { value: ContribType | ''; label: string }[] = [
  { value: '', label: 'All types' },
  { value: 'method', label: 'Method' },
  { value: 'benchmark', label: 'Benchmark' },
  { value: 'survey', label: 'Survey' },
  { value: 'empirical', label: 'Empirical' },
  { value: 'theory', label: 'Theory' },
  { value: 'position', label: 'Position' },
  { value: 'tool', label: 'Tool' },
  { value: 'incident', label: 'Incident' },
  { value: 'tutorial', label: 'Tutorial' },
  { value: 'news', label: 'News' },
  { value: 'other', label: 'Other' },
]

type ExportFormat = 'bibtex' | 'zotero'

export default function BibliographyPanel() {
  const [sinceDays, setSinceDays] = useState(365)
  const [minScore, setMinScore] = useState<string>('')
  const [contribType, setContribType] = useState<string>('')
  const [fmt, setFmt] = useState<ExportFormat>('bibtex')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleExport = async () => {
    setLoading(true)
    setError(null)

    try {
      const params = new URLSearchParams()
      params.set('since_days', String(sinceDays))
      params.set('fmt', fmt)
      if (minScore) params.set('min_score', minScore)
      if (contribType) params.set('contribution_type', contribType)

      const res = await fetch(`/api/research/bibliography?${params}`, {
        credentials: 'include',
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        setError(err.detail || 'Export failed')
        return
      }

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fmt === 'zotero' ? 'bibliography.json' : 'bibliography.bib'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setError(e.message || 'Export failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex flex-col bg-bg-base">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-default">
        <div className="flex items-center gap-2.5">
          <BookMarked className="w-4 h-4 text-accent" />
          <h1 className="text-sm font-semibold text-text-primary">Bibliography Export</h1>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 max-w-lg mx-auto w-full">
        <div className="space-y-5">
          <p className="text-xs text-text-muted leading-relaxed">
            Export your personal bibliography — only articles scored for your account. Use BibTeX for LaTeX/Overleaf, or Zotero JSON to import directly into Zotero.
          </p>

          {/* Format toggle */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">Format</label>
            <div className="flex gap-2">
              {([
                { value: 'bibtex' as ExportFormat, label: 'BibTeX', desc: '.bib · LaTeX / Overleaf' },
                { value: 'zotero' as ExportFormat, label: 'Zotero JSON', desc: '.json · CSL import' },
              ] as const).map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setFmt(opt.value)}
                  className={`flex-1 px-3 py-2.5 rounded-lg border text-left transition-all ${
                    fmt === opt.value
                      ? 'border-accent bg-accent/8 text-accent'
                      : 'border-border-default bg-bg-surface text-text-muted hover:border-border-strong'
                  }`}
                >
                  <div className="text-xs font-semibold">{opt.label}</div>
                  <div className="text-[10px] opacity-70 mt-0.5">{opt.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Time range */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">Time Range</label>
            <select
              value={sinceDays}
              onChange={e => setSinceDays(Number(e.target.value))}
              className="w-full bg-bg-surface border border-border-default rounded-lg px-3 py-2 text-sm text-text-primary"
            >
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 3 months</option>
              <option value={180}>Last 6 months</option>
              <option value={365}>Last 12 months</option>
              <option value={730}>Last 2 years</option>
              <option value={3650}>All time</option>
            </select>
          </div>

          {/* Min score */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
              Minimum Score <span className="text-text-muted font-normal normal-case">(optional)</span>
            </label>
            <input
              type="number"
              min={0}
              max={10}
              step={0.5}
              value={minScore}
              onChange={e => setMinScore(e.target.value)}
              placeholder="e.g. 7.0"
              className="w-full bg-bg-surface border border-border-default rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
            />
          </div>

          {/* Contribution type */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
              Contribution Type <span className="text-text-muted font-normal normal-case">(optional)</span>
            </label>
            <select
              value={contribType}
              onChange={e => setContribType(e.target.value)}
              className="w-full bg-bg-surface border border-border-default rounded-lg px-3 py-2 text-sm text-text-primary"
            >
              {CONTRIB_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 rounded-lg bg-danger/5 border border-danger/20 text-xs text-danger">
              {error}
            </div>
          )}

          {/* Export button */}
          <button
            onClick={handleExport}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-accent text-white hover:bg-accent-strong active:scale-[0.98]"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                {fmt === 'zotero' ? 'Download bibliography.json' : 'Download bibliography.bib'}
              </>
            )}
          </button>

          {fmt === 'zotero' && (
            <p className="text-[10px] text-text-muted leading-relaxed text-center">
              Journal, volume and page fields may be absent for arXiv preprints — Semantic Scholar does not expose them.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
