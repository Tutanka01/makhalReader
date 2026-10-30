/**
 * Presentation helpers for what the scorer stores alongside a score.
 *
 * The scorer appends a machine-readable trace to `reason`
 * ("… [news, conf=0.90, fit=1.0, …] Caps: low-fit.") and keeps the same axes
 * in `score_details`. The prose and the numbers are shown separately.
 */

interface WithDetails {
  score_details?: Record<string, unknown>
  score_details_json?: string
}

export function parseScoreDetails(article: WithDetails): Record<string, unknown> {
  if (article.score_details && typeof article.score_details === 'object') return article.score_details
  try {
    const parsed = JSON.parse(article.score_details_json ?? '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

// The trace comes last (only Caps/Adjustments follow it) and may be cut off by
// the scorer's 500-char limit, so drop everything from its opening bracket.
const TRACE_RE = /\s*\[[a-z_-]+, conf=[\s\S]*$/i
const TRAILING_NOTES_RE = /\s*(Caps|Adjustments):[\s\S]*$/
const MALFORMED_FALLBACK = 'Recovered from malformed LLM JSON.'

/** The human sentence of a score reason, without the scorer's debug trace. */
export function cleanReason(reason: string | null | undefined): string | null {
  if (!reason) return null
  let text = reason.replace(TRACE_RE, '').replace(TRAILING_NOTES_RE, '').trim()
  if (text === MALFORMED_FALLBACK) text = 'Analyse partielle : la réponse de l’IA était incomplète, le score reste indicatif.'
  if (text === 'Scored from structured relevance axes.') return null
  return text || null
}

export interface ScoreAxis {
  key: string
  label: string
  /** 0–3, as produced by the scorer. */
  value: number
  /** Penalty axes lower the score when high. */
  penalty: boolean
}

const AXES: Array<[string, string, boolean]> = [
  ['topic_fit', 'Pertinence', false],
  ['technical_depth', 'Profondeur', false],
  ['operational_value', 'Pratique', false],
  ['strategic_value', 'Stratégique', false],
  ['novelty', 'Nouveauté', false],
  ['noise_penalty', 'Bruit', true],
]

export const AXIS_MAX = 3

export function scoreAxes(details: Record<string, unknown>): ScoreAxis[] {
  return AXES.flatMap(([key, label, penalty]) => {
    const value = details[key]
    if (typeof value !== 'number' || !Number.isFinite(value)) return []
    return [{ key, label, value: Math.max(0, Math.min(AXIS_MAX, value)), penalty }]
  })
}

const CAP_LABELS: Record<string, string> = {
  'low-fit': 'hors de tes sujets',
  'high-noise': 'trop de bruit',
  'generic-content': 'contenu générique',
  'ordinary-opinion': 'opinion sans angle neuf',
  'practical-opinion': 'opinion surtout pratique',
  'routine-tutorial': 'tutoriel classique',
  'limited-announcement': 'annonce sans détail exploitable',
  'insufficient-context': 'trop peu de texte à analyser',
  'thin-extraction': 'extraction trop courte',
  'very-low-confidence': 'confiance très faible',
  'low-confidence': 'confiance faible',
}

/** Why the score was held down, in plain words. */
export function scoreCaps(details: Record<string, unknown>): string[] {
  const caps = details.caps
  if (!Array.isArray(caps)) return []
  return caps
    .filter((c): c is string => typeof c === 'string')
    .map(c => CAP_LABELS[c] ?? c.replace(/-/g, ' '))
}

/** Scorer confidence, 0–1, when known. */
export function scoreConfidence(details: Record<string, unknown>): number | null {
  const c = details.confidence
  return typeof c === 'number' && Number.isFinite(c) ? Math.max(0, Math.min(1, c)) : null
}
