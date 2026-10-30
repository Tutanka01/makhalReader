import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  BookmarkCheck,
  Bot,
  ChevronRight,
  CircleCheck,
  ExternalLink,
  Highlighter,
  Link,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'
import { isScorePending, useArticlesStore } from '../store/articles'
import { useHighlightsStore } from '../store/highlights'
import type { Article, Highlight } from '../types'
import type { Layout } from '../hooks/useLayout'
import { PaperView } from './PaperView'
import { HighlightPopover } from './HighlightPopover'
import { HighlightList } from './HighlightList'
import { AskAIPanel } from './AskAIPanel'
import { IconButton, Kbd, ScoreBadge } from './ui'
import { ArticleLensStrip } from './ArticleLenses'
import { getArticleLenses } from '../lenses'
import { pickHeroImage } from '../images'
import { articleDate, hostLabel, longDate } from '../format'
import { AXIS_MAX, cleanReason, parseScoreDetails, scoreAxes, scoreCaps, scoreConfidence } from '../scoreDetails'
import {
  ReadingSettings,
  getSavedFont,
  getSavedFontSize,
  saveFont,
  saveFontSize,
  type ReaderFont,
} from './ReadingSettings'


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

const NO_HIGHLIGHTS: Highlight[] = []

interface ReaderViewProps {
  articleId: number
  /** Source name taken from the list, when the article was opened from it. */
  feedName?: string
  layout: Layout
  /** Return to the list (compact/medium layouts, where the reader covers it). */
  onBack?: () => void
  /** Whether the article list currently shows next to (or over) the reader. */
  listOpen: boolean
  onToggleList?: () => void
  onNext?: () => void
  nextTitle?: string
}

function isArxivUrl(url: string): boolean {
  return /arxiv\.org\/abs\//i.test(url)
}

