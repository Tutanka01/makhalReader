import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { BriefingView } from './BriefingView'

afterEach(() => { vi.restoreAllMocks() })

const briefing = {
  id: 1, generated_at: new Date().toISOString(), window_start: '', window_end: '',
  model_used: 'mistral', article_count: 12, content_json: '{}',
  content: {
    intro: 'Une journée chargée côté eBPF.',
    sections: [{ title: 'eBPF', synthesis: 'Beaucoup de mouvement.', why_it_matters: 'Important.', article_ids: [1] }],
    top_picks: [1],
    articles: { '1': { id: 1, title: 'Cilium 1.16', url: 'http://x', score: 9, feed_name: 'Isovalent', tags: ['ebpf'], summary_bullets: [], reading_time: 7, read_at: null } },
  },
}

test('renders intro, top pick, and section', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => briefing })))
  render(<BriefingView onOpen={() => {}} />)
  await waitFor(() => expect(screen.getByText(/journée chargée côté eBPF/)).toBeInTheDocument())
  // The article is a top pick AND appears in its theme section, so it renders in both places.
  expect(screen.getAllByText('Cilium 1.16').length).toBeGreaterThan(0)
  expect(screen.getByText('eBPF')).toBeInTheDocument()
})

test('shows empty state with generate button when no briefing', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })))
  render(<BriefingView onOpen={() => {}} />)
  await waitFor(() => expect(screen.getByRole('button', { name: /générer/i })).toBeInTheDocument())
})
