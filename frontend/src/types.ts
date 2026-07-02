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
  score_details_json: string
  tags_json: string
  summary_bullets_json: string
  reason: string | null
  read_at: string | null
  bookmarked: boolean
  extraction_failed: boolean
  created_at: string
  user_feedback: number | null
  reading_time: number | null
  tags: string[]
  summary_bullets: string[]
  images: string[]
  score_details?: Record<string, unknown>
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
  feed_category: string
  user_feedback: number | null
  reading_time: number | null
  tags: string[]
  summary_bullets: string[]
  score_details?: Record<string, unknown>
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
export type ReadingLensKey = 'all' | 'latest' | 'opinions' | 'debates' | 'practical' | 'deep'

export interface ArticleFilter {
  category: string | null
  sort: SortOption
  status: StatusOption
  bookmarked: boolean
  minScore: number  // 0 = all, 6 = 6+, 8 = 8+
  lens: ReadingLensKey
}

export interface BriefingArticle {
  id: number
  title: string
  url: string
  score: number | null
  feed_name: string
  tags: string[]
  summary_bullets: string[]
  reading_time: number | null
  read_at: string | null
}

export interface BriefingSection {
  title: string
  synthesis: string
  why_it_matters: string
  article_ids: number[]
}

export interface BriefingContent {
  intro: string
  sections: BriefingSection[]
  top_picks: number[]
  articles: Record<string, BriefingArticle>
}

export interface Briefing {
  id: number
  generated_at: string
  window_start: string
  window_end: string
  model_used: string | null
  article_count: number
  content_json: string
  content: BriefingContent
}

export interface BriefingSummary {
  id: number
  generated_at: string
  window_start: string
  window_end: string
  model_used: string | null
  article_count: number
  intro: string
  sections_count: number
  top_picks_count: number
  top_tags: string[]
}
