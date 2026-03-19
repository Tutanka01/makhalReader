import { useCallback, useRef, useState } from 'react'
import { X, Plus, Upload, Download, Rss, Loader2, Trash2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { Feed } from '../types'

interface FeedManagerPanelProps {
  open: boolean
  onClose: () => void
  feeds: Feed[]
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
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<opml version="1.0">\n  <head><title>MakhalReader Feeds</title></head>\n  <body>\n${outlines}\n  </body>\n</opml>`
  const blob = new Blob([xml], { type: 'text/xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `makhalreader-feeds-${new Date().toISOString().slice(0, 10)}.opml`
  a.click()
  URL.revokeObjectURL(url)
}

function isHealthy(feed: Feed) {
  if (!feed.last_fetched) return false
  return Date.now() - new Date(feed.last_fetched).getTime() < 7 * 86_400_000
}

export function FeedManagerPanel({ open, onClose, feeds, onFeedsChange }: FeedManagerPanelProps) {
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

  const categories = [...new Set(feeds.map(f => f.category))].sort()

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
      fetch(`/api/feeds/${id}`, { method: 'DELETE' })
        .then(() => onFeedsChange())
        .finally(() => setDeletingId(null))
    }
  }, [confirmDeleteId, onFeedsChange])

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportMsg('')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch('/api/feeds/opml', { method: 'POST', body: formData })
      if (res.ok) {
        const data = await res.json()
        setImportMsg(`${data.added} ajoutés, ${data.skipped} déjà présents`)
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

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`
          fixed right-0 top-0 h-full w-full max-w-sm z-50
          bg-bg-surface border-l border-border-default shadow-2xl
          flex flex-col
          transition-transform duration-300 ease-out
          ${open ? 'translate-x-0' : 'translate-x-full'}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3.5 border-b border-border-subtle flex-shrink-0">
          <div className="flex items-center gap-2">
            <Rss className="w-4 h-4 text-accent-blue" />
            <span className="text-sm font-semibold text-text-primary">Feeds</span>
            <span className="text-xs text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded-full">
              {feeds.length}
            </span>
          </div>
          <div className="flex items-center gap-1">
            {/* Import OPML */}
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
            {/* Export OPML */}
            <button
              onClick={() => exportOPML(feeds)}
              className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
              title="Exporter OPML"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Import message */}
        {importMsg && (
          <div className="flex items-center gap-2 px-4 py-2 bg-accent-blue/10 border-b border-accent-blue/20">
            <CheckCircle2 className="w-3.5 h-3.5 text-accent-blue flex-shrink-0" />
            <span className="text-xs text-accent-blue">{importMsg}</span>
          </div>
        )}

        {/* Feed list */}
        <div className="flex-1 overflow-y-auto">
          {categories.map(category => (
            <div key={category}>
              <div className="px-4 py-1.5 bg-bg-elevated border-b border-border-subtle">
                <span className="text-[10px] font-semibold text-text-muted tracking-wider uppercase">
                  {category}
                </span>
              </div>
              {feeds.filter(f => f.category === category).map(feed => {
                const healthy = isHealthy(feed)
                const isConfirming = confirmDeleteId === feed.id
                const isDeleting = deletingId === feed.id
                return (
                  <div
                    key={feed.id}
                    className="flex items-center gap-3 px-4 py-2.5 border-b border-border-subtle hover:bg-bg-hover transition-colors group"
                  >
                    {/* Health dot */}
                    <div
                      className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${healthy ? 'bg-accent-green' : 'bg-accent-red/60'}`}
                      title={healthy ? 'Actif' : 'Aucun article récent'}
                    />

                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-text-primary truncate">{feed.name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
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
                          <span className="flex items-center gap-0.5 text-[10px] text-accent-red/70">
                            <AlertCircle className="w-2.5 h-2.5" />
                            Jamais lu
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Delete button */}
                    <button
                      onClick={() => handleDelete(feed.id)}
                      disabled={isDeleting}
                      className={`
                        flex items-center gap-1 rounded-md transition-all duration-150 text-[11px] font-medium flex-shrink-0
                        opacity-0 group-hover:opacity-100
                        ${isConfirming
                          ? 'px-2 py-1 bg-red-500/15 text-red-400 hover:bg-red-500/25 ring-1 ring-red-500/40 opacity-100'
                          : 'p-1.5 text-text-muted hover:text-accent-red hover:bg-bg-elevated'
                        }
                      `}
                      title={isConfirming ? 'Confirmer la suppression' : 'Supprimer'}
                    >
                      {isDeleting ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5 flex-shrink-0" />
                      )}
                      {isConfirming && <span>Confirmer?</span>}
                    </button>
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        {/* Add feed form */}
        <div className="border-t border-border-default bg-bg-surface px-4 py-4 flex-shrink-0">
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
              className="w-full bg-bg-elevated border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder-text-muted outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all"
            />
            <div className="flex gap-2">
              <input
                type="text"
                value={addName}
                onChange={e => setAddName(e.target.value)}
                placeholder="Nom (optionnel)"
                className="flex-1 bg-bg-elevated border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder-text-muted outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all"
              />
              <select
                value={addCategory}
                onChange={e => setAddCategory(e.target.value)}
                className="flex-1 bg-bg-elevated border border-border-default rounded-lg px-2 py-2 text-xs text-text-primary outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-all"
              >
                <option value="">Catégorie</option>
                {categories.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
                <option value="General">General</option>
              </select>
            </div>
            {addError && (
              <p className="text-[11px] text-accent-red flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {addError}
              </p>
            )}
            <button
              onClick={handleAdd}
              disabled={adding || !addUrl.trim()}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg bg-accent-blue text-white text-xs font-medium transition-all hover:bg-accent-blue/90 disabled:opacity-50 disabled:cursor-not-allowed"
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
    </>
  )
}
