import { useEffect, useRef, useState } from 'react'
import { formatDistanceToNow, format } from 'date-fns'
import {
  ArrowLeft,
  Bookmark,
  BookmarkCheck,
  ExternalLink,
  Link,
  RotateCcw,
  Loader2,
  AArrowDown,
  AArrowUp,
} from 'lucide-react'
import { useArticlesStore } from '../store/articles'
import { ScoreBar } from './ScoreBar'

const FONT_SIZE_KEY = 'makhal_reader_font_size'
const FONT_SIZE_MIN = 14
const FONT_SIZE_MAX = 22
const FONT_SIZE_DEFAULT = 17

function getSavedFontSize(): number {
  try {
    const v = localStorage.getItem(FONT_SIZE_KEY)
    if (v) {
      const n = parseInt(v, 10)
      if (n >= FONT_SIZE_MIN && n <= FONT_SIZE_MAX) return n
    }
  } catch {}
  return FONT_SIZE_DEFAULT
}

interface ReaderViewProps {
  articleId: number
  onBack?: () => void
  sidebarOpen: boolean
  onToggleSidebar: () => void
}

export function ReaderView({ articleId, onBack, sidebarOpen, onToggleSidebar }: ReaderViewProps) {
  const { selectedArticle, fetchArticle, markRead, markUnread, toggleBookmark } = useArticlesStore()
  const [fontSize, setFontSize] = useState(getSavedFontSize)
  const [scrollProgress, setScrollProgress] = useState(0)
  const [copied, setCopied] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchArticle(articleId)
    // Reset scroll progress on article change
    setScrollProgress(0)
    if (scrollRef.current) scrollRef.current.scrollTop = 0
  }, [articleId])

  // Auto-mark as read after 5s
  useEffect(() => {
    if (selectedArticle && !selectedArticle.read_at) {
      const timer = setTimeout(() => markRead(selectedArticle.id), 5000)
      return () => clearTimeout(timer)
    }
  }, [selectedArticle?.id])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const max = el.scrollHeight - el.clientHeight
    if (max <= 0) return
    setScrollProgress(Math.round((el.scrollTop / max) * 100))
  }

  const adjustFontSize = (delta: number) => {
    setFontSize(prev => {
      const next = Math.max(FONT_SIZE_MIN, Math.min(FONT_SIZE_MAX, prev + delta))
      try { localStorage.setItem(FONT_SIZE_KEY, String(next)) } catch {}
      return next
    })
  }

  const copyLink = () => {
    if (selectedArticle) {
      navigator.clipboard.writeText(selectedArticle.url).catch(() => {})
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  // ── Loading state ──
  if (!selectedArticle || selectedArticle.id !== articleId) {
    return (
      <div className="flex flex-col h-full">
        <Toolbar
          sidebarOpen={sidebarOpen}
          onToggleSidebar={onToggleSidebar}
          onBack={onBack}
          loading
        />
        <div className="flex items-center justify-center flex-1 bg-bg-base">
          <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
        </div>
      </div>
    )
  }

  const article = selectedArticle
  const publishedDate = article.published_at
    ? format(new Date(article.published_at), 'MMM d, yyyy')
    : null
  const relativeDate = article.published_at
    ? formatDistanceToNow(new Date(article.published_at), { addSuffix: true })
    : null
  const heroImage = article.images?.[0] || null

  return (
    <div className="flex flex-col h-full bg-bg-base overflow-hidden">

      {/* Reading progress bar — 2px at very top */}
      <div className="h-0.5 w-full bg-bg-elevated flex-shrink-0">
        <div
          className="h-full bg-accent-blue transition-all duration-150"
          style={{ width: `${scrollProgress}%` }}
        />
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle bg-bg-surface flex-shrink-0">
        <div className="flex items-center gap-1">
          {/* Sidebar toggle (desktop only) */}
          <button
            onClick={onToggleSidebar}
            className="hidden lg:flex p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
            title={sidebarOpen ? 'Hide sidebar  [' : 'Show sidebar  ['}
          >
            {sidebarOpen ? <PanelLeftCloseIcon /> : <PanelLeftOpenIcon />}
          </button>

          {/* Back button (mobile) */}
          {onBack && (
            <button
              onClick={onBack}
              className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
              aria-label="Back"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}

          <div className="w-32">
            <ScoreBar score={article.score} />
          </div>
        </div>

        <div className="flex items-center gap-0.5">
          {/* Font size */}
          <button
            onClick={() => adjustFontSize(-1)}
            disabled={fontSize <= FONT_SIZE_MIN}
            className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary disabled:opacity-30"
            title="Decrease font size"
          >
            <AArrowDown className="w-4 h-4" />
          </button>
          <span className="text-xs text-text-muted tabular-nums w-6 text-center">{fontSize}</span>
          <button
            onClick={() => adjustFontSize(1)}
            disabled={fontSize >= FONT_SIZE_MAX}
            className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary disabled:opacity-30"
            title="Increase font size"
          >
            <AArrowUp className="w-4 h-4" />
          </button>

          <div className="w-px h-4 bg-border-default mx-1" />

          {/* Read/unread toggle */}
          <button
            onClick={() => article.read_at ? markUnread(article.id) : markRead(article.id)}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              article.read_at ? 'text-accent-green' : 'text-text-secondary hover:text-text-primary'
            }`}
            title={article.read_at ? 'Mark unread' : 'Mark read'}
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          {/* Bookmark */}
          <button
            onClick={() => toggleBookmark(article.id)}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              article.bookmarked ? 'text-accent-blue' : 'text-text-secondary hover:text-text-primary'
            }`}
            title="Bookmark"
          >
            {article.bookmarked ? <BookmarkCheck className="w-4 h-4" /> : <Bookmark className="w-4 h-4" />}
          </button>

          {/* Copy link */}
          <button
            onClick={copyLink}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              copied ? 'text-accent-green' : 'text-text-secondary hover:text-text-primary'
            }`}
            title={copied ? 'Copied!' : 'Copy link'}
          >
            <Link className="w-4 h-4" />
          </button>

          {/* Open original */}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
            title="Open original"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>

      {/* Scrollable content */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto"
        onScroll={handleScroll}
      >
        <article className="max-w-2xl mx-auto px-5 py-8 pb-20">

          {/* Tags */}
          {article.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-4">
              {article.tags.map(tag => (
                <span key={tag} className="px-2 py-0.5 bg-bg-elevated rounded-full text-xs text-text-muted font-medium">
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Title */}
          <h1 className="text-2xl font-bold leading-tight text-text-primary mb-3">
            {article.title}
          </h1>

          {/* Meta */}
          <div className="flex flex-wrap items-center gap-1.5 text-sm text-text-muted mb-5 pb-5 border-b border-border-subtle">
            {article.author && (
              <span className="font-medium text-text-secondary">{article.author}</span>
            )}
            {article.author && (publishedDate || relativeDate) && <span>·</span>}
            {publishedDate && (
              <span title={relativeDate || ''}>{publishedDate}</span>
            )}
            {relativeDate && publishedDate && (
              <span className="text-text-muted">({relativeDate})</span>
            )}
          </div>

          {/* AI Summary */}
          {article.summary_bullets.length > 0 && (
            <div className="mb-6 p-4 bg-bg-surface rounded-xl border border-border-subtle">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2.5">
                AI Summary
              </p>
              <ul className="space-y-1.5">
                {article.summary_bullets.map((bullet, i) => (
                  <li key={i} className="text-sm text-text-secondary leading-relaxed flex gap-2">
                    <span className="text-accent-blue flex-shrink-0 mt-0.5">›</span>
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
              {article.reason && (
                <p className="mt-3 pt-3 border-t border-border-subtle text-xs text-text-muted italic">
                  {article.reason}
                </p>
              )}
            </div>
          )}

          {/* Hero image */}
          {heroImage && (
            <div className="mb-6 rounded-xl overflow-hidden">
              <img
                src={heroImage}
                alt=""
                className="w-full h-auto"
                loading="lazy"
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            </div>
          )}

          {/* Body */}
          {article.content_html ? (
            <div
              className="reader-content"
              style={{ fontSize: `${fontSize}px`, lineHeight: 1.75 }}
              dangerouslySetInnerHTML={{ __html: article.content_html }}
            />
          ) : article.content_text ? (
            <div
              className="font-serif text-text-primary space-y-4"
              style={{ fontSize: `${fontSize}px`, lineHeight: 1.75 }}
            >
              {article.content_text.split('\n\n').filter(Boolean).map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
          ) : (
            <div className="text-text-muted text-sm text-center py-8">
              <p>Contenu non disponible.</p>
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-accent-blue hover:underline"
              >
                Lire sur le site original <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}

          {/* Footer */}
          <div className="mt-10 pt-6 border-t border-border-subtle text-center">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm text-accent-blue hover:underline"
            >
              Lire l'article original
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>
        </article>
      </div>
    </div>
  )
}

// ── Internal: skeleton toolbar for loading state ──
function Toolbar({
  sidebarOpen,
  onToggleSidebar,
  onBack,
  loading: _loading,
}: {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onBack?: () => void
  loading?: boolean
}) {
  return (
    <div className="flex items-center px-3 py-2 border-b border-border-subtle bg-bg-surface flex-shrink-0">
      <div className="flex items-center gap-1">
        <button
          onClick={onToggleSidebar}
          className="hidden lg:flex p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary"
        >
          {sidebarOpen ? <PanelLeftCloseIcon /> : <PanelLeftOpenIcon />}
        </button>
        {onBack && (
          <button onClick={onBack} className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary">
            <ArrowLeft className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}

// Inline SVG icons (avoids adding lucide-react panel icons that may not exist in older versions)
function PanelLeftCloseIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2"/>
      <path d="M9 3v18"/>
      <path d="m16 15-3-3 3-3"/>
    </svg>
  )
}

function PanelLeftOpenIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2"/>
      <path d="M9 3v18"/>
      <path d="m14 9 3 3-3 3"/>
    </svg>
  )
}
