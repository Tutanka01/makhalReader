import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import RediscoverPanel from '../RediscoverPanel'

vi.mock('../../api/discovery', () => ({
  runExpand: vi.fn(),
  runResolve: vi.fn(),
  getExistingSubscriptions: vi.fn(),
  applyDiscoveryPack: vi.fn(),
}))

import { runExpand, runResolve, getExistingSubscriptions, applyDiscoveryPack } from '../../api/discovery'

const mockExpandResult = {
  field_label: 'NLP',
  concepts: ['transformers'],
  venue_keywords: ['ACL'],
  author_keywords: ['Jurafsky'],
  query_terms: ['nlp'],
  language: 'en',
  degraded: false,
}

const mockPack = {
  sources: [
    { name: 'ACL Anthology', provider: 'openalex', query_json: { canonical_id: 'openalex:acl' }, provenance_url: '', verified: true, label: 'journal', unverifiable: false },
  ],
  venues: [
    { name: 'ACL', provider: 'openalex', query_json: {}, provenance_url: '', verified: false, label: 'venue', unverifiable: false },
  ],
  authors: [
    { name: 'Jane Doe', provider: 'openalex', query_json: { openalex_id: 'https://openalex.org/A98765' }, provenance_url: '', verified: false, label: 'author', unverifiable: false },
  ],
}

const mockExistingEmpty = {
  source_canonical_ids: [],
  venue_names: [],
  author_openalex_ids: [],
  author_names: [],
}

const mockExistingAll = {
  source_canonical_ids: ['openalex:acl'],
  venue_names: ['ACL'],
  author_openalex_ids: ['https://openalex.org/A98765'],
  author_names: ['Jane Doe'],
}

describe('RediscoverPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows re-discover button on idle', () => {
    render(<RediscoverPanel thesisText="NLP research" onClose={vi.fn()} />)
    expect(screen.getByText('Re-discover')).toBeInTheDocument()
  })

  it('calls expand then resolve on click then shows new items', async () => {
    vi.mocked(runExpand).mockResolvedValue(mockExpandResult as any)
    vi.mocked(runResolve).mockResolvedValue(mockPack as any)
    vi.mocked(getExistingSubscriptions).mockResolvedValue(mockExistingEmpty)

    render(<RediscoverPanel thesisText="NLP research" onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Re-discover'))

    await waitFor(() => {
      expect(screen.getByText('New Sources')).toBeInTheDocument()
    })
    expect(screen.getByText('ACL Anthology')).toBeInTheDocument()
    expect(screen.getByText('New Venues')).toBeInTheDocument()
    expect(screen.getByText('ACL')).toBeInTheDocument()
    expect(screen.getByText('New Authors')).toBeInTheDocument()
    expect(screen.getByText('Jane Doe')).toBeInTheDocument()
  })

  it('filters out already-subscribed items', async () => {
    vi.mocked(runExpand).mockResolvedValue(mockExpandResult as any)
    vi.mocked(runResolve).mockResolvedValue(mockPack as any)
    vi.mocked(getExistingSubscriptions).mockResolvedValue(mockExistingAll)

    render(<RediscoverPanel thesisText="NLP research" onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Re-discover'))

    await waitFor(() => {
      expect(screen.getByText("You're up to date")).toBeInTheDocument()
    })
    expect(screen.queryByText('ACL Anthology')).not.toBeInTheDocument()
  })

  it('shows up-to-date when diff is empty', async () => {
    vi.mocked(runExpand).mockResolvedValue(mockExpandResult as any)
    vi.mocked(runResolve).mockResolvedValue(mockPack as any)
    vi.mocked(getExistingSubscriptions).mockResolvedValue(mockExistingAll)

    render(<RediscoverPanel thesisText="NLP research" onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Re-discover'))

    await waitFor(() => {
      expect(screen.getByText("You're up to date")).toBeInTheDocument()
    })
  })

  it('applies on Apply all button click', async () => {
    vi.mocked(runExpand).mockResolvedValue(mockExpandResult as any)
    vi.mocked(runResolve).mockResolvedValue(mockPack as any)
    vi.mocked(getExistingSubscriptions).mockResolvedValue(mockExistingEmpty)
    vi.mocked(applyDiscoveryPack).mockResolvedValue({ applied: true, counts: { sources: 1, venues: 1, authors: 1 } })

    render(<RediscoverPanel thesisText="NLP research" onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Re-discover'))

    await waitFor(() => {
      expect(screen.getByText('Apply all')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('Apply all'))

    await waitFor(() => {
      expect(applyDiscoveryPack).toHaveBeenCalledWith({
        sources: mockPack.sources,
        venues: mockPack.venues,
        authors: mockPack.authors,
      })
    })
    expect(screen.getByText('Applied successfully')).toBeInTheDocument()
  })

  it('calls onClose on Done', async () => {
    const onClose = vi.fn()
    vi.mocked(runExpand).mockResolvedValue(mockExpandResult as any)
    vi.mocked(runResolve).mockResolvedValue(mockPack as any)
    vi.mocked(getExistingSubscriptions).mockResolvedValue(mockExistingAll)

    render(<RediscoverPanel thesisText="NLP research" onClose={onClose} />)
    fireEvent.click(screen.getByText('Re-discover'))

    await waitFor(() => {
      expect(screen.getByText('Done')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('Done'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})