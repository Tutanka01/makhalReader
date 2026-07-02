import { useState, useMemo } from 'react'
import { format } from 'date-fns'
import {
  ExternalLink,
  X,
  FileText,
  Globe,
  Bot,
  ArrowLeft,
  Maximize2,
  Minimize2,
  Users,
  Calendar,
  Tag,
} from 'lucide-react'
import type { Article } from '../types'

interface PaperViewProps {
  article: Article
  fontSize: number
}

type PdfMode = 'none' | 'panel' | 'full'

/**
 * Safari on iOS/iPadOS cannot render PDFs in iframes — it shows a blank page.
 * Detection: classic UA check + iPadOS 13+ (reports as MacIntel with touch).
 */
function detectIOS(): boolean {
  if (typeof navigator === 'undefined') return false
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  )
}

function parseAuthors(authorStr: string | null): string[] {
  if (!authorStr) return []
  return authorStr
    .split(/,\s*(?:and\s+)?|;\s*/)
    .map(a => a.trim())
    .filter(Boolean)
}

function extractSubjects(html: string | null): string[] {
  if (!html) return []
  try {
    const m = html.match(/arxiv-subjects[^>]*>.*?<em>([^<]+)<\/em>/s)
    if (m) {
      return m[1]
        .replace(/^Categories:\s*/i, '')
        .split(/[;,]/)
        .map(s => s.trim())
        .filter(Boolean)
    }
  } catch {}
  return []
}

function arxivIdFromUrl(url: string): string | null {
  const m = url.match(/arxiv\.org\/abs\/([0-9]{4}\.[0-9]+(v\d+)?|[a-z\-]+\/\d{7})/i)
  return m ? m[1].replace(/v\d+$/, '') : null
}

