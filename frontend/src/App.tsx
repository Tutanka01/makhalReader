import { useEffect, useState, useCallback } from 'react'
import { ArticleList } from './components/ArticleList'
import { ReaderView } from './components/ReaderView'
import { useArticlesStore } from './store/articles'
import { useSSE } from './hooks/useSSE'
import type { Feed } from './types'

export default function App() {
  const [feeds, setFeeds] = useState<Feed[]>([])
  const [showReader, setShowReader] = useState(false)
  const { selectedId, setSelectedId, markRead, markUnread, toggleBookmark, articles } = useArticlesStore()

  useSSE()

  // Fetch feeds list on mount
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

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return

      const currentIndex = articles.findIndex(a => a.id === selectedId)

      switch (e.key) {
        case 'j': {
          // Next article
          if (currentIndex < articles.length - 1) {
            const next = articles[currentIndex + 1]
            handleSelectArticle(next.id)
          }
          break
        }
        case 'k': {
          // Previous article
          if (currentIndex > 0) {
            const prev = articles[currentIndex - 1]
            handleSelectArticle(prev.id)
          }
          break
        }
        case 'r': {
          // Toggle read
          if (selectedId) {
            const article = articles.find(a => a.id === selectedId)
            if (article) {
              if (article.read_at) {
                markUnread(selectedId)
              } else {
                markRead(selectedId)
              }
            }
          }
          break
        }
        case 'b': {
          // Toggle bookmark
          if (selectedId) {
            toggleBookmark(selectedId)
          }
          break
        }
        case 'o': {
          // Open original
          if (selectedId) {
            const article = articles.find(a => a.id === selectedId)
            if (article) {
              window.open(article.url, '_blank', 'noopener,noreferrer')
            }
          }
          break
        }
        case 'Escape': {
          setShowReader(false)
          break
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedId, articles, handleSelectArticle, markRead, markUnread, toggleBookmark])

  return (
    <div className="flex h-screen bg-bg-base text-text-primary overflow-hidden">
      {/* Desktop layout: side-by-side */}
      <div className="hidden lg:flex w-full h-full">
        {/* Article list panel */}
        <div className="w-[380px] flex-shrink-0 border-r border-border-default h-full overflow-hidden">
          <ArticleList
            feeds={feeds}
            onSelect={handleSelectArticle}
            selectedId={selectedId}
          />
        </div>

        {/* Reader view panel */}
        <div className="flex-1 h-full overflow-hidden">
          {selectedId ? (
            <ReaderView articleId={selectedId} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <div className="text-6xl mb-4">📰</div>
              <h2 className="text-xl font-semibold text-text-secondary mb-2">
                Select an article
              </h2>
              <p className="text-sm text-text-muted max-w-xs">
                Choose an article from the list to read it here. Use{' '}
                <kbd className="px-1 py-0.5 bg-bg-elevated rounded text-xs">j</kbd>
                {' / '}
                <kbd className="px-1 py-0.5 bg-bg-elevated rounded text-xs">k</kbd>
                {' '}to navigate.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Mobile/tablet layout: stacked */}
      <div className="flex lg:hidden w-full h-full">
        {!showReader || !selectedId ? (
          /* Article list */
          <div className="w-full h-full">
            <ArticleList
              feeds={feeds}
              onSelect={handleSelectArticle}
              selectedId={selectedId}
            />
          </div>
        ) : (
          /* Reader view */
          <div className="w-full h-full">
            <ReaderView
              articleId={selectedId}
              onBack={handleBack}
            />
          </div>
        )}
      </div>
    </div>
  )
}
