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

    SHARED_DIR = Path(__file__).parent.parent.parent / "shared"
    if str(SHARED_DIR) not in sys.path:
        sys.path.insert(0, str(SHARED_DIR))

    from database import Article, ArticleScore, Base, Feed, Organization, SessionLocal, User, init_db


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


class TestMultiTenantTables:
    """Story 1.1 — organizations & users tables + seed user."""

    def test_organizations_table_exists(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "organizations" in tables

    def test_users_table_exists(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "users" in tables

    def test_users_columns(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("users")}
        assert {"id", "email", "password_hash", "display_name", "role",
                "org_id", "onboarding_done", "created_at"}.issubset(columns)

    def test_organizations_columns(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("organizations")}
        assert {"id", "name", "created_at"}.issubset(columns)

    def test_init_db_twice_new_tables(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        db_module.init_db()  # must not raise
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "organizations" in tables
        assert "users" in tables

    def test_seed_user_created_from_auth_password(self, monkeypatch, tmp_db):
        engine, db_module = tmp_db
        monkeypatch.setenv("AUTH_PASSWORD", "test_secret_123")
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        session = Session()
        users = session.query(db_module.User).all()
        assert len(users) == 1
        assert users[0].id == 1
        assert users[0].email == "admin@basira.local"
        assert users[0].role == "admin"
        assert users[0].onboarding_done is True
        session.close()

    def test_seed_user_not_created_when_users_exist(self, monkeypatch, tmp_db):
        engine, db_module = tmp_db
        monkeypatch.setenv("AUTH_PASSWORD", "test_secret_456")
        db_module.init_db()

        # Add a second user manually
        Session = sessionmaker(bind=engine)
        session = Session()
        user2 = db_module.User(
            email="user2@test.com",
            password_hash="dummy",
            display_name="User Two",
        )
        session.add(user2)
        session.commit()
        session.close()

        # Re-init — seed should NOT add another user
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        users = Session().query(db_module.User).all()
        assert len(users) == 2  # still exactly 2

    def test_multi_tenant_migration_idempotent_with_existing_data(self, tmp_db):
        """Backward-compat: existing articles survive after adding user tables."""
        from datetime import datetime
        engine, db_module = tmp_db
        db_module.init_db()

        # Insert a pre-existing article
        Session = sessionmaker(bind=engine)
        session = Session()
        feed = db_module.Feed(
            url="https://existing.com/rss", name="Existing Feed", category="Test"
        )
        session.add(feed)
        session.commit()
        article = db_module.Article(
            feed_id=feed.id,
            title="Existing Article",
            url="https://existing.com/1",
            created_at=datetime.utcnow(),
        )
        session.add(article)
        session.commit()
        session.close()

        # Re-init adds user tables but preserves data
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        articles = Session().query(db_module.Article).all()
        assert len(articles) == 1
        assert articles[0].title == "Existing Article"


class TestArticleScoresTable:
    """Story 2.1 — article_scores table + backfill (FR-MT-7, FR-MT-12)."""

    def test_article_scores_table_exists(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "article_scores" in tables

    def test_article_scores_columns(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("article_scores")}
        expected = {"user_id", "article_id", "score", "tags_json", "summary_bullets_json",
                    "reason", "read_at", "bookmarked", "user_feedback", "contribution_type",
                    "re_document_type", "score_meta_json", "created_at"}
        assert expected.issubset(columns)

    def _make_feed_and_article(self, session, db_module, url_slug, title, seed_user=True, **kwargs):
        """Helper: create a feed + article, return the article id."""
        feed = db_module.Feed(url=f"https://{url_slug}.com/rss", name=f"{title} Feed", category="Test")
        session.add(feed)
        session.commit()

        from datetime import datetime
        article_kwargs = dict(
            feed_id=feed.id,
            title=title,
            url=f"https://{url_slug}.com/1",
            created_at=datetime.utcnow(),
            score=0.75,
            tags_json='["nlp"]',
            summary_bullets_json='["key finding"]',
            reason="Important work",
            read_at=datetime.utcnow(),
            bookmarked=True,
            contribution_type="method",
            re_document_type="elicitation",
        )
        article_kwargs.update(kwargs)
        article = db_module.Article(**article_kwargs)
        session.add(article)
        session.commit()
        session.refresh(article)
        aid = article.id
        session.close()
        return aid

    def test_backfill_preserves_article_data(self, tmp_db):
        import json
        engine, db_module = tmp_db
        db_module.init_db()

        aid = self._make_feed_and_article(
            sessionmaker(bind=engine)(), db_module,
            "backfill-preserve", "Backfill Article",
        )

        db_module.init_db()

        session = sessionmaker(bind=engine)()
        row = session.execute(
            text("SELECT * FROM article_scores WHERE user_id = 1 AND article_id = :aid"),
            {"aid": aid},
        ).fetchone()
        session.close()

        assert row is not None, "Backfill should have created article_scores row"
        assert row.score == 0.75
        assert row.tags_json == '["nlp"]'
        assert row.summary_bullets_json == '["key finding"]'
        assert row.reason == "Important work"
        assert row.bookmarked == 1
        assert row.contribution_type == "method"
        assert row.re_document_type == "elicitation"

    def test_backfill_idempotent(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()

        aid = self._make_feed_and_article(
            sessionmaker(bind=engine)(), db_module,
            "idempotent-test", "ID Article", score=0.5,
        )

        db_module.init_db()  # creates article_scores + backfills
        db_module.init_db()  # must not duplicate

        session = sessionmaker(bind=engine)()
        rows = session.execute(
            text("SELECT COUNT(*) FROM article_scores WHERE user_id = 1 AND article_id = :aid"),
            {"aid": aid},
        ).scalar()
        session.close()

        assert rows == 1, "Backfill must be idempotent — no duplicate rows"

    def test_no_data_loss_for_existing_articles(self, tmp_db):
        from datetime import datetime
        engine, db_module = tmp_db
        db_module.init_db()

        Session = sessionmaker(bind=engine)
        session = Session()
        feed = db_module.Feed(url="https://no-loss.com/rss", name="NL Feed", category="Test")
        session.add(feed)
        session.commit()
        article = db_module.Article(
            feed_id=feed.id,
            title="No Loss Article",
            url="https://no-loss.com/1",
            created_at=datetime.utcnow(),
        )
        session.add(article)
        session.commit()
        session.close()

        db_module.init_db()

        Session = sessionmaker(bind=engine)
        session = Session()
        articles = session.query(db_module.Article).all()
        assert len(articles) == 1
        assert articles[0].title == "No Loss Article"
        session.close()
