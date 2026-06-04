import { useEffect, useState, useCallback } from 'react'
import type { BootstrapResult, ClusterProposal, FacetSchema } from '../types'
import FacetSchemaEditor from './FacetSchemaEditor'

interface ConfigBootstrapStepProps {
  thesisText: string
  onNext: (result: BootstrapResult) => void
  onSkip: () => void
  saving?: boolean
}

interface EditState {
  clusters: ClusterProposal[]
  facetSchema: FacetSchema
  keywords: string[]
}

const emptyResult: BootstrapResult = {
  domain_label: '',
  scoring_clusters: [],
  facet_schema: { version: 1, dimensions: [] },
  keywords: [],
  suggested_source_queries: [],
  degraded: true,
}

function KeywordInput({ onAdd }: { onAdd: (word: string) => void }) {
  const [value, setValue] = useState('')
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const v = value.trim()
    if (!v) return
    onAdd(v)
    setValue('')
  }
  return (
    <form onSubmit={handleSubmit} className="inline-flex">
      <input
        className="w-32 px-2 py-0.5 rounded-full border border-border-default bg-transparent text-xs text-text-primary placeholder:text-text-muted/60 focus:outline-none"
        value={value}
        onChange={e => setValue(e.target.value)}
        placeholder="Add keyword"
      />
    </form>
  )
}

export default function ConfigBootstrapStep({ thesisText, onNext, onSkip, saving }: ConfigBootstrapStepProps) {
  const [loading, setLoading] = useState(true)
  const [result, setResult] = useState<BootstrapResult | null>(null)
  const [editing, setEditing] = useState<EditState | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch('/api/profile/bootstrap', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ thesis_text: thesisText }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (cancelled) return
        const br: BootstrapResult = data ?? emptyResult
        setResult(br)
        setEditing({
          clusters: br.scoring_clusters,
          facetSchema: br.facet_schema,
          keywords: br.keywords,
        })
      })
      .catch(() => {
        if (cancelled) return
        setResult(emptyResult)
        setEditing({ clusters: [], facetSchema: { version: 1, dimensions: [] }, keywords: [] })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [thesisText])

  const handleContinue = useCallback(() => {
    const merged: BootstrapResult = {
      domain_label: result?.domain_label ?? '',
      scoring_clusters: editing?.clusters ?? [],
      facet_schema: editing?.facetSchema ?? { version: 1, dimensions: [] },
      keywords: editing?.keywords ?? [],
      suggested_source_queries: result?.suggested_source_queries ?? [],
      degraded: result?.degraded ?? false,
    }
    onNext(merged)
  }, [result, editing, onNext])

  const updateCluster = (i: number, updated: ClusterProposal) => {
    if (!editing) return
    const clusters = [...editing.clusters]
    clusters[i] = updated
    setEditing({ ...editing, clusters })
  }

  const removeCluster = (i: number) => {
    if (!editing) return
    setEditing({ ...editing, clusters: editing.clusters.filter((_, idx) => idx !== i) })
  }

  const addCluster = () => {
    if (!editing) return
    setEditing({ ...editing, clusters: [...editing.clusters, { name: '', description: '', reward_level: 0.5 }] })
  }

  const removeKeyword = (i: number) => {
    if (!editing) return
    setEditing({ ...editing, keywords: editing.keywords.filter((_, idx) => idx !== i) })
  }

  const addKeyword = (word: string) => {
    if (!editing) return
    setEditing({ ...editing, keywords: [...editing.keywords, word] })
  }

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 bg-gray-200 rounded-lg w-1/3" />
        <div className="h-24 bg-gray-200 rounded-lg" />
        <div className="h-24 bg-gray-200 rounded-lg" />
        <div className="h-16 bg-gray-200 rounded-lg" />
      </div>
    )
  }

  const isDegraded = result?.degraded

  return (
    <div>
      <h2 className="text-lg font-semibold text-text-primary mb-1">Review your scoring configuration</h2>
      <p className="text-sm text-text-muted mb-7 leading-relaxed">
        Baṣīra generated these clusters, facets, and keywords from your thesis. Edit anything you like before continuing.
        {' '}<span className="text-[11px] font-mono text-text-muted">FR-MT-53 · Step 2</span>
      </p>

      {isDegraded && (
        <div className="rounded-md bg-yellow-50 border border-yellow-200 p-4 text-sm text-yellow-800 mb-6">
          Auto-generation is currently unavailable. You can configure manually or skip and set up later.
        </div>
      )}

      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-text-primary">Scoring Clusters</h3>
          {editing && (
            <button onClick={addCluster} className="text-xs text-accent hover:text-accent/80 font-medium transition-colors">
              + Add cluster
            </button>
          )}
        </div>
        <div className="space-y-3">
          {(editing?.clusters ?? []).map((c, i) => (
            <div key={i} className="border border-border-subtle rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <input
                  className="flex-1 px-3 py-1.5 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm font-semibold focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                  value={c.name}
                  onChange={e => updateCluster(i, { ...c, name: e.target.value })}
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
                    onChange={e => updateCluster(i, { ...c, reward_level: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <button
                  onClick={() => removeCluster(i)}
                  className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full hover:bg-bg-hover text-text-muted hover:text-danger transition-colors"
                  title="Remove cluster"
                >
                  ×
                </button>
              </div>
              <textarea
                className="w-full px-3 py-1.5 rounded-lg border border-border-default bg-bg-surface text-text-primary text-sm placeholder:text-text-muted/60 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 resize-none"
                value={c.description}
                onChange={e => updateCluster(i, { ...c, description: e.target.value })}
                placeholder="Cluster description"
                rows={2}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="mb-8">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Facet Dimensions</h3>
        {editing && (
          <FacetSchemaEditor
            value={editing.facetSchema}
            onChange={facetSchema => setEditing({ ...editing, facetSchema })}
          />
        )}
      </div>

      <div className="mb-8">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Keywords</h3>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {(editing?.keywords ?? []).map((kw, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-accent/10 text-accent text-xs font-medium">
              {kw}
              <button onClick={() => removeKeyword(i)} className="hover:text-danger leading-none">&times;</button>
            </span>
          ))}
          {editing && <KeywordInput onAdd={addKeyword} />}
        </div>
      </div>

      <div className="flex items-center justify-between mt-6">
        <button onClick={onSkip} disabled={saving} className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">
          {isDegraded ? "Skip — I'll configure manually" : 'Skip'}
        </button>
        <button onClick={handleContinue} disabled={saving} className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors">
          {saving ? 'Saving…' : 'Continue →'}
        </button>
      </div>
    </div>
  )
}
