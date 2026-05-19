import { useState, useEffect, useCallback } from 'react'
import { Users, RefreshCw, Trash2 } from 'lucide-react'
import type { TrackedAuthor, AuthorScanResponse } from '../types'

export default function AuthorRadarView() {
  const [authors, setAuthors] = useState<TrackedAuthor[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<AuthorScanResponse | null>(null)

  const fetchAuthors = useCallback(async () => {
    try {
      const res = await fetch('/api/research/authors', { credentials: 'include' })
      if (res.ok) {
        const data: TrackedAuthor[] = await res.json()
        setAuthors(data)
      }
    } catch (e) {
      console.error('Failed to fetch authors', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAuthors() }, [fetchAuthors])

  const handleScan = async () => {
    setScanning(true)
    setScanResult(null)
    try {
      const res = await fetch('/api/research/authors/scan', {
        method: 'POST',
        credentials: 'include',
      })
      if (res.ok) {
        const data: AuthorScanResponse = await res.json()
        setScanResult(data)
        fetchAuthors()
      }
    } catch (e) {
      console.error('Scan failed', e)
    } finally {
      setScanning(false)
    }
  }

  const handleDelete = async (ssAuthorId: string) => {
    try {
      const res = await fetch(`/api/research/authors/${ssAuthorId}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (res.ok) {
        setAuthors(prev => prev.filter(a => a.ss_author_id !== ssAuthorId))
      }
    } catch (e) {
      console.error('Delete failed', e)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-lg font-semibold text-text-primary mb-1 flex items-center gap-2">
          <Users size={18} className="text-accent-blue" />
          Author Radar
        </h1>
        <p className="text-sm text-text-muted mb-6">
          Automatically tracks authors from your high-scored papers and surfaces their new publications.
        </p>

        {/* ── Scan controls ── */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-text-primary">
            Tracked Authors ({authors.length})
          </h2>
          <button
            onClick={handleScan}
            disabled={scanning || authors.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent-blue text-white text-xs font-medium rounded-md hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
            {scanning ? 'Scanning…' : 'Scan Now'}
          </button>
        </div>

        {/* ── Scan result ── */}
        {scanResult && (
          <div className="bg-success-bg border border-success text-success text-xs rounded-md px-3 py-2 mb-4">
            Checked {scanResult.authors_checked} authors — {scanResult.new_articles_queued} new articles queued, {scanResult.skipped} skipped
          </div>
        )}

        {/* ── Authors list ── */}
        {loading ? (
          <div className="flex items-center justify-center py-12 text-text-muted text-sm">
            <RefreshCw size={16} className="animate-spin mr-2" />
            Loading authors…
          </div>
        ) : authors.length === 0 ? (
          <div className="bg-bg-surface border border-border-default rounded-lg p-8 text-center text-text-muted text-sm">
            No tracked authors yet. Authors from papers scored 7+ are added automatically.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted uppercase tracking-wider border-b border-border-subtle">
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium text-right">Papers</th>
                  <th className="pb-2 font-medium text-right">Avg Score</th>
                  <th className="pb-2 font-medium text-right">Alerts</th>
                  <th className="pb-2 font-medium text-right">Last Checked</th>
                  <th className="pb-2 font-medium text-right w-10" />
                </tr>
              </thead>
              <tbody>
                {authors.map(author => (
                  <tr key={author.ss_author_id} className="border-b border-border-subtle hover:bg-bg-hover transition-colors">
                    <td className="py-2.5 pr-4">
                      <span className="text-text-primary font-medium">{author.name}</span>
                    </td>
                    <td className="py-2.5 px-2 text-right text-text-secondary font-mono text-[13px]">
                      {author.paper_count}
                    </td>
                    <td className="py-2.5 px-2 text-right text-text-secondary font-mono text-[13px]">
                      {author.avg_score.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-2 text-right">
                      <span className={`font-mono text-[13px] ${author.alert_count > 0 ? 'text-accent-blue font-semibold' : 'text-text-muted'}`}>
                        {author.alert_count}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 text-right text-text-muted text-[13px]">
                      {author.last_checked
                        ? new Date(author.last_checked).toLocaleDateString()
                        : '—'}
                    </td>
                    <td className="py-2.5 pl-2 text-right">
                      <button
                        onClick={() => handleDelete(author.ss_author_id)}
                        className="p-1 hover:bg-danger-bg rounded text-text-muted hover:text-danger transition-colors"
                        title="Remove from tracking"
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