export function ReaderView({
  articleId,
  feedName,
  layout,
  onBack,
  listOpen,
  onToggleList,
  onNext,
  nextTitle,
}: ReaderViewProps) {
  const { selectedArticle, fetchArticle, markRead, markUnread, toggleBookmark, submitFeedback } = useArticlesStore()
  const { highlights, fetchHighlights, createHighlight, deleteHighlight } = useHighlightsStore()
  const [fontSize, setFontSize] = useState(getSavedFontSize)
  const [font, setFont] = useState<ReaderFont>(getSavedFont)
  const [copied, setCopied] = useState(false)
  const [showHighlightList, setShowHighlightList] = useState(false)
  const [showAskPanel, setShowAskPanel] = useState(false)
  const [pendingSelection, setPendingSelection] = useState<PendingSelection | null>(null)
  const [noteTooltip, setNoteTooltip] = useState<{ note: string; x: number; y: number } | null>(null)
  const [titleInView, setTitleInView] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const progressRef = useRef<HTMLDivElement>(null)
  const progressFrameRef = useRef<number | null>(null)
  const articleHighlightsRef = useRef<Highlight[]>([])
  const autoReadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const autoReadScheduledForRef = useRef<number | null>(null)

  const articleHighlights = highlights[articleId] ?? NO_HIGHLIGHTS
  articleHighlightsRef.current = articleHighlights
  const loaded = selectedArticle && selectedArticle.id === articleId ? selectedArticle : null
  const loadedId = loaded?.id ?? null

  useEffect(() => {
    fetchArticle(articleId)
    fetchHighlights(articleId)
    setPendingSelection(null)
    setTitleInView(true)
    if (scrollRef.current) scrollRef.current.scrollTop = 0
    if (progressRef.current) progressRef.current.style.transform = 'scaleX(0)'
    // Cancel any pending auto-read timer when switching articles
    if (autoReadTimerRef.current) {
      clearTimeout(autoReadTimerRef.current)
      autoReadTimerRef.current = null
      autoReadScheduledForRef.current = null
    }
  }, [articleId])

  useEffect(() => () => {
    if (progressFrameRef.current !== null) cancelAnimationFrame(progressFrameRef.current)
  }, [])

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

  // Note tooltip on highlight hover. Re-attached once the article body exists:
  // during loading there is no content element to listen on.
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
  }, [loadedId])

  // Once the big title scrolls away, repeat it in the toolbar.
  useEffect(() => {
    const title = titleRef.current
    const root = scrollRef.current
    if (!title || !root || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      ([entry]) => setTitleInView(entry.isIntersecting),
      { root, threshold: 0 },
    )
    observer.observe(title)
    return () => observer.disconnect()
  }, [loadedId])

  // Highlights are spliced into the HTML string; only redo it when the
  // article or its highlights change, not on every render.
  const bodyHtml = useMemo(() => {
    if (!loaded) return null
    const raw = loaded.content_html
      || (loaded.content_text && looksLikeHtml(loaded.content_text) ? loaded.content_text : null)
    return raw ? applyHighlights(raw, articleHighlights) : null
  }, [loaded?.id, loaded?.content_html, loaded?.content_text, articleHighlights])

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

  // Reading progress, written straight to the bar once per frame: no React
  // re-render of a long article body while scrolling.
  const handleScroll = () => {
    if (progressFrameRef.current !== null) return
    progressFrameRef.current = requestAnimationFrame(() => {
      progressFrameRef.current = null
      const el = scrollRef.current
      const bar = progressRef.current
      if (!el || !bar) return
      const max = el.scrollHeight - el.clientHeight
      bar.style.transform = `scaleX(${max > 0 ? Math.min(1, el.scrollTop / max) : 0})`
    })
  }

  const changeFontSize = (size: number) => {
    setFontSize(size)
    saveFontSize(size)
  }

  const changeFont = (next: ReaderFont) => {
    setFont(next)
    saveFont(next)
  }

  const copyLink = () => {
    if (!loaded) return
    navigator.clipboard?.writeText(loaded.url).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const compact = layout === 'compact'

  const navButtons = (
    <>
      {onToggleList && (
        <IconButton
          onClick={onToggleList}
          icon={listOpen ? PanelLeftClose : PanelLeftOpen}
          label={listOpen ? 'Masquer la liste  [' : 'Afficher la liste  ['}
        />
      )}
      {onBack && <IconButton onClick={onBack} icon={ArrowLeft} label="Retour à la liste" />}
    </>
  )

  // ── Loading state ──
  if (!loaded) {
    return (
      <div className="flex h-full flex-col bg-bg-base">
        <div className="flex h-[52px] flex-shrink-0 items-center gap-1 border-b border-border-subtle bg-bg-surface px-2 sm:px-3">
          {navButtons}
        </div>
        <div className="mx-auto w-full max-w-[44rem] px-5 pt-10 sm:px-8 sm:pt-14" aria-busy="true" aria-label="Chargement de l’article">
          <div className="briefing-shimmer mb-5 h-4 w-32 rounded" />
          <div className="briefing-shimmer mb-3 h-9 w-full rounded-md" />
          <div className="briefing-shimmer mb-8 h-9 w-2/3 rounded-md" />
          <div className="briefing-shimmer mb-10 h-36 w-full rounded-xl" />
          {[100, 96, 92, 98, 70].map((w, i) => (
            <div key={i} className="briefing-shimmer mb-3.5 h-4 rounded" style={{ width: `${w}%` }} />
          ))}
        </div>
      </div>
    )
  }

  const article = loaded
  const isPaper = isArxivUrl(article.url)
  const date = article.published_at ? new Date(article.published_at) : articleDate(article)
  const source = feedName || hostLabel(article.url)
  const host = hostLabel(article.url)
  const heroImage = pickHeroImage(article.images, article.content_html)
  const isRead = Boolean(article.read_at)
  const toggleRead = () => (isRead ? markUnread(article.id) : markRead(article.id))

  return (
    <div className={`relative flex h-full flex-col overflow-hidden bg-bg-base ${font === 'sans' ? 'reader-sans' : ''}`}>
      {/* Toolbar */}
      <div className="relative z-20 flex h-[52px] flex-shrink-0 items-center gap-2 border-b border-border-subtle bg-bg-surface px-2 sm:px-3">
        <div className="flex min-w-0 flex-1 items-center gap-1">
          {navButtons}
          <p
            aria-hidden={titleInView}
            className={`
              ml-1 min-w-0 truncate text-sm font-medium text-text-primary transition-opacity duration-200
              ${titleInView ? 'opacity-0' : 'opacity-100'}
            `}
          >
            {article.title}
          </p>
        </div>

        <div className="flex flex-shrink-0 items-center gap-0.5">
          <IconButton
            onClick={toggleRead}
            icon={CircleCheck}
            label={isRead ? 'Marquer non lu  r' : 'Marquer lu  r'}
            active={isRead}
            tone={isRead ? 'success' : 'default'}
          />
          <IconButton
            onClick={() => toggleBookmark(article.id)}
            icon={article.bookmarked ? BookmarkCheck : Bookmark}
            label={article.bookmarked ? 'Retirer des favoris  b' : 'Ajouter aux favoris  b'}
            active={article.bookmarked}
          />

          {!compact && (
            <>
              <span aria-hidden className="mx-1 h-4 w-px bg-border-default" />
              <IconButton
                onClick={() => submitFeedback(article.id, article.user_feedback === 1 ? 0 : 1)}
                icon={ThumbsUp}
                label={article.user_feedback === 1 ? 'Retirer « pertinent »' : 'Pertinent : améliore le scoring'}
                active={article.user_feedback === 1}
                tone={article.user_feedback === 1 ? 'success' : 'default'}
              />
              <IconButton
                onClick={() => submitFeedback(article.id, article.user_feedback === -1 ? 0 : -1)}
                icon={ThumbsDown}
                label={article.user_feedback === -1 ? 'Retirer « pas pour moi »' : 'Pas pour moi : améliore le scoring'}
                active={article.user_feedback === -1}
                tone={article.user_feedback === -1 ? 'danger' : 'default'}
              />
            </>
          )}

          <span aria-hidden className="mx-1 hidden h-4 w-px bg-border-default sm:block" />
          {!isPaper && (
            <span className="relative">
              <IconButton
                onClick={() => { setShowHighlightList(v => !v); setShowAskPanel(false) }}
                icon={Highlighter}
                label={`Surlignages (${articleHighlights.length})`}
                active={showHighlightList}
                tone={showHighlightList ? 'warning' : 'default'}
              />
              {articleHighlights.length > 0 && (
                <span className="pointer-events-none absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-yellow px-1 text-[10px] font-semibold tabular-nums text-on-accent">
                  {articleHighlights.length}
                </span>
              )}
            </span>
          )}
          {!isPaper && (
            <IconButton
              onClick={() => { setShowAskPanel(v => !v); setShowHighlightList(false) }}
              icon={Bot}
              label="Poser une question à l’IA"
              active={showAskPanel}
            />
          )}
          <ReadingSettings fontSize={fontSize} onFontSize={changeFontSize} font={font} onFont={changeFont} />
          {!compact && (
            <IconButton
              onClick={copyLink}
              icon={Link}
              label={copied ? 'Lien copié' : 'Copier le lien'}
              tone={copied ? 'success' : 'default'}
            />
          )}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary touch:h-10 touch:w-10"
            title="Ouvrir l’original  o"
            aria-label="Ouvrir l’original"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>

        {/* Reading progress */}
        <div aria-hidden className="absolute inset-x-0 -bottom-px h-[2px] overflow-hidden">
          <div ref={progressRef} className="h-full origin-left bg-accent-blue" style={{ transform: 'scaleX(0)' }} />
        </div>
      </div>

      {/* Paper view — dedicated layout for ArXiv papers */}
      {isPaper ? (
        <PaperView article={article} fontSize={fontSize} />
      ) : (
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          {showHighlightList && (
            <HighlightList
              highlights={articleHighlights}
              onDelete={(id) => deleteHighlight(articleId, id)}
              onClose={() => setShowHighlightList(false)}
              onScrollTo={handleScrollToHighlight}
            />
          )}

          <div ref={scrollRef} className="scroll-pane min-h-0 flex-1" onScroll={handleScroll}>
            <article className="mx-auto w-full max-w-[44rem] px-5 pb-[calc(6rem+env(safe-area-inset-bottom))] pt-8 sm:px-8 sm:pt-12">
              <header className="mb-8">
                <p className="mb-3 text-sm font-semibold text-accent-blue">{source}</p>
                <h1
                  ref={titleRef}
                  className="reader-title text-[1.85rem] leading-[1.18] text-text-primary sm:text-[2.3rem]"
                >
                  {article.title}
                </h1>
                <div className="mt-4 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm text-text-muted">
                  {article.author && (
                    <span className="font-medium text-text-secondary">{article.author}</span>
                  )}
                  <MetaItem first={!article.author}>
                    <time dateTime={date.toISOString()}>{longDate(date)}</time>
                  </MetaItem>
                  {article.reading_time ? (
                    <MetaItem>{article.reading_time} min de lecture</MetaItem>
                  ) : null}
                </div>
              </header>

              <AnalysisCard
                article={article}
                onFeedback={(value) => submitFeedback(article.id, value)}
              />

              {heroImage && (
                <div className="reader-hero mb-8 overflow-hidden rounded-lg">
                  <img
                    src={heroImage}
                    alt=""
                    className="h-auto w-full"
                    loading="lazy"
                    onError={e => {
                      const el = e.target as HTMLImageElement
                      const wrap = el.closest('.reader-hero') as HTMLElement | null
                      if (wrap) wrap.style.display = 'none'
                    }}
                  />
                </div>
              )}

              {/* Body */}
              {bodyHtml ? (
                <div
                  ref={contentRef}
                  className="reader-content"
                  style={{ fontSize: `${fontSize}px`, lineHeight: font === 'sans' ? 1.7 : 1.75 }}
                  dangerouslySetInnerHTML={{ __html: bodyHtml }}
                />
              ) : article.content_text ? (
                <div
                  ref={contentRef}
                  className="reader-plain space-y-4 font-serif text-text-primary"
                  style={{ fontSize: `${fontSize}px`, lineHeight: font === 'sans' ? 1.7 : 1.75 }}
                >
                  {article.content_text.split('\n\n').filter(Boolean).map((para, i) => (
                    <p key={i}>{para}</p>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-border-subtle bg-bg-surface px-5 py-8 text-center">
                  <p className="text-sm font-medium text-text-secondary">Le texte n’a pas pu être extrait de la page.</p>
                  <p className="mt-1 text-sm text-text-muted">L’article reste lisible sur le site d’origine.</p>
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-4 inline-flex h-10 items-center gap-2 rounded-lg bg-accent-blue px-4 text-sm font-semibold text-on-accent transition-opacity hover:opacity-90"
                  >
                    Lire sur {host}
                    <ExternalLink className="h-4 w-4" />
                  </a>
                </div>
              )}

              <footer className="mt-14 border-t border-border-subtle pt-6">
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex h-10 items-center gap-2 rounded-lg border border-border-default px-3.5 text-sm font-medium text-text-secondary transition-colors hover:border-accent-blue/40 hover:text-accent-blue"
                  >
                    <ExternalLink className="h-4 w-4" />
                    Lire sur {host}
                  </a>
                  <button
                    type="button"
                    onClick={toggleRead}
                    className="inline-flex h-10 items-center gap-2 rounded-lg px-3.5 text-sm text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
                  >
                    <CircleCheck className={`h-4 w-4 ${isRead ? 'text-accent-green' : ''}`} />
                    {isRead ? 'Marquer non lu' : 'Marquer lu'}
                  </button>
                </div>

                {onNext && nextTitle && (
                  <button
                    type="button"
                    onClick={onNext}
                    className="group mt-6 flex w-full items-center gap-4 rounded-xl border border-border-subtle bg-bg-surface p-4 text-left transition-colors hover:border-border-default sm:p-5"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2 text-xs text-text-muted">
                        Article suivant
                        {!compact && <Kbd>j</Kbd>}
                      </span>
                      <span className="mt-1.5 line-clamp-2 block font-semibold leading-snug text-text-primary">
                        {nextTitle}
                      </span>
                    </span>
                    <ArrowRight className="h-5 w-5 flex-shrink-0 text-text-muted transition-colors group-hover:text-accent-blue" />
                  </button>
                )}
              </footer>
            </article>
          </div>

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
          className="pointer-events-none fixed z-[70]"
          style={{
            left: noteTooltip.x,
            top: noteTooltip.y - 10,
            transform: 'translateX(-50%) translateY(-100%)',
          }}
        >
          <div
            className="relative rounded-xl border border-border-default bg-bg-surface px-3 py-2 text-xs leading-relaxed text-text-secondary"
            style={{ maxWidth: 220, boxShadow: 'var(--shadow-elevated)' }}
          >
            {noteTooltip.note}
            <div
              className="absolute left-1/2 -translate-x-1/2"
              style={{
                bottom: -6,
                width: 0,
                height: 0,
                borderLeft: '6px solid transparent',
                borderRight: '6px solid transparent',
                borderTop: '6px solid var(--color-popover-arrow)',
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

/** A meta item that carries its own leading separator, so a wrapped line never ends on a dot. */
function MetaItem({ children, first = false }: { children: React.ReactNode; first?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      {!first && <span aria-hidden className="h-[3px] w-[3px] rounded-full bg-text-muted/60" />}
      {children}
    </span>
  )
}

/**
 * Everything the scorer said about the article in one place: score, summary,
 * rationale, reading intent, and the feedback that trains the next scores.
 */
function AnalysisCard({ article, onFeedback }: { article: Article; onFeedback: (value: 1 | -1 | 0) => void }) {
  const pending = isScorePending(article)
  const failed = article.score === null && article.scoring_status === 'failed'
  const hasLenses = getArticleLenses(article).some(l => l.key !== 'latest' || l.tone === 'curiosity')
  const reason = cleanReason(article.reason)
  const hasSummary = article.summary_bullets.length > 0 || Boolean(reason)
  const details = parseScoreDetails(article)
  const axes = article.score !== null ? scoreAxes(details) : []

  return (
    <section
      aria-label="Analyse IA"
      className="mb-9 rounded-xl border border-accent-blue/15 bg-accent-blue/[0.045] p-4 sm:p-5"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
          <Sparkles className="h-4 w-4 text-accent-blue" />
          Analyse IA
        </h2>
        <ScoreBadge score={article.score} status={article.scoring_status} />
      </div>

      {pending && !hasSummary && (
        <p className="mt-3 text-sm leading-relaxed text-text-muted">
          L’IA lit encore cet article. Le résumé et le score s’afficheront ici dès qu’ils seront prêts.
        </p>
      )}
      {failed && !hasSummary && (
        <p className="mt-3 text-sm leading-relaxed text-text-muted">
          Le scoring IA a échoué pour cet article. Le texte reste lisible normalement.
        </p>
      )}

      {article.summary_bullets.length > 0 && (
        <ul className="mt-4 space-y-2.5">
          {article.summary_bullets.map((bullet, i) => (
            <li key={i} className="flex gap-3 text-[15px] leading-relaxed text-text-secondary">
              <span aria-hidden className="mt-[0.62em] h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent-blue" />
              <span>{bullet}</span>
            </li>
          ))}
        </ul>
      )}

      {reason && (
        <p className="mt-4 text-sm leading-relaxed text-text-muted">
          <span className="font-medium text-text-secondary">Pourquoi ce score : </span>
          {reason}
        </p>
      )}

      {hasLenses && <ArticleLensStrip article={article} max={4} skipFresh className="mt-4" />}

      {axes.length > 0 && <ScoreBreakdown axes={axes} caps={scoreCaps(details)} confidence={scoreConfidence(details)} />}

      {article.score !== null && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-t border-accent-blue/12 pt-3">
          <span className="text-xs text-text-muted">Ce score te paraît juste ? Ton avis affine les suivants.</span>
          <div className="flex gap-1.5">
            <FeedbackButton
              active={article.user_feedback === 1}
              tone="positive"
              onClick={() => onFeedback(article.user_feedback === 1 ? 0 : 1)}
            />
            <FeedbackButton
              active={article.user_feedback === -1}
              tone="negative"
              onClick={() => onFeedback(article.user_feedback === -1 ? 0 : -1)}
            />
          </div>
        </div>
      )}
    </section>
  )
}

/** The scorer's axes as small meters, folded away until asked for. */
function ScoreBreakdown({
  axes,
  caps,
  confidence,
}: {
  axes: ReturnType<typeof scoreAxes>
  caps: string[]
  confidence: number | null
}) {
  return (
    <details className="group mt-4">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-xs font-medium text-text-muted transition-colors hover:text-text-primary [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
        Détail du score
      </summary>
      <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2.5 sm:grid-cols-3">
        {axes.map(axis => (
          <div key={axis.key} className="min-w-0">
            <div className="mb-1 flex items-baseline justify-between gap-2 text-[11px]">
              <span className="truncate text-text-secondary">{axis.label}</span>
              <span className="tabular-nums text-text-muted">{axis.value.toFixed(1)}</span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-bg-elevated">
              <div
                className={`h-full rounded-full ${axis.penalty ? 'bg-accent-red/70' : 'bg-accent-blue'}`}
                style={{ width: `${(axis.value / AXIS_MAX) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      {(caps.length > 0 || confidence !== null) && (
        <p className="mt-3 text-xs leading-relaxed text-text-muted">
          {confidence !== null && <>Confiance de l’IA : {Math.round(confidence * 100)} %. </>}
          {caps.length > 0 && <>Score plafonné : {caps.join(', ')}.</>}
        </p>
      )}
    </details>
  )
}

function FeedbackButton({
  active,
  tone,
  onClick,
}: {
  active: boolean
  tone: 'positive' | 'negative'
  onClick: () => void
}) {
  const Icon = tone === 'positive' ? ThumbsUp : ThumbsDown
  const label = tone === 'positive' ? 'Pertinent' : 'Pas pour moi'
  const activeClass = tone === 'positive'
    ? 'border-accent-green/30 bg-accent-green/12 text-accent-green'
    : 'border-accent-red/30 bg-accent-red/12 text-accent-red'
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`
        inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors touch:h-10
        ${active ? activeClass : 'border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary'}
      `}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}
