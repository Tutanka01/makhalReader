"""Profile router — per-user profile configuration (Story 4.5, FR-MT-22 / 4.6, FR-MT-20)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_session
from database import UserConfig, get_db, get_valid_thesis_sections

router = APIRouter(prefix="/api/profile", tags=["profile"])
logger = structlog.get_logger().bind(service="profile")


class SectionRequest(BaseModel):
    section: str


class UserConfigResponse(BaseModel):
    user_id: int
    thesis_title: str = ""
    thesis_question: str | None = None
    thesis_contribution: str | None = None
    thesis_sections: List[str] = Field(default_factory=list)
    scoring_clusters: List[str] = Field(default_factory=list)
    tracked_venues: List[str] = Field(default_factory=list)
    avoid_topics: List[str] = Field(default_factory=list)
    weekly_goal: int = 10
    model_preference: str = "google/gemini-flash-1.5"
    prompt_profile: str = "unified"


class ConfigUpdate(BaseModel):
    thesis_title: str | None = None
    thesis_question: str | None = None
    thesis_contribution: str | None = None
    thesis_sections: List[str] | None = None
    scoring_clusters: List[str] | None = None
    tracked_venues: List[str] | None = None
    avoid_topics: List[str] | None = None
    weekly_goal: int | None = None
    model_preference: str | None = None
    prompt_profile: str | None = None


def _config_to_response(config: UserConfig) -> Dict[str, Any]:
    return {
        "user_id": config.user_id,
        "thesis_title": config.thesis_title,
        "thesis_question": config.thesis_question,
        "thesis_contribution": config.thesis_contribution,
        "thesis_sections": json.loads(config.thesis_sections_json or "[]"),
        "scoring_clusters": json.loads(config.scoring_clusters_json or "[]"),
        "tracked_venues": json.loads(config.tracked_venues_json or "[]"),
        "avoid_topics": json.loads(config.avoid_topics_json or "[]"),
        "weekly_goal": config.weekly_goal,
        "model_preference": config.model_preference,
        "prompt_profile": config.prompt_profile,
    }


def _get_user_config(db: Session, user_id: int) -> UserConfig:
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="User config not found")
    return config


# ── Sections ────────────────────────────────────────────────────────────────


@router.get("/sections", response_model=List[str])
async def list_sections(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    return sorted(get_valid_thesis_sections(db, current_user["id"]))


@router.post("/sections", response_model=List[str])
async def add_section(
    body: SectionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    user_id = current_user["id"]
    config = _get_user_config(db, user_id)
    label = body.section.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Section label cannot be empty")
    sections = json.loads(config.thesis_sections_json or "[]")
    if label in sections:
        raise HTTPException(status_code=409, detail="Section already exists")
    sections.append(label)
    config.thesis_sections_json = json.dumps(sections)
    config.prompt_cache_text = None
    config.prompt_cache_hash = None
    db.commit()
    logger.info("section_added", user_id=user_id, section=label)
    return sorted(sections)


@router.delete("/sections", response_model=List[str])
async def delete_section(
    body: SectionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    user_id = current_user["id"]
    config = _get_user_config(db, user_id)
    label = body.section.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Section label cannot be empty")
    sections = json.loads(config.thesis_sections_json or "[]")
    if label not in sections:
        raise HTTPException(status_code=404, detail="Section not found")
    sections.remove(label)
    config.thesis_sections_json = json.dumps(sections)
    config.prompt_cache_text = None
    config.prompt_cache_hash = None
    db.commit()
    logger.info("section_deleted", user_id=user_id, section=label)
    return sorted(sections)


# ── Full config ─────────────────────────────────────────────────────────────


@router.get("/config", response_model=UserConfigResponse)
async def get_config(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    config = _get_user_config(db, current_user["id"])
    return UserConfigResponse(**_config_to_response(config))


@router.put("/config", response_model=UserConfigResponse)
async def update_config(
    body: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    user_id = current_user["id"]
    config = _get_user_config(db, user_id)
    dirty = False

    updates = body.model_dump(exclude_none=True)
    if "thesis_title" in updates:
        config.thesis_title = updates["thesis_title"]
        dirty = True
    if "thesis_question" in updates:
        config.thesis_question = updates["thesis_question"]
        dirty = True
    if "thesis_contribution" in updates:
        config.thesis_contribution = updates["thesis_contribution"]
        dirty = True
    if "thesis_sections" in updates:
        config.thesis_sections_json = json.dumps(updates["thesis_sections"])
        dirty = True
    if "scoring_clusters" in updates:
        config.scoring_clusters_json = json.dumps(updates["scoring_clusters"])
        dirty = True
    if "tracked_venues" in updates:
        config.tracked_venues_json = json.dumps(updates["tracked_venues"])
        dirty = True
    if "avoid_topics" in updates:
        config.avoid_topics_json = json.dumps(updates["avoid_topics"])
        dirty = True
    if "weekly_goal" in updates:
        config.weekly_goal = updates["weekly_goal"]
        dirty = True
    if "model_preference" in updates:
        config.model_preference = updates["model_preference"]
        dirty = True
    if "prompt_profile" in updates:
        config.prompt_profile = updates["prompt_profile"]
        dirty = True

    if dirty:
        config.prompt_cache_text = None
        config.prompt_cache_hash = None
        db.commit()
        logger.info("config_updated", user_id=user_id)

    return UserConfigResponse(**_config_to_response(config))
