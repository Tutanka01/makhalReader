from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from auth import (
    COOKIE_NAME,
    _check_rate_limit,
    _clear_failure,
    _client_ip,
    _record_failure,
    clear_session_cookie,
    create_session,
    delete_session,
    get_current_user,
    set_session_cookie,
)
from database import SessionLocal, User

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: Optional[str] = "admin@basira.local"
    password: str
    remember: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register")
async def register(body: RegisterRequest, request: Request, response: Response):
    db = SessionLocal()
    try:
        user = User.register(db, body.email, body.password, body.display_name)
        if not user:
            raise HTTPException(status_code=409, detail="Email already registered")
        token = create_session(
            user_id=user.id,
            remember=False,
            user_agent=request.headers.get("User-Agent"),
        )
        set_session_cookie(response, token, remember=False)
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        }
    finally:
        db.close()


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    ip = _client_ip(request)
    _check_rate_limit(ip)

    db = SessionLocal()
    try:
        user = User.authenticate(db, body.email, body.password)
        if not user:
            _record_failure(ip)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        _clear_failure(ip)
        token = create_session(
            user_id=user.id,
            remember=body.remember,
            user_agent=request.headers.get("User-Agent"),
        )
        set_session_cookie(response, token, body.remember)
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        }
    finally:
        db.close()


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(token)
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
