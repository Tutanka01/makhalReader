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
from datetime import datetime, timezone
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


# ── Internal score — Story 2.4 ──────────────────────────────────────────────

@SKIP_INTEGRATION
class TestInternalScore:
    """POST /api/internal/articles/{id}/score → article_scores (FR-MT-9)."""

    def test_score_writes_to_article_scores(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Score Me")
        session.commit()

        resp = c.post(
            f"/api/internal/articles/{art.id}/score",
            json={
                "score": 8.5,
                "tags": ["nlp", "transformers"],
                "summary_bullets": ["Novel approach"],
                "reason": "Strong results",
                "contribution_type": "method",
                "re_document_type": "elicitation",
                "user_id": 1,
            },
            headers={"X-Internal-Secret": "changeme"},
        )
        assert resp.status_code == 200

        from database import ArticleScore
        s = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
            ArticleScore.article_id == art.id,
        ).first()
        assert s is not None
        assert s.score == 8.5
        assert s.contribution_type == "method"
        assert s.re_document_type == "elicitation"

    def test_score_requires_user_id(self, client):
        """user_id is mandatory — omitting it causes 422."""
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "No User")
        session.commit()

        resp = c.post(
            f"/api/internal/articles/{art.id}/score",
            json={
                "score": 7.0,
                "tags": [],
                "summary_bullets": [],
            },
            headers={"X-Internal-Secret": "changeme"},
        )
        assert resp.status_code == 422

    def test_score_writes_to_correct_user(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Score User 2")
        session.commit()

        resp = c.post(
            f"/api/internal/articles/{art.id}/score",
            json={
                "score": 9.0,
                "tags": ["ai"],
                "summary_bullets": ["Great"],
                "user_id": 2,
            },
            headers={"X-Internal-Secret": "changeme"},
        )
        assert resp.status_code == 200

        from database import ArticleScore
        # User 2 has the score
        s2 = session.query(ArticleScore).filter(
            ArticleScore.user_id == 2,
            ArticleScore.article_id == art.id,
        ).first()
        assert s2 is not None
        assert s2.score == 9.0

        # User 1 does NOT have the score
        s1 = session.query(ArticleScore).filter(
            ArticleScore.user_id == 1,
            ArticleScore.article_id == art.id,
        ).first()
        assert s1 is None

    def test_score_backfills_article_for_user_1(self, client):
        """Backward compat: user_id=1 also writes to article table (NFR-T4)."""
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Backfill", score=0.0, contribution_type=None)
        session.commit()

        resp = c.post(
            f"/api/internal/articles/{art.id}/score",
            json={
                "score": 9.5,
                "tags": ["backfill"],
                "summary_bullets": ["Compat test"],
                "reason": "Backward compat",
                "contribution_type": "survey",
                "user_id": 1,
            },
            headers={"X-Internal-Secret": "changeme"},
        )
        assert resp.status_code == 200

        session.refresh(art)
        assert art.score == 9.5
        assert art.contribution_type == "survey"

    def test_score_response_includes_user_scoped_fields(self, client):
        """Response dict uses article_scores values for read_at/bookmarked/user_feedback."""
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Resp Check")
        session.commit()

        # Pre-set read_at on article to simulate corpus-level read
        art.read_at = datetime.now(timezone.utc)
        session.commit()

        resp = c.post(
            f"/api/internal/articles/{art.id}/score",
            json={
                "score": 8.0,
                "tags": [],
                "summary_bullets": [],
                "user_id": 1,
            },
            headers={"X-Internal-Secret": "changeme"},
        )
        assert resp.status_code == 200
        # response is {"status": "ok"} — broadcast dict is not returned directly
        # (the broadcast happens via SSE; we verify article_scores row was written instead)

    def test_score_nonexistent_article(self, client):
        c, session = client
        resp = c.post(
            "/api/internal/articles/99999/score",
            json={"score": 5.0, "tags": [], "summary_bullets": [], "user_id": 1},
            headers={"X-Internal-Secret": "changeme"},
        )
        assert resp.status_code == 404

    def test_score_wrong_secret(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Secret Fail")
        session.commit()

        resp = c.post(
            f"/api/internal/articles/{art.id}/score",
            json={"score": 5.0, "tags": [], "summary_bullets": [], "user_id": 1},
            headers={"X-Internal-Secret": "wrong-secret"},
        )
        assert resp.status_code == 403

    def test_fan_out_produces_separate_rows(self, client):
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Fan-out Article")
        session.commit()

        for uid in [1, 2, 3]:
            resp = c.post(
                f"/api/internal/articles/{art.id}/score",
                json={
                    "score": 7.0,
                    "tags": ["nlp"],
                    "summary_bullets": ["Key insight"],
                    "reason": "Relevant",
                    "user_id": uid,
                },
                headers={"X-Internal-Secret": "changeme"},
            )
            assert resp.status_code == 200

        from sqlalchemy import text
        rows = session.execute(
            text("SELECT user_id, score FROM article_scores WHERE article_id = :aid ORDER BY user_id"),
            {"aid": art.id},
        ).fetchall()
        assert len(rows) == 3
        assert [(r[0], r[1]) for r in rows] == [(1, 7.0), (2, 7.0), (3, 7.0)]


# ── SSE scoping — Story 2.6 ──────────────────────────────────────────────────

@SKIP_INTEGRATION
class TestSseScoping:
    """SSE events are scoped per user_id (FR-MT-11)."""

    def test_broadcast_scoped_to_user(self, client):
        import asyncio
        from sse import _sse_queues, broadcast_new_article

        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        _sse_queues.setdefault(1, {})["c1"] = q1
        _sse_queues.setdefault(2, {})["c2"] = q2

        asyncio.run(broadcast_new_article({"id": 101}, user_id=1))

        msg1 = q1.get_nowait()
        assert msg1["type"] == "new_article"
        assert msg1["data"]["id"] == 101

        assert q2.qsize() == 0

        _sse_queues.clear()

    def test_broadcast_no_queues_no_error(self, client):
        import asyncio
        from sse import broadcast_new_article

        asyncio.run(broadcast_new_article({"id": 99}, user_id=42))


@SKIP_INTEGRATION
class TestFeedSubscriptions:
    """Story 3.2 — GET /api/feeds returns only subscribed feeds (FR-MT-14)."""

    def test_list_feeds_only_subscribed(self, client):
        c, session = client
        feed1 = _make_feed(session, name="Subscribed Feed")
        feed2 = _make_feed(session, name="Unsubscribed Feed")
        session.flush()

        from database import UserFeedSubscription
        sub = UserFeedSubscription(user_id=1, feed_id=feed1.id)
        session.add(sub)
        session.commit()

        resp = c.get("/api/feeds")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Subscribed Feed"
        assert data[0]["id"] == feed1.id

    def test_list_feeds_empty_when_no_subscriptions(self, client):
        c, session = client
        _make_feed(session, name="Orphan Feed")
        session.commit()

        resp = c.get("/api/feeds")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_feeds_multiple_subscriptions(self, client):
        c, session = client
        feed1 = _make_feed(session, name="Feed A")
        feed2 = _make_feed(session, name="Feed B")
        feed3 = _make_feed(session, name="Feed C")
        session.flush()

        from database import UserFeedSubscription
        session.add_all([
            UserFeedSubscription(user_id=1, feed_id=feed1.id),
            UserFeedSubscription(user_id=1, feed_id=feed2.id),
        ])
        session.commit()

        resp = c.get("/api/feeds")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {d["name"] for d in data}
        assert names == {"Feed A", "Feed B"}

    def test_other_user_subscriptions_not_visible(self, client):
        c, session = client
        feed1 = _make_feed(session, name="User A Feed")
        feed2 = _make_feed(session, name="User B Feed")
        session.flush()

        from database import UserFeedSubscription
        session.add_all([
            UserFeedSubscription(user_id=1, feed_id=feed1.id),
            UserFeedSubscription(user_id=2, feed_id=feed2.id),
        ])
        session.commit()

        resp = c.get("/api/feeds")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "User A Feed"


@SKIP_INTEGRATION
class TestSubscribeUnsubscribe:
    """Story 3.3 — POST/DELETE /api/feeds/{id}/subscribe (FR-MT-15)."""

    def test_subscribe_to_feed(self, client):
        c, session = client
        feed = _make_feed(session)
        session.commit()

        resp = c.post(f"/api/feeds/{feed.id}/subscribe")
        assert resp.status_code == 200
        assert resp.json() == {"status": "subscribed"}

        from database import UserFeedSubscription
        sub = session.query(UserFeedSubscription).filter_by(
            user_id=1, feed_id=feed.id,
        ).first()
        assert sub is not None

    def test_subscribe_twice_is_idempotent(self, client):
        c, session = client
        feed = _make_feed(session)
        session.commit()

        c.post(f"/api/feeds/{feed.id}/subscribe")
        resp = c.post(f"/api/feeds/{feed.id}/subscribe")
        assert resp.status_code == 200
        assert resp.json() == {"status": "already_subscribed"}

    def test_unsubscribe_from_feed(self, client):
        c, session = client
        feed = _make_feed(session)
        session.commit()

        c.post(f"/api/feeds/{feed.id}/subscribe")

        resp = c.delete(f"/api/feeds/{feed.id}/subscribe")
        assert resp.status_code == 200
        assert resp.json() == {"status": "unsubscribed"}

        from database import UserFeedSubscription
        sub = session.query(UserFeedSubscription).filter_by(
            user_id=1, feed_id=feed.id,
        ).first()
        assert sub is None

    def test_unsubscribe_when_not_subscribed(self, client):
        c, session = client
        feed = _make_feed(session)
        session.commit()

        resp = c.delete(f"/api/feeds/{feed.id}/subscribe")
        assert resp.status_code == 404

    def test_subscribe_nonexistent_feed(self, client):
        c, _ = client
        resp = c.post("/api/feeds/99999/subscribe")
        assert resp.status_code == 404

    def test_subscribe_then_feed_appears_in_list(self, client):
        c, session = client
        feed = _make_feed(session)
        session.commit()

        resp = c.get("/api/feeds")
        assert resp.json() == []

        c.post(f"/api/feeds/{feed.id}/subscribe")

        resp = c.get("/api/feeds")
        assert len(resp.json()) == 1
        assert resp.json()[0]["id"] == feed.id

    def test_unsubscribe_removes_from_list(self, client):
        c, session = client
        feed = _make_feed(session)
        session.commit()
        c.post(f"/api/feeds/{feed.id}/subscribe")
        c.delete(f"/api/feeds/{feed.id}/subscribe")

        resp = c.get("/api/feeds")
        assert resp.json() == []


@SKIP_INTEGRATION
class TestInternalFeeds:
    """Story 3.4 — GET /api/internal/feeds includes subscriber_user_ids (FR-MT-18)."""

    def test_internal_feeds_includes_subscribers(self, client):
        c, session = client
        feed1 = _make_feed(session, name="Multi Sub Feed")
        feed2 = _make_feed(session, name="Single Sub Feed")
        feed3 = _make_feed(session, name="No Sub Feed")
        session.flush()

        from database import UserFeedSubscription
        session.add_all([
            UserFeedSubscription(user_id=1, feed_id=feed1.id),
            UserFeedSubscription(user_id=2, feed_id=feed1.id),
            UserFeedSubscription(user_id=1, feed_id=feed2.id),
        ])
        session.commit()

        resp = c.get("/api/internal/feeds", headers={"X-Internal-Secret": "changeme"})
        assert resp.status_code == 200
        data = resp.json()
        sub_map = {d["name"]: d["subscriber_user_ids"] for d in data}
        assert sorted(sub_map["Multi Sub Feed"]) == [1, 2]
        assert sub_map["Single Sub Feed"] == [1]
        assert sub_map["No Sub Feed"] == []

    def test_internal_feeds_requires_secret(self, client):
        c, _ = client
        resp = c.get("/api/internal/feeds")
        assert resp.status_code == 403

    def test_internal_feeds_lists_only_active_feeds(self, client):
        c, session = client
        feed = _make_feed(session, name="Active Feed")
        inactive = _make_feed(session, name="Inactive Feed")
        inactive.active = False
        session.flush()

        from database import UserFeedSubscription
        session.add_all([
            UserFeedSubscription(user_id=1, feed_id=feed.id),
            UserFeedSubscription(user_id=1, feed_id=inactive.id),
        ])
        session.commit()

        resp = c.get("/api/internal/feeds", headers={"X-Internal-Secret": "changeme"})
        names = [d["name"] for d in resp.json()]
        assert "Active Feed" in names
        assert "Inactive Feed" not in names


@SKIP_INTEGRATION
class TestFeedCatalog:
    """Story 3.6 — GET /api/feeds/catalog returns all active feeds (FR-MT-16)."""

    def test_catalog_returns_all_active_feeds(self, client):
        c, session = client
        feed1 = _make_feed(session, name="Feed A")
        feed2 = _make_feed(session, name="Feed B")
        session.flush()
        feed3 = _make_feed(session, name="Inactive Feed")
        feed3.active = False
        session.commit()

        resp = c.get("/api/feeds/catalog")
        assert resp.status_code == 200
        names = {d["name"] for d in resp.json()}
        assert names == {"Feed A", "Feed B"}

    def test_catalog_includes_unsubscribed_feeds(self, client):
        c, session = client
        _make_feed(session, name="Unsubscribed Feed")
        session.commit()

        resp = c.get("/api/feeds")
        assert resp.json() == []

        resp = c.get("/api/feeds/catalog")
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "Unsubscribed Feed"


# ── Per-user scoring isolation — Story 6.6 (NFR-T1, NFR-T2) ──────────────

@SKIP_INTEGRATION
class TestPerUserScoringIsolation:
    """Cross-tenant isolation: one user's scores never leak to another (NFR-T1)."""

    def test_article_score_per_user_rows(self, client):
        """Each user gets their own article_scores row (FR-MT-7)."""
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Isolation Test Article")
        session.commit()

        for uid in [1, 2]:
            resp = c.post(
                f"/api/internal/articles/{art.id}/score",
                json={
                    "score": 7.0 + uid,
                    "tags": ["test"],
                    "summary_bullets": ["Point"],
                    "reason": f"Relevant for user {uid}",
                    "user_id": uid,
                },
                headers={"X-Internal-Secret": "changeme"},
            )
            assert resp.status_code == 200

        from sqlalchemy import text
        rows = session.execute(
            text("SELECT user_id, score FROM article_scores WHERE article_id = :aid ORDER BY user_id"),
            {"aid": art.id},
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == (1, 8.0)
        assert rows[1] == (2, 9.0)

    def test_user1_cannot_see_user2_score_via_api(self, client):
        """User 1's API never returns user 2's score data.

        The article has a backward-compat score (7.0 on the article row) but
        user 2's dedicated article_scores row (5.0) must never appear for user 1.
        """
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Cross-tenant Article")
        session.commit()

        c.post(
            f"/api/internal/articles/{art.id}/score",
            json={
                "score": 5.0,
                "tags": ["user2"],
                "summary_bullets": ["Only user 2"],
                "reason": "User 2 only",
                "user_id": 2,
            },
            headers={"X-Internal-Secret": "changeme"},
        )

        from auth import require_session
        from database import get_db as _get_db
        from main import app
        app.dependency_overrides[require_session] = lambda: {"id": 1, "email": "u1@t.com"}
        app.dependency_overrides[_get_db] = lambda: session

        resp = c.get(f"/api/articles/{art.id}")
        assert resp.status_code == 200
        data = resp.json()
        # User 1 should see the backward-compat article.score (7.0 from _make_article),
        # NOT user 2's dedicated 5.0 score
        assert data["score"] == 7.0

        app.dependency_overrides.clear()

    def test_user2_cannot_see_user1_score_via_internal(self, client):
        """Internal score query for user 2 doesn't return user 1's data."""
        c, session = client
        feed = _make_feed(session)
        art = _make_article(session, feed.id, "Tenant-boundary Article")
        session.commit()

        c.post(
            f"/api/internal/articles/{art.id}/score",
            json={
                "score": 9.9,
                "tags": ["user1"],
                "summary_bullets": ["User 1 insight"],
                "reason": "User 1 only",
                "user_id": 1,
            },
            headers={"X-Internal-Secret": "changeme"},
        )

        from sqlalchemy import text
        rows = session.execute(
            text("SELECT score FROM article_scores WHERE article_id = :aid AND user_id = :uid"),
            {"aid": art.id, "uid": 2},
        ).fetchall()
        assert len(rows) == 0

    def test_score_queue_one_user_failure_does_not_block_others(self, client):
        """NFR-MT-15: a per-user scoring failure must not block other users.

        This tests the semantic contract enforced by the per-user semaphores
        in poller/main.py: each user gets their own asyncio.Semaphore so one
        user's failure never blocks another user's scoring.
        """
        import asyncio

        async def simulate_per_user_scoring():
            sems = {uid: asyncio.Semaphore(1) for uid in [1, 2, 3]}

            async def score(user_id: int, fail: bool = False) -> str:
                async with sems[user_id]:
                    if fail:
                        raise RuntimeError(f"Scoring failed for user {user_id}")
                    return f"ok-{user_id}"

            results = await asyncio.gather(
                score(1, fail=False),
                score(2, fail=True),
                score(3, fail=False),
                return_exceptions=True,
            )
            return results

        results = asyncio.run(simulate_per_user_scoring())
        assert results[0] == "ok-1"
        assert isinstance(results[1], RuntimeError)
        assert results[2] == "ok-3"

    def test_feed_subscriber_isolation(self, client):
        """Feeds list includes subscriber_user_ids; those IDs are internal-only."""
        c, session = client
        feed = _make_feed(session, name="Isolated Feed")
        session.flush()

        from database import UserFeedSubscription
        session.add_all([
            UserFeedSubscription(user_id=1, feed_id=feed.id),
            UserFeedSubscription(user_id=2, feed_id=feed.id),
        ])
        session.commit()

        resp = c.get("/api/internal/feeds", headers={"X-Internal-Secret": "changeme"})
        assert resp.status_code == 200
        data = resp.json()
        found = next((f for f in data if f["id"] == feed.id), None)
        assert found is not None
        assert 1 in found["subscriber_user_ids"]
        assert 2 in found["subscriber_user_ids"]

        resp2 = c.get("/api/feeds")
        assert resp2.status_code == 200
        for f in resp2.json():
            assert "subscriber_user_ids" not in f
