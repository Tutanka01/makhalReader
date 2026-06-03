import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException

from auth import require_session
from database import get_db

logger = structlog.get_logger().bind(service="poll")

router = APIRouter(prefix="/api/poll", tags=["poll"])

POLLER_BASE = "http://poller:8003"


@router.post("/trigger")
async def trigger_poll(current_user: dict = Depends(require_session)):
    """Trigger a per-user poll cycle for the calling user.

    Returns immediately (202 Accepted); the poller processes feeds and
    scores articles in the background. New scored articles arrive via SSE.
    """
    user_id = current_user["id"]
    logger.info("Triggering poll for user", user_id=user_id)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{POLLER_BASE}/trigger",
                json={"user_id": user_id},
                timeout=5,
            )
            if resp.status_code != 200:
                logger.error("Poller returned error", status=resp.status_code, body=resp.text)
                raise HTTPException(status_code=502, detail="Poller rejected trigger")
        except httpx.RequestError as e:
            logger.error("Failed to reach poller", error=str(e))
            raise HTTPException(status_code=502, detail="Poller unavailable")

    return {"status": "accepted", "user_id": user_id}
