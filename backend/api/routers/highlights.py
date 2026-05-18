from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import require_session
from database import Article, Highlight, get_db
from models import HighlightCreate, HighlightOut, HighlightUpdate

router = APIRouter()
_auth = Depends(require_session)


@router.get("/api/articles/{article_id}/highlights", response_model=List[HighlightOut])
async def list_highlights(article_id: int, db: Session = Depends(get_db), _: None = _auth):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    highlights = (
        db.query(Highlight)
        .filter(Highlight.article_id == article_id)
        .order_by(Highlight.created_at)
        .all()
    )
    return [HighlightOut.model_validate(h) for h in highlights]


@router.post("/api/articles/{article_id}/highlights", response_model=HighlightOut, status_code=201)
async def create_highlight(
    article_id: int,
    body: HighlightCreate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    highlight = Highlight(
        article_id=article_id,
        selected_text=body.selected_text,
        prefix_context=body.prefix_context,
        suffix_context=body.suffix_context,
        color=body.color,
        note=body.note,
        created_at=datetime.now(timezone.utc),
    )
    db.add(highlight)
    db.commit()
    db.refresh(highlight)
    return HighlightOut.model_validate(highlight)


@router.put("/api/articles/{article_id}/highlights/{highlight_id}", response_model=HighlightOut)
async def update_highlight(
    article_id: int,
    highlight_id: int,
    body: HighlightUpdate,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    highlight = (
        db.query(Highlight)
        .filter(Highlight.id == highlight_id, Highlight.article_id == article_id)
        .first()
    )
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    if body.color is not None:
        highlight.color = body.color
    if body.note is not None:
        highlight.note = body.note
    db.commit()
    db.refresh(highlight)
    return HighlightOut.model_validate(highlight)


@router.delete("/api/articles/{article_id}/highlights/{highlight_id}")
async def delete_highlight(
    article_id: int,
    highlight_id: int,
    db: Session = Depends(get_db),
    _: None = _auth,
):
    highlight = (
        db.query(Highlight)
        .filter(Highlight.id == highlight_id, Highlight.article_id == article_id)
        .first()
    )
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    db.delete(highlight)
    db.commit()
    return {"status": "ok"}
