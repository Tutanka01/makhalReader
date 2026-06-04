import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ResearchProfileEditor from '../ResearchProfileEditor'

vi.mock('../../store/research', () => ({
  useResearchStore: vi.fn(),
}))

import { useResearchStore } from '../../store/research'

describe('ResearchProfileEditor', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    ;(useResearchStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      profile: [],
      profileLoading: false,
      profileError: null,
      fetchProfile: vi.fn(),
      saveProfile: vi.fn(),
    })
    vi.spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url === '/api/profile/config') {
          return new Response(JSON.stringify({ scoring_clusters: [], facet_schema: { version: 1, dimensions: [] } }), { status: 200 })
        }
        if (url === '/api/feeds') {
          return new Response(JSON.stringify([{ name: 'arXiv' }, { name: 'Nature' }]), { status: 200 })
        }
        return new Response(JSON.stringify({}), { status: 200 })
      })
  })

  it('renders generic section headings (no CS terminology)', async () => {
    render(<ResearchProfileEditor open={true} onClose={vi.fn()} />)

    expect(screen.getByText('Topics')).toBeInTheDocument()
    expect(screen.getByText('Methods')).toBeInTheDocument()
    expect(screen.getByText('Domains')).toBeInTheDocument()
    expect(screen.getByText('Avoid')).toBeInTheDocument()
    expect(screen.getByText('Research Clusters')).toBeInTheDocument()
    expect(screen.getByText('Facet Schema')).toBeInTheDocument()
    expect(screen.getByText('Sources')).toBeInTheDocument()
  })

  it('renders panel title generically', () => {
    render(<ResearchProfileEditor open={true} onClose={vi.fn()} />)
    expect(screen.getByText('Research Profile')).toBeInTheDocument()
  })

  it('does not render CS-specific heading text', () => {
    render(<ResearchProfileEditor open={true} onClose={vi.fn()} />)
    expect(screen.queryByText(/Contribution Types/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Document Types/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/ArXiv/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/CS Clusters/i)).not.toBeInTheDocument()
  })

  it('renders nothing when closed', () => {
    const { container } = render(<ResearchProfileEditor open={false} onClose={vi.fn()} />)
    expect(container.innerHTML).toBe('')
  })
})
