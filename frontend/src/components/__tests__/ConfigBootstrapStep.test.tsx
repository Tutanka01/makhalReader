import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ConfigBootstrapStep from '../ConfigBootstrapStep'

const mockBootstrapResult = {
  domain_label: 'Urban Mobility',
  scoring_clusters: [
    { name: 'Modal Shift', description: 'transit substitution', reward_level: 0.9 },
  ],
  facet_schema: {
    version: 1,
    dimensions: [
      { id: 'phase', label: 'Phase', type: 'enum', values: ['a', 'b'] },
    ],
  },
  keywords: ['mobility', 'cycling'],
  suggested_source_queries: ['urban cycling adoption'],
  degraded: false,
}

const mockDegradedResult = {
  domain_label: '',
  scoring_clusters: [],
  facet_schema: { version: 1, dimensions: [] },
  keywords: [],
  suggested_source_queries: [],
  degraded: true,
}

describe('ConfigBootstrapStep', () => {
  const onNext = vi.fn()
  const onSkip = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls bootstrap API on mount with thesisText', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockBootstrapResult), { status: 200 })
    )

    render(
      <ConfigBootstrapStep
        thesisText="Urban mobility study"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/profile/bootstrap', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thesis_text: 'Urban mobility study' }),
      })
    })
  })

  it('shows loading skeleton during fetch', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))
    const { container } = render(
      <ConfigBootstrapStep
        thesisText="test"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders editable cluster cards after successful fetch', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockBootstrapResult), { status: 200 })
    )

    render(
      <ConfigBootstrapStep
        thesisText="Urban mobility study"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(screen.getByDisplayValue('Modal Shift')).toBeInTheDocument()
    })
    expect(screen.getByDisplayValue('transit substitution')).toBeInTheDocument()
    expect(screen.getByDisplayValue('0.9')).toBeInTheDocument()
  })

  it('renders facet dimensions after successful fetch', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockBootstrapResult), { status: 200 })
    )

    render(
      <ConfigBootstrapStep
        thesisText="Urban mobility study"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(screen.getByDisplayValue('Phase')).toBeInTheDocument()
    })
  })

  it('renders keywords as tags after successful fetch', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockBootstrapResult), { status: 200 })
    )

    render(
      <ConfigBootstrapStep
        thesisText="Urban mobility study"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('mobility')).toBeInTheDocument()
      expect(screen.getByText('cycling')).toBeInTheDocument()
    })
  })

  it('calls onSkip when skip button is clicked', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockBootstrapResult), { status: 200 })
    )

    const user = userEvent.setup()
    render(
      <ConfigBootstrapStep
        thesisText="test"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(screen.queryByText('Skip')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Skip'))
    expect(onSkip).toHaveBeenCalledOnce()
    expect(onNext).not.toHaveBeenCalled()
  })

  it('shows degraded banner when result is degraded', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockDegradedResult), { status: 200 })
    )

    render(
      <ConfigBootstrapStep
        thesisText="test"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/Auto-generation is currently unavailable/)).toBeInTheDocument()
    })
  })

  it('calls onNext with modified cluster name after edit', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockBootstrapResult), { status: 200 })
    )

    const user = userEvent.setup()
    render(
      <ConfigBootstrapStep
        thesisText="Urban mobility study"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(screen.getByDisplayValue('Modal Shift')).toBeInTheDocument()
    })

    const nameInput = screen.getByDisplayValue('Modal Shift')
    await user.clear(nameInput)
    await user.type(nameInput, 'Mobility Shift')

    await user.click(screen.getByText('Continue →'))

    expect(onNext).toHaveBeenCalledTimes(1)
    const result = onNext.mock.calls[0][0]
    expect(result.scoring_clusters[0].name).toBe('Mobility Shift')
  })

  it('shows degraded banner on network error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'))

    render(
      <ConfigBootstrapStep
        thesisText="test"
        onNext={onNext}
        onSkip={onSkip}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/Auto-generation is currently unavailable/)).toBeInTheDocument()
    })
  })
})
