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
    require_session,
    set_session_cookie,
)
from database import Organization, SessionLocal, User

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    invite_code: Optional[str] = None


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
        org_id = None
        if body.invite_code:
            org = Organization.lookup_invite_code(db, body.invite_code)
            if not org:
                raise HTTPException(status_code=400, detail="Invalid invite code")
            org_id = org.id
        user = User.register(db, body.email, body.password, body.display_name, org_id=org_id)
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


class UpdateMeRequest(BaseModel):
    display_name: Optional[str] = None
    new_password: Optional[str] = None


@router.get("/me")
async def me(user: dict = Depends(require_session)):
    return user


@router.put("/me")
async def update_me(body: UpdateMeRequest, request: Request, user: dict = Depends(require_session)):
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user["id"]).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        if body.display_name is not None:
            if not body.display_name.strip():
                raise HTTPException(status_code=422, detail="display_name cannot be empty")
            db_user.display_name = body.display_name
        if body.new_password:
            import hashlib
            import bcrypt
            pwd_hash = bcrypt.hashpw(
                hashlib.sha256(body.new_password.encode()).digest(),
                bcrypt.gensalt(rounds=12),
            )
            db_user.password_hash = pwd_hash.decode()
        db.commit()
        db.refresh(db_user)
        return {
            "id": db_user.id,
            "email": db_user.email,
            "display_name": db_user.display_name,
            "role": db_user.role,
        }
    finally:
        db.close()
