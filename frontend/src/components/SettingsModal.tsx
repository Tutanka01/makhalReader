import { useState, useEffect } from 'react'
import { X, Loader2, Check, Eye, EyeOff } from 'lucide-react'
import { useCurrentUser } from '../context/UserContext'
import apiClient from '../apiClient'

interface Props {
  open: boolean
  onClose: () => void
}

export default function SettingsModal({ open, onClose }: Props) {
  const { user, refetch } = useCurrentUser()
  const [displayName, setDisplayName] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (open && user) {
      setDisplayName(user.display_name)
      setNewPassword('')
      setConfirmPassword('')
      setMessage(null)
      setDirty(false)
    }
  }, [open, user])

  if (!open) return null

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const body: Record<string, string> = {}
      if (displayName !== user?.display_name) {
        body.display_name = displayName
      }
      if (newPassword) {
        if (newPassword.length < 6) {
          setMessage({ type: 'error', text: 'Password must be at least 6 characters' })
          setSaving(false)
          return
        }
        if (newPassword !== confirmPassword) {
          setMessage({ type: 'error', text: 'Passwords do not match' })
          setSaving(false)
          return
        }
        body.new_password = newPassword
      }
      if (Object.keys(body).length === 0) {
        setMessage({ type: 'error', text: 'No changes to save' })
        setSaving(false)
        return
      }
      await apiClient.put('/auth/me', body)
      setMessage({ type: 'ok', text: 'Settings saved' })
      setNewPassword('')
      setConfirmPassword('')
      setDirty(false)
      refetch()
    } catch (err: any) {
      setMessage({ type: 'error', text: err?.detail || 'Failed to save settings' })
    } finally {
      setSaving(false)
    }
  }

  const changed =
    displayName !== user?.display_name ||
    newPassword.length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-bg-surface border border-border-default rounded-2xl w-full max-w-md shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
          <h2 className="text-sm font-semibold text-text-primary tracking-wide">Account Settings</h2>
          <button onClick={onClose} className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-text-primary transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Email</label>
            <input
              type="email"
              value={user?.email ?? ''}
              disabled
              className="w-full px-3 py-2 bg-bg-elevated border border-border-subtle rounded-lg text-[13px] text-text-muted cursor-not-allowed"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-text-muted mb-1">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={e => { setDisplayName(e.target.value); setDirty(true) }}
              className="w-full px-3 py-2 bg-bg-base border border-border-default rounded-lg text-[13px] text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40 transition-shadow"
              placeholder="Your display name"
              maxLength={100}
            />
          </div>

          <div className="border-t border-border-subtle pt-4">
            <label className="block text-xs font-medium text-text-muted mb-1">New Password (leave blank to keep current)</label>
            <div className="relative">
              <input
                type={showPwd ? 'text' : 'password'}
                value={newPassword}
                onChange={e => { setNewPassword(e.target.value); setDirty(true) }}
                className="w-full px-3 py-2 pr-9 bg-bg-base border border-border-default rounded-lg text-[13px] text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40 transition-shadow"
                placeholder="New password"
                minLength={6}
              />
              <button
                type="button"
                onClick={() => setShowPwd(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-primary"
              >
                {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            {newPassword && (
              <input
                type="password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2 mt-2 bg-bg-base border border-border-default rounded-lg text-[13px] text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40 transition-shadow"
                placeholder="Confirm new password"
                minLength={6}
              />
            )}
          </div>

          {message && (
            <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-lg ${
              message.type === 'ok' ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
            }`}>
              {message.type === 'ok' ? <Check size={14} /> : null}
              {message.text}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-subtle">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium text-text-secondary hover:bg-bg-elevated rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !changed}
            className="px-4 py-1.5 text-xs font-medium bg-accent text-white rounded-lg hover:bg-accent/90 disabled:opacity-40 transition-colors flex items-center gap-1.5"
          >
            {saving && <Loader2 size={12} className="animate-spin" />}
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
