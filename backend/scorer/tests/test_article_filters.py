"""Tests for Story 2.3/2.4 — article filter params and engagement scoping.

These tests verify:
- contribution_type filter returns only articles with matching contribution_type
- re_document_type=arise returns only articles where re_document_type IN (elicitation, extraction, method)
- re_document_type=none returns articles with re_document_type='none'
- Filters compose correctly with existing filters (min_score, category, etc.)
- POST /read, /unread, /bookmark, /feedback write into article_scores (Story 2.3)
- POST /read-all creates article_scores rows for all unread articles
- User isolation: one user's engagement never affects another user
- DEFAULT_FEEDS contains cs.SE and cs.RO (verified by reading source, no import needed)

The TestContributionTypeFilter / TestREDocTypeFilter / TestFilterComposability /
TestArticleEngagement / TestArticleIsolation classes
require the full Docker API environment and will be SKIPPED on the host:

    docker-compose exec api python -m pytest backend/scorer/tests/test_article_filters.py -v

TestDefaultFeedsSources reads main.py as plain text and runs on the host without Docker.
"""

import os
import sys
import re as _re
from pathlib import Path

import pytest

# ── env vars required by auth module before any API imports ──────────────
os.environ.setdefault("AUTH_PASSWORD", "test-password-for-unit-tests")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_filters.db")

# ── dep check: all packages needed to run the API in-process ─────────────
def _check_api_deps() -> bool:
    try:
        import fastapi     # noqa: F401
        import sqlalchemy  # noqa: F401
        import bcrypt      # noqa: F401
        import structlog   # noqa: F401
        import feedparser  # noqa: F401
        import httpx       # noqa: F401
        return True
    except ImportError:
        return False

DEPS_AVAILABLE = _check_api_deps()

SKIP_INTEGRATION = pytest.mark.skipif(
    not DEPS_AVAILABLE,
    reason=(
        "Full API deps not available — run inside Docker: "
        "docker-compose exec api python -m pytest backend/scorer/tests/test_article_filters.py -v"
    ),
)

API_DIR = Path(__file__).parent.parent.parent / "api"


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session(tmp_path):
    if not DEPS_AVAILABLE:
        pytest.skip("API deps not available — run inside Docker")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    from database import Article, ArticleScore, Base, Feed  # noqa: F401 — side effect: registers models

    db_file = tmp_path / "test_filters.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    if not DEPS_AVAILABLE:
        pytest.skip("API deps not available — run inside Docker")
    from fastapi.testclient import TestClient

    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))

    from auth import require_session
    from database import get_db
    from main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_session] = lambda: {"id": 1, "email": "admin@basira.local"}

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, db_session

    app.dependency_overrides.clear()


def _make_feed(session, name="Test Feed", category="Papers"):
    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    from database import Feed
    feed = Feed(url=f"http://example.com/rss/{name}", name=name, category=category)
    session.add(feed)
    session.flush()
    return feed


def _make_article(session, feed_id, title="Test", contribution_type=None, re_document_type=None, score=7.0):
    from datetime import datetime, timezone
    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    from database import Article
    art = Article(
        feed_id=feed_id,
        title=title,
        url=f"http://example.com/{title.replace(' ', '-')}",
        score=score,
        contribution_type=contribution_type,
        re_document_type=re_document_type,
        tags_json="[]",
        summary_bullets_json="[]",
        images_json="[]",
        created_at=datetime.now(timezone.utc),
    )
    session.add(art)
    session.flush()
    return art


# ── contribution_type filter ───────────────────────────────────────────────

