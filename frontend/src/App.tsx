import { useEffect, useState, useCallback } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { ArticleList } from './components/ArticleList'
import { ReaderView } from './components/ReaderView'
import { Sidebar } from './components/Sidebar'
import type { AppView } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { FeedManagerPanel } from './components/FeedManagerPanel'
import ResearchProfileEditor from './components/ResearchProfileEditor'
import { OfflineBanner } from './components/OfflineBanner'
import { LoginView } from './components/LoginView'
import { DigestView } from './components/DigestView'
import { StatsView } from './components/StatsView'
import ResearchDigestView from './components/ResearchDigestView'
import LitReviewView from './components/LitReviewView'
import ThreatView from './components/ThreatView'
import AuthorRadarView from './components/AuthorRadarView'
import WriteAssistPanel from './components/WriteAssistPanel'
import ConferenceRadar from './components/ConferenceRadar'
import HighlightManager from './components/HighlightManager'
import BibliographyPanel from './components/BibliographyPanel'
import SettingsModal from './components/SettingsModal'
import AdminPage from './components/AdminPage'
import OnboardingWizard from './components/OnboardingWizard'
import { useArticlesStore } from './store/articles'
import { useSSE } from './hooks/useSSE'
import { useOnlineStatus } from './hooks/useOnlineStatus'
import type { Feed, UserInfo } from './types'

// ---------------------------------------------------------------------------
// Auth gate
// ---------------------------------------------------------------------------

type AuthState = 'loading' | 'authenticated' | 'unauthenticated'

function useAuth(): [AuthState, () => void] {
  const [state, setState] = useState<AuthState>('loading')

  const check = useCallback(() => {
    fetch('/auth/me', { credentials: 'include' })
      .then(r => setState(r.ok ? 'authenticated' : 'unauthenticated'))
      .catch(() => setState('unauthenticated'))
  }, [])

  useEffect(() => { check() }, [check])

  return [state, check]
}

