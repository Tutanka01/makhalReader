import { useEffect, useRef, useState } from 'react'
import { formatDistanceToNow, format } from 'date-fns'
import {
  ArrowLeft,
  Bookmark,
  BookmarkCheck,
  Bot,
  ExternalLink,
  Highlighter,
  Link,
  RotateCcw,
  Loader2,
  AArrowDown,
  AArrowUp,
  ThumbsUp,
  ThumbsDown,
} from 'lucide-react'
import { useArticlesStore } from '../store/articles'
import { useHighlightsStore } from '../store/highlights'
import type { Highlight } from '../types'
import { ScoreBar } from './ScoreBar'
import { PaperView } from './PaperView'
import { HighlightPopover } from './HighlightPopover'
import { HighlightList } from './HighlightList'
import { AskAIPanel } from './AskAIPanel'

// Heuristic: does this string look like HTML rather than plain text?
// Checks for at least one block-level or common inline HTML tag.
function looksLikeHtml(text: string): boolean {
  return /<(p|div|h[1-6]|ul|ol|li|blockquote|pre|code|a|strong|em|br|img|table|thead|tbody|tr|td|th)\b/i.test(text)
}

// ── Highlight utilities ──────────────────────────────────────────────────

interface PendingSelection {
  selectedText: string
  prefixContext: string
  suffixContext: string
  /** Viewport coords of the selection rectangle */
  position: { x: number; top: number; bottom: number }
}

/** Get selected text + surrounding context from within a container element. */
function getSelectionContext(container: HTMLElement): PendingSelection | null {
  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null

  const range = sel.getRangeAt(0)
  const selectedText = sel.toString().trim()
  if (!selectedText || selectedText.length < 3) return null

  if (!container.contains(range.commonAncestorContainer)) return null

  const fullText = container.textContent || ''
  const idx = fullText.indexOf(selectedText)
  const prefixContext = idx >= 0 ? fullText.slice(Math.max(0, idx - 20), idx) : ''
  const suffixContext = idx >= 0 ? fullText.slice(idx + selectedText.length, idx + selectedText.length + 20) : ''

  const rect = range.getBoundingClientRect()
  return {
    selectedText,
    prefixContext,
    suffixContext,
    position: { x: rect.left + rect.width / 2, top: rect.top, bottom: rect.bottom },
  }
}

/**
 * Find the first index of `search` in `html` that is in text content (not inside a tag).
 * Prevents matching inside href="..." or other attributes.
 */
function findInTextContent(html: string, search: string, startFrom = 0): number {
  let idx = startFrom
  while (true) {
    const found = html.indexOf(search, idx)
    if (found === -1) return -1
    // Is this inside a tag? Check if the last '<' before `found` has no closing '>' before `found`.
    const before = html.slice(0, found)
    const lastOpen = before.lastIndexOf('<')
    const lastClose = before.lastIndexOf('>')
    if (lastOpen <= lastClose) return found   // in text content ✓
    idx = found + 1                           // inside a tag — skip
  }
}

/** Safely inject <mark> tags into HTML, only matching text content (never inside tag attributes). */
function applyHighlights(html: string, highlights: Highlight[]): string {
  if (!highlights.length) return html

  let result = html

  for (const h of highlights) {
    if (result.includes(`data-hid="${h.id}"`)) continue

    const text = h.selected_text
    const markOpen = `<mark data-hid="${h.id}" class="highlight-${h.color}">`
    const markClose = `</mark>`

    let matchIdx = -1

    // Try with prefix context (more specific — avoids wrong occurrence)
    if (h.prefix_context) {
      const prefix = h.prefix_context.slice(-8)
      const prefixIdx = findInTextContent(result, prefix)
      if (prefixIdx >= 0) {
        matchIdx = findInTextContent(result, text, prefixIdx + prefix.length - 2)
      }
    }

    // Fallback: first occurrence in text content
    if (matchIdx === -1) matchIdx = findInTextContent(result, text)

    if (matchIdx >= 0) {
      result = result.slice(0, matchIdx) + markOpen + text + markClose + result.slice(matchIdx + text.length)
    }
  }

  return result
}

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
  onNext?: () => void
  hasNext?: boolean
}

function isArxivUrl(url: string): boolean {
  return /arxiv\.org\/abs\//i.test(url)
}

