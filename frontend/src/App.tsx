import { useEffect, useState, useCallback, useRef } from 'react'
import { ArticleList } from './components/ArticleList'
import { BriefingView } from './components/briefing/BriefingView'
import type { BriefingMode } from './components/briefing/BriefingView'
import { ReaderView } from './components/ReaderView'
import { FeedManagerPanel } from './components/FeedManagerPanel'
import { OfflineBanner } from './components/OfflineBanner'
import { LoginView } from './components/LoginView'
import { StatsView } from './components/StatsView'
import { ShortcutsDialog } from './components/ShortcutsDialog'
import { NavRail, MobileHeader, MobileNavBar } from './components/NavRail'
import type { AppView } from './components/NavRail'
import { useArticlesStore } from './store/articles'
import { useSSE } from './hooks/useSSE'
import { useOnlineStatus } from './hooks/useOnlineStatus'
import { useTheme } from './hooks/useTheme'
import { useLayout } from './hooks/useLayout'
import type { Feed } from './types'
import { PanelLeftClose, PanelLeftOpen, Radar } from 'lucide-react'
import { IconButton, Kbd } from './components/ui'

// ---------------------------------------------------------------------------
// Auth gate — checks session on load, shows LoginView if unauthenticated
// ---------------------------------------------------------------------------

type AuthState = 'loading' | 'authenticated' | 'unauthenticated'

function useAuth(): [AuthState, () => void] {
  const [state, setState] = useState<AuthState>('loading')

  const check = useCallback(() => {
    fetch('/auth/status', { credentials: 'include' })
      .then(r => setState(r.ok ? 'authenticated' : 'unauthenticated'))
      .catch(() => setState('unauthenticated'))
  }, [])

  useEffect(() => { check() }, [check])

  return [state, check]
}

export default function App() {
  const [authState, recheckAuth] = useAuth()

  if (authState === 'loading') {
    return (
      <div className="flex h-[100dvh] w-screen items-center justify-center bg-bg-base">
        <div className="flex items-center gap-3 text-sm text-text-muted">
          <Radar className="h-4 w-4 animate-spin text-accent-blue [animation-duration:2.4s]" />
          Chargement…
        </div>
      </div>
    )
  }

  if (authState === 'unauthenticated') {
    return <LoginView onLogin={recheckAuth} />
  }

  return <AuthenticatedApp onLogout={recheckAuth} />
}

/** History marker pushed while the reader covers the list (compact/medium). */
const READER_STATE = 'makhalReader'

function isReaderHistoryState(state: unknown): boolean {
  return Boolean(state && typeof state === 'object' && (state as Record<string, unknown>)[READER_STATE])
}

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable
}

