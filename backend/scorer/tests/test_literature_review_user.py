"""Tests for Story 6.2 — Literature reviews user_id (FR-MT-35).

These tests verify:
- Listing reviews filters by user_id
- Getting a review requires ownership
- Deleting a review requires ownership
- Exporting a review requires ownership
- User isolation: one user's reviews never leak to another user

Requires the full Docker API environment and will be SKIPPED on the host:

    docker-compose exec api python -m pytest backend/scorer/tests/test_literature_review_user.py -v

This file must run in isolation from tests that import shared/database.py
(see test_threat_scan.py for the sys.modules trick pattern).
"""

from __future__ import annotations

import json
import os
import sys
import sys as _sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test-password-for-unit-tests")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_lit_review_user.db")


def _check_api_deps() -> bool:
    try:
        import fastapi
        import sqlalchemy
        import bcrypt
        import structlog
        import feedparser
        import httpx
        return True
    except ImportError:
        return False


DEPS_AVAILABLE = _check_api_deps()

SKIP_INTEGRATION = pytest.mark.skipif(
    not DEPS_AVAILABLE,
    reason=(
        "Full API deps not available — run inside Docker: "
        "docker-compose exec api python -m pytest "
        "backend/scorer/tests/test_literature_review_user.py -v"
    ),
)

API_DIR = Path(__file__).parent.parent.parent / "api"
USER_1 = {"id": 1, "email": "admin@basira.local"}
USER_2 = {"id": 2, "email": "other@basira.local"}


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path):
    if not DEPS_AVAILABLE:
        pytest.skip("API deps not available — run inside Docker")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    if "database" not in _sys.modules:
        _sys.modules["database"] = __import__("database")
    from database import Base, LiteratureReview

    db_file = tmp_path / "test_lit_review_user.db"
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

    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))

    from auth import require_session
    from database import get_db
    from main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_session] = lambda: USER_1

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, db_session

    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_review(session, user_id=1, topic="Test Review", window_days=30, min_rigor=0.0):
    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    from database import LiteratureReview

    body = [
        {
            "cluster_label": "Cluster A",
            "synthesis": "Synthesis text",
            "comparison_table": [],
            "gaps": [],
            "top_cite": "",
            "article_ids": [],
            "article_titles": [],
        }
    ]
    r = LiteratureReview(
        user_id=user_id,
        topic=topic,
        window_days=window_days,
        min_rigor=min_rigor,
        body_json=json.dumps(body),
        created_at=datetime.now(timezone.utc),
    )
    session.add(r)
    session.flush()
    return r


def _client_for_user(db_session, user_id: int):
    from fastapi.testclient import TestClient
    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    from auth import require_session
    from database import get_db
    from main import app
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_session] = lambda: {"id": user_id, "email": f"user{user_id}@basira.local"}
    return TestClient(app, raise_server_exceptions=True)


# ── Tests ─────────────────────────────────────────────────────────────────


@SKIP_INTEGRATION
class TestLiteratureReviewList:
    """GET /api/research/reviews — list filtering by user_id."""

    def test_lists_only_own_reviews(self, client):
        c, session = client
        _make_review(session, user_id=1, topic="Mine")
        _make_review(session, user_id=2, topic="Theirs")
        session.commit()

        resp = c.get("/api/research/reviews")

        assert resp.status_code == 200
        data = resp.json()
        topics = [r["topic"] for r in data]
        assert "Mine" in topics
        assert "Theirs" not in topics

    def test_returns_empty_list_when_none(self, client):
        c, session = client
        _make_review(session, user_id=2, topic="Not mine")
        session.commit()

        resp = c.get("/api/research/reviews")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_includes_user_id_in_summary(self, client):
        c, session = client
        _make_review(session, user_id=1, topic="With user_id")
        session.commit()

        resp = c.get("/api/research/reviews")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == 1

    def test_other_user_cannot_see_user1_reviews(self, db_session):
        _make_review(db_session, user_id=1, topic="User 1 review")
        db_session.commit()
        c2 = _client_for_user(db_session, user_id=2)

        resp = c2.get("/api/research/reviews")

        assert resp.status_code == 200
        assert resp.json() == []


@SKIP_INTEGRATION
class TestLiteratureReviewGet:
    """GET /api/research/reviews/{id} — get requires ownership."""

    def test_own_review_succeeds(self, client):
        c, session = client
        r = _make_review(session, user_id=1, topic="Mine")
        session.commit()

        resp = c.get(f"/api/research/reviews/{r.id}")

        assert resp.status_code == 200
        assert resp.json()["topic"] == "Mine"
        assert resp.json()["user_id"] == 1

    def test_other_users_review_returns_404(self, db_session):
        r = _make_review(db_session, user_id=2, topic="Theirs")
        db_session.commit()
        c1 = _client_for_user(db_session, user_id=1)

        resp = c1.get(f"/api/research/reviews/{r.id}")

        assert resp.status_code == 404

    def test_nonexistent_review_returns_404(self, client):
        c, _ = client
        resp = c.get("/api/research/reviews/99999")
        assert resp.status_code == 404


@SKIP_INTEGRATION
class TestLiteratureReviewDelete:
    """DELETE /api/research/reviews/{id} — delete requires ownership."""

    def test_own_review_deleted(self, client):
        c, session = client
        r = _make_review(session, user_id=1, topic="Mine")
        session.commit()

        resp = c.delete(f"/api/research/reviews/{r.id}")

        assert resp.status_code == 204
        get_resp = c.get(f"/api/research/reviews/{r.id}")
        assert get_resp.status_code == 404

    def test_other_users_review_returns_404(self, db_session):
        r = _make_review(db_session, user_id=2, topic="Theirs")
        db_session.commit()
        c1 = _client_for_user(db_session, user_id=1)

        resp = c1.delete(f"/api/research/reviews/{r.id}")

        assert resp.status_code == 404

    def test_nonexistent_review_returns_404(self, client):
        c, _ = client
        resp = c.delete("/api/research/reviews/99999")
        assert resp.status_code == 404


@SKIP_INTEGRATION
class TestLiteratureReviewExport:
    """GET /api/research/reviews/{id}/export — export requires ownership."""

    def test_own_review_exports(self, client):
        c, session = client
        r = _make_review(session, user_id=1, topic="Mine")
        session.commit()

        resp = c.get(f"/api/research/reviews/{r.id}/export?format=md")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")

    def test_other_users_review_export_returns_404(self, db_session):
        r = _make_review(db_session, user_id=2, topic="Theirs")
        db_session.commit()
        c1 = _client_for_user(db_session, user_id=1)

        resp = c1.get(f"/api/research/reviews/{r.id}/export?format=md")

        assert resp.status_code == 404

    def test_nonexistent_review_export_returns_404(self, client):
        c, _ = client
        resp = c.get("/api/research/reviews/99999/export?format=md")
        assert resp.status_code == 404
