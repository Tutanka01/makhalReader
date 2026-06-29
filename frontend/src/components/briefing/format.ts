import type { BriefingArticle } from '../../types'

/** Signal coding: a score's color maps to "open it" urgency, reusing the app's score tokens. */
export function scoreColor(score: number | null): string {
  const s = score ?? 0
  if (s >= 8) return 'text-score-high'
  if (s >= 6.5) return 'text-score-mid'
  return 'text-text-muted'
}

/** A score shown to the engineer keeps one decimal — it's a measurement, not a label. */
export function fmtScore(score: number | null): string {
  return (score ?? 0).toFixed(1)
}

/** Total reading time across a set of articles, in whole minutes (0 → null). */
export function totalMinutes(articles: BriefingArticle[]): number | null {
  const sum = articles.reduce((acc, a) => acc + (a.reading_time ?? 0), 0)
  return sum > 0 ? sum : null
}

/** Distinct tags across linked articles, most-frequent first, capped. */
export function topTags(articles: BriefingArticle[], limit = 4): string[] {
  const counts = new Map<string, number>()
  for (const a of articles) {
    for (const t of a.tags ?? []) counts.set(t, (counts.get(t) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([t]) => t)
}