function AuthenticatedApp({ onLogout }: { onLogout: () => void }) {
  const layout = useLayout()
  const { theme, toggleTheme } = useTheme()
  const [feeds, setFeeds] = useState<Feed[]>([])
  // Compact/medium: the reader covers the list while an article is open.
  const [readerOpen, setReaderOpen] = useState(false)
  // Wide: the list pane is pinned next to the reader (toggle with `[`).
  const [sidebarOpen, setSidebarOpen] = useState(true)
  // Medium with an article open: the list slides over the reader on demand.
  const [listOverlayOpen, setListOverlayOpen] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [feedManagerOpen, setFeedManagerOpen] = useState(false)
  const [appView, setAppView] = useState<AppView>('feed')
  const [briefingMode, setBriefingMode] = useState<BriefingMode>('live')
  const toggleBriefingMode = useCallback(() => {
    setBriefingMode(m => (m === 'live' ? 'history' : 'live'))
  }, [])
  const { selectedId, setSelectedId, markRead, markUnread, toggleBookmark, articles, searchResults } = useArticlesStore()

  useSSE(onLogout)
  const isOnline = useOnlineStatus()

  const refreshFeeds = useCallback(() => {
    fetch('/api/feeds', { credentials: 'include' })
      .then(r => {
        if (r.status === 401) { onLogout(); return [] }
        return r.json()
      })
      .then(data => { if (Array.isArray(data)) setFeeds(data) })
      .catch(console.error)
  }, [onLogout])

  useEffect(() => { refreshFeeds() }, [refreshFeeds])

  const stacked = layout !== 'wide'
  const readerVisible = appView === 'feed' && selectedId !== null && (!stacked || readerOpen)

  // ── Reader open/close, mirrored in browser history on stacked layouts so the
  //    iOS edge swipe, Android back and the browser back button close the
  //    reader instead of leaving the app.
  const readerOpenRef = useRef(readerOpen)
  readerOpenRef.current = readerOpen

  useEffect(() => {
    // A reload can land on a stale reader entry; start from a clean state.
    if (isReaderHistoryState(window.history.state)) window.history.replaceState(null, '')
    const onPopState = (e: PopStateEvent) => {
      if (!isReaderHistoryState(e.state)) {
        setReaderOpen(false)
        setListOverlayOpen(false)
      }
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const handleSelectArticle = useCallback((id: number) => {
    setSelectedId(id)
    setAppView('feed')
    setListOverlayOpen(false)
    if (stacked && !readerOpenRef.current && !isReaderHistoryState(window.history.state)) {
      window.history.pushState({ [READER_STATE]: true }, '')
    }
    setReaderOpen(true)
  }, [setSelectedId, stacked])

  const handleBack = useCallback(() => {
    if (isReaderHistoryState(window.history.state)) {
      window.history.back() // popstate closes the reader
    } else {
      setReaderOpen(false)
      setListOverlayOpen(false)
    }
  }, [])

  const toggleListPane = useCallback(() => {
    if (layout === 'wide') setSidebarOpen(v => !v)
    else if (readerVisible) setListOverlayOpen(v => !v)
  }, [layout, readerVisible])

  const currentIndex = articles.findIndex(a => a.id === selectedId)
  const nextArticle = currentIndex >= 0 ? articles[currentIndex + 1] : undefined
  const handleNext = useCallback(() => {
    if (nextArticle) handleSelectArticle(nextArticle.id)
  }, [nextArticle, handleSelectArticle])

  const selectedListItem =
    articles.find(a => a.id === selectedId) ?? searchResults.find(a => a.id === selectedId)

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return
      // Leave browser/OS shortcuts (⌘R, Ctrl+B, …) alone.
      if (e.metaKey || e.ctrlKey || e.altKey) return

      const index = articles.findIndex(a => a.id === selectedId)

      switch (e.key) {
        case '[':
          toggleListPane()
          break
        case 'j':
          if (index < articles.length - 1) {
            handleSelectArticle(articles[index + 1].id)
          }
          break
        case 'k':
          if (index > 0) {
            handleSelectArticle(articles[index - 1].id)
          }
          break
        case 'r': {
          if (selectedId) {
            const article = articles.find(a => a.id === selectedId)
            if (article) {
              article.read_at ? markUnread(selectedId) : markRead(selectedId)
            }
          }
          break
        }
        case 'b':
          if (selectedId) toggleBookmark(selectedId)
          break
        case 'o': {
          if (selectedId) {
            const article = articles.find(a => a.id === selectedId)
            if (article) window.open(article.url, '_blank', 'noopener,noreferrer')
          }
          break
        }
        case 'Escape':
          if (showHelp) setShowHelp(false)
          else if (listOverlayOpen) setListOverlayOpen(false)
          else if (stacked && readerOpen) handleBack()
          break
        case '?':
          setShowHelp(v => !v)
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [
    selectedId, articles, handleSelectArticle, markRead, markUnread, toggleBookmark,
    toggleListPane, showHelp, listOverlayOpen, stacked, readerOpen, handleBack,
  ])

  // ── List pane placement. The list stays mounted in every mode so its scroll
  //    position, loaded pages and search survive opening an article.
  type ListMode = 'pinned' | 'collapsed' | 'full' | 'overlay' | 'overlay-closed' | 'hidden'
  let listMode: ListMode
  if (appView !== 'feed') listMode = stacked ? 'hidden' : 'collapsed'
  else if (!stacked) listMode = sidebarOpen ? 'pinned' : 'collapsed'
  else if (!readerVisible) listMode = 'full'
  else if (layout === 'medium') listMode = listOverlayOpen ? 'overlay' : 'overlay-closed'
  else listMode = 'hidden'

  const listPaneClass: Record<ListMode, string> = {
    pinned: 'relative h-full w-[380px] flex-shrink-0 border-r border-border-default transition-[width] duration-300 ease-out',
    collapsed: 'invisible relative h-full w-0 flex-shrink-0 transition-[width,visibility] duration-300 ease-out',
    full: 'relative h-full min-w-0 flex-1',
    overlay: 'absolute inset-y-0 left-0 z-30 h-full w-[min(380px,88%)] border-r border-border-default shadow-pane transition-[transform,visibility] duration-300 ease-out',
    'overlay-closed': 'invisible absolute inset-y-0 left-0 z-30 h-full w-[min(380px,88%)] -translate-x-full transition-[transform,visibility] duration-300 ease-out',
    hidden: 'invisible pointer-events-none absolute inset-0',
  }
  const listInnerClass = listMode === 'pinned' || listMode === 'collapsed' ? 'h-full w-[380px]' : 'h-full w-full'
  const listHidden = listMode === 'collapsed' || listMode === 'overlay-closed' || listMode === 'hidden'

  let mainContent: React.ReactNode = null
  if (appView === 'briefing') {
    mainContent = (
      <BriefingView onOpen={handleSelectArticle} mode={briefingMode} onToggleMode={toggleBriefingMode} />
    )
  } else if (appView === 'stats') {
    mainContent = <StatsView onClose={() => setAppView('feed')} />
  } else if (readerVisible && selectedId !== null) {
    mainContent = (
      <ReaderView
        articleId={selectedId}
        feedName={selectedListItem?.feed_name}
        layout={layout}
        onBack={stacked ? handleBack : undefined}
        listOpen={layout === 'wide' ? sidebarOpen : listOverlayOpen}
        onToggleList={layout === 'compact' ? undefined : toggleListPane}
        onNext={nextArticle ? handleNext : undefined}
        nextTitle={nextArticle?.title}
      />
    )
  } else if (!stacked) {
    mainContent = <EmptyReaderState sidebarOpen={sidebarOpen} onToggleSidebar={toggleListPane} />
  }

  const chromeVisible = layout === 'compact' && !readerVisible

  return (
    <div
      className="
        flex h-[100dvh] w-full overflow-hidden bg-bg-base text-text-primary
        pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] pt-[env(safe-area-inset-top)]
      "
    >
      <OfflineBanner show={!isOnline} />

      <FeedManagerPanel
        open={feedManagerOpen}
        onClose={() => setFeedManagerOpen(false)}
        feeds={feeds}
        onFeedsChange={refreshFeeds}
      />

      {showHelp && <ShortcutsDialog onClose={() => setShowHelp(false)} />}

      {layout !== 'compact' && (
        <NavRail
          view={appView}
          onViewChange={setAppView}
          onOpenFeedManager={() => setFeedManagerOpen(true)}
          onOpenHelp={() => setShowHelp(true)}
          onLogout={onLogout}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {chromeVisible && (
          <MobileHeader
            onOpenFeedManager={() => setFeedManagerOpen(true)}
            onLogout={onLogout}
            theme={theme}
            onToggleTheme={toggleTheme}
          />
        )}

        <main className="relative flex min-h-0 flex-1 overflow-hidden">
          <aside
            aria-label="Liste des articles"
            aria-hidden={listHidden || undefined}
            className={`overflow-hidden bg-bg-base ${listPaneClass[listMode]}`}
          >
            <div className={listInnerClass}>
              <ArticleList feeds={feeds} onSelect={handleSelectArticle} selectedId={selectedId} />
            </div>
          </aside>

          {listMode === 'overlay' && (
            <div
              aria-hidden
              className="animate-fade-in absolute inset-0 z-20"
              style={{ background: 'var(--color-overlay)' }}
              onClick={() => setListOverlayOpen(false)}
            />
          )}

          {mainContent && (
            <section className="h-full min-w-0 flex-1">
              <div key={appView} className="view-enter h-full">
                {mainContent}
              </div>
            </section>
          )}
        </main>

        {chromeVisible && <MobileNavBar view={appView} onViewChange={setAppView} />}
      </div>
    </div>
  )
}

function EmptyReaderState({
  sidebarOpen,
  onToggleSidebar,
}: {
  sidebarOpen: boolean
  onToggleSidebar: () => void
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Toolbar stub to align with ReaderView toolbar */}
      <div className="flex h-[52px] flex-shrink-0 items-center border-b border-border-subtle bg-bg-surface px-3">
        <IconButton
          onClick={onToggleSidebar}
          icon={sidebarOpen ? PanelLeftClose : PanelLeftOpen}
          label={sidebarOpen ? 'Masquer la liste  [' : 'Afficher la liste  ['}
        />
      </div>
      <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
        <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-xl bg-accent-blue/10 text-accent-blue">
          <Radar className="h-6 w-6" />
        </div>
        <h2 className="mb-1.5 text-base font-semibold text-text-primary">
          Choisis un article à lire
        </h2>
        <p className="mb-6 max-w-xs text-sm leading-relaxed text-text-muted">
          Les mieux notés par l’IA sont en haut de la liste.
        </p>
        <div className="grid grid-cols-[auto_auto] items-center gap-x-3 gap-y-2 text-left text-xs text-text-muted">
          <span className="flex justify-end gap-1"><Kbd>j</Kbd><Kbd>k</Kbd></span>
          <span>Article suivant / précédent</span>
          <span className="flex justify-end"><Kbd>r</Kbd></span>
          <span>Marquer lu</span>
          <span className="flex justify-end"><Kbd>b</Kbd></span>
          <span>Favori</span>
          <span className="flex justify-end"><Kbd>?</Kbd></span>
          <span>Tous les raccourcis</span>
        </div>
      </div>
    </div>
  )
}
