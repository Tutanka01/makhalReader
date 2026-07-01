import { useState, useRef, useEffect } from 'react'
import { Loader2, LockKeyhole, ShieldCheck } from 'lucide-react'

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
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-bg-base px-6">
      <div className="relative z-10 w-full max-w-[390px]">

        {/* Logo */}
        <div className="text-center mb-10 select-none">
          <div className="mb-5 inline-flex h-14 w-14 items-center justify-center rounded-md bg-accent-blue/12 text-accent-blue">
            <LockKeyhole className="h-6 w-6" />
          </div>
          <h1 className="text-[22px] font-semibold text-text-primary">
            MakhalReader
          </h1>
          <p className="mt-1.5 text-sm text-text-muted">
            Ton flux privé, trié avant lecture.
          </p>
        </div>

        {/* Card */}
        <form
          onSubmit={submit}
          className="rounded-md bg-bg-surface p-6 shadow-2xl"
          style={{ animation: shake ? 'shake 0.4s ease' : undefined }}
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
          <div className="mb-4">
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              Mot de passe
            </label>
            <input
              ref={inputRef}
              type="password"
              value={password}
              onChange={e => { setPassword(e.target.value); setError(null) }}
              placeholder="••••••••••••••••"
              autoComplete="current-password"
              className={`w-full rounded-md border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary placeholder-text-muted outline-none transition-colors ${
                error ? 'border-accent-red/60' : 'border-transparent focus:border-accent-blue/45'
              }`}
            />
            {error && (
              <div className="mt-2 flex items-center gap-1.5 text-xs text-accent-red">
                <span>{error}</span>
              </div>
            )}
          </div>

          {/* Remember toggle */}
          <div
            className="mb-5 flex cursor-pointer select-none items-center gap-2.5"
            onClick={() => setRemember(v => !v)}
          >
            {/* Toggle pill */}
            <div className={`relative h-5 w-9 flex-shrink-0 rounded-full transition-colors ${remember ? 'bg-accent-blue' : 'bg-bg-elevated'}`}>
              <div className={`absolute top-1 h-3 w-3 rounded-full bg-bg-base transition-all ${remember ? 'left-5' : 'left-1'}`} />
            </div>
            <span className="text-sm text-text-secondary">
              Garder la session ouverte
            </span>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || !password}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-accent-blue px-3 py-2.5 text-sm font-semibold text-bg-base transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Connexion...
              </>
            ) : 'Entrer'}
          </button>
        </form>

        {/* Footer */}
        <p className="mt-5 flex items-center justify-center gap-1.5 text-[11px] text-text-muted">
          <ShieldCheck className="h-3.5 w-3.5" />
          Session HttpOnly · SameSite=Strict
        </p>
      </div>
    </div>
  )
}
