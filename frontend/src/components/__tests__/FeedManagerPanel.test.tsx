import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockCatalog = [
  { id: 1, name: 'Tech News RSS', url: 'https://example.com/rss', category: 'Tech', subscriber_count: 2, subscribed: true, last_fetched: new Date().toISOString(), article_count: 15, feed_type: 'rss' },
  { id: 2, name: 'Science Daily', url: 'https://example.com/science', category: 'Science', subscriber_count: 1, subscribed: false, last_fetched: new Date(Date.now() - 86400000 * 10).toISOString(), article_count: 3, feed_type: 'rss' },
]

const mockSources = [
  { id: 3, name: 'OpenAlex Biology', provider: 'openalex', category: 'Biology', subscribed: false, label: 'Biology papers' },
  { id: 4, name: 'arXiv ML', provider: 'arxiv', category: 'AI', subscribed: true, label: 'Machine Learning' },
  { id: 1, name: 'Tech News RSS', provider: 'rss', category: 'Tech', subscribed: true, label: null },
]

describe('FeedManagerPanel', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url instanceof URL ? url.href : url.url
      if (urlStr === '/api/feeds/catalog') {
        return Promise.resolve(new Response(JSON.stringify(mockCatalog), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${urlStr}`))
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders and shows RSS feed provider badges', async () => {
    const FeedManagerPanel = (await import('../FeedManagerPanel')).FeedManagerPanel
    render(<FeedManagerPanel currentUser={{ id: 1, display_name: 'test', email: 'test@test.com', role: 'admin', org_id: null, onboarding_done: true, created_at: null }} onFeedsChange={() => {}} />)

    expect(await screen.findByText('Tech News RSS')).toBeInTheDocument()
    expect(await screen.findByText('Science Daily')).toBeInTheDocument()
  })

  it('renders provider-based sources section', async () => {
    // Override fetch mock to return sources via the sources API too
    vi.spyOn(globalThis, 'fetch').mockImplementation((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url instanceof URL ? url.href : url.url
      if (urlStr === '/api/feeds/catalog') {
        return Promise.resolve(new Response(JSON.stringify(mockCatalog), { status: 200 }))
      }
      if (urlStr === '/api/sources') {
        return Promise.resolve(new Response(JSON.stringify(mockSources), { status: 200 }))
      }
      return Promise.reject(new Error(`unexpected fetch: ${urlStr}`))
    })

    const FeedManagerPanel = (await import('../FeedManagerPanel')).FeedManagerPanel
    render(<FeedManagerPanel currentUser={{ id: 1, display_name: 'test', email: 'test@test.com', role: 'admin', org_id: null, onboarding_done: true, created_at: null }} onFeedsChange={() => {}} />)

    expect(await screen.findByText('OpenAlex Biology')).toBeInTheDocument()
    expect(await screen.findByText('arXiv ML')).toBeInTheDocument()
    expect(await screen.findByText('OpenAlex')).toBeInTheDocument()
    expect(await screen.findByText('arXiv')).toBeInTheDocument()
  })
})
