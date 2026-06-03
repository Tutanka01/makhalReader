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
  subscribed?: boolean
}

export interface UserInfo {
  id: number
  email: string
  display_name: string
  role: string
  org_id: number | null
  onboarding_done: boolean
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
  article_titles: string[]
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

// ── External literature review — State of the Art (Semantic Scholar / OpenAlex) ──

export interface ExternalPaper {
  title: string
  abstract: string
  authors: string[]
  year: number | null
  citation_count: number
  venue: string
  url: string
  source: 'semantic_scholar' | 'openalex' | string
  relevance_score: number
}

export interface ExternalReview {
  topic: string
  papers: ExternalPaper[]
  synthesis: string
  relevance_notes: string
  comparison_table: ComparisonRow[]
  gaps: string[]
  top_cite: string
  source: string
  generated_at: string
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
  threat_overlap?: number | null
  threat_positioning_note?: string | null
  tracked_author_alert?: boolean | null
  cited_by_corpus_count?: number
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
  thesis_section?: string | null
  created_at: string
}

export interface HighlightExportRequest {
  thesis_section: string
  window_days?: number
  max_highlights?: number
}

export interface SourceArticle {
  id: number
  title: string
  url: string
}

export interface HighlightSectionCount {
  thesis_section: string
  count: number
}

export const VALID_THESIS_SECTIONS = [
  'P1 Construction',
  'P2 Consistency',
  'P3 Model Drift',
  'P4 Trust',
  'P5 Blueprint Query',
  'Lit Review / Gap',
  'Motivation',
  'Related Work',
  'Counter-argument',
] as const

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

// ── Novelty Threat Monitor (Story 5.1) ───────────────────────────────────────

// ── Author Radar (Story 5.2) ─────────────────────────────────────────────

export interface TrackedAuthor {
  ss_author_id: string
  name: string
  paper_count: number
  avg_score: number
  alert_count: number
  last_checked: string | null
}

export interface AuthorScanResponse {
  authors_checked: number
  new_articles_queued: number
  skipped: number
}

export interface NoveltyAlert {
  article_id: number
  title: string
  url: string
  score: number | null
  overlap_score: number
  positioning_note: string
  checked_at: string
}

export interface ThreatScanResponse {
  scanned: number
  alerts_created: number
  skipped: number
}

export interface ThesisContribution {
  statement: string
  updated_at: string
}

export type SortOption = 'score' | 'date' | 'cited_by_corpus'
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

// ── Reading Debt Dashboard (Story 5.4) ────────────────────────────────────

export interface OldestUnreadItem {
  id: number
  title: string
  score: number | null
  age_days: number
}

export interface ScoreBucket {
  bucket: string
  unread_count: number
}

export interface ReadingDebt {
  unread_high: number
  unread_critical: number
  unread_high_minutes: number
  weekly_goal: number
  weekly_progress: number
  backlog_clear_days: number | null
  oldest_unread_high: OldestUnreadItem[]
  score_distribution: ScoreBucket[]
}

// ── Conference Radar (Story 5.6) ──────────────────────────────────────────

export interface Conference {
  venue: string
  track: string
  abstract_deadline: string | null
  paper_deadline: string
  notification_date: string | null
  conference_date: string
  url: string
  note: string | null
  days_to_abstract: number | null
  days_to_paper: number
  is_past: boolean
  bookmarked: boolean
}

export interface NotificationCounts {
  new_threats: number
  urgent_deadlines: number
  new_author_papers: number
}

export interface MultiSectionExportRequest {
  sections: string[]
  format: 'markdown' | 'latex'
  window_days?: number
  max_highlights_per_section?: number
}

export interface HighlightManagerItem {
  id: number
  article_id: number
  selected_text: string
  prefix_context: string
  suffix_context: string
  color: string
  note: string | null
  thesis_section: string | null
  created_at: string
  article_title: string
  article_url: string
  article_score: number | null
}
