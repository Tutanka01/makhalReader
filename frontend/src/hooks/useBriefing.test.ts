import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { useBriefing } from './useBriefing'

afterEach(() => { vi.restoreAllMocks() })

test('loads latest briefing on mount', async () => {
  const briefing = { id: 1, content_json: '{}', content: { intro: 'hi', sections: [], top_picks: [], articles: {} } }
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => briefing })))

  const { result } = renderHook(() => useBriefing())
  await waitFor(() => expect(result.current.status).toBe('ready'))
  expect(result.current.briefing?.id).toBe(1)
})

test('reports empty when no briefing exists (404)', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })))
  const { result } = renderHook(() => useBriefing())
  await waitFor(() => expect(result.current.status).toBe('empty'))
})

test('generate posts and stores the new briefing', async () => {
  const made = { id: 9, content_json: '{}', content: { intro: 'new', sections: [], top_picks: [], articles: {} } }
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({}) })      // initial load
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => made })        // generate
  vi.stubGlobal('fetch', fetchMock)

  const { result } = renderHook(() => useBriefing())
  await waitFor(() => expect(result.current.status).toBe('empty'))
  await act(async () => { await result.current.generate() })
  expect(result.current.briefing?.id).toBe(9)
  expect(result.current.status).toBe('ready')
})
