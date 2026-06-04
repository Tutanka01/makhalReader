import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ReDocTypeBadge } from '../ReDocTypeBadge'

describe('ReDocTypeBadge', () => {
  it('renders nothing when type is null', () => {
    const { container } = render(<ReDocTypeBadge type={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when type is undefined', () => {
    const { container } = render(<ReDocTypeBadge type={undefined} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders badge for a known type', () => {
    render(<ReDocTypeBadge type="elicitation" />)
    expect(screen.getByText('RE: elicitation')).toBeInTheDocument()
  })

  it('renders badge for any type string', () => {
    render(<ReDocTypeBadge type="extraction" />)
    expect(screen.getByText('RE: extraction')).toBeInTheDocument()
  })
})
