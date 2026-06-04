"""Tests for Story 10.1 — facet schema columns.

Verifies:
- `user_config.facet_schema_json` (TEXT, nullable) exists after init_db()
- `article_scores.facets_json` (TEXT, nullable) exists after init_db()
- init_db() is idempotent (safe to run twice)
- Pre-existing article_scores rows retain original values; facets_json is NULL
- Seed user_id=1 has facet_schema_json NULL after migration (10-1 only; 10-2 backfills)

Run inside Docker:
    docker-compose exec api python -m pytest \\
        backend/scorer/tests/test_facet_schema_columns.py -v
"""

from __future__ import annotations

import os
import sys as _sys
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test-password-facets")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_facet_schema.db")


def _check_api_deps() -> bool:
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
        import bcrypt  # noqa: F401
        import structlog  # noqa: F401
        import feedparser  # noqa: F401
        import httpx  # noqa: F401
        return True
    except ImportError:
        return False


DEPS_AVAILABLE = _check_api_deps()

SKIP_INTEGRATION = pytest.mark.skipif(
    not DEPS_AVAILABLE,
    reason=(
        "Full API deps not available — run inside Docker: "
        "docker-compose exec api python -m pytest "
        "backend/scorer/tests/test_facet_schema_columns.py -v"
    ),
)

API_DIR = Path(__file__).parent.parent.parent / "api"


@pytest.fixture()
def tmp_db(monkeypatch, tmp_path):
    """Patch the api/database module to use a fresh SQLite file per test."""
    if not DEPS_AVAILABLE:
        pytest.skip("API deps not available — run inside Docker")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    if "database" not in _sys.modules:
        _sys.modules["database"] = __import__("database")
    import database as db_module

    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(
        db_module,
        "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine),
    )

    yield engine, db_module

    engine.dispose()


@SKIP_INTEGRATION
class TestFacetSchemaColumns:
    """AC 1: facet_schema_json on user_config; facets_json on article_scores."""

    def test_facet_schema_json_column_exists(self, tmp_db):
        from sqlalchemy import inspect
        engine, db_module = tmp_db
        db_module.init_db()
        columns = {c["name"] for c in inspect(engine).get_columns("user_config")}
        assert "facet_schema_json" in columns

    def test_facets_json_column_exists(self, tmp_db):
        from sqlalchemy import inspect
        engine, db_module = tmp_db
        db_module.init_db()
        columns = {c["name"] for c in inspect(engine).get_columns("article_scores")}
        assert "facets_json" in columns


@SKIP_INTEGRATION
class TestFacetSchemaIdempotency:
    """AC 2: init_db() twice is idempotent — no error, columns still present."""

    def test_init_db_twice_no_error(self, tmp_db):
        engine, db_module = tmp_db
        db_module.init_db()
        db_module.init_db()  # must not raise

    def test_columns_present_after_double_init(self, tmp_db):
        from sqlalchemy import inspect
        engine, db_module = tmp_db
        db_module.init_db()
        db_module.init_db()
        uc_cols = {c["name"] for c in inspect(engine).get_columns("user_config")}
        as_cols = {c["name"] for c in inspect(engine).get_columns("article_scores")}
        assert "facet_schema_json" in uc_cols
        assert "facets_json" in as_cols


@SKIP_INTEGRATION
class TestPreExistingRowsPreserved:
    """AC 3, 4: pre-existing rows survive migration; facets_json is NULL by default."""

    def test_existing_article_score_facets_json_is_null(self, tmp_db):
        from datetime import datetime
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()

        Session = sessionmaker(bind=engine)
        session = Session()
        feed = db_module.Feed(url="https://facets-row.com/rss", name="FR Feed", category="Test")
        session.add(feed)
        session.commit()
        article = db_module.Article(
            feed_id=feed.id,
            title="Facets Row Article",
            url="https://facets-row.com/1",
            created_at=datetime.utcnow(),
            score=0.42,
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        article_id = article.id
        session.close()

        # Backfill creates the article_scores row for user_id=1
        db_module.init_db()

        session = Session()
        row = session.execute(
            text("SELECT score, facets_json FROM article_scores "
                 "WHERE user_id = 1 AND article_id = :aid"),
            {"aid": article_id},
        ).fetchone()
        session.close()

        assert row is not None
        assert row.score == 0.42
        assert row.facets_json is None  # Story 10.1 leaves this NULL

    def test_seed_user_facet_schema_json_is_null(self, tmp_db):
        """AC 4: seed user_id=1 starts with facet_schema_json NULL (Story 10-2 backfills)."""
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()

        Session = sessionmaker(bind=engine)
        session = Session()
        row = session.execute(
            text("SELECT facet_schema_json FROM user_config WHERE user_id = 1")
        ).fetchone()
        session.close()

        assert row is not None  # Backfill creates the row
        assert row.facet_schema_json is None  # Not populated by 10-1
