import structlog
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_session
from database import UserConfig, get_db

logger = structlog.get_logger().bind(service="onboarding")
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingStep1Request(BaseModel):
    thesis_title: str
    thesis_question: Optional[str] = None


def _ensure_user_config(db: Session, user_id: int) -> UserConfig:
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        config = UserConfig(
            user_id=user_id,
            thesis_title="",
            thesis_question=None,
            thesis_contribution=None,
            thesis_sections_json="[]",
            scoring_clusters_json="[]",
            tracked_venues_json="[]",
            avoid_topics_json="[]",
            weekly_goal=10,
            model_preference="google/gemini-flash-1.5",
            prompt_profile="unified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(config)
        db.flush()
    return config


@router.post("/step1")
async def save_step1(
    body: OnboardingStep1Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    title = body.thesis_title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Thesis title is required")

    config = _ensure_user_config(db, current_user["id"])
    config.thesis_title = title
    config.thesis_question = body.thesis_question.strip() if body.thesis_question else None
    config.prompt_cache_text = None
    config.prompt_cache_hash = None
    config.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("onboarding_step1_saved", user_id=current_user["id"])
    return {"status": "ok"}
