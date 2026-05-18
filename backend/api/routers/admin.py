from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import require_session
from database import Article, get_db
from routers.articles import _normalize_url

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
