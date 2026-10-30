import { describe, expect, it } from 'vitest'
import { hostLabel, shortAgo } from './format'

describe('shortAgo', () => {
  const now = new Date('2026-10-03T12:00:00Z')
  const ago = (ms: number) => shortAgo(new Date(now.getTime() - ms), now)

  it('uses compact units for recent dates', () => {
    expect(ago(20_000)).toBe('maintenant')
    expect(ago(12 * 60_000)).toBe('12 min')
    expect(ago(5 * 3_600_000)).toBe('5 h')
    expect(ago(3 * 86_400_000)).toBe('3 j')
    expect(ago(15 * 86_400_000)).toBe('2 sem')
  })

  it('falls back to an absolute date after four weeks', () => {
    expect(shortAgo(new Date('2026-08-14T10:00:00Z'), now)).toBe('14 août')
    expect(shortAgo(new Date('2025-08-14T10:00:00Z'), now)).toBe('14 août 2025')
  })

  it('never shows a negative age for clock skew', () => {
    expect(shortAgo(new Date(now.getTime() + 60_000), now)).toBe('maintenant')
  })
})

describe('hostLabel', () => {
  it('drops the www prefix and tolerates bad input', () => {
    expect(hostLabel('https://www.example.com/a/b')).toBe('example.com')
    expect(hostLabel('not a url')).toBe('')
  })
})