// Map URL path → AppView string (strips leading slash)
function pathToView(pathname: string): AppView {
  const segment = pathname.replace(/^\//, '') as AppView
  const VALID_VIEWS: AppView[] = [
    'feed', 'digest', 'stats', 'research', 'litreview', 'threats',
    'authors', 'write', 'conferences', 'highlights', 'bibliography',
    'feed-manager', 'admin',
  ]
  return VALID_VIEWS.includes(segment) ? segment : 'feed'
}

export default function App() {
  const [authState, recheckAuth] = useAuth()

  if (authState === 'loading') {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-bg-base">
        <div className="flex items-center gap-3 text-text-muted text-sm">
          <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          Loading…
        </div>
      </div>
    )
  }

  if (authState === 'unauthenticated') {
    return (
      <Routes>
        <Route path="/login" element={<LoginView onLogin={recheckAuth} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/feed" replace />} />
      <Route path="/" element={<Navigate to="/feed" replace />} />
      <Route path="/*" element={<AuthenticatedApp onLogout={recheckAuth} />} />
    </Routes>
  )
}

function AuthenticatedApp({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate()
  const location = useLocation()
  const appView = pathToView(location.pathname)

  const [feeds, setFeeds] = useState<Feed[]>([])
  const [currentUser, setCurrentUser] = useState<UserInfo | null>(null)
  const [showReader, setShowReader] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showHelp, setShowHelp] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { selectedId, setSelectedId, markRead, markUnread, toggleBookmark, articles } = useArticlesStore()

  useSSE(onLogout)
  const isOnline = useOnlineStatus()

  useEffect(() => {
    fetch('/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(u => setCurrentUser(u))
      .catch(() => {})
  }, [])

  const setAppView = useCallback((view: AppView) => {
    navigate('/' + view)
    setShowReader(false)
  }, [navigate])

  // ── Onboarding gate ──────────────────────────────────────────────────
  const handleOnboardingComplete = useCallback(() => {
    fetch('/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(u => setCurrentUser(u))
      .catch(() => {})
  }, [])

  if (currentUser && !currentUser.onboarding_done) {
    return <OnboardingWizard onComplete={handleOnboardingComplete} />
  }

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

  const handleSelectArticle = useCallback((id: number) => {
    setSelectedId(id)
    setShowReader(true)
  }, [setSelectedId])

  const handleBack = useCallback(() => {
    setShowReader(false)
  }, [])

  const currentIndex = articles.findIndex(a => a.id === selectedId)
  const hasNext = currentIndex >= 0 && currentIndex < articles.length - 1
  const handleNext = useCallback(() => {
    if (currentIndex >= 0 && currentIndex < articles.length - 1) {
      handleSelectArticle(articles[currentIndex + 1].id)
    }
  }, [currentIndex, articles, handleSelectArticle])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return

      const currentIndex = articles.findIndex(a => a.id === selectedId)

      switch (e.key) {
        case '[':
          setSidebarOpen(v => !v)
          break
        case 'j':
          if (currentIndex >= 0 && currentIndex < articles.length - 1) {
            handleSelectArticle(articles[currentIndex + 1].id)
          }
          break
        case 'k':
          if (currentIndex > 0) {
            handleSelectArticle(articles[currentIndex - 1].id)
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
          setShowReader(false)
          setShowHelp(false)
          break
        case '?':
          setShowHelp(v => !v)
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedId, articles, handleSelectArticle, markRead, markUnread, toggleBookmark])

  return (
    <div className="flex h-screen bg-bg-base text-text-primary overflow-hidden">
      <OfflineBanner show={!isOnline} />

      <ResearchProfileEditor
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />

      {/* Keyboard shortcuts help overlay */}
      {showHelp && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setShowHelp(false)}
        >
          <div
            className="bg-bg-surface border border-border-default rounded-2xl p-6 w-80 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <h2 className="text-sm font-semibold text-text-primary mb-4 text-center tracking-wide">Raccourcis clavier</h2>
            <div className="space-y-2">
              {[
                ['j / k', 'Article suivant / précédent'],
                ['r', 'Marquer lu / non-lu'],
                ['b', 'Bookmark'],
                ['o', 'Ouvrir l\'original'],
                ['/', 'Rechercher'],
                ['[', 'Masquer/afficher sidebar'],
                ['?', 'Aide'],
                ['Esc', 'Fermer'],
              ].map(([key, desc]) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-xs text-text-muted">{desc}</span>
                  <kbd className="px-2 py-0.5 bg-bg-elevated rounded text-xs font-mono text-text-secondary border border-border-subtle">
                    {key}
                  </kbd>
                </div>
              ))}
            </div>
            <p className="text-center text-xs text-text-muted mt-5">Swipe ← lire · Swipe → bookmark</p>
          </div>
        </div>
      )}

      {/* ── Unified Layout ── */}
      <div className="flex w-full h-full">
        {/* Sidebar */}
        <div
          className={`
            flex-shrink-0 h-full overflow-hidden transition-all duration-300 ease-in-out
            ${sidebarOpen ? 'w-[240px]' : 'w-0'}
            lg:block ${sidebarOpen && !showReader ? 'block absolute z-40 lg:relative' : 'hidden lg:block'}
          `}
        >
          <div className="w-[240px] h-full shadow-2xl lg:shadow-none">
            <Sidebar
              currentView={appView}
              onViewChange={(v) => {
                setAppView(v)
                if (window.innerWidth < 1024) setSidebarOpen(false)
              }}
              feeds={feeds}
              onOpenProfile={() => { setProfileOpen(true); if (window.innerWidth < 1024) setSidebarOpen(false) }}
              onOpenSettings={() => { setSettingsOpen(true); if (window.innerWidth < 1024) setSidebarOpen(false) }}
              onLogout={onLogout}
            />
          </div>
        </div>

        {/* Overlay for mobile sidebar */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/20 z-30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Main Content */}
        <div className="flex-1 flex flex-col h-full overflow-hidden min-w-0 bg-bg-base relative">
          <Topbar
            breadcrumb={
              appView === 'feed' ? (showReader ? 'Article' : 'Feed') :
              appView === 'digest' ? 'Digest' :
              appView === 'stats' ? 'Stats' :
              appView === 'research' ? 'Research Clusters' :
              appView === 'threats' ? 'Threat Monitor' :
              appView === 'authors' ? 'Author Radar' :
              appView === 'write' ? 'Writing Assistant' :
              appView === 'highlights' ? 'Highlight Manager' :
              appView === 'bibliography' ? 'BibTeX Export' :
              appView === 'conferences' ? 'Conference Radar' :
              appView === 'feed-manager' ? 'Feed Manager' :
              appView === 'admin' ? 'Lab Admin' : 'Literature Review'
            }
            sidebarOpen={sidebarOpen}
            onToggleSidebar={() => setSidebarOpen(v => !v)}
          />

          <div className="flex-1 h-full overflow-hidden min-w-0 relative">
            {showReader && selectedId ? (
              <ReaderView
                articleId={selectedId}
                onBack={handleBack}
                sidebarOpen={sidebarOpen}
                onToggleSidebar={() => setSidebarOpen(v => !v)}
                onNext={handleNext}
                hasNext={hasNext}
                onNavigate={handleSelectArticle}
              />
            ) : appView === 'feed' ? (
              <ArticleList
                feeds={feeds}
                onSelect={handleSelectArticle}
                selectedId={selectedId}
                onOpenProfile={() => setProfileOpen(true)}
                currentView={appView}
                onViewChange={setAppView}
                onLogout={onLogout}
              />
            ) : appView === 'digest' ? (
              <DigestView onSelect={handleSelectArticle} />
            ) : appView === 'stats' ? (
              <StatsView onClose={() => setAppView('feed')} onSelectArticle={handleSelectArticle} />
            ) : appView === 'research' ? (
              <ResearchDigestView onSelect={handleSelectArticle} />
            ) : appView === 'threats' ? (
              <ThreatView onSelectArticle={handleSelectArticle} />
            ) : appView === 'authors' ? (
              <AuthorRadarView />
            ) : appView === 'write' ? (
              <WriteAssistPanel />
            ) : appView === 'highlights' ? (
              <HighlightManager />
            ) : appView === 'bibliography' ? (
              <BibliographyPanel />
            ) : appView === 'conferences' ? (
              <ConferenceRadar />
            ) : appView === 'feed-manager' ? (
              <FeedManagerPanel
                currentUser={currentUser}
                onFeedsChange={refreshFeeds}
              />
            ) : appView === 'admin' ? (
              <AdminPage />
            ) : (
              <LitReviewView onSelectArticle={handleSelectArticle} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
