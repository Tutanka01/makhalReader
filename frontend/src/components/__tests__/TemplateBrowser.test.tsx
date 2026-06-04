import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TemplateBrowser from '../TemplateBrowser'

const mockTemplates = [
  { id: 1, name: 'AI Research', domain_label: 'Artificial Intelligence', scope: 'global', cluster_count: 5, created_at: '2026-01-01T00:00:00' },
  { id: 2, name: 'Biology Pack', domain_label: 'Molecular Biology', scope: 'global', cluster_count: 3, created_at: '2026-01-02T00:00:00' },
]

function mockUrl(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input.toString()
}

describe('TemplateBrowser', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders template cards with name, domain_label, cluster count', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = mockUrl(input)
      if (url === '/api/templates') {
        return new Response(JSON.stringify(mockTemplates), { status: 200 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })

    render(<TemplateBrowser onApply={vi.fn()} onClose={vi.fn()} mode="onboarding" />)

    await waitFor(() => {
      expect(screen.getByText('AI Research')).toBeInTheDocument()
    })

    expect(screen.getByText('Artificial Intelligence')).toBeInTheDocument()
    expect(screen.getByText('Biology Pack')).toBeInTheDocument()
    expect(screen.getByText('5 clusters')).toBeInTheDocument()
    expect(screen.getByText('3 clusters')).toBeInTheDocument()
  })

  it('calls onApply with correct template id on click', async () => {
    const onApply = vi.fn().mockResolvedValue(undefined)
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = mockUrl(input)
      if (url === '/api/templates') {
        return new Response(JSON.stringify(mockTemplates), { status: 200 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })

    const user = userEvent.setup()
    render(<TemplateBrowser onApply={onApply} onClose={vi.fn()} mode="onboarding" />)

    await waitFor(() => {
      expect(screen.getByText('AI Research')).toBeInTheDocument()
    })

    const buttons = screen.getAllByText('Use this template')
    await user.click(buttons[0])

    await waitFor(() => {
      expect(onApply).toHaveBeenCalledWith(1)
    })
  })

  it('shows loading state while fetching', async () => {
    let resolvePromise: (v: unknown) => void = () => {}
    const fetchPromise = new Promise((resolve) => { resolvePromise = resolve })

    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      return fetchPromise as Promise<Response>
    })

    render(<TemplateBrowser onApply={vi.fn()} onClose={vi.fn()} mode="onboarding" />)

    await waitFor(() => {
      // Loader2 renders as an SVG with the spinner class
      const loader = document.querySelector('.animate-spin')
      expect(loader).toBeInTheDocument()
    })
  })

  it('shows empty state when API returns []', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = mockUrl(input)
      if (url === '/api/templates') {
        return new Response(JSON.stringify([]), { status: 200 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })

    render(<TemplateBrowser onApply={vi.fn()} onClose={vi.fn()} mode="onboarding" />)

    await waitFor(() => {
      expect(screen.getByText('No templates available yet.')).toBeInTheDocument()
    })
  })
})
