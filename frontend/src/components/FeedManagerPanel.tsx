import { useCallback, useEffect, useRef, useState } from 'react'
import { Plus, Upload, Download, Rss, Loader2, Trash2, AlertCircle, CheckCircle2, Bell, BellOff } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { Feed, Source, UserInfo } from '../types'
import { fetchSources, subscribeSource, unsubscribeSource } from '../api/sources'
import { ProviderBadge } from './ProviderBadge'

interface FeedManagerPanelProps {
  currentUser: UserInfo | null
  onFeedsChange: () => void
}

function escapeXml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function exportOPML(feeds: Feed[]) {
  const categories = [...new Set(feeds.map(f => f.category))]
  const outlines = categories.map(cat => {
    const catFeeds = feeds.filter(f => f.category === cat)
    const feedOutlines = catFeeds
      .map(f => `      <outline type="rss" text="${escapeXml(f.name)}" title="${escapeXml(f.name)}" xmlUrl="${escapeXml(f.url)}"/>`)
      .join('\n')
    return `    <outline text="${escapeXml(cat)}" title="${escapeXml(cat)}">\n${feedOutlines}\n    </outline>`
  }).join('\n')
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<opml version="1.0">\n  <head><title>Baṣīra Feeds</title></head>\n  <body>\n${outlines}\n  </body>\n</opml>`
  const blob = new Blob([xml], { type: 'text/xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `basira-feeds-${new Date().toISOString().slice(0, 10)}.opml`
  a.click()
  URL.revokeObjectURL(url)
}

function isHealthy(feed: Feed) {
  if (!feed.last_fetched) return false
  return Date.now() - new Date(feed.last_fetched).getTime() < 7 * 86_400_000
}

export function FeedManagerPanel({ currentUser, onFeedsChange }: FeedManagerPanelProps) {
  const [catalog, setCatalog] = useState<Feed[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [addUrl, setAddUrl] = useState('')
  const [addName, setAddName] = useState('')
  const [addCategory, setAddCategory] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const confirmTimers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState('')
  const [filterCat, setFilterCat] = useState('all')

  const isAdmin = currentUser?.role === 'admin'

  const fetchCatalog = useCallback(async () => {
    setLoading(true)
    try {
      const [feedsRes, srcList] = await Promise.all([
        fetch('/api/feeds/catalog', { credentials: 'include' }),
        fetchSources().catch(() => [] as Source[]),
      ])
      const feedData = feedsRes.ok ? (await feedsRes.json()) as Feed[] : []
      setCatalog(Array.isArray(feedData) ? feedData : [])
      setSources(Array.isArray(srcList) ? srcList : [])
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchCatalog() }, [fetchCatalog])

  const handleSubscribe = async (feedId: number, currentlySubscribed: boolean) => {
    setTogglingId(feedId)
    try {
      const method = currentlySubscribed ? 'DELETE' : 'POST'
      const res = await fetch(`/api/feeds/${feedId}/subscribe`, {
        method,
        credentials: 'include',
      })
      if (res.ok) {
        setCatalog(prev => prev.map(f => f.id === feedId ? { ...f, subscribed: !currentlySubscribed } : f))
        onFeedsChange()
      }
    } catch {
      /* ignore */
    } finally {
      setTogglingId(null)
    }
  }

  const handleSourceSubscribe = async (sourceId: number, currentlySubscribed: boolean) => {
    setTogglingId(sourceId)
    try {
      if (currentlySubscribed) {
        await unsubscribeSource(sourceId)
      } else {
        await subscribeSource(sourceId)
      }
      setSources(prev => prev.map(s => s.id === sourceId ? { ...s, subscribed: !currentlySubscribed } : s))
      onFeedsChange()
    } catch {
      /* ignore */
    } finally {
      setTogglingId(null)
    }
  }

  const handleAdd = async () => {
    if (!addUrl.trim()) return
    setAdding(true)
    setAddError('')
    try {
      const res = await fetch('/api/feeds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: addUrl.trim(),
          name: addName.trim() || addUrl.trim(),
          category: addCategory.trim() || 'General',
        }),
      })
      if (res.status === 409) {
        setAddError('Ce feed existe déjà.')
      } else if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setAddError(data.detail || 'URL invalide ou inaccessible.')
      } else {
        setAddUrl('')
        setAddName('')
        setAddCategory('')
        fetchCatalog()
        onFeedsChange()
      }
    } catch {
      setAddError('Erreur réseau.')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = useCallback((id: number) => {
    if (confirmDeleteId !== id) {
      setConfirmDeleteId(id)
      const t = setTimeout(() => setConfirmDeleteId(prev => prev === id ? null : prev), 3000)
      confirmTimers.current.set(id, t)
    } else {
      const t = confirmTimers.current.get(id)
      if (t) clearTimeout(t)
      confirmTimers.current.delete(id)
      setConfirmDeleteId(null)
      setDeletingId(id)
      fetch(`/api/feeds/${id}`, { method: 'DELETE', credentials: 'include' })
        .then(() => { fetchCatalog(); onFeedsChange() })
        .finally(() => setDeletingId(null))
    }
  }, [confirmDeleteId, fetchCatalog, onFeedsChange])

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportMsg('')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch('/api/feeds/opml', { method: 'POST', credentials: 'include', body: formData })
      if (res.ok) {
        const data = await res.json()
        setImportMsg(`${data.added} ajoutés, ${data.skipped} déjà présents`)
        fetchCatalog()
        onFeedsChange()
      } else {
        setImportMsg('Erreur lors de l\'import.')
      }
    } catch {
      setImportMsg('Erreur réseau.')
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const categories = ['all', ...new Set(catalog.map(f => f.category))].sort()
  const filtered = filterCat === 'all' ? catalog : catalog.filter(f => f.category === filterCat)
  const subscribedCount = catalog.filter(f => f.subscribed).length

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3.5 border-b border-border-subtle flex-shrink-0">
        <div className="flex items-center gap-2">
          <Rss className="w-4 h-4 text-accent" />
          <span className="text-sm font-semibold text-text-primary">Feed Manager</span>
          <span className="text-xs text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded-full">
            {subscribedCount}/{catalog.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <label
            className="flex items-center gap-1 p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary cursor-pointer"
            title="Importer OPML"
          >
            {importing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5" />
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".opml,.xml"
              className="hidden"
              onChange={handleImport}
            />
          </label>
          <button
            onClick={() => exportOPML(catalog)}
            className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
            title="Exporter OPML"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {importMsg && (
        <div className="flex items-center gap-2 px-6 py-2 bg-accent/10 border-b border-accent/20">
          <CheckCircle2 className="w-3.5 h-3.5 text-accent flex-shrink-0" />
          <span className="text-xs text-accent">{importMsg}</span>
        </div>
      )}

      {/* Category filter */}
      <div className="flex gap-1.5 px-6 py-3 border-b border-border-subtle overflow-x-auto flex-shrink-0">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setFilterCat(cat)}
            className={`text-xs whitespace-nowrap px-2.5 py-1 rounded-full transition-colors ${
              filterCat === cat
                ? 'bg-accent text-white'
                : 'bg-bg-elevated text-text-muted hover:text-text-primary hover:bg-bg-hover'
            }`}
          >
            {cat === 'all' ? 'Tous' : cat}
          </button>
        ))}
      </div>

      {/* Feed list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-5 h-5 animate-spin text-text-muted" />
          </div>
        ) : filtered.length === 0 && sources.filter(s => s.provider !== 'rss').filter(s => filterCat === 'all' || s.category === filterCat).length === 0 ? (
          <div className="text-center py-20 text-text-muted text-xs">
            Aucun feed ou source dans cette catégorie.
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {filtered.map(feed => {
              const healthy = isHealthy(feed)
              const isToggling = togglingId === feed.id
              const isConfirming = confirmDeleteId === feed.id
              const isDeleting = deletingId === feed.id
              const src = sources.find(s => s.id === feed.id)
              return (
                <div
                  key={`feed-${feed.id}`}
                  className="flex items-center gap-3 px-6 py-3 hover:bg-bg-hover transition-colors group"
                >
                  {/* Health dot */}
                  <div
                    className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${healthy ? 'bg-success' : 'bg-danger/60'}`}
                    title={healthy ? 'Actif' : 'Aucun article récent'}
                  />

                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-text-primary truncate">{feed.name}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <ProviderBadge provider="rss" />
                      <span className="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">
                        {feed.category}
                      </span>
                      {feed.article_count !== undefined && (
                        <span className="text-[10px] text-text-muted">
                          {feed.article_count} articles
                        </span>
                      )}
                      {feed.last_fetched && (
                        <span className="text-[10px] text-text-muted">
                          · {formatDistanceToNow(new Date(feed.last_fetched), { addSuffix: true, locale: fr })}
                        </span>
                      )}
                      {!healthy && !feed.last_fetched && (
                        <span className="flex items-center gap-0.5 text-[10px] text-danger/70">
                          <AlertCircle className="w-2.5 h-2.5" />
                          Jamais lu
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Subscribe/Unsubscribe button */}
                  <button
                    onClick={() => handleSubscribe(feed.id, !!feed.subscribed)}
                    disabled={isToggling}
                    className={`flex items-center gap-1 rounded-md transition-all text-[11px] font-medium px-2.5 py-1.5 flex-shrink-0 ${
                      feed.subscribed
                        ? 'bg-accent/10 text-accent hover:bg-accent/20'
                        : 'bg-bg-elevated text-text-muted hover:text-text-primary hover:bg-bg-hover'
                    }`}
                    title={feed.subscribed ? 'Se désabonner' : "S'abonner"}
                  >
                    {isToggling ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : feed.subscribed ? (
                      <BellOff className="w-3 h-3" />
                    ) : (
                      <Bell className="w-3 h-3" />
                    )}
                    {feed.subscribed ? 'Abonné' : "S'abonner"}
                  </button>

                  {/* Admin delete button */}
                  {isAdmin && (
                    <button
                      onClick={() => handleDelete(feed.id)}
                      disabled={isDeleting}
                      className={`flex items-center gap-1 rounded-md transition-all duration-150 text-[11px] font-medium flex-shrink-0 opacity-0 group-hover:opacity-100 ${
                        isConfirming
                          ? 'px-2 py-1 bg-red-500/15 text-red-400 hover:bg-red-500/25 ring-1 ring-red-500/40 opacity-100'
                          : 'p-1.5 text-text-muted hover:text-danger hover:bg-bg-elevated'
                      }`}
                      title={isConfirming ? 'Confirmer la suppression' : 'Supprimer'}
                    >
                      {isDeleting ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5 flex-shrink-0" />
                      )}
                      {isConfirming && <span>Confirmer?</span>}
                    </button>
                  )}
                </div>
              )
            })}

            {/* Provider sources section */}
            {filterCat === 'all' || filtered.some(f => f.category === filterCat) ? null : null}
            {sources
              .filter(s => s.provider !== 'rss')
              .filter(s => filterCat === 'all' || s.category === filterCat)
              .map(source => {
                const isToggling = togglingId === source.id
                const feedItem = catalog.find(f => f.id === source.id)
                const alreadyShown = catalog.some(f => f.id === source.id)
                if (alreadyShown) return null
                return (
                  <div
                    key={`src-${source.id}`}
                    className="flex items-center gap-3 px-6 py-3 hover:bg-bg-hover transition-colors group"
                  >
                    <div className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-accent/40" title="Provider source" />

                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-text-primary truncate">{source.name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <ProviderBadge provider={source.provider} />
                        <span className="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">
                          {source.category}
                        </span>
                        {source.label && (
                          <span className="text-[10px] text-text-muted truncate max-w-[120px]">
                            {source.label}
                          </span>
                        )}
                      </div>
                    </div>

                    <button
                      onClick={() => handleSourceSubscribe(source.id, !!source.subscribed)}
                      disabled={isToggling}
                      className={`flex items-center gap-1 rounded-md transition-all text-[11px] font-medium px-2.5 py-1.5 flex-shrink-0 ${
                        source.subscribed
                          ? 'bg-accent/10 text-accent hover:bg-accent/20'
                          : 'bg-bg-elevated text-text-muted hover:text-text-primary hover:bg-bg-hover'
                      }`}
                      title={source.subscribed ? 'Se désabonner' : "S'abonner"}
                    >
                      {isToggling ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : source.subscribed ? (
                        <BellOff className="w-3 h-3" />
                      ) : (
                        <Bell className="w-3 h-3" />
                      )}
                      {source.subscribed ? 'Abonné' : "S'abonner"}
                    </button>
                  </div>
                )
              })}
          </div>
        )}
      </div>

      {/* Add feed form */}
      <div className="border-t border-border-default bg-bg-surface px-6 py-4 flex-shrink-0">
        <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2.5">
          Ajouter un feed
        </p>
        <div className="space-y-2">
          <input
            type="url"
            value={addUrl}
            onChange={e => setAddUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="https://example.com/feed.xml"
            className="w-full bg-bg-elevated border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder-text-muted outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20 transition-all"
          />
          <div className="flex gap-2">
            <input
              type="text"
              value={addName}
              onChange={e => setAddName(e.target.value)}
              placeholder="Nom (optionnel)"
              className="flex-1 bg-bg-elevated border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder-text-muted outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20 transition-all"
            />
            <select
              value={addCategory}
              onChange={e => setAddCategory(e.target.value)}
              className="flex-1 bg-bg-elevated border border-border-default rounded-lg px-2 py-2 text-xs text-text-primary outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20 transition-all"
            >
              <option value="">Catégorie</option>
              {categories.filter(c => c !== 'all').map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
              <option value="General">General</option>
            </select>
          </div>
          {addError && (
            <p className="text-[11px] text-danger flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              {addError}
            </p>
          )}
          <button
            onClick={handleAdd}
            disabled={adding || !addUrl.trim()}
            className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg bg-accent text-white text-xs font-medium transition-all hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {adding ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Plus className="w-3.5 h-3.5" />
            )}
            Ajouter
          </button>
        </div>
      </div>
    </div>
  )
}
