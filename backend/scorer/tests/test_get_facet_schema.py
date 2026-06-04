"""Tests for Story 10.2 — get_facet_schema() + _backfill_facet_schema().

Verifies:
- get_facet_schema() returns the CS-equivalent default when user has no schema
- Default schema shape: version=1 + dimensions list with contribution_type + re_document_type
- get_facet_schema() returns the stored custom schema when one is set
- get_facet_schema() returns default without raising when user_id has no row
- _backfill_facet_schema populates user_id=1 when NULL
- _backfill_facet_schema is idempotent (does not overwrite a non-NULL value)
- init_db() leaves user_id=1 with a non-NULL facet_schema_json

Run inside Docker:
    docker-compose exec api python -m pytest \\
        backend/scorer/tests/test_get_facet_schema.py -v
"""

from __future__ import annotations

import json
import os
import sys as _sys
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test-password-get-facets")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_get_facet_schema.db")


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
        "backend/scorer/tests/test_get_facet_schema.py -v"
    ),
)

API_DIR = Path(__file__).parent.parent.parent / "api"


@pytest.fixture()
def tmp_db(monkeypatch, tmp_path):
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
class TestDefaultFacetSchema:
    """AC 1, 4: Default schema returned when user has no stored schema."""

    def test_returns_default_for_user_with_no_schema(self, tmp_db):
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()
        # Explicitly clear the backfill so we are testing the NULL fallback path
        Session = sessionmaker(bind=engine)
        session = Session()
        session.execute(
            text("UPDATE user_config SET facet_schema_json = NULL WHERE user_id = 1")
        )
        session.commit()
        schema = db_module.get_facet_schema(session, 1)
        session.close()
        assert isinstance(schema, dict)
        assert schema.get("version") == 1
        dims = schema.get("dimensions")
        assert isinstance(dims, list)
        ids = {d["id"] for d in dims}
        assert {"contribution_type", "re_document_type"}.issubset(ids)

    def test_default_dimensions_have_expected_values(self, tmp_db):
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        session = Session()
        session.execute(
            text("UPDATE user_config SET facet_schema_json = NULL WHERE user_id = 1")
        )
        session.commit()
        schema = db_module.get_facet_schema(session, 1)
        session.close()
        contrib = next(d for d in schema["dimensions"] if d["id"] == "contribution_type")
        re_doc = next(d for d in schema["dimensions"] if d["id"] == "re_document_type")
        assert "method" in contrib["values"] and "survey" in contrib["values"]
        assert set(re_doc["values"]) == {"elicitation", "extraction", "method", "none"}

    def test_returns_default_when_user_has_no_config_row(self, tmp_db):
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        session = Session()
        # user_id=999 has no row — must not raise
        schema = db_module.get_facet_schema(session, 999)
        session.close()
        assert isinstance(schema, dict)
        assert "dimensions" in schema


@SKIP_INTEGRATION
class TestCustomFacetSchema:
    """AC 3: Custom stored schema is returned verbatim."""

    def test_returns_stored_custom_schema(self, tmp_db):
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()
        custom = {
            "version": 1,
            "dimensions": [
                {
                    "id": "study_phase",
                    "label": "Study Phase",
                    "type": "enum",
                    "values": ["pilot", "field", "lab", "review"],
                },
            ],
        }
        Session = sessionmaker(bind=engine)
        session = Session()
        session.execute(
            text("UPDATE user_config SET facet_schema_json = :s WHERE user_id = 1"),
            {"s": json.dumps(custom)},
        )
        session.commit()
        got = db_module.get_facet_schema(session, 1)
        session.close()
        assert got["dimensions"][0]["id"] == "study_phase"
        assert got["dimensions"][0]["values"] == ["pilot", "field", "lab", "review"]


@SKIP_INTEGRATION
class TestBackfillFacetSchema:
    """AC 2: _backfill_facet_schema populates user_id=1 with the default."""

    def test_init_db_populates_user_1(self, tmp_db):
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
        assert row is not None
        assert row.facet_schema_json is not None
        parsed = json.loads(row.facet_schema_json)
        assert parsed["version"] == 1
        assert {d["id"] for d in parsed["dimensions"]} == {
            "contribution_type",
            "re_document_type",
        }

    def test_backfill_does_not_overwrite_custom_value(self, tmp_db):
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        session = Session()
        custom = {"version": 1, "dimensions": [{"id": "custom"}]}
        session.execute(
            text("UPDATE user_config SET facet_schema_json = :s WHERE user_id = 1"),
            {"s": json.dumps(custom)},
        )
        session.commit()
        # Re-run init — backfill should NOT overwrite the custom value
        db_module.init_db()
        row = session.execute(
            text("SELECT facet_schema_json FROM user_config WHERE user_id = 1")
        ).fetchone()
        session.close()
        assert json.loads(row.facet_schema_json) == custom

    def test_backfill_idempotent_on_null(self, tmp_db):
        """Running init_db twice still leaves user_id=1 with exactly one row, non-NULL."""
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        engine, db_module = tmp_db
        db_module.init_db()
        db_module.init_db()
        Session = sessionmaker(bind=engine)
        session = Session()
        rows = session.execute(
            text("SELECT COUNT(*) FROM user_config WHERE user_id = 1 "
                 "AND facet_schema_json IS NOT NULL")
        ).scalar()
        session.close()
        assert rows == 1
