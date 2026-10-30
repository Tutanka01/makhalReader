import { describe, expect, it } from 'vitest'
import { cleanReason, parseScoreDetails, scoreAxes, scoreCaps, scoreConfidence } from './scoreDetails'

describe('cleanReason', () => {
  it('strips the scorer trace, caps and adjustments', () => {
    const reason =
      'Concrete release details, limited depth. [release, conf=0.80, fit=2.0, depth=1.0, ops=1.5, strat=1.0, novelty=1.0, noise=0.4, score=6.0] Caps: limited-announcement. Adjustments: practical-note.'
    expect(cleanReason(reason)).toBe('Concrete release details, limited depth.')
  })

  it('handles a trace truncated by the 500-char limit', () => {
    expect(cleanReason('Short note. [news, conf=0.90, fit=1.0, depth=0.0, no')).toBe('Short note.')
  })

  it('rewrites the malformed-JSON fallback and hides empty reasons', () => {
    expect(cleanReason('Recovered from malformed LLM JSON. [paper, conf=0.35, fit=0.1]')).toMatch(/Analyse partielle/)
    expect(cleanReason('Scored from structured relevance axes. [news, conf=0.5, fit=1.0]')).toBeNull()
    expect(cleanReason(null)).toBeNull()
    expect(cleanReason('')).toBeNull()
  })

  it('keeps reasons that carry no trace', () => {
    expect(cleanReason('Plain explanation.')).toBe('Plain explanation.')
  })
})

describe('score details', () => {
  const details = parseScoreDetails({
    score_details_json: JSON.stringify({
      topic_fit: 2.4,
      technical_depth: 5, // out of range, clamped
      noise_penalty: 0.3,
      confidence: 0.9,
      caps: ['low-fit', 'unknown-cap'],
    }),
  })

  it('lists known axes in display order and clamps to the 0–3 scale', () => {
    expect(scoreAxes(details).map(a => [a.label, a.value, a.penalty])).toEqual([
      ['Pertinence', 2.4, false],
      ['Profondeur', 3, false],
      ['Bruit', 0.3, true],
    ])
  })

  it('translates caps and exposes confidence', () => {
    expect(scoreCaps(details)).toEqual(['hors de tes sujets', 'unknown cap'])
    expect(scoreConfidence(details)).toBe(0.9)
  })

  it('prefers the parsed object and survives bad JSON', () => {
    expect(parseScoreDetails({ score_details: { novelty: 1 }, score_details_json: '{"novelty":2}' })).toEqual({ novelty: 1 })
    expect(parseScoreDetails({ score_details_json: '{oops' })).toEqual({})
  })
})
