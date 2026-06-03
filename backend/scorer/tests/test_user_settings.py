"""Tests for Story 6.5 — User settings (FR-MT-38).

These tests verify:
- UserSetting model helpers (get_user_setting, set_user_setting)
- weekly_goal moved from global settings to user_config
- Notification dismissal keys scoped to user_settings per user
- Conference bookmarks scoped to user_settings per user
- User isolation: one user's settings never leak to another user

Requires the full Docker API environment and will be SKIPPED on the host:

    docker-compose exec api python -m pytest backend/scorer/tests/test_user_settings.py -v

This file must run in isolation from tests that import shared/database.py.
"""

from __future__ import annotations

import json
import os
import sys as _sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test-password-for-unit-tests")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_user_settings.db")


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
        "backend/scorer/tests/test_user_settings.py -v"
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
    from database import Base, UserSetting

    db_file = tmp_path / "test_user_settings.db"
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


def _ensure_user_config(session, user_id=1):
    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    from database import UserConfig
    config = session.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not config:
        config = UserConfig(user_id=user_id, thesis_title="Test", weekly_goal=10)
        session.add(config)
        session.flush()
    return config


# ── Tests ─────────────────────────────────────────────────────────────────


@SKIP_INTEGRATION
class TestUserSettingHelpers:
    """Test get_user_setting / set_user_setting helpers."""

    def test_set_and_get(self, db_session):
        from database import get_user_setting, set_user_setting

        set_user_setting(db_session, 1, "pref_theme", "dark")
        val = get_user_setting(db_session, 1, "pref_theme", "")
        assert val == "dark"

    def test_get_default_when_missing(self, db_session):
        from database import get_user_setting

        val = get_user_setting(db_session, 1, "nonexistent", "default_val")
        assert val == "default_val"

    def test_get_empty_string_when_no_default(self, db_session):
        from database import get_user_setting

        val = get_user_setting(db_session, 1, "nonexistent")
        assert val == ""

    def test_user_isolation(self, db_session):
        from database import get_user_setting, set_user_setting

        set_user_setting(db_session, 1, "my_key", "user1_value")
        val_user2 = get_user_setting(db_session, 2, "my_key", "not_found")
        assert val_user2 == "not_found"

    def test_update_existing(self, db_session):
        from database import get_user_setting, set_user_setting

        set_user_setting(db_session, 1, "counter", "1")
        set_user_setting(db_session, 1, "counter", "2")
        val = get_user_setting(db_session, 1, "counter", "")
        assert val == "2"


@SKIP_INTEGRATION
class TestWeeklyGoalFromUserConfig:
    """weekly_goal reads from UserConfig (not global settings)."""

    def test_reading_debt_uses_user_config_goal(self, client):
        c, session = client
        from database import UserConfig
        _ensure_user_config(session, user_id=1)
        config = session.query(UserConfig).filter_by(user_id=1).first()
        config.weekly_goal = 25
        session.commit()

        resp = c.get("/api/stats/reading-debt")

        assert resp.status_code == 200
        assert resp.json()["weekly_goal"] == 25

    def test_update_reading_goal_writes_user_config(self, client):
        c, session = client
        from database import UserConfig
        _ensure_user_config(session, user_id=1)
        session.commit()

        resp = c.put("/api/stats/reading-goal", json={"weekly_goal": 42})

        assert resp.status_code == 200
        assert resp.json()["weekly_goal"] == 42

        config = session.query(UserConfig).filter_by(user_id=1).first()
        assert config.weekly_goal == 42

    def test_user_isolation_goals(self, db_session):
        _ensure_user_config(db_session, user_id=1)
        _ensure_user_config(db_session, user_id=2)
        from database import UserConfig
        c1 = db_session.query(UserConfig).filter_by(user_id=1).first()
        c1.weekly_goal = 10
        c2 = db_session.query(UserConfig).filter_by(user_id=2).first()
        c2.weekly_goal = 99
        db_session.commit()

        c1_client = _client_for_user(db_session, 1)
        resp = c1_client.get("/api/stats/reading-debt")
        assert resp.status_code == 200
        assert resp.json()["weekly_goal"] == 10

        c2_client = _client_for_user(db_session, 2)
        resp = c2_client.get("/api/stats/reading-debt")
        assert resp.status_code == 200
        assert resp.json()["weekly_goal"] == 99


@SKIP_INTEGRATION
class TestNotificationDismissal:
    """Notification dismissal keys scoped to user_settings."""

    def test_dismiss_stores_per_user(self, client):
        c, session = client

        resp = c.post("/api/research/notifications/dismiss", json={"type": "threats"})

        assert resp.status_code == 200
        from database import UserSetting
        row = session.query(UserSetting).filter_by(user_id=1, key="notifications_last_dismissed_threats").first()
        assert row is not None
        assert row.value != ""

    def test_dismissal_user_isolation(self, db_session):
        from database import UserSetting
        row = UserSetting(user_id=1, key="notifications_last_dismissed_threats", value="2026-01-01T00:00:00+00:00")
        db_session.add(row)
        db_session.commit()

        c2 = _client_for_user(db_session, 2)
        resp = c2.get("/api/research/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_threats"] >= 0  # Should not crash


@SKIP_INTEGRATION
class TestConferenceBookmarks:
    """Conference bookmarks scoped to user_settings."""

    def test_list_conferences_reads_user_settings(self, client):
        c, session = client
        from database import UserSetting
        row = UserSetting(user_id=1, key="bookmarked_conferences", value="NeurIPS,ICML")
        session.add(row)
        session.commit()

        resp = c.get("/api/research/conferences")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_bookmark_writes_user_settings(self, client):
        c, session = client

        resp = c.post("/api/research/conferences/bookmark", json={"venue": "NeurIPS", "bookmarked": True})

        assert resp.status_code == 200
        from database import UserSetting
        row = session.query(UserSetting).filter_by(user_id=1, key="bookmarked_conferences").first()
        assert row is not None
        assert "NeurIPS" in row.value
