import { useEffect, useState, useCallback } from 'react'
import { Flame, BookOpen, Bookmark, Star, X, RefreshCw, ChevronRight } from 'lucide-react'
import { useStatsStore } from '../store/stats'
import type { ReadingDebt } from '../types'

interface StatsViewProps {
  onClose: () => void
  onSelectArticle?: (id: number) => void
}

const ACCENT_COLORS = [
  'text-accent',
  'text-success',
  'text-warning',
  'text-purple',
  'text-danger',
  'text-accent',
]

export function StatsView({ onClose, onSelectArticle }: StatsViewProps) {
  const { stats, loading, fetchStats } = useStatsStore()

  const [debt, setDebt] = useState<ReadingDebt | null>(null)
  const [debtLoading, setDebtLoading] = useState(true)
  const [goalInput, setGoalInput] = useState<number>(10)
  const [goalSaving, setGoalSaving] = useState(false)

  const fetchDebt = useCallback(async () => {
    setDebtLoading(true)
    try {
      const res = await fetch('/api/stats/reading-debt', { credentials: 'include' })
      if (res.ok) {
        const data: ReadingDebt = await res.json()
        setDebt(data)
        setGoalInput(data.weekly_goal)
      }
    } catch (e) {
      console.error('Failed to fetch reading debt', e)
    } finally {
      setDebtLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStats()
    fetchDebt()
  }, [fetchStats, fetchDebt])

  const handleGoalSave = async () => {
    setGoalSaving(true)
    try {
      await fetch('/api/stats/reading-goal', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ weekly_goal: goalInput }),
      })
      fetchDebt()
    } catch (e) {
      console.error('Failed to save goal', e)
    } finally {
      setGoalSaving(false)
    }
  }

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
              <Flame className={`w-6 h-6 ${(s?.streak_days ?? 0) > 0 ? 'text-warning' : 'text-text-muted'}`} />
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
            <BookOpen className="w-4 h-4 text-accent mx-auto mb-1" />
            <div className="text-xl font-bold text-text-primary tabular-nums">{s?.total_read ?? 0}</div>
            <div className="text-xs text-text-muted">lus</div>
          </div>
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-3 text-center">
            <Bookmark className="w-4 h-4 text-accent mx-auto mb-1" />
            <div className="text-xl font-bold text-text-primary tabular-nums">{s?.total_bookmarked ?? 0}</div>
            <div className="text-xs text-text-muted">bookmarks</div>
          </div>
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-3 text-center">
            <Star className="w-4 h-4 text-warning mx-auto mb-1" />
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
            <span className="text-sm font-semibold text-warning">{s?.total_highlights}</span>
          </div>
        )}

        {/* ── Reading Debt Dashboard (Story 5.4) ── */}
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
            Reading Debt
          </h3>
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-4 space-y-4">
            {debtLoading && !debt ? (
              <div className="flex items-center justify-center py-4">
                <RefreshCw className="w-4 h-4 animate-spin text-text-muted" />
              </div>
            ) : debt ? (
              <>
                {/* Unread high counter */}
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-4xl font-bold tabular-nums text-text-primary">
                      {debt.unread_high}
                    </div>
                    <div className="text-xs text-text-muted mt-1">
                      high-value papers unread
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-semibold tabular-nums text-warning">
                      {Math.round(debt.unread_high_minutes / 60)}h
                    </div>
                    <div className="text-xs text-text-muted">
                      estimated reading time
                    </div>
                  </div>
                </div>

                {/* Critical indicator */}
                {debt.unread_critical > 0 && (
                  <div className="flex items-center gap-2 text-xs text-danger bg-danger/5 rounded-lg px-3 py-2">
                    <Star className="w-3 h-3 fill-danger" />
                    {debt.unread_critical} paper{debt.unread_critical > 1 ? 's' : ''} with score ≥ 9
                  </div>
                )}

                {/* Weekly progress */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">Weekly progress</span>
                    <div className="flex items-center gap-2">
                      <span className="text-text-primary font-medium tabular-nums">
                        {debt.weekly_progress} / {debt.weekly_goal}
                      </span>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          min={1}
                          max={100}
                          value={goalInput}
                          onChange={(e) => {
                            const v = parseInt(e.target.value, 10)
                            if (!isNaN(v)) setGoalInput(Math.max(1, Math.min(100, v)))
                          }}
                          onBlur={handleGoalSave}
                          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
                          className="w-10 text-center text-[11px] bg-bg-base border border-border-default rounded px-1 py-0.5 text-text-muted focus:outline-none focus:border-accent/50 tabular-nums"
                        />
                        <span className="text-text-muted">/wk</span>
                      </div>
                    </div>
                  </div>
                  <div className="h-2 rounded-full bg-bg-elevated overflow-hidden">
                    <div
                      className={`h-2 rounded-full transition-all duration-500 ${
                        debt.weekly_progress >= debt.weekly_goal ? 'bg-success' : 'bg-accent'
                      }`}
                      style={{
                        width: `${Math.min(100, Math.round((debt.weekly_progress / debt.weekly_goal) * 100))}%`,
                      }}
                    />
                  </div>
                  <p className="text-[11px] text-text-muted">
                    {debt.backlog_clear_days != null
                      ? `At your current pace, clear backlog in ${debt.backlog_clear_days} day${debt.backlog_clear_days !== 1 ? 's' : ''}`
                      : 'Set a goal and read to see estimate'}
                  </p>
                </div>

                {/* Score distribution */}
                <div className="space-y-1.5">
                  <span className="text-[11px] text-text-muted">Score distribution</span>
                  {debt.score_distribution.map((b) => {
                    const maxDist = Math.max(...debt.score_distribution.map((x) => x.unread_count), 1)
                    return (
                      <div key={b.bucket} className="flex items-center gap-2">
                        <span className="text-[11px] text-text-secondary w-8 flex-shrink-0 text-right">{b.bucket}</span>
                        <div className="flex-1 bg-bg-elevated rounded-full h-1.5 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-accent/60 transition-all"
                            style={{ width: `${(b.unread_count / maxDist) * 100}%` }}
                          />
                        </div>
                        <span className="text-[11px] text-text-muted tabular-nums w-6 text-right">{b.unread_count}</span>
                      </div>
                    )
                  })}
                </div>

                {/* Top 5 oldest unread */}
                {debt.oldest_unread_high.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] text-text-muted">Oldest high-value unread</span>
                    {debt.oldest_unread_high.map((item) => (
                      <div
                        key={item.id}
                        onClick={() => onSelectArticle?.(item.id)}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-hover cursor-pointer transition-colors group"
                      >
                        <span className="text-[11px] text-text-muted tabular-nums w-8 flex-shrink-0 font-mono">
                          {item.age_days}d
                        </span>
                        <span className="text-xs text-text-secondary flex-1 truncate group-hover:text-text-primary transition-colors">
                          {item.title}
                        </span>
                        {item.score != null && (
                          <span className="text-[11px] text-accent font-medium tabular-nums">{item.score.toFixed(1)}</span>
                        )}
                        <ChevronRight className="w-3 h-3 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                      </div>
                    ))}
                  </div>
                )}

                {/* Empty state for no debt */}
                {debt.unread_high === 0 && (
                  <div className="text-center py-3 text-xs text-text-muted">
                    All caught up! No high-value papers waiting.
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-3 text-xs text-text-muted">
                Could not load reading debt data.
              </div>
            )}
          </div>
        </div>

        {/* 7-day bar chart */}
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">7 derniers jours</h3>
          <div className="bg-bg-surface rounded-xl border border-border-subtle p-4">
            <div className="flex items-end justify-between gap-1.5 h-20">
              {last7.map((day) => (
                <div key={day.date} className="flex flex-col items-center flex-1 gap-1">
                  <div className="relative flex-1 w-full flex items-end">
                    <div
                      className="w-full rounded-sm bg-accent/60 transition-all duration-300 min-h-[2px]"
                      style={{ height: `${(day.count / maxCount) * 100}%` }}
                      title={`${day.count} article${day.count > 1 ? 's' : ''}`}
                    />
                  </div>
                  <span className="text-[10px] text-text-muted">{day.label}</span>
                  {day.count > 0 && (
                    <span className="text-[10px] text-accent font-medium">{day.count}</span>
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
                      className="h-full bg-accent/60 rounded-full transition-all duration-300"
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