export function ReaderView({ articleId, onBack, sidebarOpen, onToggleSidebar, onNext, hasNext }: ReaderViewProps) {
  const { selectedArticle, fetchArticle, markRead, markUnread, toggleBookmark, submitFeedback } = useArticlesStore()
  const { highlights, fetchHighlights, createHighlight, deleteHighlight } = useHighlightsStore()
  const [fontSize, setFontSize] = useState(getSavedFontSize)
  const [scrollProgress, setScrollProgress] = useState(0)
  const [copied, setCopied] = useState(false)
  const [showHighlightList, setShowHighlightList] = useState(false)
  const [showAskPanel, setShowAskPanel] = useState(false)
  const [pendingSelection, setPendingSelection] = useState<PendingSelection | null>(null)
  const [noteTooltip, setNoteTooltip] = useState<{ note: string; x: number; y: number } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const articleHighlightsRef = useRef<typeof articleHighlights>([])
  const autoReadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const autoReadScheduledForRef = useRef<number | null>(null)

  const articleHighlights = highlights[articleId] ?? []
  articleHighlightsRef.current = articleHighlights

  useEffect(() => {
    fetchArticle(articleId)
    fetchHighlights(articleId)
    // Reset scroll progress on article change
    setScrollProgress(0)
    setPendingSelection(null)
    if (scrollRef.current) scrollRef.current.scrollTop = 0
    // Cancel any pending auto-read timer when switching articles
    if (autoReadTimerRef.current) {
      clearTimeout(autoReadTimerRef.current)
      autoReadTimerRef.current = null
      autoReadScheduledForRef.current = null
    }
  }, [articleId])

  // Auto-mark as read after 5s — guarded to fire only once per article
  useEffect(() => {
    if (
      selectedArticle &&
      !selectedArticle.read_at &&
      autoReadScheduledForRef.current !== selectedArticle.id
    ) {
      autoReadScheduledForRef.current = selectedArticle.id
      autoReadTimerRef.current = setTimeout(() => markRead(selectedArticle.id), 5000)
      return () => {
        if (autoReadTimerRef.current) clearTimeout(autoReadTimerRef.current)
      }
    }
  }, [selectedArticle?.id, selectedArticle?.read_at])

  // Detect text selection for highlighting
  useEffect(() => {
    const handleMouseUp = () => {
      const container = contentRef.current
      if (!container) return
      const ctx = getSelectionContext(container)
      if (ctx) setPendingSelection(ctx)
    }
    document.addEventListener('mouseup', handleMouseUp)
    document.addEventListener('touchend', handleMouseUp)
    return () => {
      document.removeEventListener('mouseup', handleMouseUp)
      document.removeEventListener('touchend', handleMouseUp)
    }
  }, [])

  // Note tooltip on highlight hover
  useEffect(() => {
    const container = contentRef.current
    if (!container) return

    const handleMouseOver = (e: MouseEvent) => {
      const mark = (e.target as HTMLElement).closest('mark[data-hid]') as HTMLElement | null
      if (!mark) { setNoteTooltip(null); return }
      const hid = parseInt(mark.getAttribute('data-hid') || '0', 10)
      const h = articleHighlightsRef.current.find(h => h.id === hid)
      if (!h?.note) { setNoteTooltip(null); return }
      const rect = mark.getBoundingClientRect()
      setNoteTooltip({ note: h.note, x: rect.left + rect.width / 2, y: rect.top })
    }

    const handleMouseLeave = () => setNoteTooltip(null)

    container.addEventListener('mouseover', handleMouseOver)
    container.addEventListener('mouseleave', handleMouseLeave)
    return () => {
      container.removeEventListener('mouseover', handleMouseOver)
      container.removeEventListener('mouseleave', handleMouseLeave)
    }
  }, [])

  const handleSaveHighlight = async (color: string, note: string) => {
    if (!pendingSelection) return
    setPendingSelection(null)
    window.getSelection()?.removeAllRanges()
    await createHighlight(articleId, {
      selected_text: pendingSelection.selectedText,
      prefix_context: pendingSelection.prefixContext,
      suffix_context: pendingSelection.suffixContext,
      color,
      note: note || undefined,
    })
  }

  const handleScrollToHighlight = (h: Highlight) => {
    const el = document.querySelector(`mark[data-hid="${h.id}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

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
  const isPaper = isArxivUrl(article.url)

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
          {/* Font size — hidden on small screens to avoid clipping feedback buttons */}
          <button
            onClick={() => adjustFontSize(-1)}
            disabled={fontSize <= FONT_SIZE_MIN}
            className="hidden sm:flex p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary disabled:opacity-30"
            title="Decrease font size"
          >
            <AArrowDown className="w-4 h-4" />
          </button>
          <span className="hidden sm:inline text-xs text-text-muted tabular-nums w-6 text-center">{fontSize}</span>
          <button
            onClick={() => adjustFontSize(1)}
            disabled={fontSize >= FONT_SIZE_MAX}
            className="hidden sm:flex p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary disabled:opacity-30"
            title="Increase font size"
          >
            <AArrowUp className="w-4 h-4" />
          </button>

          <div className="hidden sm:block w-px h-4 bg-border-default mx-1" />

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

          {/* Feedback */}
          <div className="w-px h-4 bg-border-default mx-0.5" />
          <button
            onClick={() => submitFeedback(article.id, article.user_feedback === 1 ? 0 : 1)}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              article.user_feedback === 1 ? 'text-accent-green' : 'text-text-secondary hover:text-accent-green'
            }`}
            title={article.user_feedback === 1 ? 'Remove like' : 'Like — improve future scoring'}
          >
            <ThumbsUp className="w-4 h-4" />
          </button>
          <button
            onClick={() => submitFeedback(article.id, article.user_feedback === -1 ? 0 : -1)}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              article.user_feedback === -1 ? 'text-red-400' : 'text-text-secondary hover:text-red-400'
            }`}
            title={article.user_feedback === -1 ? 'Remove dislike' : 'Dislike — improve future scoring'}
          >
            <ThumbsDown className="w-4 h-4" />
          </button>

          {/* Highlight list */}
          <div className="w-px h-4 bg-border-default mx-0.5" />
          <button
            onClick={() => { setShowHighlightList((v) => !v); setShowAskPanel(false) }}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              showHighlightList ? 'text-accent-yellow' : 'text-text-secondary hover:text-text-primary'
            }`}
            title={`Surlignages (${articleHighlights.length})`}
          >
            <Highlighter className="w-4 h-4" />
          </button>

          {/* Ask AI */}
          <button
            onClick={() => { setShowAskPanel((v) => !v); setShowHighlightList(false) }}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              showAskPanel ? 'text-accent-blue' : 'text-text-secondary hover:text-text-primary'
            }`}
            title="Poser une question à l'IA"
          >
            <Bot className="w-4 h-4" />
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

      {/* Paper view — dedicated layout for ArXiv papers */}
      {isPaper ? (
        <PaperView article={article} fontSize={fontSize} />
      ) : (
        /* Scrollable content — regular articles */
        <div className="flex-1 overflow-hidden relative flex flex-col min-h-0">
          {/* Highlight list overlay — absolute, doesn't affect flex flow */}
          {showHighlightList && (
            <HighlightList
              highlights={articleHighlights}
              onDelete={(id) => deleteHighlight(articleId, id)}
              onClose={() => setShowHighlightList(false)}
              onScrollTo={handleScrollToHighlight}
            />
          )}

          {/* Scrollable article — flex-1 */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto min-h-0"
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
                ref={contentRef}
                className="reader-content"
                style={{ fontSize: `${fontSize}px`, lineHeight: 1.75 }}
                dangerouslySetInnerHTML={{ __html: applyHighlights(article.content_html, articleHighlights) }}
              />
            ) : article.content_text ? (
              looksLikeHtml(article.content_text) ? (
                <div
                  ref={contentRef}
                  className="reader-content"
                  style={{ fontSize: `${fontSize}px`, lineHeight: 1.75 }}
                  dangerouslySetInnerHTML={{ __html: applyHighlights(article.content_text, articleHighlights) }}
                />
              ) : (
                <div
                  ref={contentRef}
                  className="font-serif text-text-primary space-y-4"
                  style={{ fontSize: `${fontSize}px`, lineHeight: 1.75 }}
                >
                  {article.content_text.split('\n\n').filter(Boolean).map((para, i) => (
                    <p key={i}>{para}</p>
                  ))}
                </div>
              )
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

            {/* Auto-advance — next article */}
            {hasNext && onNext && scrollProgress >= 80 && (
              <button
                onClick={onNext}
                className="mt-6 w-full flex items-center justify-between px-4 py-3 rounded-xl bg-bg-surface border border-border-subtle hover:border-accent-blue/40 hover:bg-bg-elevated transition-all duration-200 group"
              >
                <span className="text-xs text-text-muted group-hover:text-text-secondary transition-colors">
                  Article suivant
                </span>
                <svg
                  className="w-4 h-4 text-text-muted group-hover:text-accent-blue transition-colors translate-x-0 group-hover:translate-x-0.5 duration-200"
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            )}
          </article>
          </div>

          {/* Ask AI panel — at bottom of content area */}
          {showAskPanel && (
            <AskAIPanel
              articleId={articleId}
              onClose={() => setShowAskPanel(false)}
            />
          )}
        </div>
      )}

      {/* Highlight popover — appears on text selection */}
      {pendingSelection && (
        <HighlightPopover
          position={pendingSelection.position}
          selectedText={pendingSelection.selectedText}
          onSave={handleSaveHighlight}
          onClose={() => setPendingSelection(null)}
        />
      )}

      {/* Note tooltip — appears on hovering a highlight that has a note */}
      {noteTooltip && (
        <div
          className="fixed z-[70] pointer-events-none"
          style={{
            left: noteTooltip.x,
            top: noteTooltip.y - 10,
            transform: 'translateX(-50%) translateY(-100%)',
          }}
        >
          <div
            className="relative rounded-xl px-3 py-2 text-xs leading-relaxed shadow-2xl"
            style={{
              background: '#1E2430',
              border: '1px solid #2A3341',
              color: '#A0ADB8',
              maxWidth: 220,
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
          >
            {noteTooltip.note}
            {/* Arrow pointing down */}
            <div
              className="absolute left-1/2 -translate-x-1/2"
              style={{
                bottom: -6,
                width: 0,
                height: 0,
                borderLeft: '6px solid transparent',
                borderRight: '6px solid transparent',
                borderTop: '6px solid #2A3341',
              }}
            />
          </div>
        </div>
      )}
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
