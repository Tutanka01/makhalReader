import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ScoreBadge, scoreTier, signalBars } from './ui'

describe('signal meter scale', () => {
  it('maps a 0–10 score onto four bars', () => {
    expect([0, 1.5, 3.6, 5.7, 7, 8, 10].map(signalBars)).toEqual([0, 1, 2, 3, 3, 4, 4])
  })

  it('uses the shared score bands', () => {
    expect([9, 8, 7.9, 5, 4.9].map(scoreTier)).toEqual(['high', 'high', 'mid', 'mid', 'low'])
  })
})

describe('ScoreBadge', () => {
  it('shows the score when known', () => {
    render(<ScoreBadge score={7.24} status="done" />)
    expect(screen.getByRole('img', { name: 'Score IA 7.2 sur 10' })).toHaveTextContent('7.2')
  })

  it('reads as in progress while the scorer works, not as missing data', () => {
    render(<ScoreBadge score={null} status="processing" />)
    expect(screen.getByRole('img', { name: /en cours de calcul/ })).toHaveTextContent('Analyse…')
    expect(screen.queryByText('--')).not.toBeInTheDocument()
  })

  it('says when scoring gave up', () => {
    render(<ScoreBadge score={null} status="failed" compact />)
    expect(screen.getByRole('img', { name: /échoué/ })).toHaveTextContent('n/a')
  })
})
