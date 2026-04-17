import { useEffect } from 'react'
import { Flame, BookOpen, Bookmark, Star, X, RefreshCw } from 'lucide-react'
import { useStatsStore } from '../store/stats'

interface StatsViewProps {
  onClose: () => void
}

const ACCENT_COLORS = [
  'text-accent-blue',
  'text-accent-green',
  'text-accent-yellow',
  'text-purple-400',
  'text-pink-400',
  'text-cyan-400',
]

export function StatsView({ onClose }: StatsViewProps) {
  const { stats, loading, fetchStats } = useStatsStore()

  useEffect(() => {
    fetchStats()
  }, [])

  if (loading && !stats) {
    return (
      <div className="flex flex-col h-full bg-bg-base items-center justify-center">
        <RefreshCw className="w-5 h-5 animate-spin text-text-muted" />
      </div>
    )
  }

  const s = stats

  // Bar chart: last 7 days
  const last7 = (() => {
    const days: { label: string; count: number; date: string }[] = []
    for (let i = 6; i >= 0; i--) {
      const d = new Date()
      d.setDate(d.getDate() - i)
      const iso = d.toISOString().slice(0, 10)
      const label = d.toLocaleDateString('fr-FR', { weekday: 'short' })
      const entry = s?.daily_counts.find((c) => c.date === iso)
      days.push({ label, count: entry?.count ?? 0, date: iso })
    }
    return days
  })()
  const maxCount = Math.max(...last7.map((d) => d.count), 1)

  // Tag cloud sizing
  const topTags = s?.top_tags.slice(0, 20) ?? []
  const maxTagCount = topTags[0]?.count ?? 1
  function tagSize(count: number): string {
    const ratio = count / maxTagCount
    if (ratio >= 0.8) return 'text-base font-semibold'
    if (ratio >= 0.5) return 'text-sm font-medium'
    if (ratio >= 0.3) return 'text-xs font-medium'
    return 'text-xs'
  }

  // Category bars
  const catEntries = Object.entries(s?.articles_per_category ?? {}).sort((a, b) => b[1] - a[1])
  const maxCat = catEntries[0]?.[1] ?? 1

  return (
    <div className="flex flex-col h-full bg-bg-base overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle flex-shrink-0 bg-bg-surface">
        <h2 className="text-sm font-semibold text-text-primary">Statistiques de lecture</h2>
        <div className="flex items-center gap-1">
          <button
            onClick={fetchStats}
            className="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
            title="Rafraîchir"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="px-4 py-4 space-y-6">

        {/* Streak */}
        <div className="flex items-center justify-center py-4 bg-bg-surface rounded-xl border border-border-subtle">
          <div className="text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Flame className={`w-6 h-6 ${(s?.streak_days ?? 0) > 0 ? 'text-accent-yellow' : 'text-text-muted'}`} />
              <span className={`text-4xl font-bold tabular-nums ${(s?.streak_days ?? 0) > 0 ? 'text-text-primary' : 'text-text-muted'}`}>
                {s?.streak_days ?? 0}
              </span>
            </div>
            <p className="text-xs text-text-muted">
              {(s?.streak_days ?? 0) > 1 ? 'jours consécutifs' : (s?.streak_days ?? 0) === 1 ? 'jour de streak' : 'Lisez aujourd\'hui pour commencer !'}
            </p>
          </div>
        </div>

        {/* Summary pills */}
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-3 text-center">
            <BookOpen className="w-4 h-4 text-accent-blue mx-auto mb-1" />
            <div className="text-xl font-bold text-text-primary tabular-nums">{s?.total_read ?? 0}</div>
            <div className="text-xs text-text-muted">lus</div>
          </div>
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-3 text-center">
            <Bookmark className="w-4 h-4 text-accent-blue mx-auto mb-1" />
            <div className="text-xl font-bold text-text-primary tabular-nums">{s?.total_bookmarked ?? 0}</div>
            <div className="text-xs text-text-muted">bookmarks</div>
          </div>
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-3 text-center">
            <Star className="w-4 h-4 text-accent-yellow mx-auto mb-1" />
            <div className="text-xl font-bold text-text-primary tabular-nums">
              {s?.avg_score_read != null ? s.avg_score_read.toFixed(1) : '—'}
            </div>
            <div className="text-xs text-text-muted">score moy.</div>
          </div>
        </div>

        {/* Highlights count */}
        {(s?.total_highlights ?? 0) > 0 && (
          <div className="flex items-center justify-between bg-bg-surface rounded-xl border border-border-subtle px-4 py-3">
            <span className="text-xs text-text-secondary">Surlignages enregistrés</span>
            <span className="text-sm font-semibold text-accent-yellow">{s?.total_highlights}</span>
          </div>
        )}

        {/* 7-day bar chart */}
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">7 derniers jours</h3>
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-4">
            <div className="flex items-end justify-between gap-1.5 h-20">
              {last7.map((day) => (
                <div key={day.date} className="flex flex-col items-center flex-1 gap-1">
                  <div className="relative flex-1 w-full flex items-end">
                    <div
                      className="w-full rounded-sm bg-accent-blue/60 transition-all duration-300 min-h-[2px]"
                      style={{ height: `${(day.count / maxCount) * 100}%` }}
                      title={`${day.count} article${day.count > 1 ? 's' : ''}`}
                    />
                  </div>
                  <span className="text-[10px] text-text-muted">{day.label}</span>
                  {day.count > 0 && (
                    <span className="text-[10px] text-accent-blue font-medium">{day.count}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Top tags cloud */}
        {topTags.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Top tags lus</h3>
            <div className="bg-bg-surface rounded-xl border border-border-subtle p-4">
              <div className="flex flex-wrap gap-2">
                {topTags.map((t, i) => (
                  <span
                    key={t.tag}
                    className={`${tagSize(t.count)} ${ACCENT_COLORS[i % ACCENT_COLORS.length]} transition-opacity hover:opacity-80`}
                    title={`${t.count} article${t.count > 1 ? 's' : ''}`}
                  >
                    {t.tag}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Articles per category */}
        {catEntries.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">Par catégorie</h3>
            <div className="bg-bg-surface rounded-xl border border-border-subtle p-4 space-y-2.5">
              {catEntries.map(([cat, count]) => (
                <div key={cat} className="flex items-center gap-3">
                  <span className="text-xs text-text-secondary w-24 flex-shrink-0 truncate">{cat}</span>
                  <div className="flex-1 bg-bg-elevated rounded-full h-2 overflow-hidden">
                    <div
                      className="h-full bg-accent-blue/60 rounded-full transition-all duration-300"
                      style={{ width: `${(count / maxCat) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-text-muted tabular-nums w-8 text-right">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!s && (
          <div className="text-center py-8 text-text-muted text-sm">
            Aucune donnée disponible.
          </div>
        )}

      </div>
    </div>
  )
}
