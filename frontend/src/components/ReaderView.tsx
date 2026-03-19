import { useEffect } from 'react'
import { formatDistanceToNow, format } from 'date-fns'
import {
  ArrowLeft,
  Bookmark,
  BookmarkCheck,
  ExternalLink,
  Link,
  RotateCcw,
  Loader2,
} from 'lucide-react'
import { useArticlesStore } from '../store/articles'
import { ScoreBar } from './ScoreBar'

interface ReaderViewProps {
  articleId: number
  onBack?: () => void
}

export function ReaderView({ articleId, onBack }: ReaderViewProps) {
  const { selectedArticle, fetchArticle, markRead, markUnread, toggleBookmark } = useArticlesStore()

  useEffect(() => {
    fetchArticle(articleId)
  }, [articleId])

  // Auto-mark as read after 3 seconds
  useEffect(() => {
    if (selectedArticle && !selectedArticle.read_at) {
      const timer = setTimeout(() => {
        markRead(selectedArticle.id)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [selectedArticle?.id])

  const copyLink = () => {
    if (selectedArticle) {
      navigator.clipboard.writeText(selectedArticle.url).catch(() => {})
    }
  }

  if (!selectedArticle) {
    return (
      <div className="flex items-center justify-center h-full bg-bg-base">
        <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
      </div>
    )
  }

  const article = selectedArticle
  const publishedDate = article.published_at
    ? format(new Date(article.published_at), 'MMMM d, yyyy')
    : null
  const relativeDate = article.published_at
    ? formatDistanceToNow(new Date(article.published_at), { addSuffix: true })
    : null

  const heroImage = article.images?.[0] || null

  return (
    <div className="flex flex-col h-full bg-bg-base overflow-hidden">
      {/* Top toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-bg-surface flex-shrink-0">
        <div className="flex items-center gap-2">
          {onBack && (
            <button
              onClick={onBack}
              className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
              aria-label="Back"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}
          <ScoreBar score={article.score} />
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => article.read_at ? markUnread(article.id) : markRead(article.id)}
            className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
            aria-label={article.read_at ? 'Mark unread' : 'Mark read'}
            title={article.read_at ? 'Mark unread' : 'Mark read'}
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <button
            onClick={() => toggleBookmark(article.id)}
            className={`p-1.5 rounded-lg hover:bg-bg-hover transition-colors ${
              article.bookmarked ? 'text-accent-blue' : 'text-text-secondary hover:text-text-primary'
            }`}
            aria-label="Toggle bookmark"
            title="Bookmark"
          >
            {article.bookmarked
              ? <BookmarkCheck className="w-4 h-4" />
              : <Bookmark className="w-4 h-4" />
            }
          </button>
          <button
            onClick={copyLink}
            className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
            aria-label="Copy link"
            title="Copy link"
          >
            <Link className="w-4 h-4" />
          </button>
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-secondary hover:text-text-primary"
            aria-label="Open original"
            title="Open original"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>

      {/* Article content */}
      <div className="flex-1 overflow-y-auto">
        <article className="max-w-2xl mx-auto px-4 py-8 pb-16">
          {/* Tags */}
          {article.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-4">
              {article.tags.map(tag => (
                <span
                  key={tag}
                  className="px-2 py-0.5 bg-bg-elevated rounded-full text-xs text-text-muted font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Title */}
          <h1 className="text-2xl font-bold leading-tight text-text-primary mb-4">
            {article.title}
          </h1>

          {/* Meta */}
          <div className="flex flex-wrap items-center gap-2 text-sm text-text-muted mb-6 pb-6 border-b border-border-subtle">
            {article.author && (
              <span className="font-medium text-text-secondary">{article.author}</span>
            )}
            {article.author && (publishedDate || relativeDate) && (
              <span>·</span>
            )}
            {publishedDate && (
              <span title={relativeDate || ''}>{publishedDate}</span>
            )}
          </div>

          {/* AI Summary */}
          {article.summary_bullets.length > 0 && (
            <div className="mb-6 p-4 bg-bg-surface rounded-xl border border-border-subtle">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                AI Summary
              </p>
              <ul className="space-y-1.5">
                {article.summary_bullets.map((bullet, i) => (
                  <li key={i} className="text-sm text-text-secondary leading-relaxed flex gap-2">
                    <span className="text-accent-blue flex-shrink-0 mt-0.5">•</span>
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
                className="w-full h-auto object-cover"
                loading="lazy"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            </div>
          )}

          {/* Body content */}
          {article.content_html ? (
            <div
              className="reader-content font-serif text-reader-body text-text-primary"
              dangerouslySetInnerHTML={{ __html: article.content_html }}
            />
          ) : article.content_text ? (
            <div className="font-serif text-reader-body text-text-primary space-y-4">
              {article.content_text.split('\n\n').filter(Boolean).map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
          ) : (
            <div className="text-text-muted text-sm text-center py-8">
              <p>No content available.</p>
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-accent-blue hover:underline"
              >
                Read on original site <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}

          {/* Footer link */}
          <div className="mt-8 pt-6 border-t border-border-subtle text-center">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm text-accent-blue hover:underline"
            >
              Read full article on original site
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>
        </article>
      </div>
    </div>
  )
}
