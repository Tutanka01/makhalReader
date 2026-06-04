import { useEffect, useState, useCallback } from 'react'
import { Loader2 } from 'lucide-react'
import { runExpand, runResolve } from '../api/discovery'
import { createSource, unsubscribeSource } from '../api/sources'
import type { ExpandResult, DiscoveryPack, DiscoveredItem } from '../types'
import { ProviderBadge } from './ProviderBadge'

interface DiscoveryStepProps {
  thesisText: string
  onNext: (pack: DiscoveryPack) => void
  onSkip: () => void
  saving?: boolean
}

type Phase = 'loading' | 'expand' | 'resolving' | 'error' | 'results'

const emptyResult: ExpandResult = {
  field_label: '',
  concepts: [],
  venue_keywords: [],
  author_keywords: [],
  query_terms: [],
  language: '',
  degraded: true,
}

export default function DiscoveryStep({ thesisText, onNext, onSkip, saving }: DiscoveryStepProps) {
  const [phase, setPhase] = useState<Phase>('loading')
  const [expandResult, setExpandResult] = useState<ExpandResult | null>(null)
  const [pack, setPack] = useState<DiscoveryPack | null>(null)
  const [subscribed, setSubscribed] = useState<Map<string, number>>(new Map())
  const [toggling, setToggling] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setPhase('loading')
    runExpand(thesisText)
      .then(data => {
        if (cancelled) return
        setExpandResult(data ?? emptyResult)
        setPhase(data?.degraded ? 'expand' : 'expand')
      })
      .catch(() => {
        if (cancelled) return
        setExpandResult(emptyResult)
        setPhase('error')
      })
    return () => { cancelled = true }
  }, [thesisText])

  const handleDiscover = useCallback(async () => {
    if (!expandResult) return
    setPhase('resolving')
    try {
      const result = await runResolve(expandResult)
      setPack(result)
      setPhase('results')
    } catch {
      setPhase('error')
    }
  }, [expandResult])

  const handleSubscribe = useCallback(async (item: DiscoveredItem) => {
    const key = `${item.name}|${item.provider}`
    setToggling(key)
    try {
      const source = await createSource(item)
      setSubscribed(prev => new Map(prev).set(key, source.id))
    } catch {
      // silently fail
    } finally {
      setToggling(null)
    }
  }, [])

  const handleUnsubscribe = useCallback(async (item: DiscoveredItem) => {
    const key = `${item.name}|${item.provider}`
    const id = subscribed.get(key)
    if (!id) return
    setToggling(key)
    try {
      await unsubscribeSource(id)
      setSubscribed(prev => {
        const next = new Map(prev)
        next.delete(key)
        return next
      })
    } catch {
      // silently fail
    } finally {
      setToggling(null)
    }
  }, [subscribed])

  const handleContinue = useCallback(() => {
    onNext(pack ?? { sources: [], venues: [], authors: [] })
  }, [pack, onNext])

  function renderItem(item: DiscoveredItem) {
    const key = `${item.name}|${item.provider}`
    const isSubscribed = subscribed.has(key)
    const isToggling = toggling === key
    return (
      <div key={key} className="flex items-center justify-between py-2 px-3 rounded-lg border border-border-subtle bg-bg-surface">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm text-text-primary truncate">{item.name}</span>
          <ProviderBadge provider={item.provider} />
          {item.verified && (
            <span className="text-[10px] text-green-600 font-medium shrink-0">verified</span>
          )}
          {item.unverifiable && (
            <span className="text-[10px] text-yellow-600 font-medium shrink-0">unverifiable</span>
          )}
        </div>
        <button
          onClick={() => isSubscribed ? handleUnsubscribe(item) : handleSubscribe(item)}
          disabled={isToggling}
          className="shrink-0 ml-2 px-3 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-50"
        >
          {isToggling ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : isSubscribed ? (
            <span className="text-text-secondary hover:text-danger">Unsubscribe</span>
          ) : (
            <span className="text-accent hover:text-accent/80">Subscribe</span>
          )}
        </button>
      </div>
    )
  }

  function renderSection(title: string, items: DiscoveredItem[], emptyMsg: string) {
    return (
      <div className="mb-6">
        <h3 className="text-sm font-semibold text-text-primary mb-2">{title}</h3>
        {items.length === 0 ? (
          <p className="text-xs text-text-muted italic">{emptyMsg}</p>
        ) : (
          <div className="space-y-1.5">
            {items.map(renderItem)}
          </div>
        )}
      </div>
    )
  }

  if (phase === 'loading') {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 bg-gray-200 rounded-lg w-1/3" />
        <div className="h-16 bg-gray-200 rounded-lg" />
        <div className="h-24 bg-gray-200 rounded-lg" />
      </div>
    )
  }

  if (phase === 'error') {
    return (
      <div>
        <div className="rounded-md bg-yellow-50 border border-yellow-200 p-4 text-sm text-yellow-800 mb-6">
          Source discovery is currently unavailable. You can skip this step and configure sources later.
        </div>
        <div className="flex items-center justify-between mt-6">
          <button onClick={onSkip} className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors">
            Skip
          </button>
          <button onClick={onSkip} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition-colors">
            Continue →
          </button>
        </div>
      </div>
    )
  }

  if (phase === 'expand' && expandResult) {
    const tags = [
      ...expandResult.concepts.map(c => ({ group: 'concepts' as const, value: c })),
      ...expandResult.venue_keywords.map(v => ({ group: 'venue' as const, value: v })),
      ...expandResult.author_keywords.map(a => ({ group: 'author' as const, value: a })),
      ...expandResult.query_terms.map(q => ({ group: 'query' as const, value: q })),
    ]
    return (
      <div>
        <h2 className="text-lg font-semibold text-text-primary mb-1">Discover research sources</h2>
        <p className="text-sm text-text-muted mb-7 leading-relaxed">
          Baṣīra analysed your thesis and identified the research domain below. Review and click "Discover" to find relevant sources.
          {' '}<span className="text-[11px] font-mono text-text-muted">FR-MT-59 · Step 4</span>
        </p>

        {expandResult.degraded && (
          <div className="rounded-md bg-yellow-50 border border-yellow-200 p-4 text-sm text-yellow-800 mb-6">
            Auto-classification is currently unavailable. You can skip this step and configure sources later.
          </div>
        )}

        <div className="mb-6">
          <h3 className="text-sm font-semibold text-text-primary mb-1">Research domain</h3>
          <p className="text-base font-medium text-text-primary">{expandResult.field_label || thesisText.slice(0, 60)}</p>
        </div>

        {tags.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-text-primary mb-2">Classified keywords</h3>
            <div className="flex flex-wrap gap-1.5">
              {tags.map((t, i) => {
                const groupColor = t.group === 'concepts' ? 'bg-blue-100 text-blue-700'
                  : t.group === 'venue' ? 'bg-purple-100 text-purple-700'
                  : t.group === 'author' ? 'bg-green-100 text-green-700'
                  : 'bg-gray-100 text-gray-700'
                return (
                  <span key={i} className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${groupColor}`}>
                    {t.value}
                  </span>
                )
              })}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between mt-6">
          <button onClick={onSkip} disabled={saving} className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">
            Skip
          </button>
          <button onClick={handleDiscover} disabled={saving || expandResult.degraded} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors">
            {saving ? 'Saving…' : 'Discover Sources →'}
          </button>
        </div>
      </div>
    )
  }

  if (phase === 'resolving') {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-accent mb-4" />
        <p className="text-sm text-text-muted">Searching academic sources…</p>
      </div>
    )
  }

  // phase === 'results'
  const allEmpty = pack && pack.sources.length === 0 && pack.venues.length === 0 && pack.authors.length === 0
  return (
    <div>
      <h2 className="text-lg font-semibold text-text-primary mb-1">Discovered sources</h2>
      <p className="text-sm text-text-muted mb-7 leading-relaxed">
        Baṣīra found the following sources matching your thesis. Subscribe to the ones you want to track.
      </p>

      {allEmpty && (
        <div className="rounded-md bg-yellow-50 border border-yellow-200 p-4 text-sm text-yellow-800 mb-6">
          No sources were found. You can skip this step and configure sources manually later.
        </div>
      )}

      {pack && (
        <>
          {renderSection('Sources', pack.sources, 'No source venues found')}
          {renderSection('Venues', pack.venues, 'No venues found')}
          {renderSection('Authors', pack.authors, 'No authors found')}
        </>
      )}

      <div className="flex items-center justify-between mt-6">
        <button onClick={onSkip} disabled={saving} className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">
          Skip
        </button>
        <button onClick={handleContinue} disabled={saving} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors">
          {saving ? 'Saving…' : 'Continue →'}
        </button>
      </div>
    </div>
  )
}
