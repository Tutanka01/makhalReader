// ── Research classification types (Story 2.3) ────────────────────────────
export type ContribType =
  | 'method' | 'benchmark' | 'survey' | 'empirical'
  | 'theory' | 'position' | 'tool' | 'incident'
  | 'tutorial' | 'news' | 'other'

export type REDocType = 'elicitation' | 'extraction' | 'method' | 'none'

export interface PaperMeta {
  is_paper?: boolean
  source?: string
  paper_id?: string
  doi?: string
  abstract?: string
  authors?: string[]
  year?: number
  methods?: string[]
  datasets?: string[]
  metrics?: string[]
  fields_of_study?: string[]
  contribution_type?: ContribType
  re_document_type?: REDocType
  confidence?: number
}

export interface ScoreMeta {
  contribution_type?: ContribType
  re_document_type?: REDocType
  novelty?: number
  rigor?: number
  relevance_to_topics?: number
}

// ── Feed ─────────────────────────────────────────────────────────────────
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
  contribution_type: ContribType | null
  re_document_type: REDocType | null
  paper_meta: PaperMeta
  score_meta: ScoreMeta
  embedding_indexed: number | null   // 1 = indexed in ChromaDB (Story 3.1)
  tags: string[]
  summary_bullets: string[]
  images: string[]
}

// ── Semantic Retrieval (Story 3.1) ────────────────────────────────────────
export interface RelatedArticle {
  id: number
  title: string
  url: string
  score: number | null
  contribution_type: ContribType | null
  re_document_type: REDocType | null
  similarity: number  // 0.0–1.0
}

// ── Topic Cluster Map (Story 3.2) ─────────────────────────────────────────
export interface Cluster {
  cluster_id: number
  size: number
  centroid_title: string
  top_tags: string[]
  article_ids: number[]
}

// ── Researcher Profile (Story 3.3) ────────────────────────────────────────────

export type ProfileKind = 'topic' | 'method' | 'domain' | 'avoid'

export interface ResearchProfileEntry {
  id?: number
  kind: ProfileKind
  label: string
  weight: number
  source: 'manual' | 'feedback'
}

// ── Literature review (Story 3.4) ─────────────────────────────────────────────

export interface ComparisonRow {
  work: string
  method: string
  dataset: string
  key_result: string
}

export interface ReviewCluster {
  cluster_label: string
  synthesis: string
  comparison_table: ComparisonRow[]
  gaps: string[]
  top_cite: string
  article_ids: number[]
  article_titles: string[]
}

export interface LiteratureReview {
  id: number
  topic: string
  window_days: number
  min_rigor: number
  clusters: ReviewCluster[]
  created_at: string
}

export interface LiteratureReviewSummary {
  id: number
  topic: string
  window_days: number
  min_rigor: number
  created_at: string
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
  contribution_type: ContribType | null
  re_document_type: REDocType | null
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
  minScore: number          // 0 = all, 6 = 6+, 8 = 8+
  contributionType: ContribType | null
  ariseOnly: boolean        // true = re_document_type ∈ {elicitation, extraction, method}
}
