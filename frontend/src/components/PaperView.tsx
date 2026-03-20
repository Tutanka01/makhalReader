import { useState } from 'react'
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
  const color =
    score >= 8 ? '#3FB950' : score >= 6 ? '#D29922' : '#6B7685'
  const bg =
    score >= 8 ? 'rgba(63,185,80,0.12)' : score >= 6 ? 'rgba(210,153,34,0.12)' : 'rgba(107,118,133,0.12)'
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-bold tabular-nums px-2 py-0.5 rounded-full border"
      style={{ color, background: bg, borderColor: color + '40' }}
    >
      {score.toFixed(1)}
      <span className="font-normal opacity-60">/ 10</span>
    </span>
  )
}

export function PaperView({ article, fontSize }: PaperViewProps) {
  const [pdfMode, setPdfMode] = useState<PdfMode>('none')

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
      setPdfMode(window.innerWidth >= 1024 ? 'panel' : 'full')
    } else {
      setPdfMode('none')
    }
  }

  // ── Full-screen PDF mode ──────────────────────────────────────────────────
  if (pdfMode === 'full' && pdfUrl) {
    return (
      <div className="flex flex-col flex-1 min-h-0 bg-bg-base">
        <div className="flex items-center justify-between px-3 py-2 bg-bg-surface border-b border-border-subtle flex-shrink-0">
          <button
            onClick={() => setPdfMode('none')}
            className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to abstract
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setPdfMode('panel')}
              className="hidden lg:flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            >
              <Minimize2 className="w-3 h-3" />
              Split view
            </button>
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-accent-blue hover:underline"
            >
              Open in new tab
            </a>
          </div>
        </div>
        <iframe src={pdfUrl} className="flex-1 w-full border-0" title="Paper PDF" />
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
                  className="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold tracking-wide"
                  style={{
                    background: 'rgba(68,147,248,0.1)',
                    color: '#4493F8',
                    border: '1px solid rgba(68,147,248,0.25)',
                  }}
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
                className="flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg border transition-colors group"
                style={{
                  background: 'rgba(30,36,48,1)',
                  borderColor: '#2A3341',
                  color: '#A0ADB8',
                }}
                onMouseEnter={e => {
                  ;(e.currentTarget as HTMLElement).style.borderColor = '#4493F8'
                  ;(e.currentTarget as HTMLElement).style.color = '#4493F8'
                }}
                onMouseLeave={e => {
                  ;(e.currentTarget as HTMLElement).style.borderColor = '#2A3341'
                  ;(e.currentTarget as HTMLElement).style.color = '#A0ADB8'
                }}
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
              className="relative pl-5 py-1"
              style={{ borderLeft: '3px solid rgba(68,147,248,0.5)' }}
            >
              <p
                className="text-[11px] font-bold uppercase tracking-[0.12em] mb-3"
                style={{ color: 'rgba(68,147,248,0.8)' }}
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
              <div
                className="flex items-center justify-between gap-2 px-4 py-3 border-b border-border-subtle"
                style={{ background: '#1E2430' }}
              >
                <div className="flex items-center gap-2">
                  <Bot className="w-3.5 h-3.5 text-accent-blue flex-shrink-0" />
                  <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-text-secondary">
                    AI Analysis
                  </span>
                </div>
                <ScorePill score={article.score} />
              </div>
              <div className="px-4 py-4 space-y-3" style={{ background: '#161B22' }}>
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
            {pdfUrl && (
              <button
                onClick={togglePdf}
                className="flex-1 min-w-[130px] flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-semibold transition-all duration-150 active:scale-95"
                style={{
                  background: pdfMode !== 'none' ? 'rgba(68,147,248,0.25)' : '#4493F8',
                  color: pdfMode !== 'none' ? '#4493F8' : '#fff',
                  fontSize: '0.875em',
                  border: pdfMode !== 'none' ? '1px solid rgba(68,147,248,0.4)' : 'none',
                }}
              >
                <FileText className="w-4 h-4 flex-shrink-0" />
                {pdfMode !== 'none' ? 'Hide PDF' : 'View PDF'}
              </button>
            )}
            {htmlUrl && (
              <a
                href={htmlUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 min-w-[130px] flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-semibold border border-border-default text-text-secondary hover:text-text-primary hover:border-border-subtle transition-all active:scale-95"
                style={{ background: '#1E2430', fontSize: '0.875em' }}
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
              style={{ background: '#161B22', fontSize: '0.875em' }}
              title="Open on arXiv"
            >
              <ExternalLink className="w-4 h-4" />
              arXiv
            </a>
          </div>

        </div>
      </div>

      {/* ── Right: PDF split panel (desktop only) ── */}
      {pdfMode === 'panel' && pdfUrl && (
        <div className="flex-1 flex flex-col min-h-0 hidden lg:flex">
          <div className="flex items-center justify-between px-3 py-2 bg-bg-surface border-b border-border-subtle flex-shrink-0">
            <span className="text-xs text-text-muted font-medium">PDF</span>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPdfMode('full')}
                className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
              >
                <Maximize2 className="w-3 h-3" />
                Full screen
              </button>
              <a
                href={pdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent-blue hover:underline"
              >
                Open in tab
              </a>
              <button
                onClick={() => setPdfMode('none')}
                className="p-0.5 text-text-muted hover:text-text-primary transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <iframe
            src={pdfUrl}
            className="flex-1 w-full border-0 bg-bg-base"
            title="Paper PDF"
          />
        </div>
      )}

    </div>
  )
}
