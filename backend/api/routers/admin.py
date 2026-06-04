import json
import structlog
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from pydantic import BaseModel

from auth import require_session
from database import Article, Feed, Organization, User, UserConfig, UserFeedSubscription, get_db
from routers.articles import _normalize_url

logger = structlog.get_logger().bind(service="admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])
_auth = Depends(require_session)


@router.delete("/articles/broken")
async def delete_broken_articles(db: Session = Depends(get_db), _: None = _auth):
    """
    Delete articles that have garbled content or no meaningful title.
    Call once after upgrading the extractor to clean up old bad data.
    """
    def _is_garbled(text: Optional[str]) -> bool:
        if not text or len(text) < 20:
            return False
        sample = text[:1000]
        bad = sum(1 for c in sample if c == "\ufffd" or (ord(c) < 32 and c not in "\t\n\r"))
        return (bad / len(sample)) > 0.04

    def _is_no_title(title: str) -> bool:
        t = (title or "").strip()
        return not t or t in ("[no-title]", "no-title", "Untitled", "") or len(t) < 3

    articles = db.query(Article).all()
    to_delete = []
    for a in articles:
        if _is_garbled(a.content_text) or _is_garbled(a.content_html):
            to_delete.append(a.id)
        elif _is_no_title(a.title) and not a.bookmarked:
            to_delete.append(a.id)

    if to_delete:
        db.query(Article).filter(Article.id.in_(to_delete)).delete(synchronize_session=False)
        db.commit()

    return {"deleted": len(to_delete)}


@router.post("/normalize-urls")
async def normalize_article_urls(db: Session = Depends(get_db), _: None = _auth):
    """
    One-time migration: normalize all article URLs already in the DB so they
    match the canonical form now used by the poller. Safe to call multiple
    times — idempotent. Merges duplicate normalized URLs by keeping the
    article with richer content and deleting the other.
    """
    articles = db.query(Article).all()
    updated = 0
    merged = 0
    skipped = 0

    for article in articles:
        canonical = _normalize_url(article.url)
        if canonical == article.url:
            continue

        conflict = db.query(Article).filter(
            Article.url == canonical,
            Article.id != article.id,
        ).first()

        if conflict:
            keep = conflict if len(conflict.content_text or "") >= len(article.content_text or "") else article
            drop = article if keep is conflict else conflict
            if drop.bookmarked:
                keep.bookmarked = True
            db.delete(drop)
            if keep.url != canonical:
                keep.url = canonical
            merged += 1
        else:
            article.url = canonical
            updated += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Migration failed: {e}")

    return {"updated": updated, "merged": merged, "skipped": skipped}


@router.post("/reindex")
async def reindex_chroma(db: Session = Depends(get_db), _: None = _auth):
    """Copy old 'articles' Chroma collection to 'articles_u1' (Story 7.4).

    One-time migration for existing deployments. Idempotent — safe to call
    multiple times. Returns how many vectors were migrated (0 if already done).
    Also called automatically at startup.
    """
    from embedder import _migrate_chroma_articles_to_per_user  # noqa: PLC0415
    count = _migrate_chroma_articles_to_per_user()
    if count > 0:
        logger.info("admin_reindex_complete", migrated=count)
    return {"status": "ok", "migrated": count}


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


class OrgCreateRequest(BaseModel):
    name: str


@router.post("/org")
async def create_org(
    body: OrgCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    _require_admin(current_user)
    if current_user.get("org_id"):
        raise HTTPException(status_code=409, detail="Already belongs to an organization")
    label = body.name.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Organization name cannot be empty")

    code = f"LAB-{secrets.token_hex(3).upper()}"
    org = Organization(name=label, code=code)
    db.add(org)
    db.flush()

    user = db.query(User).filter(User.id == current_user["id"]).first()
    user.org_id = org.id
    db.commit()
    logger.info("org_created", org_id=org.id, name=label, admin_id=current_user["id"])
    return {"id": org.id, "name": org.name, "invite_code": org.code}


@router.get("/org")
async def get_org(db: Session = Depends(get_db), current_user: dict = Depends(require_session)):
    _require_admin(current_user)
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="No organization — create one first")

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    members = (
        db.query(User, UserConfig.thesis_title)
        .outerjoin(UserConfig, User.id == UserConfig.user_id)
        .filter(User.org_id == org_id)
        .all()
    )
    member_list = [
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role,
            "onboarding_done": u.onboarding_done,
            "thesis_title": thesis or "",
        }
        for u, thesis in members
    ]

    catalog_rows = (
        db.query(
            Feed.id,
            Feed.name,
            Feed.category,
            func.count(UserFeedSubscription.user_id).label("subscriber_count"),
        )
        .outerjoin(UserFeedSubscription, Feed.id == UserFeedSubscription.feed_id)
        .filter(Feed.active == True)
        .group_by(Feed.id)
        .order_by(Feed.category, Feed.name)
        .all()
    )
    catalog = [
        {"id": row.id, "name": row.name, "category": row.category, "subscriber_count": row.subscriber_count, "provider": "rss"}
        for row in catalog_rows
    ]

    return {
        "id": org.id,
        "name": org.name,
        "invite_code": org.code,
        "members": member_list,
        "feed_catalog": catalog,
    }


@router.post("/org/invite-code")
async def regenerate_invite_code(db: Session = Depends(get_db), current_user: dict = Depends(require_session)):
    _require_admin(current_user)
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization")

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    new_code = f"LAB-{secrets.token_hex(3).upper()}"
    org.code = new_code
    db.commit()
    logger.info("invite_code_regenerated", org_id=org_id)
    return {"invite_code": new_code}


class UpdateMemberRoleRequest(BaseModel):
    role: str


@router.patch("/org/members/{user_id}")
async def update_member_role(
    user_id: int,
    body: UpdateMemberRoleRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    _require_admin(current_user)
    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'member'")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    org_id = current_user.get("org_id")
    target = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found in your organization")

    target.role = body.role
    db.commit()
    logger.info("member_role_updated", user_id=user_id, role=body.role, by=current_user["id"])
    return {"ok": True, "id": user_id, "role": body.role}


@router.delete("/org/members/{user_id}")
async def remove_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_session),
):
    _require_admin(current_user)
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    org_id = current_user.get("org_id")
    target = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found in your organization")

    target.org_id = None
    target.role = "member"
    db.commit()
    logger.info("member_removed", user_id=user_id, from_org=org_id, by=current_user["id"])
    return {"ok": True}
