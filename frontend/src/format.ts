import { format } from 'date-fns'
import { fr } from 'date-fns/locale'

/** The date an article is best described by: publication, else ingestion. */
export function articleDate(article: { published_at: string | null; created_at: string }): Date {
  return new Date(article.published_at || article.created_at)
}

/**
 * Compact age for dense lists: "maintenant", "12 min", "5 h", "3 j", "2 sem",
 * then an absolute date. Scans faster than "il y a environ 5 heures".
 */
export function shortAgo(date: Date, now: Date = new Date()): string {
  const seconds = Math.max(0, (now.getTime() - date.getTime()) / 1000)
  if (!Number.isFinite(seconds)) return ''
  if (seconds < 60) return 'maintenant'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} j`
  if (days < 28) return `${Math.floor(days / 7)} sem`
  return format(date, date.getFullYear() === now.getFullYear() ? 'd MMM' : 'd MMM yyyy', { locale: fr })
}

/** Long-form publication date for the reader header: "3 octobre 2026". */
export function longDate(date: Date): string {
  return format(date, 'd MMMM yyyy', { locale: fr })
}

/** Readable host of an article URL, used when no feed name is at hand. */
export function hostLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}
