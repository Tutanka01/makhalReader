import type { Article, ArticleListItem, ReadingLensKey } from './types'

export interface LensDefinition {
  key: ReadingLensKey
  label: string
  shortLabel: string
  description: string
  tone: 'neutral' | 'fresh' | 'opinion' | 'debate' | 'practical' | 'deep' | 'curiosity'
}

export interface ArticleLens extends LensDefinition {
  reason: string
}

export const LENS_FILTERS: LensDefinition[] = [
  {
    key: 'all',
    label: 'Tout le radar',
    shortLabel: 'Tout',
    description: 'Le flux normal, sans intention forcée.',
    tone: 'neutral',
  },
  {
    key: 'latest',
    label: 'Dernières sorties',
    shortLabel: 'Nouveau',
    description: 'Ce qui vient de sortir, avant jugement sévère.',
    tone: 'fresh',
  },
  {
    key: 'opinions',
    label: 'Ce que les gens disent',
    shortLabel: 'Opinions',
    description: 'Blogs, positions, rants et lectures subjectives.',
    tone: 'opinion',
  },
  {
    key: 'debates',
    label: 'Débats & backlash',
    shortLabel: 'Débats',
    description: 'Signaux controversés ou opinions qui montent.',
    tone: 'debate',
  },
  {
    key: 'practical',
    label: 'Actionnable',
    shortLabel: 'Pratique',
    description: 'Retours terrain, workflows, tutos et postmortems.',
    tone: 'practical',
  },
  {
    key: 'deep',
    label: 'Deep dives',
    shortLabel: 'Deep',
    description: 'Articles denses, techniques, papiers et architectures.',
    tone: 'deep',
  },
]

const LENS_BY_KEY = new Map(LENS_FILTERS.map((lens) => [lens.key, lens]))

const CONTRARIAN_RE = /\b(ai is|ai isn't|ai sucks|ai is shit|broken|overhyped|bullshit|stop using|against|critique|rant|backlash|hate|dead)\b/i
const OPINION_RE = /\b(opinion|why i|i think|essay|personal|notes|thoughts|position|take)\b/i

interface ArticleLike {
  title: string
  published_at: string | null
  created_at: string
  score: number | null
  tags: string[]
  score_details_json?: string
  score_details?: Record<string, unknown>
}

function parseScoreDetails(article: ArticleLike): Record<string, unknown> {
  if (article.score_details && typeof article.score_details === 'object') return article.score_details
  try {
    const parsed = JSON.parse(article.score_details_json ?? '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function numberDetail(details: Record<string, unknown>, key: string): number {
  const value = details[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function stringDetail(details: Record<string, unknown>, key: string): string {
  const value = details[key]
  return typeof value === 'string' ? value : ''
}

function listDetail(details: Record<string, unknown>, key: string): string[] {
  const value = details[key]
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function daysSince(article: ArticleLike): number | null {
  const raw = article.published_at || article.created_at
  if (!raw) return null
  const time = new Date(raw).getTime()
  if (!Number.isFinite(time)) return null
  return (Date.now() - time) / 86_400_000
}

function lens(key: ReadingLensKey, reason: string): ArticleLens | null {
  const definition = LENS_BY_KEY.get(key)
  return definition ? { ...definition, reason } : null
}

export function getArticleLenses(article: ArticleLike): ArticleLens[] {
  const details = parseScoreDetails(article)
  const declared = new Set(listDetail(details, 'reading_lenses'))
  const contentType = stringDetail(details, 'content_type')
  const topicFit = numberDetail(details, 'topic_fit')
  const technicalDepth = numberDetail(details, 'technical_depth')
  const operationalValue = numberDetail(details, 'operational_value')
  const novelty = numberDetail(details, 'novelty')
  const noisePenalty = numberDetail(details, 'noise_penalty')
  const ageDays = daysSince(article)
  const title = article.title || ''
  const tags = article.tags || []

  const found: ArticleLens[] = []
  const push = (key: ReadingLensKey, reason: string) => {
    if (found.some((item) => item.key === key)) return
    const item = lens(key, reason)
    if (item) found.push(item)
  }

  if (ageDays !== null && ageDays <= 3) {
    push('latest', ageDays < 1 ? 'sorti aujourd’hui' : 'sorti il y a moins de 3 jours')
  }

  if (
    declared.has('opinion') ||
    declared.has('community-signal') ||
    contentType === 'opinion' ||
    OPINION_RE.test(title)
  ) {
    push('opinions', 'utile pour sentir une position ou une humeur du moment')
  }

  if (
    declared.has('contrarian') ||
    declared.has('debate') ||
    declared.has('weak-signal') ||
    CONTRARIAN_RE.test(title) ||
    (contentType === 'opinion' && topicFit >= 1.6 && novelty >= 0.8)
  ) {
    push('debates', 'signal de débat, backlash ou angle tranché à surveiller')
  }

  if (
    declared.has('practical') ||
    operationalValue >= 1.8 ||
    contentType === 'tutorial' ||
    contentType === 'postmortem'
  ) {
    push('practical', 'contient un usage, retour terrain ou apprentissage réutilisable')
  }

  if (
    declared.has('deep-dive') ||
    technicalDepth >= 2.0 ||
    contentType === 'paper' ||
    tags.some((tag) => /kernel|ebpf|paper|architecture|internals/i.test(tag))
  ) {
    push('deep', 'densité technique ou mécanismes à inspecter')
  }

  if (
    article.score !== null &&
    article.score !== undefined &&
    article.score < 6 &&
    topicFit >= 1.7 &&
    (contentType === 'opinion' || declared.has('weak-signal') || CONTRARIAN_RE.test(title))
  ) {
    const curiosity = lens('opinions', noisePenalty >= 1.8 ? 'faible rigueur, mais signal de curiosité' : 'score modeste, mais angle intéressant')
    if (curiosity && !found.some((item) => item.reason.includes('curiosité'))) {
      found.unshift({ ...curiosity, tone: 'curiosity', shortLabel: 'Curiosité' })
    }
  }

  return found.slice(0, 4)
}

export function getPrimaryLens(article: ArticleLike): ArticleLens | null {
  return getArticleLenses(article)[0] || null
}

export function lensToneClass(tone: LensDefinition['tone']): string {
  switch (tone) {
    case 'fresh':
      return 'border-accent-blue/20 bg-accent-blue/10 text-accent-blue'
    case 'opinion':
      return 'border-accent-yellow/22 bg-accent-yellow/10 text-accent-yellow'
    case 'debate':
      return 'border-accent-red/22 bg-accent-red/10 text-accent-red'
    case 'practical':
      return 'border-accent-green/22 bg-accent-green/10 text-accent-green'
    case 'deep':
      return 'border-text-muted/20 bg-bg-elevated text-text-secondary'
    case 'curiosity':
      return 'border-accent-yellow/28 bg-accent-yellow/14 text-accent-yellow'
    default:
      return 'border-border-subtle bg-bg-elevated/70 text-text-muted'
  }
}
