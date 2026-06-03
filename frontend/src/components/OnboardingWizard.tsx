import { useState } from 'react'

interface OnboardingWizardProps {
  onComplete: () => void
}

const STEPS = ['Thesis', 'Clusters', 'Feeds', 'First run']

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1)
  const [thesisTitle, setThesisTitle] = useState('')
  const [thesisQuestion, setThesisQuestion] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleContinue = async () => {
    const title = thesisTitle.trim()
    if (!title) {
      setError('Thesis title is required')
      return
    }
    setError('')
    setSaving(true)
    try {
      const res = await fetch('/api/onboarding/step1', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thesis_title: title, thesis_question: thesisQuestion.trim() || null }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Failed to save')
        setSaving(false)
        return
      }
      onComplete()
    } catch {
      setError('Network error')
      setSaving(false)
    }
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg-base">
      <div className="w-full max-w-lg px-6">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-10">
          {STEPS.map((label, i) => {
            const n = i + 1
            const cls = n < step ? 'done' : n === step ? 'on' : ''
            return (
              <div key={label} className="flex items-center gap-2">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold transition-colors ${
                      cls === 'done'
                        ? 'bg-accent text-white'
                        : cls === 'on'
                          ? 'bg-accent text-white'
                          : 'bg-bg-elevated text-text-muted'
                    }`}
                  >
                    {cls === 'done' ? '✓' : n}
                  </span>
                  <span
                    className={`text-xs font-medium ${
                      cls === 'on' ? 'text-text-primary' : 'text-text-muted'
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <span
                    className={`w-8 h-px ${
                      n <= step ? 'bg-accent' : 'bg-border-subtle'
                    }`}
                  />
                )}
              </div>
            )
          })}
        </div>

        {/* Panel */}
        <div>
          <h2 className="text-lg font-semibold text-text-primary mb-1">Set up your thesis</h2>
          <p className="text-sm text-text-muted mb-7 leading-relaxed">
            Baṣīra scores every paper against <em>your</em> research — not a generic rubric.{' '}
            <span className="text-[11px] font-mono text-text-muted">FR-MT-49 · Step 1</span>
          </p>

          <div className="mb-5">
            <label className="block text-sm font-medium text-text-primary mb-1.5">
              Thesis title <span className="text-text-muted text-xs font-normal">required</span>
            </label>
            <input
              className="w-full px-3 py-2 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm placeholder:text-text-muted/60 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors"
              value={thesisTitle}
              onChange={e => setThesisTitle(e.target.value)}
              placeholder="e.g. AI-Driven Requirements Engineering for MBSE"
              disabled={saving}
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-text-primary mb-1.5">
              Research question <span className="text-text-muted text-xs font-normal">optional</span>
            </label>
            <textarea
              className="w-full px-3 py-2 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm placeholder:text-text-muted/60 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors resize-none"
              value={thesisQuestion}
              onChange={e => setThesisQuestion(e.target.value)}
              placeholder="What core question drives your reading?"
              rows={3}
              disabled={saving}
            />
          </div>

          {error && (
            <p className="text-danger text-xs mb-4">{error}</p>
          )}

          <div className="flex items-center justify-end">
            <button
              onClick={handleContinue}
              disabled={saving}
              className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving…' : 'Continue →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
