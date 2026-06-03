import { useCallback, useEffect, useState } from 'react'

interface OnboardingWizardProps {
  onComplete: () => void
}

const STEPS = ['Thesis', 'Clusters', 'Feeds', 'First run']

interface Cluster {
  name: string
  reward_level: string
  weight: number
  description: string
}

interface Template {
  id: string
  name: string
  clusters: Cluster[]
}

const REWARD_COLORS: Record<string, string> = {
  critical: 'bg-emerald-500/10 text-emerald-600',
  high: 'bg-blue-500/10 text-blue-600',
  tangential: 'bg-amber-500/10 text-amber-600',
  noise: 'bg-gray-500/10 text-gray-500',
}

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1)
  const [thesisTitle, setThesisTitle] = useState('')
  const [thesisQuestion, setThesisQuestion] = useState('')
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/onboarding/templates', { credentials: 'include' })
      .then(r => r.ok ? r.json() : [])
      .then(data => setTemplates(data))
      .catch(() => {})
  }, [])

  const handleStep1 = async () => {
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
      setSaving(false)
      setStep(2)
    } catch {
      setError('Network error')
      setSaving(false)
    }
  }

  const handleStep2 = async () => {
    if (!selectedTemplate) {
      setError('Select a template to continue')
      return
    }
    setError('')
    setSaving(true)
    try {
      const res = await fetch('/api/onboarding/step2', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: selectedTemplate }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Failed to save')
        setSaving(false)
        return
      }
      setSaving(false)
      setStep(3)
    } catch {
      setError('Network error')
      setSaving(false)
    }
  }

  const handleComplete = async () => {
    setCompleting(true)
    setError('')
    try {
      const res = await fetch('/api/onboarding/complete', {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Failed to complete')
        setCompleting(false)
        return
      }
      onComplete()
    } catch {
      setError('Network error')
      setCompleting(false)
    }
  }

  const activeTemplate = templates.find(t => t.id === selectedTemplate)

  const StepIndicator = () => (
    <div className="flex items-center justify-center gap-2 mb-10">
      {STEPS.map((label, i) => {
        const n = i + 1
        const cls = n < step ? 'done' : n === step ? 'on' : ''
        return (
          <div key={label} className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-semibold transition-colors ${cls === 'done' ? 'bg-accent text-white' : cls === 'on' ? 'bg-accent text-white' : 'bg-bg-elevated text-text-muted'}`}>
                {cls === 'done' ? '✓' : n}
              </span>
              <span className={`text-xs font-medium ${cls === 'on' ? 'text-text-primary' : 'text-text-muted'}`}>{label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <span className={`w-8 h-px ${n <= step ? 'bg-accent' : 'bg-border-subtle'}`} />
            )}
          </div>
        )
      })}
    </div>
  )

  if (step === 1) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-bg-base">
        <div className="w-full max-w-lg px-6">
          <StepIndicator />
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
              <input className="w-full px-3 py-2 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm placeholder:text-text-muted/60 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors" value={thesisTitle} onChange={e => setThesisTitle(e.target.value)} placeholder="e.g. AI-Driven Requirements Engineering for MBSE" disabled={saving} />
            </div>
            <div className="mb-6">
              <label className="block text-sm font-medium text-text-primary mb-1.5">
                Research question <span className="text-text-muted text-xs font-normal">optional</span>
              </label>
              <textarea className="w-full px-3 py-2 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm placeholder:text-text-muted/60 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 transition-colors resize-none" value={thesisQuestion} onChange={e => setThesisQuestion(e.target.value)} placeholder="What core question drives your reading?" rows={3} disabled={saving} />
            </div>
            {error && <p className="text-danger text-xs mb-4">{error}</p>}
            <div className="flex items-center justify-end">
              <button onClick={handleStep1} disabled={saving} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors">
                {saving ? 'Saving…' : 'Continue →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (step === 2) {
    return (
      <div className="flex h-screen w-screen items-start justify-center bg-bg-base pt-20 overflow-y-auto">
        <div className="w-full max-w-2xl px-6 pb-12">
          <StepIndicator />
          <div>
            <h2 className="text-lg font-semibold text-text-primary mb-1">Choose your scoring clusters</h2>
            <p className="text-sm text-text-muted mb-7 leading-relaxed">
              Pick a domain template, then tune it. Clusters define what scores high — and which double as thesis sections.{' '}
              <span className="text-[11px] font-mono text-text-muted">FR-MT-50 · Step 2</span>
            </p>
            <div className="grid grid-cols-2 gap-3 mb-6">
              {templates.map(t => (
                <div
                  key={t.id}
                  onClick={() => { setSelectedTemplate(t.id); setError('') }}
                  className={`border rounded-xl px-4 py-3.5 cursor-pointer transition-all ${selectedTemplate === t.id ? 'border-accent bg-accent/5 ring-1 ring-accent/30' : 'border-border-default hover:border-border-hover hover:bg-bg-hover'}`}
                >
                  <div className="text-sm font-semibold text-text-primary">{t.name}</div>
                  <div className="text-xs text-text-muted mt-0.5">{t.clusters.length} reward clusters</div>
                </div>
              ))}
            </div>
            {activeTemplate && (
              <div className="border border-border-subtle rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 text-[11px] font-medium text-text-muted border-b border-border-subtle">Preview — edit anytime in Research Config</div>
                {activeTemplate.clusters.map((c, i) => (
                  <div key={i} className="px-4 py-3 border-b border-border-subtle last:border-b-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="flex-1 text-sm font-semibold text-text-primary">{c.name}</span>
                      <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${REWARD_COLORS[c.reward_level] || ''}`}>{c.reward_level}</span>
                    </div>
                    <div className="text-[12.5px] text-text-secondary">{c.description}</div>
                  </div>
                ))}
              </div>
            )}
            {error && <p className="text-danger text-xs mt-4">{error}</p>}
            <div className="flex items-center justify-between mt-6">
              <button onClick={() => setStep(1)} className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors">
                ← Back
              </button>
              <button onClick={handleStep2} disabled={saving || !selectedTemplate} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors">
                {saving ? 'Saving…' : 'Continue →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Step 3/4 — placeholder (feeds and first run come in 9.3/9.4)
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg-base">
      <div className="w-full max-w-lg px-6">
        <StepIndicator />
        <div>
          <h2 className="text-lg font-semibold text-text-primary mb-1">Almost there!</h2>
          <p className="text-sm text-text-muted mb-7 leading-relaxed">
            Your thesis and scoring clusters are set. Feed selection and first-run scoring will be available soon.{' '}
            <span className="text-[11px] font-mono text-text-muted">FR-MT-52</span>
          </p>
          {error && <p className="text-danger text-xs mb-4">{error}</p>}
          <div className="flex items-center justify-end">
            <button onClick={handleComplete} disabled={completing} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors">
              {completing ? 'Completing…' : 'Finish — start reading →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
