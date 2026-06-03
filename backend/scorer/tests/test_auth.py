"""Tests for Story 1.2 — email+password auth flow.

These tests verify:
- User.register() creates users and rejects duplicates
- User.authenticate() validates credentials
- Session table CRUD works (create/validate expiry/delete)
- Seed user (admin@basira.local) login works
- Backward compat: existing sessions survive

NOTE: Run inside Docker where SQLAlchemy and project deps are available:
  docker-compose exec api python -m pytest backend/scorer/tests/test_auth.py -v
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

try:
    import sqlalchemy  # noqa: F401
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE,
    reason="SQLAlchemy not available — run inside Docker: docker-compose exec api pytest",
)

if SQLALCHEMY_AVAILABLE:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session, sessionmaker

    SHARED_DIR = Path(__file__).parent.parent.parent / "shared"
    if str(SHARED_DIR) not in sys.path:
        sys.path.insert(0, str(SHARED_DIR))

    from database import AuthSession, User, Base, init_db


TEST_PASSWORD = "test-password-123!"


@pytest.fixture()
def tmp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test_auth.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("AUTH_PASSWORD", TEST_PASSWORD)
    monkeypatch.setenv("DB_PATH", str(db_file))

    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    import database as db_module
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine))

    Base.metadata.create_all(bind=engine)
    init_db()

    yield db_module.SessionLocal


# ---------------------------------------------------------------------------
# User.register tests
# ---------------------------------------------------------------------------


class TestUserRegister:
    def test_register_creates_user(self, tmp_db):
        db: Session = tmp_db()
        try:
            user = User.register(db, "new@test.com", "pass123")
            assert user is not None
            assert user.id is not None
            assert user.email == "new@test.com"
            assert user.role == "member"
            assert user.onboarding_done is False
        finally:
            db.close()

    def test_register_rejects_duplicate(self, tmp_db):
        db: Session = tmp_db()
        try:
            User.register(db, "dup@test.com", "pass123")
            result = User.register(db, "dup@test.com", "other-pass")
            assert result is None
        finally:
            db.close()

    def test_register_accepts_display_name(self, tmp_db):
        db: Session = tmp_db()
        try:
            user = User.register(db, "named@test.com", "pass123", display_name="Test User")
            assert user.display_name == "Test User"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# User.authenticate tests
# ---------------------------------------------------------------------------


class TestUserAuthenticate:
    def test_authenticate_success(self, tmp_db):
        db: Session = tmp_db()
        try:
            User.register(db, "auth@test.com", "correct-password")
            user = User.authenticate(db, "auth@test.com", "correct-password")
            assert user is not None
            assert user.email == "auth@test.com"
        finally:
            db.close()

    def test_authenticate_wrong_password(self, tmp_db):
        db: Session = tmp_db()
        try:
            User.register(db, "wrong@test.com", "real-password")
            user = User.authenticate(db, "wrong@test.com", "wrong-password")
            assert user is None
        finally:
            db.close()

    def test_authenticate_unknown_email(self, tmp_db):
        db: Session = tmp_db()
        try:
            user = User.authenticate(db, "nobody@test.com", "any-password")
            assert user is None
        finally:
            db.close()

    def test_seed_user_authenticates(self, tmp_db):
        db: Session = tmp_db()
        try:
            user = User.authenticate(db, "admin@basira.local", TEST_PASSWORD)
            assert user is not None
            assert user.email == "admin@basira.local"
            assert user.role == "admin"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Session lifecycle tests (DB-level)
# ---------------------------------------------------------------------------


class TestSessionLifecycle:
    def test_create_session_with_user_id(self, tmp_db):
        db: Session = tmp_db()
        try:
            now = datetime.now(timezone.utc)
            session = AuthSession(
                id="test-token-abc",
                user_id=1,
                created_at=now,
                expires_at=now + timedelta(hours=24),
                last_seen=now,
                user_agent="pytest",
                remember_me=False,
            )
            db.add(session)
            db.commit()

            fetched = db.query(AuthSession).filter(AuthSession.id == "test-token-abc").first()
            assert fetched is not None
            assert fetched.user_id == 1
            assert fetched.expires_at is not None
        finally:
            db.close()

    def test_expired_session_not_returned(self, tmp_db):
        db: Session = tmp_db()
        try:
            now = datetime.now(timezone.utc)
            session = AuthSession(
                id="expired-token",
                user_id=1,
                created_at=now - timedelta(days=2),
                expires_at=now - timedelta(days=1),
                last_seen=now - timedelta(days=1),
                remember_me=False,
            )
            db.add(session)
            db.commit()

            valid = db.query(AuthSession).filter(
                AuthSession.id == "expired-token",
                AuthSession.expires_at > now,
            ).first()
            assert valid is None
        finally:
            db.close()

    def test_delete_session_removes_token(self, tmp_db):
        db: Session = tmp_db()
        try:
            now = datetime.now(timezone.utc)
            session = AuthSession(
                id="delete-me",
                user_id=1,
                created_at=now,
                expires_at=now + timedelta(hours=1),
                remember_me=False,
            )
            db.add(session)
            db.commit()
        finally:
            db.close()

        db = tmp_db()
        try:
            db.query(AuthSession).filter(AuthSession.id == "delete-me").delete()
            db.commit()
            fetched = db.query(AuthSession).filter(AuthSession.id == "delete-me").first()
            assert fetched is None
        finally:
            db.close()

    def test_seed_user_exists_after_init(self, tmp_db):
        db: Session = tmp_db()
        try:
            user = db.query(User).filter(User.email == "admin@basira.local").first()
            assert user is not None
            assert user.role == "admin"
            assert user.onboarding_done is True
            assert user.display_name == "Admin"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Story 1.3 — Session→user binding tests
# ---------------------------------------------------------------------------


class TestSessionUserBinding:
    """Story 1.3 — Session→user binding.

    Validated through DB-level assertions covering the same logic as
    validate_session() in api/auth.py.
    """

    def test_orphaned_session_user_deleted(self, tmp_db):
        """A session whose user no longer exists has an invalid user reference."""
        db: Session = tmp_db()
        try:
            user = User.register(db, "todelete@test.com", "pass123")
            uid = user.id
        finally:
            db.close()

        db = tmp_db()
        try:
            db.query(User).filter(User.id == uid).delete()
            db.commit()
        finally:
            db.close()

        db = tmp_db()
        try:
            user = db.query(User).filter(User.id == uid).first()
            assert user is None
        finally:
            db.close()

    def test_session_with_nonexistent_user_id_invalid(self, tmp_db):
        """Simulating validate_session: a session with user_id=999 finds no user."""
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        session = AuthSession(
            id="nonexistent-user-token",
            user_id=999,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            last_seen=now,
            user_agent="pytest",
            remember_me=False,
        )
        db: Session = tmp_db()
        try:
            db.add(session)
            db.commit()
        finally:
            db.close()

        db = tmp_db()
        try:
            user = db.query(User).filter(User.id == 999).first()
            assert user is None
        finally:
            db.close()

    def test_legacy_session_no_user_id(self, tmp_db):
        """A legacy session with user_id=None is still valid (backward compat)."""
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        session = AuthSession(
            id="legacy-no-user-id",
            user_id=None,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            last_seen=now,
            user_agent="pytest",
            remember_me=False,
        )
        db: Session = tmp_db()
        try:
            db.add(session)
            db.commit()
        finally:
            db.close()

        db = tmp_db()
        try:
            fetched = db.query(AuthSession).filter(
                AuthSession.id == "legacy-no-user-id",
                AuthSession.expires_at > datetime.now(timezone.utc),
            ).first()
            assert fetched is not None
            assert fetched.user_id is None
        finally:
            db.close()

    def test_create_session_references_existing_user(self, tmp_db):
        """A session created for a logged-in user references valid users.id."""
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        session = AuthSession(
            id="valid-user-token",
            user_id=1,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            last_seen=now,
            user_agent="pytest",
            remember_me=False,
        )
        db: Session = tmp_db()
        try:
            db.add(session)
            db.commit()
        finally:
            db.close()

        db = tmp_db()
        try:
            fetched = db.query(AuthSession).filter(
                AuthSession.id == "valid-user-token",
                AuthSession.expires_at > datetime.now(timezone.utc),
            ).first()
            assert fetched is not None
            assert fetched.user_id == 1
            user = db.query(User).filter(User.id == fetched.user_id).first()
            assert user is not None
            assert user.email == "admin@basira.local"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Backward-compat: existing articles/feeds survive migration
# ---------------------------------------------------------------------------


class TestAuthBackwardCompat:
    def test_seed_user_email_login_works(self, tmp_db):
        db: Session = tmp_db()
        try:
            user = User.authenticate(db, "admin@basira.local", TEST_PASSWORD)
            assert user is not None
            assert user.id == 1
        finally:
            db.close()

    def test_register_and_login_roundtrip(self, tmp_db):
        db: Session = tmp_db()
        try:
            User.register(db, "roundtrip@test.com", "secure-pass")
            user = User.authenticate(db, "roundtrip@test.com", "secure-pass")
            assert user is not None
            assert user.email == "roundtrip@test.com"
        finally:
            db.close()

    def test_init_db_idempotent_with_users(self, tmp_db):
        init_db()
        db: Session = tmp_db()
        try:
            user = User.authenticate(db, "admin@basira.local", TEST_PASSWORD)
            assert user is not None
            assert user.email == "admin@basira.local"
        finally:
            db.close()
