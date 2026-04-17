import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

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

    # Computed fields
    tags: List[str] = []
    summary_bullets: List[str] = []
    images: List[str] = []

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


class InternalScoreUpdate(BaseModel):
    score: float
    tags: List[str] = []
    summary_bullets: List[str] = []
    reason: Optional[str] = None


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


class HighlightUpdate(BaseModel):
    color: Optional[str] = None
    note: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _HIGHLIGHT_COLORS:
            raise ValueError(f"color must be one of {sorted(_HIGHLIGHT_COLORS)}")
        return v


class HighlightOut(BaseModel):
    id: int
    article_id: int
    selected_text: str
    prefix_context: str
    suffix_context: str
    color: str
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


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
