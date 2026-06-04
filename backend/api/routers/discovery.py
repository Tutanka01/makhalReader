"""Discovery API router — EXPAND + RESOLVE endpoints (Story 13-3).

Exposes the source_discovery service functions behind authenticated endpoints
with per-user rate limiting (expand only — resolve is stateless data transform).

FR-MT-59–62: HTTP layer wrapping expand + resolve_verify_rank services.
"""

import os
import time
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from auth import require_session
from services import source_discovery

router = APIRouter(prefix="/api/discovery", tags=["discovery"])
_auth = Depends(require_session)
logger = structlog.get_logger().bind(service="discovery")

# ---------------------------------------------------------------------------
# Rate limiter — per-user, in-memory (identical pattern to profile router)
# ---------------------------------------------------------------------------

EXPAND_RATE_LIMIT = int(os.getenv("EXPAND_RATE_LIMIT", "10"))
EXPAND_RATE_WINDOW_SECONDS = int(os.getenv("EXPAND_RATE_WINDOW_SECONDS", "3600"))
_expand_calls: dict[int, list[float]] = {}


def _check_expand_rate_limit(user_id: int) -> Optional[int]:
    now = time.monotonic()
    window = EXPAND_RATE_WINDOW_SECONDS
    history = _expand_calls.setdefault(user_id, [])
    cutoff = now - window
    history[:] = [t for t in history if t > cutoff]
    if len(history) >= EXPAND_RATE_LIMIT:
        retry_after = int(window - (now - history[0])) + 1
        return max(retry_after, 1)
    history.append(now)
    return None


def _reset_expand_rate_limits() -> None:
    _expand_calls.clear()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ExpandRequest(BaseModel):
    thesis_text: str


class ResolveRequest(BaseModel):
    expand_result: dict


# ---------------------------------------------------------------------------
# POST /api/discovery/expand
# ---------------------------------------------------------------------------


@router.post("/expand", response_model=source_discovery.ExpandResult)
async def post_expand(
    body: ExpandRequest,
    response: Response,
    current_user: dict = Depends(require_session),
):
    user_id = current_user["id"]
    retry_after = _check_expand_rate_limit(user_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Expand rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    result = await source_discovery.expand(body.thesis_text)
    logger.info(
        "expand_endpoint",
        user_id=user_id,
        degraded=result.degraded,
        concepts=len(result.concepts),
    )
    return result


# ---------------------------------------------------------------------------
# POST /api/discovery/resolve
# ---------------------------------------------------------------------------


@router.post("/resolve", response_model=source_discovery.DiscoveryPack)
async def post_resolve(
    body: ResolveRequest,
    current_user: dict = Depends(require_session),
):
    user_id = current_user["id"]
    try:
        expand_result = source_discovery.ExpandResult.model_validate(body.expand_result)
        pack = await source_discovery.resolve_verify_rank(expand_result)
        logger.info(
            "resolve_endpoint",
            user_id=user_id,
            sources=len(pack.sources),
            venues=len(pack.venues),
            authors=len(pack.authors),
        )
        return pack
    except Exception as e:
        logger.warning("resolve_endpoint_failed", user_id=user_id, error=str(e))
        return source_discovery.DiscoveryPack()


# ---------------------------------------------------------------------------
# GET /api/discovery/existing
# ---------------------------------------------------------------------------


class ExistingResponse(BaseModel):
    source_canonical_ids: list[str] = []
    venue_names: list[str] = []
    author_openalex_ids: list[str] = []
    author_names: list[str] = []


@router.get("/existing")
async def get_existing(current_user: dict = Depends(require_session)):
    user_id = current_user["id"]
    from sqlalchemy import text
    from database import engine as _engine

    with _engine.connect() as conn:
        source_rows = conn.execute(
            text("SELECT s.canonical_id FROM sources s JOIN user_source_subscriptions uss ON s.id = uss.source_id WHERE uss.user_id = :uid"),
            {"uid": user_id},
        ).fetchall()
        venue_rows = conn.execute(
            text("SELECT venue_name FROM tracked_venues WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchall()
        author_rows = conn.execute(
            text("SELECT openalex_id, name FROM tracked_authors WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchall()

    return ExistingResponse(
        source_canonical_ids=[r[0] for r in source_rows if r[0]],
        venue_names=[r[0] for r in venue_rows],
        author_openalex_ids=[r[0] for r in author_rows if r[0]],
        author_names=[r[1] for r in author_rows],
    )


# ---------------------------------------------------------------------------
# POST /api/discovery/apply
# ---------------------------------------------------------------------------


class ApplyResponse(BaseModel):
    applied: bool = True
    counts: dict = {}


@router.post("/apply")
async def post_apply(
    body: source_discovery.ApplyRequest,
    current_user: dict = Depends(require_session),
):
    user_id = current_user["id"]
    try:
        counts = source_discovery.apply_discovery_pack(
            user_id=user_id,
            sources=body.sources,
            venues=body.venues,
            authors=body.authors,
        )
        logger.info("apply_endpoint", user_id=user_id, counts=counts)
        return ApplyResponse(applied=True, counts=counts)
    except Exception as e:
        logger.error("apply_endpoint_failed", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
