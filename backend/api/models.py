import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_HIGHLIGHT_COLORS = {"yellow", "green", "blue", "purple"}


class FeedCreate(BaseModel):
    url: str
    name: str
    category: str = "General"


class FeedOut(BaseModel):
    id: int
    url: str
    name: str
    category: str
    active: bool
    last_fetched: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ArticleOut(BaseModel):
    id: int
    feed_id: int
    title: str
    url: str
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    images_json: str = "[]"
    score: Optional[float] = None
    tags_json: str = "[]"
    summary_bullets_json: str = "[]"
    reason: Optional[str] = None
    read_at: Optional[datetime] = None
    bookmarked: bool = False
    extraction_failed: bool = False
    created_at: datetime
    user_feedback: Optional[int] = None
    score_meta_json: Optional[str] = None
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
    paper_meta_json: Optional[str] = None

    # Computed fields
    tags: List[str] = []
    summary_bullets: List[str] = []
    images: List[str] = []
    score_meta: Dict[str, Any] = {}
    paper_meta: Dict[str, Any] = {}

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def parse_json_fields(self) -> "ArticleOut":
        try:
            self.tags = json.loads(self.tags_json or "[]")
        except Exception:
            self.tags = []
        try:
            self.summary_bullets = json.loads(self.summary_bullets_json or "[]")
        except Exception:
            self.summary_bullets = []
        try:
            self.images = json.loads(self.images_json or "[]")
        except Exception:
            self.images = []
        try:
            self.score_meta = json.loads(self.score_meta_json or "{}")
        except Exception:
            self.score_meta = {}
        try:
            self.paper_meta = json.loads(self.paper_meta_json or "{}")
        except Exception:
            self.paper_meta = {}
        return self


class ArticleListItem(BaseModel):
    id: int
    feed_id: int
    title: str
    url: str
    published_at: Optional[datetime] = None
    score: Optional[float] = None
    tags_json: str = "[]"
    summary_bullets_json: str = "[]"
    reason: Optional[str] = None
    read_at: Optional[datetime] = None
    bookmarked: bool = False
    extraction_failed: bool = False
    created_at: datetime
    feed_name: str = ""
    user_feedback: Optional[int] = None
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
    threat_overlap: Optional[float] = None
    threat_positioning_note: Optional[str] = None
    tracked_author_alert: Optional[bool] = None
    cited_by_corpus_count: int = 0

    # Computed fields
    tags: List[str] = []
    summary_bullets: List[str] = []

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def parse_json_fields(self) -> "ArticleListItem":
        try:
            self.tags = json.loads(self.tags_json or "[]")
        except Exception:
            self.tags = []
        try:
            self.summary_bullets = json.loads(self.summary_bullets_json or "[]")
        except Exception:
            self.summary_bullets = []
        return self


class RelatedArticleOut(BaseModel):
    id: int
    title: str
    url: str
    score: Optional[float] = None
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
    similarity: float  # 0.0–1.0 (1 - cosine_distance)


class ClusterOut(BaseModel):
    cluster_id: int
    size: int
    centroid_title: str
    top_tags: List[str]
    article_ids: List[int]
    article_titles: List[str] = []


# ── Researcher Profile (Story 3.3) ────────────────────────────────────────────

class ResearchProfileEntry(BaseModel):
    id: Optional[int] = None
    kind: str          # 'topic'|'method'|'domain'|'avoid'
    label: str
    weight: float = 1.0
    source: str = "manual"   # 'manual'|'feedback'


class ResearchProfileUpsert(BaseModel):
    entries: List[ResearchProfileEntry]


# ── Literature review (Story 3.4) ───────────────────────────────────────────

class ComparisonRow(BaseModel):
    work: str = ""
    method: str = ""
    dataset: str = ""
    key_result: str = ""


class ReviewClusterOut(BaseModel):
    cluster_label: str
    synthesis: str
    comparison_table: List[ComparisonRow] = []
    gaps: List[str] = []
    top_cite: str = ""
    article_ids: List[int] = []
    article_titles: List[str] = []


class LiteratureReviewCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    window_days: int = Field(default=30, ge=1, le=365)
    min_rigor: float = Field(default=0.0, ge=0.0, le=1.0)


class LiteratureReviewOut(BaseModel):
    id: int
    topic: str
    window_days: int
    min_rigor: float
    clusters: List[ReviewClusterOut]
    created_at: datetime


class LiteratureReviewSummaryOut(BaseModel):
    id: int
    topic: str
    window_days: int
    min_rigor: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ── External literature review (State of the Art) ────────────────────────────

class ExternalPaper(BaseModel):
    title: str
    abstract: str = ""
    authors: List[str] = []
    year: Optional[int] = None
    citation_count: int = 0
    venue: str = ""
    url: str = ""
    source: str = ""
    relevance_score: float = 0.0


class ExternalReviewCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=20, ge=5, le=40)
    min_year: int = Field(default=2018, ge=2000, le=2026)


