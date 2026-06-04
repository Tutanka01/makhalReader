import { useEffect, useRef, useState } from 'react'
import { AlertCircle, ArrowRight, Check, Loader2, Lock, Mail, User } from 'lucide-react'

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
  const emailRef = useRef<HTMLInputElement>(null)

  useEffect(() => { emailRef.current?.focus() }, [mode])

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode)
    setError(null)
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
      } else {
        const body: Record<string, string> = { email, password }
        if (displayName.trim()) body.display_name = displayName.trim()
        if (inviteCode.trim()) body.invite_code = inviteCode.trim()

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
      }
    } catch {
      setError('Connection error.')
    } finally {
      setLoading(false)
    }
  }

  const inputBase = 'w-full rounded-md border border-border-default bg-bg px-10 py-2.5 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/15'
  const isDisabled = loading || !email || !password

  return (
    <div className="min-h-screen w-full bg-bg-base text-text-primary">
      <div className="mx-auto grid min-h-screen w-full max-w-6xl grid-cols-1 lg:grid-cols-[1fr_420px]">
        <section className="hidden border-r border-border-subtle px-10 py-12 lg:flex lg:flex-col lg:justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="Baṣīra" className="h-10 w-10 rounded-md object-cover" />
            <div>
              <div className="text-base font-semibold">Baṣīra</div>
              <div className="text-xs text-text-muted">Private research intelligence</div>
            </div>
          </div>

          <div className="max-w-xl">
            <h1 className="mb-4 text-4xl font-semibold leading-tight tracking-normal text-text-primary">
              Research feeds that stay quiet until you configure them.
            </h1>
            <p className="max-w-lg text-sm leading-6 text-text-secondary">
              Create your account, define your thesis, choose feeds, then Baṣīra starts polling and scoring only for you.
            </p>
            <div className="mt-8 grid max-w-lg grid-cols-1 gap-3">
              {[
                'No default user or hidden seed profile',
                'No RSS, extraction, or LLM calls before onboarding',
                'Per-user feeds, scores, and research context',
              ].map(item => (
                <div key={item} className="flex items-center gap-3 text-sm text-text-secondary">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-success-bg text-success">
                    <Check size={13} strokeWidth={2.5} />
                  </span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="text-xs text-text-muted">
            HttpOnly session cookies, scoped user data, Docker-local runtime.
          </div>
        </section>

        <main className="flex min-h-screen items-center justify-center px-5 py-8">
          <div className="w-full max-w-[390px]">
            <div className="mb-8 flex items-center gap-3 lg:hidden">
              <img src="/logo.png" alt="Baṣīra" className="h-10 w-10 rounded-md object-cover" />
              <div>
                <div className="text-base font-semibold">Baṣīra</div>
                <div className="text-xs text-text-muted">Private research intelligence</div>
              </div>
            </div>

            <div className="mb-6">
              <h2 className="text-xl font-semibold">
                {mode === 'login' ? 'Sign in' : 'Create your account'}
              </h2>
              <p className="mt-1 text-sm leading-6 text-text-muted">
                {mode === 'login'
                  ? 'Use your account to open your configured research feed.'
                  : 'The first account becomes admin and starts with onboarding.'}
              </p>
            </div>

            <div className="mb-5 grid grid-cols-2 rounded-md border border-border-subtle bg-bg-secondary p-1">
              <button
                type="button"
                onClick={() => switchMode('login')}
                className={`rounded px-3 py-2 text-sm font-medium transition-colors ${mode === 'login' ? 'bg-bg text-text-primary shadow-sm' : 'text-text-muted hover:text-text-primary'}`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => switchMode('register')}
                className={`rounded px-3 py-2 text-sm font-medium transition-colors ${mode === 'register' ? 'bg-bg text-text-primary shadow-sm' : 'text-text-muted hover:text-text-primary'}`}
              >
                Register
              </button>
            </div>

            <form onSubmit={submit} className="space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-text-secondary">Email</span>
                <span className="relative block">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
                  <input
                    ref={emailRef}
                    type="email"
                    value={email}
                    onChange={e => { setEmail(e.target.value); setError(null) }}
                    placeholder="you@university.edu"
                    autoComplete="email"
                    className={inputBase}
                  />
                </span>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-text-secondary">Password</span>
                <span className="relative block">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
                  <input
                    type="password"
                    value={password}
                    onChange={e => { setPassword(e.target.value); setError(null) }}
                    placeholder="Enter password"
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    className={inputBase}
                  />
                </span>
              </label>

              {mode === 'register' && (
                <>
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-medium text-text-secondary">Display name</span>
                    <span className="relative block">
                      <User className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
                      <input
                        type="text"
                        value={displayName}
                        onChange={e => setDisplayName(e.target.value)}
                        placeholder="Optional"
                        autoComplete="name"
                        className={inputBase}
                      />
                    </span>
                  </label>

                  <label className="block">
                    <span className="mb-1.5 block text-xs font-medium text-text-secondary">Invite code</span>
                    <input
                      type="text"
                      value={inviteCode}
                      onChange={e => setInviteCode(e.target.value)}
                      placeholder="Optional"
                      className="w-full rounded-md border border-border-default bg-bg px-3 py-2.5 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/15"
                    />
                  </label>
                </>
              )}

              {mode === 'login' && (
                <label className="flex cursor-pointer items-center gap-3 text-sm text-text-secondary">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={e => setRemember(e.target.checked)}
                    className="h-4 w-4 rounded border-border-default text-accent focus:ring-accent"
                  />
                  Keep me signed in
                </label>
              )}

              {error && (
                <div className="flex items-start gap-2 rounded-md border border-danger/20 bg-danger-bg px-3 py-2 text-sm text-danger">
                  <AlertCircle className="mt-0.5 shrink-0" size={16} />
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={isDisabled}
                className="flex h-10 w-full items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="animate-spin" size={16} />
                    {mode === 'login' ? 'Signing in' : 'Creating account'}
                  </>
                ) : (
                  <>
                    {mode === 'login' ? 'Sign in' : 'Create account'}
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </form>
          </div>
        </main>
      </div>
    </div>
  )
}
