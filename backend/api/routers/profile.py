"""Profile router — per-user profile configuration (Story 4.5, FR-MT-22)."""
from typing import List

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_session
from database import UserConfig, get_db, get_valid_thesis_sections

router = APIRouter(prefix="/api/profile", tags=["profile"])
logger = structlog.get_logger().bind(service="profile")


class SectionRequest(BaseModel):
    section: str


@router.get("/sections", response_model=List[str])
async def list_sections(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Return the current user's thesis sections."""
    return sorted(get_valid_thesis_sections(db, current_user["id"]))


@router.post("/sections", response_model=List[str])
async def add_section(
    body: SectionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Add a thesis section for the current user."""
    user_id = current_user["id"]
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="User config not found")
    label = body.section.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Section label cannot be empty")
    import json
    sections = json.loads(config.thesis_sections_json or "[]")
    if label in sections:
        raise HTTPException(status_code=409, detail="Section already exists")
    sections.append(label)
    config.thesis_sections_json = json.dumps(sections)
    db.commit()
    logger.info("section_added", user_id=user_id, section=label)
    return sorted(sections)


@router.delete("/sections", response_model=List[str])
async def delete_section(
    body: SectionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    """Remove a thesis section for the current user."""
    user_id = current_user["id"]
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="User config not found")
    label = body.section.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Section label cannot be empty")
    import json
    sections = json.loads(config.thesis_sections_json or "[]")
    if label not in sections:
        raise HTTPException(status_code=404, detail="Section not found")
    sections.remove(label)
    config.thesis_sections_json = json.dumps(sections)
    db.commit()
    logger.info("section_deleted", user_id=user_id, section=label)
    return sorted(sections)
