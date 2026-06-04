import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { FacetBadge } from '../FacetBadge'
import type { FacetSchema } from '../../types'

const schema: FacetSchema = {
  version: 1,
  dimensions: [
    { id: 'phase', label: 'Phase', type: 'enum', values: ['a', 'b', 'c'] },
    { id: 'method', label: 'Method', type: 'enum', values: ['qual', 'quant'] },
  ],
}

describe('FacetBadge', () => {
  it('renders nothing when facetsJson is null', () => {
    const { container } = render(<FacetBadge facetsJson={null} schema={schema} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when facetsJson is undefined', () => {
    const { container } = render(<FacetBadge facetsJson={undefined} schema={schema} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when schema is null', () => {
    const { container } = render(<FacetBadge facetsJson='[{"dimensionId":"phase","value":"a"}]' schema={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when facetsJson is invalid JSON', () => {
    const { container } = render(<FacetBadge facetsJson='not-json' schema={schema} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders a badge for each known dimension', () => {
    render(
      <FacetBadge
        facetsJson={JSON.stringify([
          { dimensionId: 'phase', value: 'a' },
          { dimensionId: 'method', value: 'quant' },
        ])}
        schema={schema}
      />
    )

    expect(screen.getByText('Phase: a')).toBeInTheDocument()
    expect(screen.getByText('Method: quant')).toBeInTheDocument()
  })

  it('skips unknown dimension IDs silently', () => {
    render(
      <FacetBadge
        facetsJson={JSON.stringify([
          { dimensionId: 'nonexistent', value: 'x' },
        ])}
        schema={schema}
      />
    )

    expect(screen.queryByText(/nonexistent/)).not.toBeInTheDocument()
  })
})
