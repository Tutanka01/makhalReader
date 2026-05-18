"""Database migration tests for Story 2.1 new columns.

These tests verify:
- The three new nullable columns exist after init_db() runs
- init_db() is idempotent (safe to run twice)
- Articles created before Story 2.1 (without new fields) survive migration

NOTE: Run inside Docker where SQLAlchemy and project deps are available:
  docker-compose exec api python -m pytest backend/scorer/tests/test_database_migrations.py -v

These tests import from backend/shared/database.py which requires SQLAlchemy.
They will be SKIPPED automatically on the host if SQLAlchemy is not installed.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Try importing SQLAlchemy — skip all tests if unavailable (host environment)
try:
    import sqlalchemy
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE,
    reason="SQLAlchemy not available — run inside Docker: docker-compose exec api pytest",
)

if SQLALCHEMY_AVAILABLE:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker

    SHARED_DIR = Path(__file__).parent.parent.parent.parent / "shared"
    if str(SHARED_DIR) not in sys.path:
        sys.path.insert(0, str(SHARED_DIR))

    from database import Article, Base, Feed, SessionLocal, init_db


@pytest.fixture()
def tmp_db(monkeypatch, tmp_path):
    """Provide a fresh SQLite database in a temp directory for each test."""
    db_file = tmp_path / "test.db"
    db_url = f"sqlite:///{db_file}"

    from sqlalchemy.orm import sessionmaker
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    # Patch module-level engine and SessionLocal
    import database as db_module
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine))

    # Also patch the WAL pragma listener (not critical for tests)
    yield engine, db_module

    engine.dispose()


class TestNewColumnsExistAfterMigration:
    def test_score_meta_json_column_exists(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("articles")}
        assert "score_meta_json" in columns

    def test_contribution_type_column_exists(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("articles")}
        assert "contribution_type" in columns

    def test_re_document_type_column_exists(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("articles")}
        assert "re_document_type" in columns


class TestMigrationIdempotency:
    def test_init_db_twice_no_error(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        db_module.init_db()  # must not raise

    def test_all_columns_present_after_double_init(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        db_module.init_db()
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("articles")}
        assert {"score_meta_json", "contribution_type", "re_document_type"}.issubset(columns)


class TestNullableColumnsRoundtrip:
    def _make_feed(self, session, db_module):
        feed = db_module.Feed(url="https://example.com/feed", name="Test Feed", category="General")
        session.add(feed)
        session.commit()
        session.refresh(feed)
        return feed

    def test_article_without_new_fields_has_none_values(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        session = Session()

        feed = self._make_feed(session, db_module)
        from datetime import datetime
        article = db_module.Article(
            feed_id=feed.id,
            title="Test Article",
            url="https://example.com/1",
            created_at=datetime.utcnow(),
        )
        session.add(article)
        session.commit()
        session.refresh(article)

        assert article.score_meta_json is None
        assert article.contribution_type is None
        assert article.re_document_type is None
        session.close()

    def test_article_with_new_fields_survives_roundtrip(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        session = Session()

        feed = self._make_feed(session, db_module)
        from datetime import datetime
        import json
        score_meta = {"novelty": 0.8, "rigor": 0.9}
        article = db_module.Article(
            feed_id=feed.id,
            title="Research Paper",
            url="https://arxiv.org/abs/1234.5678",
            created_at=datetime.utcnow(),
            contribution_type="method",
            re_document_type="elicitation",
            score_meta_json=json.dumps(score_meta),
        )
        session.add(article)
        session.commit()

        fetched = session.query(db_module.Article).filter_by(url="https://arxiv.org/abs/1234.5678").first()
        assert fetched.contribution_type == "method"
        assert fetched.re_document_type == "elicitation"
        assert json.loads(fetched.score_meta_json) == score_meta
        session.close()
