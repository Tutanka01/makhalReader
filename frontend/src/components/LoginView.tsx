import { useState, useRef, useEffect } from 'react'

interface Props {
  onLogin: () => void
}

type AuthMode = 'login' | 'register'

export function LoginView({ onLogin }: Props) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [shake, setShake] = useState(false)
  const emailRef = useRef<HTMLInputElement>(null)

  useEffect(() => { emailRef.current?.focus() }, [mode])

  const switchMode = (m: AuthMode) => {
    setMode(m)
    setError(null)
    setShake(false)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password || loading) return
    setLoading(true)
    setError(null)

    try {
      if (mode === 'login') {
        const resp = await fetch('/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ email, password, remember }),
        })

        if (resp.ok) {
          onLogin()
          return
        }

        const data = await resp.json().catch(() => ({}))
        setError(
          resp.status === 429
            ? (data.detail ?? 'Too many attempts. Please wait.')
            : (data.detail ?? 'Invalid credentials.')
        )
        setPassword('')
        setShake(true)
        setTimeout(() => setShake(false), 500)
      } else {
        const body: Record<string, string> = { email, password }
        if (displayName) body.display_name = displayName
        if (inviteCode) body.invite_code = inviteCode

        const resp = await fetch('/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body),
        })

        if (resp.ok) {
          onLogin()
          return
        }

        const data = await resp.json().catch(() => ({}))
        setError(data.detail ?? 'Registration failed.')
        setPassword('')
        setShake(true)
        setTimeout(() => setShake(false), 500)
      }
    } catch {
      setError('Connection error.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-bg-base overflow-hidden relative">
      {/* Background glow */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute rounded-full opacity-20 blur-3xl"
          style={{
            width: 600,
            height: 600,
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -60%)',
            background: 'radial-gradient(circle, var(--accent) 0%, var(--purple) 40%, transparent 70%)',
          }}
        />
      </div>

      {/* Subtle grid */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)',
          backgroundSize: '52px 52px',
        }}
      />

      <div className="relative z-10 w-full max-w-[380px] px-6">

        {/* Logo */}
        <div className="text-center mb-10 select-none">
          <img
            src="/logo.png"
            alt="Baṣīra Logo"
            className="inline-flex w-14 h-14 rounded-2xl mb-5 object-cover"
          />
          <h1 style={{ color: 'var(--text-primary)', fontSize: 22, fontWeight: 600, letterSpacing: '-0.03em', margin: 0 }}>
            Baṣīra
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
            Your private intelligence feed
          </p>
        </div>

        {/* Card */}
        <form
          onSubmit={submit}
          style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 20,
            padding: '28px 28px 24px',
            backdropFilter: 'blur(12px)',
            animation: shake ? 'shake 0.4s ease' : undefined,
          }}
        >
          <style>{`
            @keyframes shake {
              0%,100%{transform:translateX(0)}
              20%{transform:translateX(-8px)}
              40%{transform:translateX(8px)}
              60%{transform:translateX(-5px)}
              80%{transform:translateX(5px)}
            }
          `}</style>

          {/* Tabs */}
          <div style={{
            display: 'flex',
            gap: 4,
            background: 'var(--bg-secondary)',
            padding: 3,
            borderRadius: 8,
            marginBottom: 20,
          }}>
            <button
              type="button"
              onClick={() => switchMode('login')}
              style={{
                flex: 1,
                padding: '7px 0',
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
                background: mode === 'login' ? 'var(--bg)' : 'transparent',
                color: mode === 'login' ? 'var(--text-primary)' : 'var(--text-muted)',
                boxShadow: mode === 'login' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
                border: 'none',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={() => switchMode('register')}
              style={{
                flex: 1,
                padding: '7px 0',
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
                background: mode === 'register' ? 'var(--bg)' : 'transparent',
                color: mode === 'register' ? 'var(--text-primary)' : 'var(--text-muted)',
                boxShadow: mode === 'register' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
                border: 'none',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              Create account
            </button>
          </div>

          {/* Email field */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 7, fontWeight: 500 }}>
              Email
            </label>
            <input
              ref={emailRef}
              type="email"
              value={email}
              onChange={e => { setEmail(e.target.value); setError(null) }}
              placeholder="you@university.edu"
              autoComplete="email"
              style={{
                width: '100%',
                padding: '11px 14px',
                borderRadius: 10,
                border: `1.5px solid ${error ? 'var(--danger)' : 'var(--border-default)'}`,
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                fontSize: 14,
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => {
                if (!error) e.target.style.borderColor = 'var(--accent)'
              }}
              onBlur={e => {
                if (!error) e.target.style.borderColor = 'var(--border-default)'
              }}
            />
          </div>

          {/* Password field */}
          <div style={{ marginBottom: mode === 'register' ? 12 : 16 }}>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 7, fontWeight: 500 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={e => { setPassword(e.target.value); setError(null) }}
              placeholder="••••••••••••••••"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              style={{
                width: '100%',
                padding: '11px 14px',
                borderRadius: 10,
                border: `1.5px solid ${error ? 'var(--danger)' : 'var(--border-default)'}`,
                background: 'var(--bg-elevated)',
                color: 'var(--text-primary)',
                fontSize: 14,
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => {
                if (!error) e.target.style.borderColor = 'var(--accent)'
              }}
              onBlur={e => {
                if (!error) e.target.style.borderColor = 'var(--border-default)'
              }}
            />
          </div>

          {/* Register-only fields */}
          {mode === 'register' && (
            <>
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 7, fontWeight: 500 }}>
                  Display name <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>— optional</span>
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  placeholder="e.g. Rachid Fall"
                  autoComplete="name"
                  style={{
                    width: '100%',
                    padding: '11px 14px',
                    borderRadius: 10,
                    border: '1.5px solid var(--border-default)',
                    background: 'var(--bg-elevated)',
                    color: 'var(--text-primary)',
                    fontSize: 14,
                    outline: 'none',
                    boxSizing: 'border-box',
                    transition: 'border-color 0.15s',
                  }}
                  onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
                  onBlur={e => { e.target.style.borderColor = 'var(--border-default)' }}
                />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 7, fontWeight: 500 }}>
                  Invite code <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>— optional, joins a lab</span>
                </label>
                <input
                  type="text"
                  value={inviteCode}
                  onChange={e => setInviteCode(e.target.value)}
                  placeholder="e.g. EVA-LAB-2026"
                  style={{
                    width: '100%',
                    padding: '11px 14px',
                    borderRadius: 10,
                    border: '1.5px solid var(--border-default)',
                    background: 'var(--bg-elevated)',
                    color: 'var(--text-primary)',
                    fontSize: 14,
                    outline: 'none',
                    boxSizing: 'border-box',
                    transition: 'border-color 0.15s',
                  }}
                  onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
                  onBlur={e => { e.target.style.borderColor = 'var(--border-default)' }}
                />
              </div>
            </>
          )}

          {/* Error */}
          {error && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="2.5" strokeLinecap="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <span style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</span>
            </div>
          )}

          {/* Remember toggle (login only) */}
          {mode === 'login' && (
            <div
              style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22, cursor: 'pointer', userSelect: 'none' }}
              onClick={() => setRemember(v => !v)}
            >
              <div style={{
                position: 'relative',
                width: 36,
                height: 20,
                borderRadius: 99,
                background: remember ? 'var(--accent)' : 'var(--bg-hover)',
                transition: 'background 0.2s',
                flexShrink: 0,
              }}>
                <div style={{
                  position: 'absolute',
                  top: 3,
                  left: remember ? 19 : 3,
                  width: 14,
                  height: 14,
                  borderRadius: '50%',
                  background: 'white',
                  transition: 'left 0.2s',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.4)',
                }}/>
              </div>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                Keep me signed in
              </span>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || !email || !password}
            style={{
              width: '100%',
              padding: '11px',
              borderRadius: 10,
              border: 'none',
              cursor: loading || !email || !password ? 'not-allowed' : 'pointer',
              background: loading || !email || !password
                ? 'color-mix(in srgb, var(--accent) 35%, transparent)'
                : 'linear-gradient(135deg, var(--accent), var(--purple))',
              color: loading || !email || !password ? 'rgba(255,255,255,0.4)' : 'white',
              fontSize: 14,
              fontWeight: 600,
              transition: 'all 0.15s',
              letterSpacing: '-0.01em',
            }}
          >
            {loading ? (
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <svg style={{ animation: 'spin 0.8s linear infinite' }} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
                <style>{'@keyframes spin{to{transform:rotate(360deg)}}'}</style>
                {mode === 'login' ? 'Signing in…' : 'Creating account…'}
              </span>
            ) : mode === 'login' ? 'Sign in →' : 'Create account →'}
          </button>
        </form>

        {/* Footer */}
        <p style={{ textAlign: 'center', marginTop: 24, fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.02em' }}>
          HttpOnly · Secure · SameSite=Strict
        </p>
      </div>
    </div>
  )
}
