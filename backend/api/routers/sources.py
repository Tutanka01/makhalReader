import json
import os
import sys
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_session
from database import Source, UserSourceSubscription, get_db
from models import SourceOut

_extractor_dir = os.path.join(os.path.dirname(__file__), "..", "..", "extractor")
if _extractor_dir not in sys.path:
    sys.path.insert(0, _extractor_dir)

from providers import PROVIDER_REGISTRY  # noqa: E402
from providers.base import SourceIntent, SourceProvider  # noqa: E402

router = APIRouter()
_auth = Depends(require_session)


class ProviderResolveRequest(BaseModel):
    provider: str
    query: str = ""
    category: str = ""


class ProviderResolveResult(BaseModel):
    name: str
    provider: str
    query_json: Optional[str] = None
    label: Optional[str] = None
    category: str = ""
    provenance_url: Optional[str] = None


class SourceCreateRequest(BaseModel):
    name: str
    provider: str = "rss"
    query_json: Optional[str] = None
    label: Optional[str] = None
    category: str = "General"


@router.get("/api/sources", response_model=List[SourceOut])
async def list_sources(db: Session = Depends(get_db), current_user: dict = Depends(require_session)):
    rows = (
        db.query(Source, UserSourceSubscription.user_id.label("subscribed_user_id"))
        .outerjoin(
            UserSourceSubscription,
            (Source.id == UserSourceSubscription.source_id)
            & (UserSourceSubscription.user_id == current_user["id"]),
        )
        .filter(Source.active == True)
        .order_by(Source.name)
        .all()
    )
    result = []
    for src, sub_user_id in rows:
        out = SourceOut.model_validate(src)
        out.subscribed = sub_user_id is not None
        result.append(out)
    return result


@router.post("/api/sources", response_model=SourceOut)
async def create_source(body: SourceCreateRequest, db: Session = Depends(get_db), current_user: dict = Depends(require_session)):
    source = Source(
        name=body.name,
        provider=body.provider,
        query_json=body.query_json,
        label=body.label,
        category=body.category,
        active=True,
    )
    db.add(source)
    db.flush()
    existing_sub = (
        db.query(UserSourceSubscription)
        .filter_by(user_id=current_user["id"], source_id=source.id)
        .first()
    )
    if not existing_sub:
        db.add(UserSourceSubscription(user_id=current_user["id"], source_id=source.id))
    db.commit()
    db.refresh(source)
    return SourceOut.model_validate(source)


@router.delete("/api/sources/{source_id}")
async def delete_source(source_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_session)):
    sub = (
        db.query(UserSourceSubscription)
        .filter_by(user_id=current_user["id"], source_id=source_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Source not found or not subscribed")
    db.delete(sub)
    db.commit()
    return {"status": "ok"}


@router.post("/api/sources/resolve", response_model=List[ProviderResolveResult])
async def resolve_source(body: ProviderResolveRequest, current_user: dict = Depends(require_session)):
    if body.provider not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")
    provider_cls = PROVIDER_REGISTRY[body.provider]
    provider: SourceProvider = provider_cls()
    intent = SourceIntent(query=body.query, category=body.category)
    try:
        results = await provider.resolve(intent)
    except Exception:
        raise HTTPException(status_code=502, detail="Provider resolve failed")
    return [
        ProviderResolveResult(
            name=r.name,
            provider=r.provider,
            query_json=json.dumps(r.query_json) if r.query_json else None,
            label=r.label,
            category=r.category or body.category,
            provenance_url=r.provenance_url,
        )
        for r in results
    ]


@router.post("/api/sources/{source_id}/subscribe")
async def subscribe_source(source_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_session)):
    source = db.query(Source).filter(Source.id == source_id, Source.active == True).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    existing = (
        db.query(UserSourceSubscription)
        .filter_by(user_id=current_user["id"], source_id=source_id)
        .first()
    )
    if not existing:
        db.add(UserSourceSubscription(user_id=current_user["id"], source_id=source_id))
        db.commit()
    return {"status": "ok"}


@router.delete("/api/sources/{source_id}/subscribe")
async def unsubscribe_source(source_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_session)):
    sub = (
        db.query(UserSourceSubscription)
        .filter_by(user_id=current_user["id"], source_id=source_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Not subscribed to this source")
    db.delete(sub)
    db.commit()
    return {"status": "ok"}


@router.get("/api/sources/providers")
async def list_providers():
    return {pid: {"provider_id": pid} for pid in PROVIDER_REGISTRY}
