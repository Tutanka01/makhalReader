import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ContribTypeBadge } from '../ContribTypeBadge'

describe('ContribTypeBadge', () => {
  it('renders nothing when type is null', () => {
    const { container } = render(<ContribTypeBadge type={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when type is undefined', () => {
    const { container } = render(<ContribTypeBadge type={undefined} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders badge for a known type', () => {
    render(<ContribTypeBadge type="method" />)
    expect(screen.getByText('Contribution: method')).toBeInTheDocument()
  })

  it('renders badge for any type string', () => {
    render(<ContribTypeBadge type="empirical" />)
    expect(screen.getByText('Contribution: empirical')).toBeInTheDocument()
  })
})
