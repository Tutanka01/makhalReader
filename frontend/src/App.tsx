import { useEffect, useState, useCallback } from 'react'
import { ArticleList } from './components/ArticleList'
import { ReaderView } from './components/ReaderView'
import { useArticlesStore } from './store/articles'
import { useSSE } from './hooks/useSSE'
import type { Feed } from './types'

export default function App() {
  const [feeds, setFeeds] = useState<Feed[]>([])
  const [showReader, setShowReader] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showHelp, setShowHelp] = useState(false)
  const { selectedId, setSelectedId, markRead, markUnread, toggleBookmark, articles } = useArticlesStore()

  useSSE()

  useEffect(() => {
    fetch('/api/feeds')
      .then(r => r.json())
      .then(setFeeds)
      .catch(console.error)
  }, [])

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
          if (currentIndex < articles.length - 1) {
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

      {/* ── Desktop layout ── */}
      <div className="hidden lg:flex w-full h-full">

        {/* Sidebar — collapsible */}
        <div
          className={`
            flex-shrink-0 border-r border-border-default h-full overflow-hidden
            transition-all duration-300 ease-in-out
            ${sidebarOpen ? 'w-[380px]' : 'w-0'}
          `}
        >
          <div className="w-[380px] h-full">
            <ArticleList
              feeds={feeds}
              onSelect={handleSelectArticle}
              selectedId={selectedId}
            />
          </div>
        </div>

        {/* Reader panel */}
        <div className="flex-1 h-full overflow-hidden min-w-0">
          {selectedId ? (
            <ReaderView
              articleId={selectedId}
              sidebarOpen={sidebarOpen}
              onToggleSidebar={() => setSidebarOpen(v => !v)}
              onNext={handleNext}
              hasNext={hasNext}
            />
          ) : (
            <EmptyReaderState
              sidebarOpen={sidebarOpen}
              onToggleSidebar={() => setSidebarOpen(v => !v)}
            />
          )}
        </div>
      </div>

      {/* ── Mobile layout ── */}
      <div className="flex lg:hidden w-full h-full">
        {!showReader || !selectedId ? (
          <div className="w-full h-full">
            <ArticleList
              feeds={feeds}
              onSelect={handleSelectArticle}
              selectedId={selectedId}
            />
          </div>
        ) : (
          <div className="w-full h-full">
            <ReaderView
              articleId={selectedId}
              onBack={handleBack}
              sidebarOpen={false}
              onToggleSidebar={() => {}}
              onNext={handleNext}
              hasNext={hasNext}
            />
          </div>
        )}
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
    <div className="flex flex-col h-full">
      {/* Toolbar stub to align with ReaderView toolbar */}
      <div className="flex items-center px-3 py-3 border-b border-border-subtle bg-bg-surface flex-shrink-0">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
          title={sidebarOpen ? 'Hide sidebar  [' : 'Show sidebar  ['}
        >
          {sidebarOpen ? (
            // PanelLeftClose
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>
            </svg>
          ) : (
            // PanelLeftOpen
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>
            </svg>
          )}
        </button>
      </div>
      <div className="flex flex-col items-center justify-center flex-1 text-center p-8">
        <div className="text-5xl mb-4 opacity-30">◉</div>
        <h2 className="text-base font-semibold text-text-secondary mb-1">
          Select an article
        </h2>
        <p className="text-xs text-text-muted max-w-xs leading-relaxed">
          <kbd className="px-1.5 py-0.5 bg-bg-elevated rounded text-xs font-mono">j</kbd>
          {' / '}
          <kbd className="px-1.5 py-0.5 bg-bg-elevated rounded text-xs font-mono">k</kbd>
          {' '}navigate{'  ·  '}
          <kbd className="px-1.5 py-0.5 bg-bg-elevated rounded text-xs font-mono">r</kbd>
          {' '}read{'  ·  '}
          <kbd className="px-1.5 py-0.5 bg-bg-elevated rounded text-xs font-mono">b</kbd>
          {' '}bookmark{'  ·  '}
          <kbd className="px-1.5 py-0.5 bg-bg-elevated rounded text-xs font-mono">[</kbd>
          {' '}sidebar
        </p>
      </div>
    </div>
  )
}
