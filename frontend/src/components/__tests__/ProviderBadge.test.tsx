import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ProviderBadge } from '../ProviderBadge'

describe('ProviderBadge', () => {
  it('renders RSS badge', () => {
    render(<ProviderBadge provider="rss" />)
    expect(screen.getByText('RSS')).toBeInTheDocument()
  })

  it('renders arXiv badge', () => {
    render(<ProviderBadge provider="arxiv" />)
    expect(screen.getByText('arXiv')).toBeInTheDocument()
  })

  it('renders OpenAlex badge', () => {
    render(<ProviderBadge provider="openalex" />)
    expect(screen.getByText('OpenAlex')).toBeInTheDocument()
  })

  it('renders unknown provider as label fallback', () => {
    render(<ProviderBadge provider="custom" />)
    expect(screen.getByText('custom')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<ProviderBadge provider="rss" className="ml-2" />)
    expect(container.firstChild).toHaveClass('ml-2')
  })
})
