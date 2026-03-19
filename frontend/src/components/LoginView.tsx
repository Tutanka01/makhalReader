import { useState, useRef, useEffect } from 'react'

interface Props {
  onLogin: () => void
}

export function LoginView({ onLogin }: Props) {
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [shake, setShake] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password || loading) return
    setLoading(true)
    setError(null)

    try {
      const resp = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ password, remember }),
      })

      if (resp.ok) {
        onLogin()
        return
      }

      const data = await resp.json().catch(() => ({}))
      setError(
        resp.status === 429
          ? (data.detail ?? 'Too many attempts. Please wait.')
          : 'Incorrect password.'
      )
      setPassword('')
      setShake(true)
      setTimeout(() => setShake(false), 500)
      setTimeout(() => inputRef.current?.focus(), 10)
    } catch {
      setError('Connection error.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{ fontFamily: 'system-ui, -apple-system, sans-serif' }}
      className="min-h-screen w-full flex items-center justify-center bg-[#0a0a0b] overflow-hidden relative"
    >
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
            background: 'radial-gradient(circle, #6366f1 0%, #8b5cf6 40%, transparent 70%)',
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
          <div
            className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-5"
            style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}
          >
            <span style={{ fontSize: 26, color: 'white', lineHeight: 1 }}>◉</span>
          </div>
          <h1 style={{ color: '#f4f4f5', fontSize: 22, fontWeight: 600, letterSpacing: '-0.03em', margin: 0 }}>
            MakhalReader
          </h1>
          <p style={{ color: '#71717a', fontSize: 13, marginTop: 6 }}>
            Your private intelligence feed
          </p>
        </div>

        {/* Card */}
        <form
          onSubmit={submit}
          style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
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

          {/* Password field */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, color: '#a1a1aa', marginBottom: 7, fontWeight: 500 }}>
              Password
            </label>
            <input
              ref={inputRef}
              type="password"
              value={password}
              onChange={e => { setPassword(e.target.value); setError(null) }}
              placeholder="••••••••••••••••"
              autoComplete="current-password"
              style={{
                width: '100%',
                padding: '11px 14px',
                borderRadius: 10,
                border: `1.5px solid ${error ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.1)'}`,
                background: 'rgba(255,255,255,0.06)',
                color: '#f4f4f5',
                fontSize: 14,
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => {
                if (!error) e.target.style.borderColor = 'rgba(99,102,241,0.7)'
              }}
              onBlur={e => {
                if (!error) e.target.style.borderColor = 'rgba(255,255,255,0.1)'
              }}
            />
            {error && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2.5" strokeLinecap="round">
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span style={{ fontSize: 12, color: '#f87171' }}>{error}</span>
              </div>
            )}
          </div>

          {/* Remember toggle */}
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22, cursor: 'pointer', userSelect: 'none' }}
            onClick={() => setRemember(v => !v)}
          >
            {/* Toggle pill */}
            <div style={{
              position: 'relative',
              width: 36,
              height: 20,
              borderRadius: 99,
              background: remember ? '#6366f1' : 'rgba(255,255,255,0.1)',
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
            <span style={{ fontSize: 13, color: '#a1a1aa' }}>
              Keep me signed in
            </span>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || !password}
            style={{
              width: '100%',
              padding: '11px',
              borderRadius: 10,
              border: 'none',
              cursor: loading || !password ? 'not-allowed' : 'pointer',
              background: loading || !password
                ? 'rgba(99,102,241,0.35)'
                : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              color: loading || !password ? 'rgba(255,255,255,0.4)' : 'white',
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
                Signing in…
              </span>
            ) : 'Sign in →'}
          </button>
        </form>

        {/* Footer */}
        <p style={{ textAlign: 'center', marginTop: 24, fontSize: 11, color: '#3f3f46', letterSpacing: '0.02em' }}>
          HttpOnly · Secure · SameSite=Strict
        </p>
      </div>
    </div>
  )
}