@SKIP_INTEGRATION
class TestContributionTypeFilter:
    def test_no_filter_returns_all(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Survey A", contribution_type="survey")
        _make_article(session, feed.id, "Method B", contribution_type="method")
        _make_article(session, feed.id, "No type C", contribution_type=None)
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_filter_by_survey(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Survey A", contribution_type="survey")
        _make_article(session, feed.id, "Method B", contribution_type="method")
        _make_article(session, feed.id, "No type C", contribution_type=None)
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0&contribution_type=survey")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Survey A"
        assert data[0]["contribution_type"] == "survey"

    def test_filter_by_method(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Method A", contribution_type="method")
        _make_article(session, feed.id, "Method B", contribution_type="method")
        _make_article(session, feed.id, "Survey C", contribution_type="survey")
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0&contribution_type=method")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(a["contribution_type"] == "method" for a in data)

    def test_filter_returns_empty_when_no_match(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Survey", contribution_type="survey")
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0&contribution_type=benchmark")
        assert resp.status_code == 200
        assert resp.json() == []


# ── re_document_type filter ────────────────────────────────────────────────

@SKIP_INTEGRATION
class TestREDocTypeFilter:
    def test_arise_returns_elicitation_extraction_method(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Elix A", re_document_type="elicitation")
        _make_article(session, feed.id, "Extr B", re_document_type="extraction")
        _make_article(session, feed.id, "Meth C", re_document_type="method")
        _make_article(session, feed.id, "None D", re_document_type="none")
        _make_article(session, feed.id, "Null E", re_document_type=None)
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0&re_document_type=arise")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        returned_types = {a["re_document_type"] for a in data}
        assert returned_types == {"elicitation", "extraction", "method"}

    def test_arise_excludes_none_type(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "None A", re_document_type="none")
        _make_article(session, feed.id, "Null B", re_document_type=None)
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0&re_document_type=arise")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_filter_by_specific_re_type(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Elix A", re_document_type="elicitation")
        _make_article(session, feed.id, "Extr B", re_document_type="extraction")
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0&re_document_type=elicitation")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Elix A"

    def test_filter_by_none_re_type(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "None A", re_document_type="none")
        _make_article(session, feed.id, "Elix B", re_document_type="elicitation")
        session.commit()

        resp = c.get("/api/articles?status=all&sort=score&limit=50&offset=0&re_document_type=none")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["re_document_type"] == "none"


# ── Composability ─────────────────────────────────────────────────────────

@SKIP_INTEGRATION
class TestFilterComposability:
    def test_contribution_type_composes_with_min_score(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Survey High", contribution_type="survey", score=9.0)
        _make_article(session, feed.id, "Survey Low", contribution_type="survey", score=3.0)
        _make_article(session, feed.id, "Method High", contribution_type="method", score=9.5)
        session.commit()

        resp = c.get(
            "/api/articles?status=all&sort=score&limit=50&offset=0"
            "&contribution_type=survey&min_score=8"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Survey High"

    def test_arise_composes_with_contribution_type(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Method+Elix",
                       contribution_type="method", re_document_type="elicitation")
        _make_article(session, feed.id, "Survey+Elix",
                       contribution_type="survey", re_document_type="elicitation")
        _make_article(session, feed.id, "Method+None",
                       contribution_type="method", re_document_type="none")
        session.commit()

        resp = c.get(
            "/api/articles?status=all&sort=score&limit=50&offset=0"
            "&contribution_type=method&re_document_type=arise"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Method+Elix"

    def test_arise_composes_with_category(self, client):
        c, session = client
        papers_feed = _make_feed(session, "Papers Feed", category="Papers")
        ai_feed = _make_feed(session, "AI Feed", category="AI")
        _make_article(session, papers_feed.id, "Papers+Elix", re_document_type="elicitation")
        _make_article(session, ai_feed.id, "AI+Elix", re_document_type="elicitation")
        session.commit()

        resp = c.get(
            "/api/articles?status=all&sort=score&limit=50&offset=0"
            "&re_document_type=arise&category=Papers"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Papers+Elix"


# ── DEFAULT_FEEDS source tests (no import needed — read file as text) ──────

class TestDefaultFeedsSources:
    """Verify new feed entries by reading main.py source — no import-time side effects.

    These tests run on the host without Docker or any extra dependencies.
    """

    MAIN_PY = Path(__file__).parent.parent.parent / "api" / "main.py"

    def _source(self):
        return self.MAIN_PY.read_text(encoding="utf-8")

    def test_cs_se_feed_present(self):
        assert "export.arxiv.org/rss/cs.SE" in self._source(), (
            "cs.SE (Software Engineering) feed URL missing from DEFAULT_FEEDS in main.py"
        )

    def test_cs_ro_feed_present(self):
        assert "export.arxiv.org/rss/cs.RO" in self._source(), (
            "cs.RO (Robotics/MBSE) feed URL missing from DEFAULT_FEEDS in main.py"
        )

    def test_cs_ai_appears_exactly_once(self):
        count = self._source().count("export.arxiv.org/rss/cs.AI")
        assert count == 1, f"cs.AI should appear exactly once, found {count}"

    def test_cs_se_is_in_papers_category(self):
        lines = [ln for ln in self._source().splitlines() if "rss/cs.SE" in ln]
        assert lines, "No line with cs.SE found in main.py"
        assert all("Papers" in ln for ln in lines), (
            f"cs.SE feed line missing 'Papers' category: {lines}"
        )

    def test_cs_ro_is_in_papers_category(self):
        lines = [ln for ln in self._source().splitlines() if "rss/cs.RO" in ln]
        assert lines, "No line with cs.RO found in main.py"
        assert all("Papers" in ln for ln in lines), (
            f"cs.RO feed line missing 'Papers' category: {lines}"
        )

    def test_no_duplicate_feed_urls_in_source(self):
        urls = _re.findall(r'"url":\s*"(https?://[^"]+)"', self._source())
        duplicates = [u for u in urls if urls.count(u) > 1]
        assert not duplicates, f"Duplicate feed URLs found in DEFAULT_FEEDS: {duplicates}"


# ── Article engagement — Story 2.3 ──────────────────────────────────────────

@SKIP_INTEGRATION
class TestArticleEngagement:
    """POST /read, /unread, /bookmark, /feedback, /read-all → article_scores."""

    def test_mark_read_creates_article_score(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Readable")
        session.commit()

        resp = c.post(f"/api/articles/{art.id}/read")
        assert resp.status_code == 200

        from database import ArticleScore
        score = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
            ArticleScore.article_id == art.id,
        ).first()
        assert score is not None
        assert score.read_at is not None

    def test_mark_read_twice_idempotent(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Read Twice")
        session.commit()

        resp1 = c.post(f"/api/articles/{art.id}/read")
        assert resp1.status_code == 200
        resp2 = c.post(f"/api/articles/{art.id}/read")
        assert resp2.status_code == 200

        from database import ArticleScore
        scores = session.query(ArticleScore).filter(
            ArticleScore.article_id == art.id,
        ).all()
        assert len(scores) == 1

    def test_mark_unread_after_read(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Unreadable")
        session.commit()

        c.post(f"/api/articles/{art.id}/read")
        c.post(f"/api/articles/{art.id}/unread")

        from database import ArticleScore
        score = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
            ArticleScore.article_id == art.id,
        ).first()
        assert score is not None
        assert score.read_at is None

    def test_toggle_bookmark_on(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Bookmark Me")
        session.commit()

        resp = c.post(f"/api/articles/{art.id}/bookmark")
        assert resp.status_code == 200
        assert resp.json()["bookmarked"] is True

        from database import ArticleScore
        score = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
            ArticleScore.article_id == art.id,
        ).first()
        assert score is not None
        assert score.bookmarked is True

    def test_toggle_bookmark_off(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Bookmark Toggle")
        session.commit()

        c.post(f"/api/articles/{art.id}/bookmark")
        resp = c.post(f"/api/articles/{art.id}/bookmark")
        assert resp.status_code == 200
        assert resp.json()["bookmarked"] is False

    def test_feedback_like(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Like Me")
        session.commit()

        resp = c.post(f"/api/articles/{art.id}/feedback", json={"value": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_feedback"] == 1

        from database import ArticleScore
        score = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
            ArticleScore.article_id == art.id,
        ).first()
        assert score is not None
        assert score.user_feedback == 1

    def test_feedback_dislike(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Dislike Me")
        session.commit()

        resp = c.post(f"/api/articles/{art.id}/feedback", json={"value": -1})
        assert resp.status_code == 200
        assert resp.json()["user_feedback"] == -1

    def test_feedback_remove(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Remove Feedback")
        session.commit()

        c.post(f"/api/articles/{art.id}/feedback", json={"value": 1})
        resp = c.post(f"/api/articles/{art.id}/feedback", json={"value": 0})
        assert resp.status_code == 200
        assert resp.json()["user_feedback"] is None

    def test_feedback_invalid_value(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Bad Feedback")
        session.commit()

        resp = c.post(f"/api/articles/{art.id}/feedback", json={"value": 42})
        assert resp.status_code == 422

    def test_mark_all_read_creates_scores(self, client):
        c, session = client
        feed = _make_feed(session)
        a1 = _make_article(session, feed.id, "Alpha", score=7.0)
        a2 = _make_article(session, feed.id, "Beta", score=8.0)
        session.commit()

        resp = c.post("/api/articles/read-all")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 2

        from database import ArticleScore
        scores = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
        ).all()
        assert len(scores) == 2
        assert all(s.read_at is not None for s in scores)

    def test_mark_all_read_with_category_filter(self, client):
        c, session = client
        papers_feed = _make_feed(session, "Papers Feed", category="Papers")
        ai_feed = _make_feed(session, "AI Feed", category="AI")
        _make_article(session, papers_feed.id, "Paper A", score=7.0)
        ai_art = _make_article(session, ai_feed.id, "AI A", score=8.0)
        session.commit()

        resp = c.post("/api/articles/read-all?category=Papers")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 1

        from database import ArticleScore
        ai_score = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
            ArticleScore.article_id == ai_art.id,
        ).first()
        assert ai_score is None, "AI article should not be marked read"

    def test_mark_all_read_with_min_score_filter(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "Low", score=3.0)
        high = _make_article(session, feed.id, "High", score=9.0)
        session.commit()

        resp = c.post("/api/articles/read-all?min_score=5")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 1

        from database import ArticleScore
        scores = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
        ).all()
        assert len(scores) == 1
        assert scores[0].article_id == high.id

    def test_mark_all_read_idempotent(self, client):
        c, session = client
        feed = _make_feed(session)
        _make_article(session, feed.id, "One")
        session.commit()

        c.post("/api/articles/read-all")
        resp = c.post("/api/articles/read-all")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 0

    def test_mark_read_nonexistent_article(self, client):
        c, _ = client
        resp = c.post("/api/articles/99999/read")
        assert resp.status_code == 404


@SKIP_INTEGRATION
class TestArticleIsolation:
    """User A's engagement must never leak to User B (NFR-T1, FR-MT-7)."""

    def _client_for_user(self, db_session, user_id: int):
        from fastapi.testclient import TestClient
        if str(API_DIR) not in sys.path:
            sys.path.insert(0, str(API_DIR))
        from auth import require_session
        from database import get_db
        from main import app
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[require_session] = lambda: {"id": user_id, "email": f"user{user_id}@test.local"}
        return TestClient(app, raise_server_exceptions=True)

    def test_user_a_read_keeps_user_b_unread(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Isolation Read")
        session.commit()

        c.post(f"/api/articles/{art.id}/read")

        c2 = self._client_for_user(session, 2)
        resp = c2.get("/api/articles?status=all&limit=50")
        data = resp.json()
        found = next(a for a in data if a["id"] == art.id)
        assert found["read_at"] is None, "User B should see article as unread"

    def test_user_a_bookmark_keeps_user_b_unbookmarked(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Isolation Bookmark")
        session.commit()

        c.post(f"/api/articles/{art.id}/bookmark")

        c2 = self._client_for_user(session, 2)
        resp = c2.get("/api/articles?status=all&limit=50")
        data = resp.json()
        found = next(a for a in data if a["id"] == art.id)
        assert found["bookmarked"] is False, "User B should see article as unbookmarked"

    def test_user_a_feedback_keeps_user_b_neutral(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Isolation Feedback")
        session.commit()

        c.post(f"/api/articles/{art.id}/feedback", json={"value": 1})

        c2 = self._client_for_user(session, 2)
        resp = c2.get(f"/api/articles/{art.id}")
        assert resp.status_code == 200
        found = resp.json()
        assert found["user_feedback"] is None, "User B should see no feedback"

    def test_user_a_mark_all_read_does_not_affect_user_b(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Isolation Read-All")
        session.commit()

        c.post("/api/articles/read-all")

        c2 = self._client_for_user(session, 2)
        resp = c2.get("/api/articles?status=unread&limit=50")
        data = resp.json()
        assert any(a["id"] == art.id for a in data), "User B should still see article as unread"
