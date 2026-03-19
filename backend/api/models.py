import json
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, model_validator


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
