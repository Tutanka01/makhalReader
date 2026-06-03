"""Tests for Story 6.4 — Tracked authors user_id (FR-MT-37).

These tests verify:
- Listing authors filters by user_id
- Deleting an author requires ownership
- Scanning authors uses the correct user scope
- User isolation: one user's authors never leak to another user

Requires the full Docker API environment and will be SKIPPED on the host:

    docker-compose exec api python -m pytest backend/scorer/tests/test_tracked_authors_user.py -v

This file must run in isolation from tests that import shared/database.py.
"""

from __future__ import annotations

import os
import sys as _sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test-password-for-unit-tests")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_tracked_authors_user.db")


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
        "backend/scorer/tests/test_tracked_authors_user.py -v"
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
    from database import Base, TrackedAuthor

    db_file = tmp_path / "test_tracked_authors_user.db"
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


def _make_author(session, user_id=1, ss_author_id="12345678", name="Test Author",
                  paper_count=5, avg_score=7.5, alert_count=1):
    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    from database import TrackedAuthor

    a = TrackedAuthor(
        ss_author_id=ss_author_id,
        name=name,
        paper_count=paper_count,
        avg_score=avg_score,
        alert_count=alert_count,
        last_checked=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        user_id=user_id,
    )
    session.add(a)
    session.flush()
    return a


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
class TestTrackedAuthorList:
    """GET /api/research/authors — list filtering by user_id."""

    def test_lists_only_own_authors(self, client):
        c, session = client
        _make_author(session, user_id=1, ss_author_id="u1_a", name="Mine")
        _make_author(session, user_id=2, ss_author_id="u2_a", name="Theirs")
        session.commit()

        resp = c.get("/api/research/authors")

        assert resp.status_code == 200
        data = resp.json()
        names = [a["name"] for a in data]
        assert "Mine" in names
        assert "Theirs" not in names

    def test_returns_empty_list_when_none(self, client):
        c, session = client
        _make_author(session, user_id=2, ss_author_id="u2_a", name="Not mine")
        session.commit()

        resp = c.get("/api/research/authors")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_includes_user_id_in_output(self, client):
        c, session = client
        _make_author(session, user_id=1, ss_author_id="u1_a", name="With user_id")
        session.commit()

        resp = c.get("/api/research/authors")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == 1

    def test_other_user_cannot_see_user1_authors(self, db_session):
        _make_author(db_session, user_id=1, ss_author_id="u1_a", name="User 1 author")
        db_session.commit()
        c2 = _client_for_user(db_session, user_id=2)

        resp = c2.get("/api/research/authors")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_authors_sorted_by_relevance(self, client):
        c, session = client
        _make_author(session, user_id=1, ss_author_id="low", name="Low Score", paper_count=1, avg_score=1.0)
        _make_author(session, user_id=1, ss_author_id="high", name="High Score", paper_count=10, avg_score=9.0)
        session.commit()

        resp = c.get("/api/research/authors")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "High Score"
        assert data[1]["name"] == "Low Score"

@SKIP_INTEGRATION
class TestTrackedAuthorDelete:
    """DELETE /api/research/authors/{ss_author_id} — delete requires ownership."""

    def test_own_author_deleted(self, client):
        c, session = client
        _make_author(session, user_id=1, ss_author_id="del_me", name="Mine")
        session.commit()

        resp = c.delete("/api/research/authors/del_me")

        assert resp.status_code == 204

        get_resp = c.get("/api/research/authors")
        assert get_resp.json() == []

    def test_other_users_author_returns_404(self, db_session):
        _make_author(db_session, user_id=2, ss_author_id="theirs", name="Theirs")
        db_session.commit()
        c1 = _client_for_user(db_session, user_id=1)

        resp = c1.delete("/api/research/authors/theirs")

        assert resp.status_code == 404

    def test_nonexistent_author_returns_404(self, client):
        c, _ = client
        resp = c.delete("/api/research/authors/nonexistent_id")
        assert resp.status_code == 404


@SKIP_INTEGRATION
class TestTrackedAuthorScan:
    """POST /api/research/authors/scan — scan uses correct user scope."""

    def test_scan_with_no_authors_returns_zero(self, client):
        c, session = client
        session.commit()

        resp = c.post("/api/research/authors/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["authors_checked"] == 0
        assert data["new_articles_queued"] == 0
        assert data["skipped"] == 0
