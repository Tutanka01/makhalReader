import json
import structlog
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_session
from database import User, UserConfig, get_db

logger = structlog.get_logger().bind(service="onboarding")
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


# ── Cluster templates (mirrors prototype) ─────────────────────────────────


TEMPLATES: List[Dict[str, Any]] = [
    {"id": "nlp-ai", "name": "NLP / AI", "clusters": [
        {"name": "LLM Reasoning & Agents", "reward_level": "critical", "weight": 4.0, "description": "Chain-of-thought, tool use, multi-agent orchestration, GraphRAG."},
        {"name": "Requirement Extraction w/ LLMs", "reward_level": "high", "weight": 3.5, "description": "NL\u2192formal requirements, elicitation, traceability."},
        {"name": "Benchmarks & Evaluation", "reward_level": "high", "weight": 2.5, "description": "New datasets, eval protocols, leaderboards."},
        {"name": "General DevOps / Infra", "reward_level": "noise", "weight": 0.5, "description": "K8s, CI/CD, incident retros \u2014 deprioritize."},
    ]},
    {"id": "software-eng", "name": "Software Eng.", "clusters": [
        {"name": "AI-MBSE & Model Transformation", "reward_level": "critical", "weight": 4.0, "description": "Arcadia/Capella, SysML, model-to-model."},
        {"name": "Systems-of-Systems Interop", "reward_level": "high", "weight": 3.0, "description": "SoS architecture, interoperability, emergence."},
        {"name": "Empirical SE Studies", "reward_level": "tangential", "weight": 1.5, "description": "Mining repos, developer surveys."},
    ]},
    {"id": "robotics", "name": "Robotics", "clusters": [
        {"name": "Embodied Policy Learning", "reward_level": "critical", "weight": 4.0, "description": "RL/IL for manipulation, sim-to-real."},
        {"name": "Perception & SLAM", "reward_level": "high", "weight": 3.0, "description": "Mapping, localization, sensor fusion."},
        {"name": "Safety & Verification", "reward_level": "high", "weight": 2.5, "description": "Formal guarantees for autonomous systems."},
    ]},
    {"id": "computer-vision", "name": "Computer Vision", "clusters": [
        {"name": "Generative Vision", "reward_level": "critical", "weight": 4.0, "description": "Diffusion, video gen, 3D synthesis."},
        {"name": "Open-Vocab Detection", "reward_level": "high", "weight": 3.0, "description": "VLMs, grounding, segmentation."},
        {"name": "Datasets & Benchmarks", "reward_level": "tangential", "weight": 1.5, "description": "New CV corpora."},
    ]},
    {"id": "general-cs", "name": "General CS", "clusters": [
        {"name": "Core Topic A", "reward_level": "high", "weight": 3.0, "description": "Your primary research area."},
        {"name": "Adjacent Methods", "reward_level": "tangential", "weight": 1.5, "description": "Cross-disciplinary techniques."},
        {"name": "Off-topic", "reward_level": "noise", "weight": 0.5, "description": "Deprioritize."},
    ]},
]


# ── Schemas ───────────────────────────────────────────────────────────────


class OnboardingStep1Request(BaseModel):
    thesis_title: str
    thesis_question: Optional[str] = None


class OnboardingStep2Request(BaseModel):
    template_id: str


# ── Helpers ───────────────────────────────────────────────────────────────


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


def _invalidate_prompt_cache(config: UserConfig) -> None:
    config.prompt_cache_text = None
    config.prompt_cache_hash = None


# ── Step 1: Thesis setup ──────────────────────────────────────────────────


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
    _invalidate_prompt_cache(config)
    config.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("onboarding_step1_saved", user_id=current_user["id"])
    return {"status": "ok"}


# ── Templates listing ─────────────────────────────────────────────────────


@router.get("/templates")
async def list_templates(_: dict = Depends(require_session)):
    return TEMPLATES


# ── Step 2: Cluster template selection ────────────────────────────────────


@router.post("/step2")
async def save_step2(
    body: OnboardingStep2Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    template = next((t for t in TEMPLATES if t["id"] == body.template_id), None)
    if not template:
        raise HTTPException(status_code=400, detail="Invalid template")

    config = _ensure_user_config(db, current_user["id"])
    config.scoring_clusters_json = json.dumps(template["clusters"])
    _invalidate_prompt_cache(config)
    config.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("onboarding_step2_saved", user_id=current_user["id"], template=body.template_id)
    return {"status": "ok"}


# ── Complete onboarding ────────────────────────────────────────────────────


@router.post("/complete")
async def complete_onboarding(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.onboarding_done = True
    db.commit()

    logger.info("onboarding_complete", user_id=current_user["id"])
    return {"status": "ok"}