class ExternalReviewOut(BaseModel):
    topic: str
    papers: List[ExternalPaper]
    synthesis: str
    relevance_notes: str = ""
    comparison_table: List[ComparisonRow] = []
    gaps: List[str] = []
    top_cite: str = ""
    source: str
    generated_at: datetime


# ── ARISE export (Story 4.1) ──────────────────────────────────────────────────


class AriseExportRequest(BaseModel):
    """Lower bound on `published_at` (inclusive). Naive datetimes are treated as UTC."""

    since: datetime

    @field_validator("since", mode="after")
    @classmethod
    def normalize_since_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class AriseArticleOut(BaseModel):
    """NFR15 export row — exactly these keys in JSON responses."""

    id: int
    title: str
    url: str
    published_at: datetime
    re_document_type: str
    contribution_type: Optional[str] = None
    paper_meta: Dict[str, Any] = Field(default_factory=dict)
    content_text: str = ""
    score_meta: Dict[str, Any] = Field(default_factory=dict)
    feed_name: str
    tags: List[str] = Field(default_factory=list)


def build_arise_row(article: Any, feed_name: str) -> AriseArticleOut:
    """Build one ARISE export object from an Article ORM row + joined feed name."""
    paper_meta: Dict[str, Any] = {}
    if article.paper_meta_json:
        try:
            parsed = json.loads(article.paper_meta_json)
            if isinstance(parsed, dict):
                paper_meta = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    score_meta: Dict[str, Any] = {}
    if article.score_meta_json:
        try:
            parsed = json.loads(article.score_meta_json)
            if isinstance(parsed, dict):
                score_meta = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    tags: List[str] = []
    if article.tags_json:
        try:
            parsed = json.loads(article.tags_json)
            if isinstance(parsed, list):
                tags = [str(t) for t in parsed]
        except (json.JSONDecodeError, TypeError):
            pass

    pub = article.published_at
    if pub is None:
        raise ValueError("build_arise_row requires published_at — caller must filter")

    return AriseArticleOut(
        id=int(article.id),
        title=str(article.title or ""),
        url=str(article.url or ""),
        published_at=pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc),
        re_document_type=str(article.re_document_type or ""),
        contribution_type=article.contribution_type,
        paper_meta=paper_meta,
        content_text=str(article.content_text or ""),
        score_meta=score_meta,
        feed_name=str(feed_name or ""),
        tags=tags,
    )


class FeedWithCount(FeedOut):
    article_count: int = 0


class InternalArticleCreate(BaseModel):
    feed_id: int
    title: str
    url: str
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    content_html: Optional[str] = None
    content_text: Optional[str] = None
    images: List[str] = []
    extraction_failed: bool = False
    paper_meta_json: Optional[str] = None
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
    tracked_author_alert: bool = False
    ss_paper_id: Optional[str] = None


class InternalScoreUpdate(BaseModel):
    score: float
    tags: List[str] = []
    summary_bullets: List[str] = []
    reason: Optional[str] = None
    contribution_type: Optional[str] = None
    re_document_type: Optional[str] = None
    novelty: Optional[float] = None
    rigor: Optional[float] = None
    relevance_to_topics: Optional[float] = None


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

