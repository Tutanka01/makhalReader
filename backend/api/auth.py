"""
Authentication module — session-based auth for MakhalReader.

Flow:
  POST /auth/login  → validates password, sets HttpOnly cookie, returns 200
  POST /auth/logout → deletes session from DB, clears cookie
  GET  /auth/status → returns {ok: true} if session valid, 401 otherwise

All /api/* routes (except /api/health and /api/internal/*) require a valid
session cookie. Internal routes keep their X-Internal-Secret header auth.
"""
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Cookie, HTTPException, Request, Response

from database import AuthSession, SessionLocal

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Password is read from env and hashed once at import time.
_RAW_PASSWORD = os.getenv("AUTH_PASSWORD", "")
if not _RAW_PASSWORD:
    raise RuntimeError(
        "AUTH_PASSWORD env var is required. "
        "Set it in your .env file before starting the API."
    )

# bcrypt has a 72-byte hard limit — hash a SHA-256 digest of the password
# first so any password length is safely supported.
import hashlib as _hashlib
_PASSWORD_HASH: bytes = bcrypt.hashpw(
    _hashlib.sha256(_RAW_PASSWORD.encode()).digest(),
    bcrypt.gensalt(rounds=12),
)

COOKIE_NAME = "makhal_sid"
SESSION_TTL_SHORT = timedelta(hours=24)
SESSION_TTL_LONG = timedelta(days=365)

# Set HTTPS_ONLY=false in .env for local HTTP development.
# In production (behind Caddy with TLS), keep it true (default).
_HTTPS_ONLY = os.getenv("HTTPS_ONLY", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Brute-force protection — in-memory, per-IP
# ---------------------------------------------------------------------------

_LOCKOUT_THRESHOLD = 5       # failed attempts before lockout
_LOCKOUT_SECONDS = 60        # lockout duration

_fail_counts: dict[str, int] = defaultdict(int)
_lockout_until: dict[str, float] = {}


def _client_ip(request: Request) -> str:
    """Best-effort client IP (respects X-Forwarded-For from Caddy)."""
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

def verify_password(plain: str) -> bool:
    import hashlib
    digest = hashlib.sha256(plain.encode()).digest()
    return bcrypt.checkpw(digest, _PASSWORD_HASH)


def create_session(remember: bool, user_agent: Optional[str]) -> str:
    token = secrets.token_hex(32)  # 256-bit entropy
    now = datetime.now(timezone.utc)
    ttl = SESSION_TTL_LONG if remember else SESSION_TTL_SHORT
    db = SessionLocal()
    try:
        db.add(AuthSession(
            id=token,
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


def validate_session(token: str) -> bool:
    """Returns True and refreshes last_seen if the session is valid."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        session = (
            db.query(AuthSession)
            .filter(AuthSession.id == token, AuthSession.expires_at > now)
            .first()
        )
        if not session:
            return False
        session.last_seen = now
        db.commit()
        return True
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
    """Called periodically to keep the sessions table lean."""
    db = SessionLocal()
    try:
        db.query(AuthSession).filter(
            AuthSession.expires_at <= datetime.now(timezone.utc)
        ).delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FastAPI dependency — use on every protected route
# ---------------------------------------------------------------------------

def require_session(makhal_sid: Optional[str] = Cookie(None)):
    """FastAPI dependency. Raises 401 if the session cookie is missing/invalid."""
    if not makhal_sid or not validate_session(makhal_sid):
        raise HTTPException(status_code=401, detail="Authentication required")


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def set_session_cookie(response: Response, token: str, remember: bool):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,              # not accessible from JS
        secure=_HTTPS_ONLY,         # HTTPS only in prod; HTTP ok locally
        samesite="strict",          # CSRF protection
        max_age=int(SESSION_TTL_LONG.total_seconds()) if remember else None,
        path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/", samesite="strict")
