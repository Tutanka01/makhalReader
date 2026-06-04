import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_session
from sqlalchemy.orm import Session

from database import User, UserFeedSubscription, get_db

logger = structlog.get_logger().bind(service="poll")

router = APIRouter(prefix="/api/poll", tags=["poll"])

POLLER_BASE = "http://poller:8003"


class TriggerPollRequest(BaseModel):
    bootstrap: bool = False


@router.post("/trigger")
async def trigger_poll(
    body: TriggerPollRequest | None = None,
    current_user: dict = Depends(require_session),
    db: Session = Depends(get_db),
):
    """Trigger a per-user poll cycle for the calling user.

    Returns immediately (202 Accepted); the poller processes feeds and
    scores articles in the background. New scored articles arrive via SSE.
    """
    user_id = current_user["id"]
    logger.info("Triggering poll for user", user_id=user_id)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.onboarding_done:
        raise HTTPException(status_code=409, detail="Complete onboarding before polling")
    has_subscription = (
        db.query(UserFeedSubscription)
        .filter(UserFeedSubscription.user_id == user_id)
        .first()
        is not None
    )
    if not has_subscription:
        raise HTTPException(status_code=409, detail="Subscribe to at least one feed before polling")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{POLLER_BASE}/trigger",
                json={"user_id": user_id, "bootstrap": bool(body and body.bootstrap)},
                timeout=5,
            )
            if resp.status_code != 200:
                logger.error("Poller returned error", status=resp.status_code, body=resp.text)
                raise HTTPException(status_code=502, detail="Poller rejected trigger")
        except httpx.RequestError as e:
            logger.error("Failed to reach poller", error=str(e))
            raise HTTPException(status_code=502, detail="Poller unavailable")

    return {"status": "accepted", "user_id": user_id}


@router.get("/status")
async def poll_status(current_user: dict = Depends(require_session)):
    user_id = current_user["id"]
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{POLLER_BASE}/status/{user_id}", timeout=5)
            if resp.status_code != 200:
                logger.error("Poller status returned error", status=resp.status_code, body=resp.text)
                raise HTTPException(status_code=502, detail="Poller status unavailable")
            return resp.json()
        except httpx.RequestError as e:
            logger.error("Failed to reach poller status", error=str(e))
            raise HTTPException(status_code=502, detail="Poller unavailable")
