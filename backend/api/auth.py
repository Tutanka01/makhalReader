"""
Authentication module — session-based auth for Baṣīra.

Flow:
  POST /auth/register → creates user, sets cookie, returns user
  POST /auth/login    → validates email+password, sets cookie, returns user
  POST /auth/logout   → deletes session, clears cookie
  GET  /auth/me       → returns current user (protected)

All /api/* routes (except /api/health and /api/internal/*) require a valid
session cookie via the require_session dependency.
"""
from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, Response

from database import AuthSession, SessionLocal, User

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COOKIE_NAME = "basira_sid"
SESSION_TTL_SHORT = timedelta(hours=24)
SESSION_TTL_LONG = timedelta(days=365)

_HTTPS_ONLY = os.getenv("HTTPS_ONLY", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Brute-force protection — in-memory, per-IP
# ---------------------------------------------------------------------------

_LOCKOUT_THRESHOLD = 5
_LOCKOUT_SECONDS = 60

_fail_counts: dict[str, int] = defaultdict(int)
_lockout_until: dict[str, float] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str):
    now = time.monotonic()
    if _lockout_until.get(ip, 0) > now:
        remaining = int(_lockout_until[ip] - now)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {remaining}s.",
        )


def _record_failure(ip: str):
    _fail_counts[ip] += 1
    if _fail_counts[ip] >= _LOCKOUT_THRESHOLD:
        _lockout_until[ip] = time.monotonic() + _LOCKOUT_SECONDS
        _fail_counts[ip] = 0


def _clear_failure(ip: str):
    _fail_counts.pop(ip, None)
    _lockout_until.pop(ip, None)


# ---------------------------------------------------------------------------
# Core auth helpers
# ---------------------------------------------------------------------------


def create_session(user_id: int, remember: bool, user_agent: str | None) -> str:
    token = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    ttl = SESSION_TTL_LONG if remember else SESSION_TTL_SHORT
    db = SessionLocal()
    try:
        db.add(AuthSession(
            id=token,
            user_id=user_id,
            created_at=now,
            expires_at=now + ttl,
            last_seen=now,
            user_agent=(user_agent or "")[:500],
            remember_me=remember,
        ))
        db.commit()
    finally:
        db.close()
    return token


def validate_session(token: str) -> tuple[bool, int | None]:
    """Returns (is_valid, user_id). user_id may be None for legacy sessions.
    Orphaned sessions (user deleted) are cleaned up and treated as invalid."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        session = (
            db.query(AuthSession)
            .filter(AuthSession.id == token, AuthSession.expires_at > now)
            .first()
        )
        if not session:
            return False, None
        if session.user_id is not None:
            user = db.query(User).filter(User.id == session.user_id).first()
            if not user:
                db.delete(session)
                db.commit()
                return False, None
        session.last_seen = now
        db.commit()
        return True, session.user_id
    finally:
        db.close()


def delete_session(token: str):
    db = SessionLocal()
    try:
        db.query(AuthSession).filter(AuthSession.id == token).delete()
        db.commit()
    finally:
        db.close()


def purge_expired_sessions():
    db = SessionLocal()
    try:
        db.query(AuthSession).filter(
            AuthSession.expires_at <= datetime.now(timezone.utc)
        ).delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def require_session(basira_sid: Optional[str] = Cookie(None)):
    """FastAPI dependency. Raises 401 if the session cookie is missing/invalid."""
    if not basira_sid:
        raise HTTPException(status_code=401, detail="Authentication required")
    valid, _ = validate_session(basira_sid)
    if not valid:
        raise HTTPException(status_code=401, detail="Authentication required")


def get_current_user(
    basira_sid: Optional[str] = Cookie(None),
    _none: None = Depends(require_session),
) -> dict:
    """FastAPI dependency. Returns the current user dict or raises 401."""
    valid, user_id = validate_session(basira_sid)
    if not valid or not user_id:
        user_id = 1
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "org_id": user.org_id,
            "onboarding_done": user.onboarding_done,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def set_session_cookie(response: Response, token: str, remember: bool):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_HTTPS_ONLY,
        samesite="strict",
        max_age=int(SESSION_TTL_LONG.total_seconds()) if remember else None,
        path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/", samesite="strict")