function ScorePill({ score }: { score: number | null }) {
  if (score === null) return null
  const tone =
    score >= 8 ? 'text-score-high bg-score-high/10 border-score-high/30'
    : score >= 6 ? 'text-score-mid bg-score-mid/10 border-score-mid/30'
    : 'text-text-muted bg-bg-elevated border-border-default'
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-bold tabular-nums px-2 py-0.5 rounded-full border ${tone}`}
    >
      {score.toFixed(1)}
      <span className="font-normal opacity-60">/ 10</span>
    </span>
  )
}

export function PaperView({ article, fontSize }: PaperViewProps) {
  const [pdfMode, setPdfMode] = useState<PdfMode>('none')
  const isIOS = useMemo(() => detectIOS(), [])

  const paperId = arxivIdFromUrl(article.url)
  const pdfUrl = paperId ? `https://arxiv.org/pdf/${paperId}` : null
  const htmlUrl = paperId ? `https://ar5iv.org/abs/${paperId}` : null
  const authors = parseAuthors(article.author)
  const subjects = extractSubjects(article.content_html)
  const publishedDate = article.published_at
    ? format(new Date(article.published_at), 'MMMM d, yyyy')
    : null

  const togglePdf = () => {
    if (pdfMode === 'none') {
      // On iOS, iframes can't render PDFs — go directly to ar5iv HTML viewer
      if (isIOS) {
        setPdfMode(window.innerWidth >= 1024 ? 'panel' : 'full')
      } else {
        setPdfMode(window.innerWidth >= 1024 ? 'panel' : 'full')
      }
    } else {
      setPdfMode('none')
    }
  }

  // Use ar5iv HTML in iframe by default (more reliable than arXiv PDF framing).
  // PDF stays available via "open in new tab" links.
  const viewerUrl = htmlUrl || pdfUrl
  const viewerLabel = htmlUrl ? 'HTML Viewer' : 'PDF'

  // ── Full-screen viewer mode ───────────────────────────────────────────────
  if (pdfMode === 'full' && viewerUrl) {
    return (
      <div className="flex flex-col flex-1 min-h-0 bg-bg-base">
        <div className="flex items-center justify-between px-3 py-2 bg-bg-surface border-b border-border-subtle flex-shrink-0 gap-2">
          <button
            onClick={() => setPdfMode('none')}
            className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors flex-shrink-0"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to abstract
          </button>
          <div className="flex items-center gap-3 flex-shrink-0">
            <button
              onClick={() => setPdfMode('panel')}
              className="hidden lg:flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            >
              <Minimize2 className="w-3 h-3" />
              Split view
            </button>
            {pdfUrl && (
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent-blue hover:underline"
              >
                {isIOS ? 'Open PDF ↗' : 'Open in new tab'}
              </a>
            )}
          </div>
        </div>
        {/* iOS notice banner */}
        {isIOS && (
          <div className="flex items-center justify-between px-3 py-1.5 bg-bg-elevated border-b border-border-subtle flex-shrink-0">
            <span className="text-xs text-text-muted">
              Affichage HTML (ar5iv) — Safari iOS ne supporte pas les PDFs inline
            </span>
            {pdfUrl && (
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-accent-blue hover:underline flex-shrink-0 ml-3"
              >
                📄 Ouvrir le PDF
              </a>
            )}
          </div>
        )}
        <iframe
          src={viewerUrl}
          className="flex-1 w-full border-0"
          title={isIOS ? 'Paper HTML (ar5iv)' : 'Paper PDF'}
        />
      </div>
    )
  }

  // ── Abstract + optional split PDF panel ──────────────────────────────────
  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">

      {/* ── Left / main: paper content ── */}
      <div
        className={`flex flex-col overflow-y-auto transition-all duration-300 ${
          pdfMode === 'panel'
            ? 'w-[420px] flex-shrink-0 border-r border-border-default'
            : 'flex-1'
        }`}
      >
        <div
          className="px-6 py-8 pb-24 max-w-2xl mx-auto w-full"
          style={{ fontSize: `${fontSize}px` }}
        >

          {/* Subject categories */}
          {subjects.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-5">
              <Tag className="w-3 h-3 text-text-muted self-center flex-shrink-0" />
              {subjects.slice(0, 6).map(s => (
                <span
                  key={s}
                  className="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold tracking-wide bg-accent-blue/10 text-accent-blue border border-accent-blue/25"
                >
                  {s}
                </span>
              ))}
            </div>
          )}

          {/* Title */}
          <h1
            className="font-bold leading-tight text-text-primary mb-5"
            style={{ fontFamily: 'Georgia, "Times New Roman", serif', fontSize: '1.45em', lineHeight: 1.35 }}
          >
            {article.title}
          </h1>

          {/* Authors */}
          {authors.length > 0 && (
            <div className="flex flex-wrap items-start gap-1.5 mb-5">
              <Users className="w-3.5 h-3.5 text-text-muted mt-0.5 flex-shrink-0" />
              {authors.slice(0, 7).map((author, i) => (
                <span
                  key={i}
                  className="text-xs text-text-secondary bg-bg-elevated px-2.5 py-1 rounded-full border border-border-default hover:border-border-subtle hover:text-text-primary transition-colors"
                >
                  {author}
                </span>
              ))}
              {authors.length > 7 && (
                <span className="text-xs text-text-muted px-2 py-1">
                  +{authors.length - 7} more
                </span>
              )}
            </div>
          )}

          {/* Meta: date + arXiv ID */}
          <div className="flex flex-wrap items-center gap-3 mb-8 pb-6 border-b border-border-subtle">
            {publishedDate && (
              <div className="flex items-center gap-1.5 text-xs text-text-muted">
                <Calendar className="w-3 h-3" />
                {publishedDate}
              </div>
            )}
            {paperId && (
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg border border-border-default bg-bg-elevated text-text-muted transition-colors hover:border-accent-blue/45 hover:text-accent-blue"
              >
                <span className="opacity-50">arXiv:</span>
                {paperId}
                <ExternalLink className="w-3 h-3 opacity-60" />
              </a>
            )}
          </div>

          {/* Abstract */}
          <section className="mb-7">
            <div
              className="relative pl-5 py-1 border-l-[3px] border-accent-blue/50"
            >
              <p
                className="text-[11px] font-bold uppercase tracking-[0.12em] mb-3 text-accent-blue/80"
              >
                Abstract
              </p>
              <p
                className="text-text-primary leading-relaxed"
                style={{ fontFamily: 'Georgia, serif', lineHeight: 1.85, fontSize: '0.93em' }}
              >
                {article.content_text || 'Abstract not available.'}
              </p>
            </div>
          </section>

          {/* AI Analysis */}
          {article.summary_bullets.length > 0 && (
            <section className="mb-7 rounded-xl overflow-hidden border border-border-default">
              <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-border-subtle bg-bg-elevated">
                <div className="flex items-center gap-2">
                  <Bot className="w-3.5 h-3.5 text-accent-blue flex-shrink-0" />
                  <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-text-secondary">
                    AI Analysis
                  </span>
                </div>
                <ScorePill score={article.score} />
              </div>
              <div className="px-4 py-4 space-y-3 bg-bg-surface">
                {article.summary_bullets.map((bullet, i) => (
                  <div key={i} className="flex gap-2.5 leading-relaxed" style={{ fontSize: '0.88em' }}>
                    <span className="text-accent-blue flex-shrink-0 mt-0.5 font-bold">›</span>
                    <span className="text-text-secondary">{bullet}</span>
                  </div>
                ))}
                {article.reason && (
                  <p
                    className="pt-3 mt-1 border-t border-border-subtle text-text-muted italic leading-relaxed"
                    style={{ fontSize: '0.82em' }}
                  >
                    {article.reason}
                  </p>
                )}
              </div>
            </section>
          )}

          {/* Action buttons */}
          <div className="flex flex-wrap gap-3">
            {(pdfUrl || htmlUrl) && (
              <button
                onClick={togglePdf}
                className={`flex-1 min-w-[130px] flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-semibold transition-all duration-150 active:scale-95 ${
                  pdfMode !== 'none'
                    ? 'bg-accent-blue/20 text-accent-blue border border-accent-blue/40'
                    : 'bg-accent-blue text-white'
                }`}
                style={{ fontSize: '0.875em' }}
              >
                <FileText className="w-4 h-4 flex-shrink-0" />
                {pdfMode !== 'none' ? 'Hide viewer' : htmlUrl ? 'Read paper (HTML)' : 'View PDF'}
              </button>
            )}
            {htmlUrl && (
              <a
                href={htmlUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 min-w-[130px] flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-semibold border border-border-default text-text-secondary hover:text-text-primary hover:border-border-subtle transition-all active:scale-95"
                style={{ background: 'var(--color-bg-elevated)', fontSize: '0.875em' }}
              >
                <Globe className="w-4 h-4 flex-shrink-0" />
                HTML version
              </a>
            )}
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-1.5 px-4 py-3 rounded-xl border border-border-default text-text-muted hover:text-text-secondary transition-all active:scale-95"
              style={{ background: 'var(--color-bg-surface)', fontSize: '0.875em' }}
              title="Open on arXiv"
            >
              <ExternalLink className="w-4 h-4" />
              arXiv
            </a>
          </div>

        </div>
      </div>

      {/* ── Right: viewer split panel (desktop only) ── */}
      {pdfMode === 'panel' && viewerUrl && (
        <div className="flex-1 flex flex-col min-h-0 hidden lg:flex">
          <div className="flex items-center justify-between px-3 py-2 bg-bg-surface border-b border-border-subtle flex-shrink-0">
            <span className="text-xs text-text-muted font-medium">{viewerLabel}</span>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPdfMode('full')}
                className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
              >
                <Maximize2 className="w-3 h-3" />
                Full screen
              </button>
              {pdfUrl && (
                <a
                  href={pdfUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-accent-blue hover:underline"
                >
                  {isIOS ? 'PDF ↗' : 'Open in tab'}
                </a>
              )}
              <button
                onClick={() => setPdfMode('none')}
                className="p-0.5 text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <iframe
            src={viewerUrl}
            className="flex-1 w-full border-0 bg-bg-base"
            title={isIOS ? 'Paper HTML (ar5iv)' : 'Paper PDF'}
          />
        </div>
      )}

    </div>
  )
}
