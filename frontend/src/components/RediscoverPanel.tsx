import { useState, useCallback } from 'react'
import { Loader2, RefreshCw, X } from 'lucide-react'
import { runExpand, runResolve, getExistingSubscriptions, applyDiscoveryPack, type ExistingSubscriptions } from '../api/discovery'
import type { DiscoveredItem, DiscoveryPack } from '../types'
import { ProviderBadge } from './ProviderBadge'

interface RediscoverPanelProps {
  thesisText: string
  onClose: () => void
}

type Phase = 'idle' | 'running' | 'diff' | 'applying' | 'done'

function computeDiff(pack: DiscoveryPack, existing: ExistingSubscriptions) {
  const existingCanonical = new Set(existing.source_canonical_ids)
  const existingVenues = new Set(existing.venue_names.map(n => n.toLowerCase()))
  const existingAuthorIds = new Set(existing.author_openalex_ids)
  const existingAuthorNames = new Set(existing.author_names.map(n => n.toLowerCase()))

  const newSources = pack.sources.filter(s => {
    const cid = (s.query_json?.canonical_id as string) || ''
    return !existingCanonical.has(cid)
  })
  const newVenues = pack.venues.filter(v => !existingVenues.has(v.name.toLowerCase()))
  const newAuthors = pack.authors.filter(a => {
    const oid = (a.query_json?.openalex_id as string) || ''
    return oid ? !existingAuthorIds.has(oid) : !existingAuthorNames.has(a.name.toLowerCase())
  })
  return { sources: newSources, venues: newVenues, authors: newAuthors }
}

export default function RediscoverPanel({ thesisText, onClose }: RediscoverPanelProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState('')
  const [pack, setPack] = useState<DiscoveryPack | null>(null)
  const [diff, setDiff] = useState<DiscoveryPack | null>(null)
  const [existing, setExisting] = useState<ExistingSubscriptions | null>(null)

  const handleRediscover = useCallback(async () => {
    setPhase('running')
    setError('')
    try {
      const expandResult = await runExpand(thesisText)
      const discoveryPack = await runResolve(expandResult)
      const existingSubs = await getExistingSubscriptions()
      setPack(discoveryPack)
      setExisting(existingSubs)
      const d = computeDiff(discoveryPack, existingSubs)
      setDiff(d)
      const total = d.sources.length + d.venues.length + d.authors.length
      setPhase(total === 0 ? 'done' : 'diff')
    } catch {
      setError('Discovery failed. Please try again.')
      setPhase('idle')
    }
  }, [thesisText])

  const handleApplyAll = useCallback(async () => {
    if (!diff) return
    setPhase('applying')
    try {
      await applyDiscoveryPack({ sources: diff.sources, venues: diff.venues, authors: diff.authors })
      setPhase('done')
    } catch {
      setError('Failed to apply. Please try again.')
      setPhase('diff')
    }
  }, [diff])

  const handleDone = useCallback(() => {
    onClose()
  }, [onClose])

  const isUpToDate = phase === 'done' && diff && diff.sources.length === 0 && diff.venues.length === 0 && diff.authors.length === 0

  function renderItem(item: DiscoveredItem) {
    return (
      <div key={`${item.name}|${item.provider}`} className="flex items-center justify-between py-2 px-3 rounded-lg border border-border-subtle bg-bg-surface">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm text-text-primary truncate">{item.name}</span>
          <ProviderBadge provider={item.provider} />
          {item.verified && (
            <span className="text-[10px] text-green-600 font-medium shrink-0">verified</span>
          )}
        </div>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent font-medium shrink-0 ml-2">New</span>
      </div>
    )
  }

  function renderSection(title: string, items: DiscoveredItem[], emptyMsg: string) {
    return (
      <div className="mb-4">
        <h4 className="text-xs font-semibold text-text-primary mb-1.5">{title}</h4>
        {items.length === 0 ? (
          <p className="text-xs text-text-muted italic">{emptyMsg}</p>
        ) : (
          <div className="space-y-1.5">{items.map(renderItem)}</div>
        )}
      </div>
    )
  }

  return (
    <div className="border-t border-border-subtle mt-4 pt-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-text-secondary flex items-center gap-1.5">
          <RefreshCw size={13} />
          Re-discover sources
        </h4>
      </div>

      {phase === 'idle' && !error && (
        <p className="text-xs text-text-muted mb-3">
          Run discovery again to find new sources matching your thesis.
        </p>
      )}

      {error && (
        <p className="text-xs text-danger mb-3">{error}</p>
      )}

      {phase === 'idle' && (
        <button
          onClick={handleRediscover}
          className="flex items-center gap-1.5 text-xs rounded bg-accent px-3 py-1.5 font-medium text-white hover:bg-accent/90"
        >
          <RefreshCw size={12} />
          Re-discover
        </button>
      )}

      {phase === 'running' && (
        <div className="flex items-center gap-2 text-xs text-text-muted py-2">
          <Loader2 size={14} className="animate-spin" />
          Running discovery…
        </div>
      )}

      {phase === 'diff' && diff && (
        <div>
          {renderSection('New Sources', diff.sources, 'No new sources')}
          {renderSection('New Venues', diff.venues, 'No new venues')}
          {renderSection('New Authors', diff.authors, 'No new authors')}
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={handleApplyAll}
              className="flex items-center gap-1.5 text-xs rounded bg-accent px-3 py-1.5 font-medium text-white hover:bg-accent/90"
            >
              Apply all
            </button>
            <button
              onClick={handleDone}
              className="text-xs text-text-muted hover:text-text-secondary"
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {phase === 'applying' && (
        <div className="flex items-center gap-2 text-xs text-text-muted py-2">
          <Loader2 size={14} className="animate-spin" />
          Applying…
        </div>
      )}

      {phase === 'done' && (
        <div>
          {isUpToDate ? (
            <div className="text-center py-4">
              <p className="text-sm font-medium text-text-primary">You're up to date</p>
              <p className="text-xs text-text-muted mt-1">No new sources found since your last discovery run.</p>
            </div>
          ) : (
            <p className="text-xs text-success font-medium mb-2">Applied successfully</p>
          )}
          <button
            onClick={handleDone}
            className="flex items-center gap-1.5 text-xs rounded bg-accent px-3 py-1.5 font-medium text-white hover:bg-accent/90 mt-2"
          >
            <X size={12} />
            Done
          </button>
        </div>
      )}
    </div>
  )
}