import { useCallback, useEffect, useState } from 'react'
import { Shield, Plus } from 'lucide-react'

interface OrgMember {
  id: number
  email: string
  display_name: string
  role: string
  onboarding_done: boolean
  thesis: string
}

interface CatalogFeed {
  id: number
  name: string
  category: string
  subscriber_count: number
}

interface OrgData {
  id: number
  name: string
  invite_code: string | null
  members: OrgMember[]
  feed_catalog: CatalogFeed[]
}

export default function AdminPage() {
  const [org, setOrg] = useState<OrgData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [regenerating, setRegenerating] = useState(false)
  const [toast, setToast] = useState('')

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2600)
  }

  const fetchOrg = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/admin/org', { credentials: 'include' })
      if (res.ok) {
        setOrg(await res.json())
      } else {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Failed to load org')
      }
    } catch {
      setError('Network error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchOrg() }, [fetchOrg])

  const handleRegenerateCode = async () => {
    setRegenerating(true)
    try {
      const res = await fetch('/api/admin/org/invite-code', {
        method: 'POST',
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        setOrg(prev => prev ? { ...prev, invite_code: data.invite_code } : prev)
        showToast('New invite code generated')
      }
    } catch {
      showToast('Failed to regenerate code')
    } finally {
      setRegenerating(false)
    }
  }

  const initials = (name: string) =>
    name.split(' ').map(s => s[0]).join('').toUpperCase().slice(0, 2)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-sm">
        <svg className="animate-spin mr-2" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M21 12a9 9 0 11-6.219-8.56"/>
        </svg>
        Loading…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-danger text-sm">
        {error}
      </div>
    )
  }

  if (!org) return null

  const memberCount = org.members.length
  const code = org.invite_code || '—'

  return (
    <div className="h-full overflow-y-auto" style={{ padding: '28px 32px' }}>
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-bg-elevated border border-border-default rounded-lg px-4 py-2 text-sm text-text-primary shadow-2xl">
          {toast}
        </div>
      )}

      <div className="flex items-start gap-3 bg-bg-elevated border border-border-subtle rounded-xl px-5 py-4 mb-6">
        <div className="w-9 h-9 rounded-lg bg-purple-500/10 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Shield size={18} className="text-purple-500" />
        </div>
        <div className="text-sm text-text-primary leading-relaxed">
          <strong>{org.name}</strong> — admin view. You manage the shared catalog and members, but you <strong>cannot</strong> see any researcher's private scores, highlights or reviews.{' '}
          <span className="text-[11px] font-mono text-text-muted">NFR-T1 · FR-MT-47</span>
        </div>
      </div>

      <div className="border border-border-subtle rounded-xl overflow-hidden mb-6">
        <div style={{ padding: '14px 18px' }}>
          <h4 className="text-sm font-semibold text-text-primary m-0">Members</h4>
          <div className="text-xs text-text-muted mt-0.5">
            {memberCount} researcher{memberCount !== 1 ? 's' : ''} · invite code{' '}
            <span className="font-mono bg-bg-hover px-1.5 py-0.5 rounded text-text-primary">{code}</span>
            <button
              onClick={handleRegenerateCode}
              disabled={regenerating}
              className="ml-2 text-xs text-accent hover:underline disabled:opacity-50"
            >
              {regenerating ? '…' : 'Regenerate'}
            </button>
          </div>
        </div>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-t border-border-subtle text-xs text-text-muted uppercase tracking-wider">
              <th className="text-left px-[18px] py-2.5 font-medium">Researcher</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Email</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Role</th>
              <th className="text-left px-[18px] py-2.5 font-medium hidden sm:table-cell">Thesis</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Onboarded</th>
            </tr>
          </thead>
          <tbody>
            {org.members.map(m => (
              <tr key={m.id} className="border-t border-border-subtle hover:bg-bg-hover/50">
                <td className="px-[18px] py-2.5">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold text-white flex-shrink-0"
                      style={{ background: m.role === 'admin' ? '#6B4FBB' : '#2F6FED' }}
                    >
                      {initials(m.display_name || m.email)}
                    </div>
                    <span className="text-text-primary text-[13px]">{m.display_name || m.email}</span>
                  </div>
                </td>
                <td className="px-[18px] py-2.5 text-text-secondary text-[13px]">{m.email}</td>
                <td className="px-[18px] py-2.5">
                  <span
                    className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium"
                    style={{
                      background: m.role === 'admin' ? 'var(--purple-bg, #F3E8FF)' : 'var(--bg-active, #F0F0F0)',
                      color: m.role === 'admin' ? 'var(--purple, #9333EA)' : 'var(--text-secondary, #6B7280)',
                    }}
                  >
                    {m.role}
                  </span>
                </td>
                <td className="px-[18px] py-2.5 text-text-secondary text-[13px] hidden sm:table-cell truncate max-w-[200px]">
                  {m.thesis || '—'}
                </td>
                <td className="px-[18px] py-2.5">
                  {m.onboarding_done ? (
                    <span className="text-emerald-600 font-semibold text-[13px]">✓ active</span>
                  ) : (
                    <span className="text-amber-600 text-[13px]">pending</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border border-border-subtle rounded-xl overflow-hidden">
        <div style={{ padding: '14px 18px' }} className="flex items-center">
          <div>
            <h4 className="text-sm font-semibold text-text-primary m-0">Shared feed catalog</h4>
            <div className="text-xs text-text-muted mt-0.5">
              Polled once for the whole lab; each member subscribes & is scored individually (fan-out).
            </div>
          </div>
          <button
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-accent hover:bg-accent/10 border border-accent/30 transition-colors"
            onClick={() => showToast('Add catalog feed — use Feed Manager')}
          >
            <Plus size={14} /> Add feed
          </button>
        </div>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-t border-border-subtle text-xs text-text-muted uppercase tracking-wider">
              <th className="text-left px-[18px] py-2.5 font-medium">Feed</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Category</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Subscribers</th>
            </tr>
          </thead>
          <tbody>
            {org.feed_catalog.map(f => (
              <tr key={f.id} className="border-t border-border-subtle hover:bg-bg-hover/50">
                <td className="px-[18px] py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-[7px] h-[7px] rounded-full bg-accent/60 flex-shrink-0" />
                    <span className="text-text-primary text-[13px]">{f.name}</span>
                  </div>
                </td>
                <td className="px-[18px] py-2.5 text-text-secondary text-[13px]">{f.category}</td>
                <td className="px-[18px] py-2.5">
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium" style={{ background: 'var(--bg-active, #F0F0F0)', color: 'var(--text-secondary, #6B7280)' }}>
                    {f.subscriber_count} {f.subscriber_count === 1 ? 'researcher' : 'researchers'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
