export interface Feed {
  id: number
  url: string
  name: string
  category: string
  active: boolean
  last_fetched: string | null
  article_count?: number
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
  user_feedback: number | null
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
  user_feedback: number | null
  tags: string[]
  summary_bullets: string[]
}

export interface Highlight {
  id: number
  article_id: number
  selected_text: string
  prefix_context: string
  suffix_context: string
  color: 'yellow' | 'green' | 'blue' | 'purple'
  note: string | null
  created_at: string
}

export interface DailyReadCount {
  date: string
  count: number
}

export interface TagFrequency {
  tag: string
  count: number
}

export interface Stats {
  total_read: number
  total_unread: number
  total_bookmarked: number
  streak_days: number
  daily_counts: DailyReadCount[]
  avg_score_read: number | null
  top_tags: TagFrequency[]
  total_highlights: number
  articles_per_category: Record<string, number>
}

export type SortOption = 'score' | 'date'
export type StatusOption = 'unread' | 'read' | 'all'

export interface ArticleFilter {
  category: string | null
  sort: SortOption
  status: StatusOption
  bookmarked: boolean
  minScore: number  // 0 = all, 6 = 6+, 8 = 8+
}
