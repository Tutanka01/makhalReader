export interface Feed {
  id: number
  url: string
  name: string
  category: string
  active: boolean
  last_fetched: string | null
}

export interface Article {
  id: number
  feed_id: number
  title: string
  url: string
  published_at: string | null
  author: string | null
  content_html: string | null
  content_text: string | null
  images_json: string
  score: number | null
  tags_json: string
  summary_bullets_json: string
  reason: string | null
  read_at: string | null
  bookmarked: boolean
  extraction_failed: boolean
  created_at: string
  tags: string[]
  summary_bullets: string[]
  images: string[]
}

export interface ArticleListItem {
  id: number
  feed_id: number
  title: string
  url: string
  published_at: string | null
  score: number | null
  tags_json: string
  summary_bullets_json: string
  reason: string | null
  read_at: string | null
  bookmarked: boolean
  extraction_failed: boolean
  created_at: string
  feed_name: string
  tags: string[]
  summary_bullets: string[]
}

export type SortOption = 'score' | 'date'
export type StatusOption = 'unread' | 'read' | 'all'

export interface ArticleFilter {
  category: string | null
  sort: SortOption
  status: StatusOption
  bookmarked: boolean
}
