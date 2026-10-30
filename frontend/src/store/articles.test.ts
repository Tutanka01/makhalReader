import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Article, ArticleListItem } from '../types'
import { isScorePending, scoringPatch, useArticlesStore } from './articles'

function item(overrides: Partial<ArticleListItem> = {}): ArticleListItem {
  return {
    id: 1,
    feed_id: 1,
    title: 'Pending article',
    url: 'https://example.com/a',
    published_at: '2026-10-03T08:00:00Z',
    score: null,
    tags_json: '[]',
    summary_bullets_json: '[]',
    reason: null,
    read_at: null,
    bookmarked: false,
    extraction_failed: false,
    created_at: '2026-10-03T08:00:00Z',
    feed_name: 'Example',
    feed_category: 'Tech',
    user_feedback: null,
    reading_time: 4,
    scoring_status: 'queued',
    tags: [],
    summary_bullets: [],
    ...overrides,
  }
}

const initial = useArticlesStore.getState()

beforeEach(() => {
  // setFilter triggers a fetch; keep it inert.
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })))
})

afterEach(() => {
  useArticlesStore.setState(initial, true)
  vi.restoreAllMocks()
})

describe('upsertArticle', () => {
  it('fills in the score of an article already on screen, in place', () => {
    useArticlesStore.setState({ articles: [item({ id: 2, title: 'Other' }), item()] })

    useArticlesStore.getState().upsertArticle(item({
      score: 7.2,
      scoring_status: 'done',
      tags: ['ebpf'],
      summary_bullets: ['Point clé'],
      reason: 'Solide.',
    }))

    const { articles } = useArticlesStore.getState()
    expect(articles.map(a => a.id)).toEqual([2, 1])
    expect(articles[1]).toMatchObject({ score: 7.2, scoring_status: 'done', tags: ['ebpf'], summary_bullets: ['Point clé'] })
  })

  it('does not overwrite local read, bookmark or feedback state', () => {
    useArticlesStore.setState({
      articles: [item({ read_at: '2026-10-03T09:00:00Z', bookmarked: true, user_feedback: 1 })],
    })

    useArticlesStore.getState().upsertArticle(item({ score: 5, scoring_status: 'done' }))

    expect(useArticlesStore.getState().articles[0]).toMatchObject({
      score: 5,
      read_at: '2026-10-03T09:00:00Z',
      bookmarked: true,
      user_feedback: 1,
    })
  })

  it('refreshes the open article and search results too', () => {
    const open = { ...item(), content_html: '<p>x</p>' } as unknown as Article
    useArticlesStore.setState({ articles: [], searchResults: [item()], selectedArticle: open })

    useArticlesStore.getState().upsertArticle(item({ score: 8.4, scoring_status: 'done' }))

    const state = useArticlesStore.getState()
    expect(state.searchResults[0].score).toBe(8.4)
    expect(state.selectedArticle?.score).toBe(8.4)
    expect(state.selectedArticle?.content_html).toBe('<p>x</p>')
  })

  it('prepends unseen articles that match the active filter', () => {
    useArticlesStore.setState({ articles: [item({ id: 2 })] })
    useArticlesStore.getState().upsertArticle(item({ id: 3, score: 6, scoring_status: 'done' }))
    expect(useArticlesStore.getState().articles.map(a => a.id)).toEqual([3, 2])
  })

  it('skips unseen articles below the minimum score', () => {
    useArticlesStore.setState({ articles: [], filter: { ...initial.filter, minScore: 8 } })
    useArticlesStore.getState().upsertArticle(item({ id: 3, score: 6, scoring_status: 'done' }))
    expect(useArticlesStore.getState().articles).toEqual([])
  })
})

describe('scoring helpers', () => {
  it('treats a missing score as pending unless scoring failed', () => {
    expect(isScorePending({ score: null, scoring_status: 'queued' })).toBe(true)
    expect(isScorePending({ score: null, scoring_status: undefined })).toBe(true)
    expect(isScorePending({ score: null, scoring_status: 'failed' })).toBe(false)
    expect(isScorePending({ score: 0, scoring_status: 'done' })).toBe(false)
  })

  it('only carries scorer-owned fields', () => {
    const patch = scoringPatch(item({ score: 6, read_at: 'x', bookmarked: true, title: 'New title' }))
    expect(patch).toHaveProperty('score', 6)
    expect(patch).not.toHaveProperty('read_at')
    expect(patch).not.toHaveProperty('bookmarked')
    expect(patch).not.toHaveProperty('title')
  })
})
