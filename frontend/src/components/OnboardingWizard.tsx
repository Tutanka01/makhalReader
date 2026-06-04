import { useEffect, useState } from 'react'
import ConfigBootstrapStep from './ConfigBootstrapStep'
import FacetSchemaEditor from './FacetSchemaEditor'
import TemplateBrowser from './TemplateBrowser'
import { Loader2 } from 'lucide-react'
import type { BootstrapResult, ClusterProposal, FacetSchema } from '../types'

interface OnboardingWizardProps {
  onComplete: () => void
}

const STEPS = ['Thesis', 'Clusters', 'Feeds', 'First run']

interface CatalogFeed {
  id: number
  name: string
  url: string
  category: string
  subscribed: boolean
}

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1)
  const [thesisTitle, setThesisTitle] = useState('')
  const [thesisQuestion, setThesisQuestion] = useState('')
  const [saving, setSaving] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [error, setError] = useState('')

  const [catalog, setCatalog] = useState<CatalogFeed[]>([])
  const [toggling, setToggling] = useState<number | null>(null)

  const [manualClusters, setManualClusters] = useState<ClusterProposal[]>([])
  const [manualFacetSchema, setManualFacetSchema] = useState<FacetSchema>({ version: 1, dimensions: [] })
  const [showTemplates, setShowTemplates] = useState(false)

  const [pollPhase, setPollPhase] = useState<'running' | 'preview'>('running')
  const [scoredCount, setScoredCount] = useState(0)
  const [createdCount, setCreatedCount] = useState(0)
  const [previewArticles, setPreviewArticles] = useState<any[]>([])
  const [pollTriggered, setPollTriggered] = useState(false)
  const [pollFinished, setPollFinished] = useState(false)

  useEffect(() => {
    if (step === 3) {
      fetch('/api/feeds/catalog', { credentials: 'include' })
        .then(r => r.ok ? r.json() : [])
        .then(data => setCatalog(data))
        .catch(() => {})
    }
  }, [step])

  const handleStep1 = async () => {
    setError('')
    setSaving(true)
    try {
      const res = await fetch('/api/onboarding/step1', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thesis_title: thesisTitle.trim(), thesis_question: thesisQuestion.trim() || null }),
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

  const handleBootstrapNext = async (result: BootstrapResult | null) => {
    setSaving(true)
    setError('')
    try {
      const res = await fetch('/api/profile/config', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thesis_text: thesisTitle,
          domain_label: result?.domain_label ?? '',
          scoring_clusters: result?.scoring_clusters ?? [],
          facet_schema: result?.facet_schema ?? { version: 1, dimensions: [] },
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Failed to save config')
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

  const handleBootstrapSkip = () => {
    setStep(3)
  }

  const handleApplyTemplate = async (templateId: number) => {
    try {
      const res = await fetch(`/api/profile/from-template/${templateId}`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) return
      const data = await res.json()
      if (Array.isArray(data.scoring_clusters)) setManualClusters(data.scoring_clusters)
      if (data.facet_schema) setManualFacetSchema(data.facet_schema)
      setShowTemplates(false)
    } catch { /* ignore */ }
  }

  const handleManualNext = async () => {
    setSaving(true)
    setError('')
    try {
      const res = await fetch('/api/profile/config', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scoring_clusters: manualClusters,
          facet_schema: manualFacetSchema,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Failed to save config')
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

  const handleToggleFeed = async (feed: CatalogFeed) => {
    setToggling(feed.id)
    setError('')
    try {
      const method = feed.subscribed ? 'DELETE' : 'POST'
      const res = await fetch(`/api/feeds/${feed.id}/subscribe`, {
        method,
        credentials: 'include',
      })
      if (res.ok) {
        setCatalog(prev => prev.map(f => f.id === feed.id ? { ...f, subscribed: !f.subscribed } : f))
      }
    } catch {
      setError('Failed to toggle feed')
    } finally {
      setToggling(null)
    }
  }

  const handleComplete = async () => {
    const selectedFeeds = catalog.filter(feed => feed.subscribed).length
    if (selectedFeeds === 0) {
      setError('Select at least one feed to start your first run')
      return
    }

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
      setCompleting(false)
      setPollPhase('running')
      setPollTriggered(false)
      setPollFinished(false)
      setScoredCount(0)
      setCreatedCount(0)
      setPreviewArticles([])
      setStep(4)
    } catch {
      setError('Network error')
      setCompleting(false)
    }
  }

  // ── Step 4: trigger poll, stream via SSE, show top 3 ──────────────────

  useEffect(() => {
    if (step !== 4 || pollTriggered) return
    setPollTriggered(true)

    // Trigger poll
    fetch('/api/poll/trigger', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bootstrap: true }),
    })
      .then(async res => {
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          setError(data.detail || 'Failed to start polling')
          setPollPhase('preview')
        }
      })
      .catch(() => {
        setError('Failed to start polling')
        setPollPhase('preview')
      })

    // Connect SSE
    const evtSource = new EventSource('/api/stream', { withCredentials: true })
    const collected: any[] = []

    evtSource.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'new_article' && msg.data?.score != null) {
          collected.push(msg.data)
          setScoredCount(collected.length)
        }
      } catch {}
    }

    // Poll preview endpoint every 5s
    const previewTimer = setInterval(async () => {
      try {
        const res = await fetch('/api/onboarding/preview', { credentials: 'include' })
        if (res.ok) {
          const data = await res.json()
          if (data.length >= 1) {
            setPreviewArticles(data)
          }
        }
      } catch {}
    }, 5000)

    const statusTimer = setInterval(async () => {
      try {
        const res = await fetch('/api/poll/status', { credentials: 'include' })
        if (!res.ok) return
        const status = await res.json()
        if (status.status === 'complete' || status.status === 'failed') {
          if (typeof status.articles_created === 'number') {
            setCreatedCount(status.articles_created)
          }
          if (typeof status.articles_scored === 'number') {
            setScoredCount(status.articles_scored)
          }
          setPollFinished(true)
          if (status.status === 'failed') {
            setError(status.error || 'Poll failed')
          }
          setPollPhase('preview')
          clearInterval(articleCheck)
          clearInterval(previewTimer)
          clearInterval(statusTimer)
          evtSource.close()
        }
      } catch {}
    }, 2000)

    // After 3 articles or 45s timeout, show preview
    const articleCheck = setInterval(() => {
      if (collected.length >= 3) {
        setPollFinished(true)
        setPollPhase('preview')
        clearInterval(articleCheck)
        clearInterval(previewTimer)
        clearInterval(statusTimer)
        evtSource.close()
      }
    }, 1000)

    const timeout = setTimeout(() => {
      setPollFinished(true)
      setPollPhase('preview')
      clearInterval(articleCheck)
      clearInterval(previewTimer)
      clearInterval(statusTimer)
      evtSource.close()
    }, 30000)

    return () => {
      evtSource.close()
      clearInterval(articleCheck)
      clearInterval(previewTimer)
      clearInterval(statusTimer)
      clearTimeout(timeout)
    }
  }, [step, pollTriggered])

  const selectedFeedCount = catalog.filter(feed => feed.subscribed).length

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
                Thesis title <span className="text-text-muted text-xs font-normal">optional</span>
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
            <div className="flex items-center justify-between">
              <button
                onClick={() => { setThesisTitle(''); setStep(2) }}
                className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors"
              >
                Skip
              </button>
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
    const hasThesis = thesisTitle.trim().length > 0
    return (
      <div className="flex h-screen w-screen items-start justify-center bg-bg-base pt-20 overflow-y-auto">
        <div className="w-full max-w-2xl px-6 pb-12">
          <StepIndicator />

          <button
            onClick={() => setShowTemplates(true)}
            className="mb-6 text-xs rounded bg-accent/10 text-accent px-3 py-1.5 font-medium hover:bg-accent/20 transition-colors"
          >
            Browse Starter Packs
          </button>
          {showTemplates && (
            <TemplateBrowser
              onApply={handleApplyTemplate}
              onClose={() => setShowTemplates(false)}
              mode="onboarding"
            />
          )}

          {hasThesis ? (
            <ConfigBootstrapStep
              thesisText={thesisTitle}
              onNext={handleBootstrapNext}
              onSkip={handleBootstrapSkip}
              saving={saving}
            />
          ) : (
            <div>
              <h2 className="text-lg font-semibold text-text-primary mb-1">Configure your research profile</h2>
              <p className="text-sm text-text-muted mb-7 leading-relaxed">
                Set up the research clusters and facets you want Baṣīra to score against.
              </p>

              <div className="mb-8">
                <h3 className="text-sm font-semibold text-text-primary mb-3">Scoring Clusters</h3>
                <div className="space-y-3">
                  {manualClusters.map((c, i) => (
                    <div key={i} className="border border-border-subtle rounded-xl p-4 space-y-3">
                      <div className="flex items-center gap-2">
                        <input
                          className="flex-1 px-3 py-1.5 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm font-semibold focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                          value={c.name}
                          onChange={e => {
                            const next = [...manualClusters]
                            next[i] = { ...c, name: e.target.value }
                            setManualClusters(next)
                          }}
                          placeholder="Cluster name"
                        />
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] text-text-muted">Weight:</span>
                          <input
                            type="number"
                            min={0}
                            max={1}
                            step={0.1}
                            className="w-16 px-2 py-1 rounded-lg border border-border-default bg-bg-surface text-text-primary text-xs text-center focus:outline-none focus:border-accent"
                            value={c.reward_level}
                            onChange={e => {
                              const next = [...manualClusters]
                              next[i] = { ...c, reward_level: parseFloat(e.target.value) || 0 }
                              setManualClusters(next)
                            }}
                          />
                        </div>
                        <button
                          onClick={() => setManualClusters(manualClusters.filter((_, idx) => idx !== i))}
                          className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full hover:bg-bg-hover text-text-muted hover:text-danger transition-colors"
                          title="Remove cluster"
                        >
                          ×
                        </button>
                      </div>
                      <textarea
                        className="w-full px-3 py-1.5 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm placeholder:text-text-muted/60 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 resize-none"
                        value={c.description}
                        onChange={e => {
                          const next = [...manualClusters]
                          next[i] = { ...c, description: e.target.value }
                          setManualClusters(next)
                        }}
                        placeholder="Cluster description"
                        rows={2}
                      />
                    </div>
                  ))}
                  <button
                    onClick={() => setManualClusters([...manualClusters, { name: '', description: '', reward_level: 0.5 }])}
                    className="text-xs text-accent hover:text-accent/80 font-medium transition-colors"
                  >
                    + Add cluster
                  </button>
                </div>
              </div>

              <div className="mb-8">
                <h3 className="text-sm font-semibold text-text-primary mb-3">Facet Dimensions</h3>
                <FacetSchemaEditor
                  value={manualFacetSchema}
                  onChange={setManualFacetSchema}
                />
              </div>

              {error && <p className="text-danger text-xs mt-4">{error}</p>}
              <div className="flex items-center justify-between mt-6">
                <button
                  onClick={handleBootstrapSkip}
                  disabled={saving}
                  className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50"
                >
                  Skip
                </button>
                <button
                  onClick={handleManualNext}
                  disabled={saving}
                  className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
                >
                  {saving ? 'Saving…' : 'Continue →'}
                </button>
              </div>
            </div>
          )}
          {error && <p className="text-danger text-xs mt-4">{error}</p>}
        </div>
      </div>
    )
  }

  if (step === 3) {
    const grouped: Record<string, CatalogFeed[]> = {}
    const feeds = Array.isArray(catalog) ? catalog : []
    for (const feed of feeds) {
      const cat = feed.category || 'General'
      if (!grouped[cat]) grouped[cat] = []
      grouped[cat].push(feed)
    }

    return (
      <div className="flex h-screen w-screen items-start justify-center bg-bg-base pt-16 overflow-y-auto">
        <div className="w-full max-w-2xl px-6 pb-12">
          <StepIndicator />
          <div>
            <h2 className="text-lg font-semibold text-text-primary mb-1">Pick your feeds</h2>
            <p className="text-sm text-text-muted mb-7 leading-relaxed">
              Subscribe to research feeds relevant to your thesis. Toggle any feed on or off.{' '}
              <span className="text-[11px] font-mono text-text-muted">FR-MT-51 · Step 3</span>
            </p>
            {feeds.length === 0 && (
              <p className="text-sm text-text-muted">No feeds available in the catalog yet.</p>
            )}
            {Object.entries(grouped).map(([cat, feeds]) => (
              <div key={cat} className="mb-6">
                <h3 className="text-[11px] font-semibold uppercase tracking-widest text-text-muted mb-3">{cat}</h3>
                <div className="grid grid-cols-2 gap-2.5">
                  {feeds.map(feed => (
                    <div
                      key={feed.id}
                      className={`border rounded-xl px-4 py-3.5 flex items-center gap-3 transition-all ${feed.subscribed ? 'border-accent/40 bg-accent/[0.04]' : 'border-border-default bg-transparent'}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-text-primary truncate">{feed.name}</div>
                      </div>
                      <button
                        onClick={() => handleToggleFeed(feed)}
                        disabled={toggling === feed.id}
                        className={`shrink-0 w-16 h-7 rounded-lg text-[11px] font-semibold transition-all ${feed.subscribed ? 'bg-accent text-white hover:bg-accent/90' : 'border border-border-default text-text-muted hover:border-border-hover'} disabled:opacity-50`}
                      >
                        {toggling === feed.id ? '…' : feed.subscribed ? 'On' : 'Off'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {error && <p className="text-danger text-xs mt-4">{error}</p>}
            <div className="flex items-center justify-between mt-6">
              <button onClick={() => setStep(2)} className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors">
                ← Back
              </button>
              <button onClick={handleComplete} disabled={completing || selectedFeedCount === 0} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors">
                {completing ? 'Saving…' : `Start first run${selectedFeedCount ? ` (${selectedFeedCount})` : ''} →`}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Step 4 — first run poll with SSE progress + top 3 preview
  if (step === 4 && pollPhase === 'running') {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-bg-base">
        <div className="w-full max-w-sm px-6 text-center">
          <StepIndicator />
          <div className="mt-8">
            <div className="flex items-center justify-center gap-1.5 mb-5">
              <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <h2 className="text-lg font-semibold text-text-primary mb-2">Running your first poll</h2>
            <p className="text-sm text-text-muted leading-relaxed mb-4">
              Baṣīra is scanning your feeds, extracting articles, and scoring them against your thesis.
            </p>
            <div className="text-xs text-text-muted font-mono">
              Created {createdCount} · scored {scoredCount}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Step 4 — top 3 preview
  const top3 = previewArticles.slice(0, 3)
  return (
    <div className="flex h-screen w-screen items-start justify-center bg-bg-base pt-16 overflow-y-auto">
      <div className="w-full max-w-lg px-6 pb-12">
        <StepIndicator />
        <div>
          <h2 className="text-lg font-semibold text-text-primary mb-1">Your first results are in</h2>
          <p className="text-sm text-text-muted mb-7 leading-relaxed">
            These are the top-scoring articles so far, calibrated to <em>your</em> thesis. Scores will improve as Baṣīra learns your preferences.{' '}
            <span className="text-[11px] font-mono text-text-muted">FR-MT-51 · Step 4</span>
          </p>

          {top3.length === 0 && (
            <p className="text-sm text-text-muted mb-6">
              {pollFinished
                ? 'The first poll finished, but no new article could be scored from the selected feeds. You can start reading now and adjust feeds anytime.'
                : 'No articles have been scored yet. The poll is still running.'}
            </p>
          )}

          {top3.map((a, i) => (
            <div key={a.id} className="border border-border-subtle rounded-xl p-4 mb-3">
              <div className="flex items-start gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-accent/10 text-accent text-[11px] font-bold flex items-center justify-center mt-0.5">
                  {i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-text-primary leading-snug mb-1">{a.title}</div>
                  <div className="text-[11px] text-text-muted mb-2">{a.feed_name}</div>
                  {a.reason && (
                    <div className="text-[12px] text-text-secondary leading-relaxed line-clamp-2">{a.reason}</div>
                  )}
                </div>
                <div className="shrink-0 flex items-center justify-center w-10 h-10 rounded-lg bg-accent/10 text-accent text-sm font-bold">
                  {a.score?.toFixed(1)}
                </div>
              </div>
            </div>
          ))}

          {error && <p className="text-danger text-xs mt-4">{error}</p>}
          <div className="flex items-center justify-end mt-6">
            <button onClick={onComplete} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition-colors">
              Finish — start reading →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
