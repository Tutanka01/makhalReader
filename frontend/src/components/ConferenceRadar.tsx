import { useState, useEffect, useCallback } from 'react'
import { Calendar, ExternalLink, Bookmark, BookmarkCheck, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import type { Conference } from '../types'

export default function ConferenceRadar() {
  const [conferences, setConferences] = useState<Conference[]>([])
  const [loading, setLoading] = useState(true)
  const [pastOpen, setPastOpen] = useState(false)

  const fetchConferences = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/research/conferences', { credentials: 'include' })
      if (res.ok) {
        const data: Conference[] = await res.json()
        setConferences(data)
      }
    } catch (e) {
      console.error('Failed to fetch conferences', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConferences()
  }, [fetchConferences])

  const toggleBookmark = async (venue: string, currentlyBookmarked: boolean) => {
    try {
      const res = await fetch('/api/research/conferences/bookmark', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ venue, bookmarked: !currentlyBookmarked }),
      })
      if (res.ok) {
        const data: Conference[] = await res.json()
        setConferences(data)
      }
    } catch (e) {
      console.error('Failed to toggle bookmark', e)
    }
  }

  const upcoming = conferences.filter(c => !c.is_past || c.bookmarked)
  const past = conferences.filter(c => c.is_past && !c.bookmarked)

  function urgencyClass(days: number): string {
    if (days <= 14) return 'text-red-500 font-bold'
    if (days <= 30) return 'text-orange-400 font-semibold'
    return 'text-green-500'
  }

  function formatDate(iso: string | null): string {
    if (!iso) return '—'
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return (
    <div className="h-full flex flex-col bg-bg-base">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-default">
        <div className="flex items-center gap-2.5">
          <Calendar className="w-4 h-4 text-accent" />
          <h1 className="text-sm font-semibold text-text-primary">Conference Radar</h1>
        </div>
        <button
          onClick={fetchConferences}
          className="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 max-w-3xl mx-auto w-full">
        {loading && conferences.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-5 h-5 animate-spin text-text-muted" />
          </div>
        ) : (
          <div className="space-y-3">
            {/* Upcoming */}
            {upcoming.map((conf) => (
              <div
                key={conf.venue}
                className={`rounded-xl border p-4 transition-colors ${
                  conf.bookmarked
                    ? 'bg-accent/5 border-accent/30'
                    : conf.days_to_paper <= 14 && !conf.is_past
                      ? 'bg-danger/5 border-danger/20'
                      : 'bg-bg-surface border-border-default'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-text-primary">{conf.venue}</h3>
                      <span className="text-[11px] text-text-muted bg-bg-elevated rounded px-1.5 py-[1px]">
                        {conf.track}
                      </span>
                      {conf.note && (
                        <span className="text-[11px] text-text-muted italic hidden sm:inline">
                          — {conf.note}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-xs text-text-secondary mt-2">
                      {conf.abstract_deadline && (
                        <span>Abstract: {formatDate(conf.abstract_deadline)}</span>
                      )}
                      <span>
                        Paper:{' '}
                        <a
                          href={conf.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent hover:underline"
                        >
                          {formatDate(conf.paper_deadline)}
                        </a>
                      </span>
                      <span>Conference: {formatDate(conf.conference_date)}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => toggleBookmark(conf.venue, conf.bookmarked)}
                      className="p-1.5 rounded-md hover:bg-bg-hover transition-colors"
                      title={conf.bookmarked ? 'Remove bookmark' : 'Bookmark'}
                    >
                      {conf.bookmarked
                        ? <BookmarkCheck className="w-4 h-4 text-accent" />
                        : <Bookmark className="w-4 h-4 text-text-muted" />
                      }
                    </button>
                    <a
                      href={conf.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
                      title="Open conference website"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>

                {/* Countdown bar */}
                <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border-subtle">
                  {conf.days_to_abstract != null && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-[11px] text-text-muted">Abstract:</span>
                      <span className={`text-sm tabular-nums ${urgencyClass(conf.days_to_abstract)}`}>
                        {conf.days_to_abstract < 0
                          ? `${Math.abs(conf.days_to_abstract)}d ago`
                          : `${conf.days_to_abstract}d`
                        }
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] text-text-muted">Paper:</span>
                    <span className={`text-sm tabular-nums ${urgencyClass(conf.days_to_paper)}`}>
                      {conf.days_to_paper < 0
                        ? `${Math.abs(conf.days_to_paper)}d ago`
                        : `${conf.days_to_paper}d`
                      }
                    </span>
                  </div>
                </div>
              </div>
            ))}

            {/* Past deadlines */}
            {past.length > 0 && (
              <div className="pt-4">
                <button
                  onClick={() => setPastOpen(v => !v)}
                  className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors mb-2"
                >
                  {pastOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                  Past deadlines ({past.length})
                </button>
                {pastOpen && (
                  <div className="space-y-2">
                    {past.map((conf) => (
                      <div
                        key={conf.venue}
                        className="rounded-xl border border-border-default bg-bg-surface p-3 opacity-60"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="text-xs font-semibold text-text-primary">{conf.venue}</h4>
                              <span className="text-[11px] text-text-muted">{conf.track}</span>
                            </div>
                            <div className="text-[11px] text-text-muted mt-1">
                              Paper deadline: {formatDate(conf.paper_deadline)}
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => toggleBookmark(conf.venue, conf.bookmarked)}
                              className="p-1 rounded hover:bg-bg-hover transition-colors"
                            >
                              {conf.bookmarked
                                ? <BookmarkCheck className="w-3.5 h-3.5 text-accent" />
                                : <Bookmark className="w-3.5 h-3.5 text-text-muted" />
                              }
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Empty */}
            {conferences.length === 0 && (
              <div className="text-center py-12 text-sm text-text-muted">
                No conference data available.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}