class HighlightCreate(BaseModel):
    selected_text: str
    prefix_context: str = ""
    suffix_context: str = ""
    color: str = "yellow"
    note: Optional[str] = None

    @field_validator("selected_text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("selected_text cannot be empty")
        if len(v) > 2000:
            raise ValueError("selected_text must be ≤ 2000 characters")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if v not in _HIGHLIGHT_COLORS:
            raise ValueError(f"color must be one of {sorted(_HIGHLIGHT_COLORS)}")
        return v


_VALID_THESIS_SECTIONS = {
    "P1 Construction",
    "P2 Consistency",
    "P3 Model Drift",
    "P4 Trust",
    "P5 Blueprint Query",
    "Lit Review / Gap",
    "Motivation",
    "Related Work",
    "Counter-argument",
}


class HighlightUpdate(BaseModel):
    color: Optional[str] = None
    note: Optional[str] = None
    thesis_section: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _HIGHLIGHT_COLORS:
            raise ValueError(f"color must be one of {sorted(_HIGHLIGHT_COLORS)}")
        return v

    @field_validator("thesis_section")
    @classmethod
    def validate_thesis_section(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_THESIS_SECTIONS:
            raise ValueError(f"thesis_section must be one of {sorted(_VALID_THESIS_SECTIONS)}")
        return v


class HighlightOut(BaseModel):
    id: int
    article_id: int
    selected_text: str
    prefix_context: str
    suffix_context: str
    color: str
    note: Optional[str] = None
    thesis_section: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HighlightExportRequest(BaseModel):
    thesis_section: str = Field(..., min_length=1)
    window_days: int = Field(default=90, ge=1, le=365)
    max_highlights: int = Field(default=30, ge=2, le=100)


class SourceArticle(BaseModel):
    id: int
    title: str
    url: str


class HighlightExportOut(BaseModel):
    thesis_section: str
    highlight_count: int
    article_count: int
    synthesis_text: str
    source_articles: List[SourceArticle]


# ---------------------------------------------------------------------------
# Ask AI
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question cannot be empty")
        if len(v) > 500:
            raise ValueError("question must be ≤ 500 characters")
        return v


# ---------------------------------------------------------------------------
# Reading statistics
# ---------------------------------------------------------------------------

class DailyReadCount(BaseModel):
    date: str   # "2026-04-17"
    count: int


class TagFrequency(BaseModel):
    tag: str
    count: int


class StatsOut(BaseModel):
    total_read: int
    total_unread: int
    total_bookmarked: int
    streak_days: int
    daily_counts: List[DailyReadCount]
    avg_score_read: Optional[float]
    top_tags: List[TagFrequency]
    total_highlights: int
    articles_per_category: Dict[str, int]


# ---------------------------------------------------------------------------
# Novelty Threat Monitor (Story 5.1)
# ---------------------------------------------------------------------------

class ThesisContributionOut(BaseModel):
    statement: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class ThesisContributionUpdate(BaseModel):
    statement: str = Field(..., max_length=2000)


class NoveltyAlertOut(BaseModel):
    article_id: int
    title: str
    url: str
    score: Optional[float] = None
    overlap_score: float
    positioning_note: str
    checked_at: datetime


class ThreatScanResponse(BaseModel):
    scanned: int
    alerts_created: int
    skipped: int


# ---------------------------------------------------------------------------
# Author Radar (Story 5.2)
# ---------------------------------------------------------------------------

class TrackedAuthorOut(BaseModel):
    ss_author_id: str
    name: str
    paper_count: int
    avg_score: float
    alert_count: int
    last_checked: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AuthorScanResponse(BaseModel):
    authors_checked: int
    new_articles_queued: int
    skipped: int


# ---------------------------------------------------------------------------
# Reading Debt Dashboard (Story 5.4)
# ---------------------------------------------------------------------------

class OldestUnreadItem(BaseModel):
    id: int
    title: str
    score: Optional[float] = None
    age_days: int


class ScoreBucket(BaseModel):
    bucket: str
    unread_count: int


class ReadingDebtOut(BaseModel):
    unread_high: int
    unread_critical: int
    unread_high_minutes: int
    weekly_goal: int
    weekly_progress: int
    backlog_clear_days: Optional[float] = None
    oldest_unread_high: List[OldestUnreadItem]
    score_distribution: List[ScoreBucket]


class ReadingGoalUpdate(BaseModel):
    weekly_goal: int = Field(..., ge=1, le=100)


# ---------------------------------------------------------------------------
# In-Corpus Citation Graph (Story 5.5)
# ---------------------------------------------------------------------------

class TopCitedItem(BaseModel):
    id: int
    title: str
    score: Optional[float] = None
    cited_by_corpus_count: int


class CitationIndexResult(BaseModel):
    indexed_papers: int
    total_citation_links: int
    last_indexed_at: Optional[datetime] = None


class CitationStatsOut(BaseModel):
    indexed_papers: int
    total_citation_links: int
    top_cited: List[TopCitedItem]
    last_indexed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Conference Radar (Story 5.6)
# ---------------------------------------------------------------------------

class ConferenceOut(BaseModel):
    venue: str
    track: str
    abstract_deadline: Optional[str] = None
    paper_deadline: str
    notification_date: Optional[str] = None
    conference_date: str
    url: str
    note: Optional[str] = None
    days_to_abstract: Optional[int] = None
    days_to_paper: int
    is_past: bool
    bookmarked: bool


class ConferenceBookmark(BaseModel):
    venue: str = Field(..., min_length=1)
    bookmarked: bool


# ---------------------------------------------------------------------------
# Notification Badges (Story 6.2)
# ---------------------------------------------------------------------------

class NotificationCounts(BaseModel):
    new_threats: int = 0
    urgent_deadlines: int = 0
    new_author_papers: int = 0


class DismissNotificationsRequest(BaseModel):
    type: str = Field(..., pattern=r"^(threats|conferences|authors)$")


# ---------------------------------------------------------------------------
# Multi-Section Export (Story 6.3)
# ---------------------------------------------------------------------------

class MultiSectionExportRequest(BaseModel):
    sections: List[str] = Field(..., min_length=1, max_length=20)
    format: str = Field(default="markdown", pattern=r"^(markdown|latex)$")
    window_days: int = Field(default=90, ge=1, le=365)
    max_highlights_per_section: int = Field(default=30, ge=2, le=100)


class BulkUpdateHighlightsRequest(BaseModel):
    highlight_ids: List[int] = Field(..., min_length=1)
    thesis_section: str = Field(..., min_length=1)

    @field_validator("thesis_section")
    @classmethod
    def validate_section(cls, v: str) -> str:
        if v not in _VALID_THESIS_SECTIONS:
            raise ValueError(f"thesis_section must be one of {sorted(_VALID_THESIS_SECTIONS)}")
        return v
