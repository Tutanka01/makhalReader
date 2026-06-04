"""Profile router — per-user profile configuration (Story 4.5, FR-MT-22 / 4.6, FR-MT-20).

Story 11.2 — extends with `POST /api/profile/bootstrap` (preview-only, no
persistence) plus `thesis_text`, `domain_label`, `facet_schema` fields on
GET/PUT `/api/profile/config`.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_session
from database import ConfigTemplate, UserConfig, get_db, get_valid_thesis_sections
from services import config_bootstrap

router = APIRouter(prefix="/api/profile", tags=["profile"])
# Story 11.3 — branch router for template listing (prefix /api, not /api/profile).
templates_router = APIRouter(prefix="/api", tags=["templates"])
logger = structlog.get_logger().bind(service="profile")

# ── Bootstrap rate limiter (Story 11.2) ────────────────────────────────────
#
# NFR-DA6 — module-level dict mapping user_id → list of recent request
# timestamps. Per-user, in-memory, no Redis. Reset on api restart, which is
# fine because the LLM cache also lives in-memory.

BOOTSTRAP_RATE_LIMIT = int(os.getenv("BOOTSTRAP_RATE_LIMIT", "10"))
BOOTSTRAP_RATE_WINDOW_SECONDS = int(os.getenv("BOOTSTRAP_RATE_WINDOW_SECONDS", "3600"))
_bootstrap_calls: dict[int, list[float]] = {}


def _check_bootstrap_rate_limit(user_id: int) -> Optional[int]:
    """Return seconds until reset if user is over limit, else None."""
    now = time.monotonic()
    window = BOOTSTRAP_RATE_WINDOW_SECONDS
    history = _bootstrap_calls.setdefault(user_id, [])
    # Drop expired entries
    cutoff = now - window
    history[:] = [t for t in history if t > cutoff]
    if len(history) >= BOOTSTRAP_RATE_LIMIT:
        retry_after = int(window - (now - history[0])) + 1
        return max(retry_after, 1)
    history.append(now)
    return None


def _reset_bootstrap_rate_limits() -> None:
    """Test-only hook so unit tests can isolate rate-limit state."""
    _bootstrap_calls.clear()


class SectionRequest(BaseModel):
    section: str


class UserConfigResponse(BaseModel):
    user_id: int
    thesis_title: str = ""
    thesis_question: str | None = None
    thesis_contribution: str | None = None
    thesis_sections: List[str] = Field(default_factory=list)
    scoring_clusters: List[Any] = Field(default_factory=list)
    tracked_venues: List[str] = Field(default_factory=list)
    avoid_topics: List[str] = Field(default_factory=list)
    weekly_goal: int = 10
    model_preference: str = "google/gemini-flash-1.5"
    prompt_profile: str = "unified"
    # Story 11.2 — bootstrap fields
    thesis_text: str | None = None
    domain_label: str | None = None
    facet_schema: dict | None = None


class ConfigUpdate(BaseModel):
    thesis_title: str | None = None
    thesis_question: str | None = None
    thesis_contribution: str | None = None
    thesis_sections: List[str] | None = None
    scoring_clusters: List[Any] | None = None
    tracked_venues: List[str] | None = None
    avoid_topics: List[str] | None = None
    weekly_goal: int | None = None
    model_preference: str | None = None
    prompt_profile: str | None = None
    # Story 11.2 — bootstrap fields
    thesis_text: str | None = None
    domain_label: str | None = None
    facet_schema: dict | None = None


class BootstrapRequest(BaseModel):
    thesis_text: str


def _config_to_response(config: UserConfig) -> Dict[str, Any]:
    # Story 11.2 — facet_schema_json may be NULL on legacy rows
    facet_schema: dict | None = None
    if config.facet_schema_json:
        try:
            parsed = json.loads(config.facet_schema_json)
            if isinstance(parsed, dict):
                facet_schema = parsed
        except (json.JSONDecodeError, TypeError):
            facet_schema = None
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
        # Story 11.2 — bootstrap fields
        "thesis_text": config.thesis_text,
        "domain_label": config.domain_label,
        "facet_schema": facet_schema,
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
    # Story 11.2 — bootstrap fields. Changing thesis_text or facet_schema also
    # invalidates the bootstrap cache so the next preview is regenerated.
    bootstrap_dirty = False
    if "thesis_text" in updates:
        config.thesis_text = updates["thesis_text"]
        config.bootstrap_hash = None
        bootstrap_dirty = True
        dirty = True
    if "domain_label" in updates:
        config.domain_label = updates["domain_label"]
        dirty = True
    if "facet_schema" in updates:
        config.facet_schema_json = json.dumps(updates["facet_schema"])
        bootstrap_dirty = True
        dirty = True

    if dirty:
        config.prompt_cache_text = None
        config.prompt_cache_hash = None
        db.commit()
        logger.info("config_updated", user_id=user_id)
        if bootstrap_dirty:
            # Clear the in-memory bootstrap LLM cache so a subsequent preview
            # call regenerates against the new thesis / facet schema.
            try:
                config_bootstrap._cache_clear()
            except Exception:
                pass

    return UserConfigResponse(**_config_to_response(config))


# ── Template listing (Story 11.3) ──────────────────────────────────────────


@templates_router.get("/templates", response_model=List[Dict[str, Any]])
async def list_templates(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Return all global templates plus org-scoped templates for the user's org."""
    try:
        rows = db.query(ConfigTemplate).filter(
            ConfigTemplate.scope == "global"
        ).all()
    except Exception:
        return []
    return [
        {
            "id": t.id,
            "slug": t.slug,
            "name": t.name,
            "domain_label": t.domain_label,
            "scope": t.scope,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


@router.post("/from-template/{template_id}", response_model=UserConfigResponse)
async def apply_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Apply a starter-pack template body to the current user's config.

    Preserves existing ``thesis_text`` if non-empty (AC4). Merges
    ``scoring_clusters``, ``facet_schema``, ``domain_label`` from the
    template.
    """
    user_id = current_user["id"]
    config = _get_user_config(db, user_id)

    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    try:
        body = json.loads(template.body_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid template body_json")

    if "scoring_clusters" in body and isinstance(body["scoring_clusters"], list):
        config.scoring_clusters_json = json.dumps(body["scoring_clusters"])
    if "facet_schema" in body and isinstance(body["facet_schema"], dict):
        config.facet_schema_json = json.dumps(body["facet_schema"])
    if template.domain_label:
        config.domain_label = template.domain_label

    config.prompt_cache_text = None
    config.prompt_cache_hash = None

    db.commit()
    logger.info(
        "template_applied",
        user_id=user_id,
        template_id=template_id,
        slug=template.slug,
    )
    return UserConfigResponse(**_config_to_response(config))


# ── Bootstrap preview (Story 11.2) ─────────────────────────────────────────


@router.post("/bootstrap", response_model=config_bootstrap.BootstrapResult)
async def post_bootstrap(
    body: BootstrapRequest,
    response: Response,
    current_user: dict = Depends(require_session),
):
    """Generate a proposed config from a free-text thesis description.

    Preview-only — no persistence (FR-MT-53). Caller must follow up with a
    PUT /api/profile/config to persist the chosen fields.
    """
    user_id = current_user["id"]
    retry_after = _check_bootstrap_rate_limit(user_id)
    if retry_after is not None:
        # NFR-DA6 — surface a Retry-After so the client backs off cleanly.
        raise HTTPException(
            status_code=429,
            detail="Bootstrap rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    result = await config_bootstrap.generate(body.thesis_text)
    logger.info(
        "bootstrap_preview",
        user_id=user_id,
        degraded=result.degraded,
        clusters=len(result.scoring_clusters),
    )
    return result
