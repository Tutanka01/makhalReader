from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from database import Article, Base, Feed
from models import InternalScoreFailure, InternalScoringClaimRequest, InternalScoreUpdate


def _memory_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.mark.asyncio
async def test_health_contract_stays_public_and_minimal():
    assert await main.health() == {"status": "ok"}


@pytest.mark.asyncio
async def test_internal_score_update_persists_and_broadcasts(monkeypatch):
    db = _memory_session()
    db.add(Feed(id=1, url="https://example.test/feed.xml", name="Feed", category="Infra"))
    db.add(
        Article(
            id=10,
            feed_id=1,
            title="Queued article",
            url="https://example.test/a",
            content_text="body",
            content_html="<p>body</p>",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    broadcasts = []

    async def fake_broadcast(payload):
        broadcasts.append(payload)

    monkeypatch.setattr(main, "_broadcast_new_article", fake_broadcast)

    result = await main.internal_score_article(
        10,
        InternalScoreUpdate(
            score=7.4,
            tags=["ops"],
            summary_bullets=["Useful detail"],
            reason="Concrete operational value.",
            score_details={"scoring_version": 3},
        ),
        x_internal_secret=main.API_SECRET,
        db=db,
    )

    article = db.query(Article).filter(Article.id == 10).one()
    assert result == {"status": "ok"}
    assert article.score == 7.4
    assert '"scoring_version": 3' in article.score_details_json
    assert broadcasts[0]["id"] == 10
    assert broadcasts[0]["score"] == 7.4
    assert broadcasts[0]["score_details"] == {"scoring_version": 3}
    assert article.scoring_status == "done"
    assert article.scored_at is not None


@pytest.mark.asyncio
async def test_internal_scoring_claim_marks_articles_processing():
    db = _memory_session()
    db.add(Feed(id=1, url="https://example.test/feed.xml", name="Feed", category="Infra"))
    db.add(
        Article(
            id=20,
            feed_id=1,
            title="Needs score",
            url="https://example.test/needs-score",
            content_text="body",
            created_at=datetime.now(timezone.utc),
            scoring_status="queued",
            score_attempts=0,
        )
    )
    db.commit()

    result = main.internal_claim_scoring_batch(
        InternalScoringClaimRequest(limit=1),
        x_internal_secret=main.API_SECRET,
        db=db,
    )

    article = db.query(Article).filter(Article.id == 20).one()
    assert result["items"][0]["article_id"] == 20
    assert result["items"][0]["attempts"] == 1
    assert article.scoring_status == "processing"
    assert article.score_attempts == 1
    assert article.score_locked_at is not None


@pytest.mark.asyncio
async def test_internal_score_failure_schedules_retry_then_failed():
    db = _memory_session()
    db.add(Feed(id=1, url="https://example.test/feed.xml", name="Feed", category="Infra"))
    db.add(
        Article(
            id=30,
            feed_id=1,
            title="Retry me",
            url="https://example.test/retry-me",
            content_text="body",
            created_at=datetime.now(timezone.utc),
            scoring_status="processing",
            score_attempts=1,
            score_locked_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    retry = main.internal_score_article_failed(
        30,
        InternalScoreFailure(error="LLM returned bad JSON"),
        x_internal_secret=main.API_SECRET,
        db=db,
    )

    article = db.query(Article).filter(Article.id == 30).one()
    assert retry["status"] == "retry"
    assert article.next_score_attempt_at is not None
    assert article.score_locked_at is None
    assert "bad JSON" in article.score_last_error

    article.score_attempts = main.SCORING_MAX_ATTEMPTS
    article.scoring_status = "processing"
    article.score_locked_at = datetime.now(timezone.utc)
    db.commit()

    failed = main.internal_score_article_failed(
        30,
        InternalScoreFailure(error="still bad"),
        x_internal_secret=main.API_SECRET,
        db=db,
    )

    assert failed["status"] == "failed"
    assert article.scoring_status == "failed"
    assert article.next_score_attempt_at is None


@pytest.mark.asyncio
async def test_internal_requeue_failed_resets_retry_state():
    db = _memory_session()
    db.add(Feed(id=1, url="https://example.test/feed.xml", name="Feed", category="Infra"))
    db.add(
        Article(
            id=40,
            feed_id=1,
            title="Failed article",
            url="https://example.test/failed",
            content_text="body",
            created_at=datetime.now(timezone.utc),
            scoring_status="failed",
            score_attempts=main.SCORING_MAX_ATTEMPTS,
            score_last_error="bad model",
        )
    )
    db.commit()

    result = main.internal_requeue_failed_scoring(
        limit=10,
        x_internal_secret=main.API_SECRET,
        db=db,
    )

    article = db.query(Article).filter(Article.id == 40).one()
    assert result == {"status": "ok", "requeued": 1}
    assert article.scoring_status == "queued"
    assert article.score_attempts == 0
    assert article.score_last_error is None
