import { useCallback, useEffect, useState } from 'react'
import { Shield, Plus, Copy, RefreshCw, CheckCircle, Clock, Building2, Trash2, ShieldCheck, ShieldOff } from 'lucide-react'
import apiClient, { ApiError } from '../apiClient'
import { useCurrentUser } from '../context/UserContext'
import type { Organization } from '../types'
import { ProviderBadge } from './ProviderBadge'

// ── Create org panel ────────────────────────────────────────────────────────

function CreateOrgPanel({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const label = name.trim()
    if (!label || loading) return
    setLoading(true)
    setError(null)
    try {
      await apiClient.post('/api/admin/org', { name: label })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Erreur lors de la création')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-20">
      <div className="w-full max-w-md">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-5" style={{ background: 'var(--purple-bg, #F3E8FF)' }}>
          <Building2 size={20} style={{ color: 'var(--purple, #9333EA)' }} />
        </div>
        <h1 className="text-xl font-semibold text-text-primary mb-2 tracking-tight">
          Créer votre laboratoire
        </h1>
        <p className="text-sm text-text-muted mb-7">
          Donnez un nom à votre organisation pour générer un code d'invitation et gérer vos membres.
        </p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1.5">Nom du laboratoire</label>
            <input
              type="text"
              value={name}
              onChange={e => { setName(e.target.value); setError(null) }}
              placeholder="ex. EVA Lab / LIG-MBSE"
              className="w-full px-3 py-2.5 rounded-lg border border-border-default bg-bg-elevated text-text-primary text-sm outline-none transition-colors"
              style={{ boxSizing: 'border-box' }}
            />
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
          <button
            type="submit"
            disabled={!name.trim() || loading}
            className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-40"
            style={{ background: 'linear-gradient(135deg, var(--accent), var(--purple))' }}
          >
            {loading ? 'Création…' : 'Créer le laboratoire →'}
          </button>
        </form>
      </div>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────

export default function AdminPage() {
  const { user, refetch: refetchUser } = useCurrentUser()
  const [org, setOrg] = useState<Organization | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [toast, setToast] = useState('')
  const [memberAction, setMemberAction] = useState<number | null>(null)

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2600)
  }

  const fetchOrg = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.get<Organization>('/api/admin/org')
      setOrg(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setOrg(null)
      } else {
        setError(err instanceof ApiError ? err.detail : 'Erreur de chargement')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (user?.org_id) fetchOrg()
  }, [user?.org_id, fetchOrg])

  const handleOrgCreated = async () => {
    await refetchUser()
    await fetchOrg()
  }

  const handleRegenerateCode = async () => {
    setRegenerating(true)
    try {
      const result = await apiClient.post<{ invite_code: string }>('/api/admin/org/invite-code')
      setOrg(prev => prev ? { ...prev, invite_code: result.invite_code } : prev)
      showToast('Nouveau code généré')
    } catch {
      showToast('Échec de la régénération')
    } finally {
      setRegenerating(false)
    }
  }

  const handleCopy = async () => {
    if (!org?.invite_code) return
    await navigator.clipboard.writeText(org.invite_code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleRoleChange = async (memberId: number, newRole: 'admin' | 'member') => {
    setMemberAction(memberId)
    try {
      await apiClient.patch(`/api/admin/org/members/${memberId}`, { role: newRole })
      setOrg(prev => prev ? {
        ...prev,
        members: prev.members.map(m => m.id === memberId ? { ...m, role: newRole } : m),
      } : prev)
      showToast(newRole === 'admin' ? 'Membre promu administrateur' : 'Rôle rétrogradé à membre')
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Échec de la mise à jour')
    } finally {
      setMemberAction(null)
    }
  }

  const handleRemoveMember = async (memberId: number, displayName: string) => {
    const ok = window.confirm(`Retirer "${displayName}" de l'organisation ? Ses données restent intactes.`)
    if (!ok) return
    setMemberAction(memberId)
    try {
      await apiClient.del(`/api/admin/org/members/${memberId}`)
      setOrg(prev => prev ? {
        ...prev,
        members: prev.members.filter(m => m.id !== memberId),
      } : prev)
      showToast('Membre retiré de l\'organisation')
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : 'Échec du retrait')
    } finally {
      setMemberAction(null)
    }
  }

  const initials = (name: string) =>
    name.split(' ').map(s => s[0]).join('').toUpperCase().slice(0, 2) || '?'

  if (user?.role !== 'admin') {
    return (
      <div className="flex items-center justify-center h-full text-sm text-text-muted">
        Accès réservé aux administrateurs.
      </div>
    )
  }

  if (!user.org_id) {
    return <CreateOrgPanel onCreated={handleOrgCreated} />
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-2 text-sm text-text-muted">
        <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M21 12a9 9 0 11-6.219-8.56"/>
        </svg>
        Chargement…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center space-y-2">
          <p className="text-sm text-danger">{error}</p>
          <button onClick={fetchOrg} className="text-xs text-accent hover:underline">Réessayer</button>
        </div>
      </div>
    )
  }

  if (!org) return null

  return (
    <div className="h-full overflow-y-auto" style={{ padding: '28px 32px' }}>
      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-bg-elevated border border-border-default rounded-lg px-4 py-2 text-sm text-text-primary shadow-2xl">
          {toast}
        </div>
      )}

      {/* Privacy banner */}
      <div className="flex items-start gap-3 bg-bg-elevated border border-border-subtle rounded-xl px-5 py-4 mb-6">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5" style={{ background: 'var(--purple-bg, #F3E8FF)' }}>
          <Shield size={16} style={{ color: 'var(--purple, #9333EA)' }} />
        </div>
        <div className="text-sm text-text-primary leading-relaxed">
          <strong>{org.name}</strong> — vue administrateur. Vous gérez le catalogue partagé et les membres, mais vous <strong>ne pouvez pas</strong> voir les scores, highlights ou reviews privés de chaque chercheur.{' '}
          <span className="text-[11px] font-mono text-text-muted">NFR-T1 · FR-MT-47</span>
        </div>
      </div>

      {/* Invite code */}
      <div className="border border-border-subtle rounded-xl p-4 mb-6">
        <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Code d'invitation</div>
        <div className="flex items-center gap-2">
          <code className="flex-1 px-3 py-2 bg-bg-elevated rounded-lg text-sm font-mono text-text-primary border border-border-subtle tracking-widest select-all">
            {org.invite_code || '—'}
          </code>
          <button
            onClick={handleCopy}
            disabled={!org.invite_code}
            title="Copier"
            className="p-2 rounded-lg border border-border-default bg-bg-elevated text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40"
          >
            {copied ? <CheckCircle size={14} className="text-success" /> : <Copy size={14} />}
          </button>
          <button
            onClick={handleRegenerateCode}
            disabled={regenerating}
            title="Régénérer"
            className="p-2 rounded-lg border border-border-default bg-bg-elevated text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40"
          >
            <RefreshCw size={14} className={regenerating ? 'animate-spin' : ''} />
          </button>
        </div>
        <p className="text-[11px] text-text-muted mt-2">
          Partagez ce code à la création de compte pour rattacher un chercheur à votre org.
        </p>
      </div>

      {/* Members table */}
      <div className="border border-border-subtle rounded-xl overflow-hidden mb-6">
        <div className="flex items-center justify-between px-[18px] py-3 border-b border-border-subtle">
          <div>
            <span className="text-sm font-semibold text-text-primary">Membres</span>
            <span className="ml-2 text-xs text-text-muted bg-bg-elevated px-2 py-0.5 rounded-full font-mono">
              {org.members.length}
            </span>
          </div>
        </div>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-xs text-text-muted uppercase tracking-wider border-b border-border-subtle bg-bg-elevated/50">
              <th className="text-left px-[18px] py-2.5 font-medium">Chercheur</th>
              <th className="text-left px-[18px] py-2.5 font-medium hidden md:table-cell">Email</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Rôle</th>
              <th className="text-left px-[18px] py-2.5 font-medium hidden sm:table-cell">Thèse</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Onboarding</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {org.members.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-[18px] py-8 text-center text-sm text-text-muted">
                  Aucun membre pour l'instant — partagez le code d'invitation.
                </td>
              </tr>
            ) : org.members.map(m => {
              const isSelf = m.id === user.id
              const busy = memberAction === m.id
              return (
                <tr key={m.id} className="border-t border-border-subtle hover:bg-bg-hover/50 transition-colors">
                  <td className="px-[18px] py-2.5">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold text-white flex-shrink-0"
                        style={{ background: m.role === 'admin' ? 'var(--purple, #9333EA)' : 'var(--accent, #2F6FED)' }}
                      >
                        {initials(m.display_name || m.email)}
                      </div>
                      <span className="text-text-primary text-[13px]">{m.display_name || m.email}</span>
                      {isSelf && <span className="text-[10px] text-text-muted italic">(vous)</span>}
                    </div>
                  </td>
                  <td className="px-[18px] py-2.5 text-text-secondary text-[13px] hidden md:table-cell">{m.email}</td>
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
                  <td className="px-[18px] py-2.5 text-text-secondary text-[13px] hidden sm:table-cell">
                    <span className="truncate block max-w-[160px]" title={m.thesis_title}>
                      {m.thesis_title || <span className="italic text-text-muted">Non renseignée</span>}
                    </span>
                  </td>
                  <td className="px-[18px] py-2.5">
                    {m.onboarding_done ? (
                      <span className="flex items-center gap-1 text-[13px] font-medium text-success">
                        <CheckCircle size={12} /> Terminé
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[13px] text-text-muted">
                        <Clock size={12} /> En attente
                      </span>
                    )}
                  </td>
                  <td className="px-[18px] py-2.5">
                    {isSelf ? (
                      <span className="text-[11px] text-text-muted">—</span>
                    ) : (
                      <div className="flex items-center gap-1">
                        {m.role === 'member' ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleRoleChange(m.id, 'admin')}
                            title="Promouvoir admin"
                            className="p-1.5 rounded-md text-text-muted hover:text-purple hover:bg-purple/10 transition-colors disabled:opacity-40"
                          >
                            <ShieldCheck size={14} />
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => handleRoleChange(m.id, 'member')}
                            title="Rétrograder membre"
                            className="p-1.5 rounded-md text-text-muted hover:text-accent hover:bg-accent/10 transition-colors disabled:opacity-40"
                          >
                            <ShieldOff size={14} />
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => handleRemoveMember(m.id, m.display_name || m.email)}
                          title="Retirer de l'org"
                          className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-colors disabled:opacity-40"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Feed catalog */}
      <div className="border border-border-subtle rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-[18px] py-3 border-b border-border-subtle">
          <div>
            <span className="text-sm font-semibold text-text-primary">Catalogue de feeds partagé</span>
            <p className="text-xs text-text-muted mt-0.5">
              Pollé une fois pour tout le labo — chaque membre s'abonne et est scoré individuellement (fan-out).
            </p>
          </div>
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[13px] font-medium text-accent hover:bg-accent/10 border border-accent/30 transition-colors ml-4 flex-shrink-0"
            onClick={() => showToast('Utilisez le Feed Manager pour ajouter des feeds au catalogue.')}
          >
            <Plus size={13} /> Ajouter
          </button>
        </div>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-xs text-text-muted uppercase tracking-wider border-b border-border-subtle bg-bg-elevated/50">
              <th className="text-left px-[18px] py-2.5 font-medium">Feed</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Type</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Catégorie</th>
              <th className="text-left px-[18px] py-2.5 font-medium">Abonnés</th>
            </tr>
          </thead>
          <tbody>
            {org.feed_catalog.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-[18px] py-8 text-center text-sm text-text-muted">
                  Aucun feed actif.
                </td>
              </tr>
            ) : org.feed_catalog.map(f => (
              <tr key={f.id} className="border-t border-border-subtle hover:bg-bg-hover/50 transition-colors">
                <td className="px-[18px] py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-[7px] h-[7px] rounded-full flex-shrink-0" style={{ background: 'var(--accent)' }} />
                    <span className="text-text-primary text-[13px]">{f.name}</span>
                  </div>
                </td>
                <td className="px-[18px] py-2.5">
                  <ProviderBadge provider={f.provider} />
                </td>
                <td className="px-[18px] py-2.5 text-text-secondary text-[13px]">{f.category}</td>
                <td className="px-[18px] py-2.5">
                  <span
                    className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium"
                    style={{ background: 'var(--bg-active, #F0F0F0)', color: 'var(--text-secondary, #6B7280)' }}
                  >
                    {f.subscriber_count} {f.subscriber_count === 1 ? 'abonné' : 'abonnés'}
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
