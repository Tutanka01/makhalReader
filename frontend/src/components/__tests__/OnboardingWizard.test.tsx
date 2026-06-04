import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import OnboardingWizard from '../OnboardingWizard'

const validBootstrapResponse = {
  domain_label: 'Test',
  scoring_clusters: [],
  facet_schema: { version: 1, dimensions: [] },
  keywords: [],
  suggested_source_queries: [],
  degraded: false,
}

function mockUrl(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input.toString()
}

describe('OnboardingWizard — Step 2 manual build path', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows ConfigBootstrapStep when thesis entered and submitted', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = mockUrl(input)
        if (url === '/api/onboarding/step1') {
          return new Response(JSON.stringify({}), { status: 200 })
        }
        return new Response(JSON.stringify(validBootstrapResponse), { status: 200 })
      })

    render(<OnboardingWizard onComplete={vi.fn()} />)

    const input = screen.getByPlaceholderText(/e.g. AI-Driven/)
    await userEvent.type(input, 'Urban Mobility')
    await userEvent.click(screen.getByText('Continue →'))

    await waitFor(() => {
      expect(screen.getByText(/Review your scoring configuration/)).toBeInTheDocument()
    })
  })

  it('shows manual build view when Skip clicked on step 1', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = mockUrl(input)
        if (url === '/api/feeds/catalog') return new Response(JSON.stringify([]), { status: 200 })
        return new Response(JSON.stringify({}), { status: 200 })
      })

    render(<OnboardingWizard onComplete={vi.fn()} />)

    await userEvent.click(screen.getByText('Skip'))

    await waitFor(() => {
      expect(screen.getByText('Configure your research profile')).toBeInTheDocument()
    })

    expect(screen.getByText('Scoring Clusters')).toBeInTheDocument()
    expect(screen.getByText('Facet Dimensions')).toBeInTheDocument()
    expect(screen.getByText('+ Add cluster')).toBeInTheDocument()
    expect(screen.getByText('Skip')).toBeInTheDocument()
    expect(screen.getByText('Continue →')).toBeInTheDocument()
  })

  it('adds a cluster card on clicking Add cluster', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = mockUrl(input)
        if (url === '/api/feeds/catalog') return new Response(JSON.stringify([]), { status: 200 })
        return new Response(JSON.stringify({}), { status: 200 })
      })

    const user = userEvent.setup()
    render(<OnboardingWizard onComplete={vi.fn()} />)

    await user.click(screen.getByText('Skip'))
    await waitFor(() => {
      expect(screen.getByText('Configure your research profile')).toBeInTheDocument()
    })

    await user.click(screen.getByText('+ Add cluster'))

    await waitFor(() => {
      const nameInputs = screen.getAllByPlaceholderText('Cluster name')
      expect(nameInputs.length).toBe(1)
    })
    expect(screen.getByPlaceholderText('Cluster description')).toBeInTheDocument()
  })

  it('saves manual clusters via PUT /api/profile/config on Continue', async () => {
    let putPayload: unknown = null
    vi.spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL, opts?: RequestInit) => {
        const url = mockUrl(input)
        if (url === '/api/profile/config' && opts?.method === 'PUT') {
          putPayload = JSON.parse(opts.body as string)
          return new Response(JSON.stringify({}), { status: 200 })
        }
        if (url === '/api/feeds/catalog') return new Response(JSON.stringify([]), { status: 200 })
        return new Response(JSON.stringify({}), { status: 200 })
      })

    const user = userEvent.setup()
    render(<OnboardingWizard onComplete={vi.fn()} />)

    await user.click(screen.getByText('Skip'))
    await waitFor(() => {
      expect(screen.getByText('Configure your research profile')).toBeInTheDocument()
    })

    await user.click(screen.getByText('+ Add cluster'))
    await waitFor(() => {
      expect(screen.getAllByPlaceholderText('Cluster name').length).toBe(1)
    })

    const nameInput = screen.getByPlaceholderText('Cluster name')
    await user.type(nameInput, 'Urban Mobility')
    await user.click(screen.getByText('Continue →'))

    await waitFor(() => {
      expect(putPayload).not.toBeNull()
    })
    const body = putPayload as Record<string, unknown>
    expect(body.scoring_clusters).toBeDefined()
    expect(body.facet_schema).toBeDefined()
    expect(body).not.toHaveProperty('thesis_text')
  })

  it('does NOT call bootstrap API on manual save', async () => {
    const calls: string[] = []
    vi.spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL, _opts?: RequestInit) => {
        const url = mockUrl(input)
        calls.push(url)
        if (url === '/api/feeds/catalog') return new Response(JSON.stringify([]), { status: 200 })
        return new Response(JSON.stringify({}), { status: 200 })
      })

    const user = userEvent.setup()
    render(<OnboardingWizard onComplete={vi.fn()} />)

    await user.click(screen.getByText('Skip'))
    await waitFor(() => {
      expect(screen.getByText('Configure your research profile')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Continue →'))

    await waitFor(() => {
      expect(calls).not.toContain('/api/profile/bootstrap')
    })
  })
})
