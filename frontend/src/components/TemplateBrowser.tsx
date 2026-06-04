import { useEffect, useState } from 'react'
import { X, Loader2 } from 'lucide-react'

interface ApiTemplate {
  id: number
  name: string
  domain_label: string
  scope: 'global' | 'org' | 'user'
  cluster_count: number | null
  created_at: string
}

interface TemplateBrowserProps {
  onApply: (templateId: number) => Promise<void>
  onClose: () => void
  mode: 'onboarding' | 'editor'
}

export default function TemplateBrowser({ onApply, onClose, mode }: TemplateBrowserProps) {
  const [templates, setTemplates] = useState<ApiTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [applyingId, setApplyingId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')

    fetch('/api/templates', { credentials: 'include' })
      .then(r => {
        if (!r.ok) throw new Error('Failed to load templates')
        return r.json()
      })
      .then(data => {
        if (!cancelled) setTemplates(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setError('Could not load templates')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [])

  const handleApply = async (id: number) => {
    setApplyingId(id)
    try {
      await onApply(id)
    } finally {
      setApplyingId(null)
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-bg-surface rounded-xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col"
          onClick={e => e.stopPropagation()}
        >
          <div className="flex items-center gap-2 px-5 py-4 border-b border-border-subtle">
            <h2 className="text-sm font-semibold text-text-primary flex-1">
              {mode === 'onboarding' ? 'Browse Starter Packs' : 'Template Browser'}
            </h2>
            <button onClick={onClose} className="text-text-muted hover:text-text-primary">
              <X size={16} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {loading && (
              <div className="flex justify-center py-10 text-text-muted">
                <Loader2 size={22} className="animate-spin" />
              </div>
            )}

            {error && (
              <p className="text-xs text-danger text-center py-10">{error}</p>
            )}

            {!loading && !error && templates.length === 0 && (
              <p className="text-xs text-text-muted text-center py-10">
                No templates available yet.
              </p>
            )}

            {!loading && !error && templates.length > 0 && (
              <div className="grid grid-cols-2 gap-3">
                {templates.map(t => (
                  <div
                    key={t.id}
                    className="rounded-lg border border-border bg-surface p-4 flex flex-col gap-2"
                  >
                    <div className="text-sm font-semibold text-text truncate">{t.name}</div>
                    <div className="text-xs text-text-muted truncate">
                      {t.domain_label || '—'}
                    </div>
                    <div>
                      <span className="text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full">
                        {t.cluster_count ?? '—'} clusters
                      </span>
                    </div>
                    <button
                      onClick={() => handleApply(t.id)}
                      disabled={applyingId === t.id}
                      className="mt-auto rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50 transition-colors"
                    >
                      {applyingId === t.id ? (
                        <Loader2 size={12} className="animate-spin mx-auto" />
                      ) : (
                        'Use this template'
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
