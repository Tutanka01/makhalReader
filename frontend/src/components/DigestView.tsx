import { useCallback, useEffect, useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'
import { DigestCard } from './DigestCard'
import type { ArticleListItem } from '../types'

interface DigestViewProps {
  onSelect: (id: number) => void
}

const TIERS = [
  { emoji: '🔥', label: 'Excellent', min: 9 },
  { emoji: '⭐', label: 'Top', min: 7 },
  { emoji: '👍', label: 'Bon', min: 5 },
] as const

type Hours = 24 | 48

export function DigestView({ onSelect }: DigestViewProps) {
  const [articles, setArticles] = useState<ArticleListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [hours, setHours] = useState<Hours>(24)

  const fetchDigest = useCallback(async (h: Hours) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/digest?hours=${h}&limit=20`)
      if (res.ok) {
        const data = await res.json()
        setArticles(data)
      }
    } catch {
      // offline — keep current articles
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchDigest(hours) }, [hours, fetchDigest])

  const byTier = TIERS.map(tier => ({
    ...tier,
    articles: articles.filter(a => {
      const s = a.score ?? 0
      const next = TIERS.find(t => t.min > tier.min)
      return s >= tier.min && (!next || s < next.min)
    }),
  })).filter(t => t.articles.length > 0)

  const today = format(new Date(), "EEEE d MMMM", { locale: fr })

  return (
    <div className="flex flex-col h-full bg-bg-base overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-5 pb-3 flex-shrink-0">
        <div>
          <h2 className="text-sm font-bold text-text-primary tracking-tight">Digest du jour</h2>
          <p className="text-[11px] text-text-muted capitalize mt-0.5">{today}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {/* Hours toggle */}
          <div className="flex rounded-lg overflow-hidden border border-border-default text-[11px]">
            {([24, 48] as Hours[]).map(h => (
              <button
                key={h}
                onClick={() => setHours(h)}
                className={`px-2.5 py-1 transition-colors ${
                  hours === h
                    ? 'bg-accent-blue text-white'
                    : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
                } ${h === 48 ? 'border-l border-border-default' : ''}`}
              >
                {h}h
              </button>
            ))}
          </div>
          <button
            onClick={() => fetchDigest(hours)}
            disabled={loading}
            className="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-muted hover:text-text-primary disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex justify-center items-center flex-1 py-16">
          <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
        </div>
      ) : byTier.length === 0 ? (
        <div className="flex flex-col items-center justify-center flex-1 text-center px-8 py-16">
          <div className="text-4xl mb-3 opacity-20">◎</div>
          <p className="text-sm font-medium text-text-secondary mb-1">Aucun article scoré</p>
          <p className="text-xs text-text-muted leading-relaxed max-w-[200px]">
            Le scorer n'a pas encore traité les articles des dernières {hours}h.
          </p>
        </div>
      ) : (
        <div className="px-3 pb-8 space-y-6 flex-1">
          {byTier.map(tier => (
            <section key={tier.label}>
              <div className="flex items-center gap-1.5 mb-2.5">
                <span className="text-sm">{tier.emoji}</span>
                <span className="text-xs font-semibold text-text-secondary">{tier.label}</span>
                <span className="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded-full">
                  {tier.articles.length}
                </span>
              </div>
              <div className="space-y-2">
                {tier.articles.map(article => (
                  <DigestCard
                    key={article.id}
                    article={article}
                    onClick={() => onSelect(article.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
