"""Tests for Story 11.3 — config-templates-table.

Verifies:
- config_templates table exists with correct schema after init_db (AC1).
- seed_config_templates inserts 5+ global templates idempotently (AC2).
- GET /api/templates returns global templates for authenticated user (AC3).
- POST /api/profile/from-template/{id} applies template, preserves thesis (AC4).
- Non-existent template returns 404.

Run inside Docker:
    docker-compose exec api python -m pytest \\
        backend/scorer/tests/test_config_templates.py -v
"""
from __future__ import annotations

import json
import os
import sys as _sys
from pathlib import Path

import pytest


os.environ.setdefault("AUTH_PASSWORD", "test-password-templates")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_templates.db")


def _check_api_deps() -> bool:
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
        import pydantic  # noqa: F401
        import httpx  # noqa: F401
        import structlog  # noqa: F401
        return True
    except ImportError:
        return False


DEPS_AVAILABLE = _check_api_deps()

SKIP_INTEGRATION = pytest.mark.skipif(
    not DEPS_AVAILABLE,
    reason=(
        "Full API deps not available — run inside Docker: "
        "docker-compose exec api python -m pytest "
        "backend/scorer/tests/test_config_templates.py -v"
    ),
)

API_DIR = Path(__file__).parent.parent.parent / "api"


# ---------------------------------------------------------------------------
# AC1 + AC2: table creation + seeding (via init_db)
# ---------------------------------------------------------------------------


@SKIP_INTEGRATION
class TestConfigTemplatesTable:
    """config_templates table exists after init_db with correct schema."""

    def test_table_exists_after_init_db(self, tmp_db):
        engine, _db_module = tmp_db
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "config_templates" in tables

    def test_columns_have_expected_names(self, tmp_db):
        engine, _db_module = tmp_db
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("config_templates")}
        expected = {"id", "slug", "name", "domain_label", "body_json", "scope", "owner_user_id", "created_at"}
        assert expected.issubset(columns)


@SKIP_INTEGRATION
class TestSeedConfigTemplates:
    """Seed inserts 5+ global templates idempotently."""

    def test_has_at_least_5_global_templates(self, tmp_db):
        engine, db_module = tmp_db
        from sqlalchemy import text
        with engine.connect() as conn:
            db_module._seed_config_templates(conn)
            result = conn.execute(text("SELECT COUNT(*) FROM config_templates WHERE scope='global'"))
            count = result.scalar()
        assert count >= 5

    def test_idempotent_double_seed(self, tmp_db):
        engine, db_module = tmp_db
        from sqlalchemy import text
        with engine.connect() as conn:
            db_module._seed_config_templates(conn)
            db_module._seed_config_templates(conn)
            result = conn.execute(text("SELECT COUNT(*) FROM config_templates"))
            count = result.scalar()
        assert count >= 5

    def test_templates_have_required_body_json_fields(self, tmp_db):
        engine, db_module = tmp_db
        from sqlalchemy import text
        with engine.connect() as conn:
            db_module._seed_config_templates(conn)
            rows = conn.execute(text("SELECT slug, body_json FROM config_templates")).fetchall()
        for slug, body_json in rows:
            body = json.loads(body_json)
            assert "scoring_clusters" in body, f"{slug} missing scoring_clusters"
            assert "facet_schema" in body, f"{slug} missing facet_schema"
            assert "keywords" in body, f"{slug} missing keywords"
            assert "suggested_source_queries" in body, f"{slug} missing suggested_source_queries"


# ---------------------------------------------------------------------------
# Fixtures for HTTP tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path):
    if not DEPS_AVAILABLE:
        pytest.skip("API deps not available — run inside Docker")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base

    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    if "database" not in _sys.modules:
        _sys.modules["database"] = __import__("database")

    db_file = tmp_path / "test_templates.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def seeded_db(db_session):
    """Seed the config_templates table and one UserConfig row."""
    from database import ConfigTemplate, UserConfig

    for t in _SEED_TEMPLATES:
        db_session.add(ConfigTemplate(**t))
    db_session.add(
        UserConfig(
            user_id=42,
            thesis_title="Pre-existing thesis",
            thesis_text="Preserve me",
            thesis_sections_json="[]",
            scoring_clusters_json="[]",
            tracked_venues_json="[]",
            avoid_topics_json="[]",
            prompt_profile="unified",
        )
    )
    db_session.commit()
    return db_session


_SEED_TEMPLATES = [
    {
        "slug": "cs-software-engineering",
        "name": "CS / Software Engineering",
        "domain_label": "Computer Science",
        "scope": "global",
        "body_json": json.dumps({
            "scoring_clusters": [{"name": "Systems", "description": "OS/networking", "reward_level": 0.8}],
            "facet_schema": {"version": 1, "dimensions": [{"id": "ctype", "label": "CType", "type": "enum", "values": ["A", "B"]}]},
            "keywords": ["systems"],
            "suggested_source_queries": ["arxiv cs"],
        }),
    },
    {
        "slug": "design-hci",
        "name": "Design / HCI",
        "domain_label": "HCI",
        "scope": "global",
        "body_json": json.dumps({
            "scoring_clusters": [{"name": "UX", "description": "User experience", "reward_level": 0.9}],
            "facet_schema": {"version": 1, "dimensions": [{"id": "method", "label": "Method", "type": "enum", "values": ["QUAL", "QUANT"]}]},
            "keywords": ["HCI"],
            "suggested_source_queries": ["CHI"],
        }),
    },
]


@pytest.fixture()
def client(seeded_db, monkeypatch):
    """TestClient with auth/DB overrides."""
    from fastapi.testclient import TestClient
    from auth import require_session
    from database import get_db
    from main import app

    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))

    from routers import profile
    profile._reset_bootstrap_rate_limits()

    app.dependency_overrides[get_db] = lambda: seeded_db
    app.dependency_overrides[require_session] = lambda: {"id": 42, "email": "u42@test.local"}
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# AC3: GET /api/templates
# ---------------------------------------------------------------------------


@SKIP_INTEGRATION
class TestListTemplates:
    """GET /api/templates returns accessible templates."""

    def test_returns_global_templates(self, client):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        slugs = {t["slug"] for t in body}
        assert "cs-software-engineering" in slugs
        assert "design-hci" in slugs

    def test_list_response_excludes_body_json(self, client):
        resp = client.get("/api/templates")
        body = resp.json()
        for t in body:
            assert "body_json" not in t

    def test_list_response_includes_expected_fields(self, client):
        resp = client.get("/api/templates")
        body = resp.json()
        for t in body:
            assert "id" in t
            assert "slug" in t
            assert "name" in t
            assert "domain_label" in t
            assert "scope" in t

    def test_unauthorized_request_rejected(self, seeded_db):
        from fastapi.testclient import TestClient
        from database import get_db
        from main import app

        if str(API_DIR) not in _sys.path:
            _sys.path.insert(0, str(API_DIR))

        app.dependency_overrides[get_db] = lambda: seeded_db
        try:
            with TestClient(app) as raw:
                resp = raw.get("/api/templates")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# AC4: POST /api/profile/from-template/{id}
# ---------------------------------------------------------------------------


@SKIP_INTEGRATION
class TestApplyTemplate:
    """POST /api/profile/from-template/{id} applies template body to user config."""

    def test_applies_scoring_clusters_and_facet_schema(self, client, seeded_db):
        from database import UserConfig
        resp = client.post("/api/profile/from-template/1")
        assert resp.status_code == 200
        body = resp.json()

        seeded_db.expire_all()
        row = seeded_db.query(UserConfig).filter_by(user_id=42).first()
        clusters = json.loads(row.scoring_clusters_json)
        assert len(clusters) == 1
        assert clusters[0]["name"] == "Systems"

        schema = json.loads(row.facet_schema_json)
        assert schema["dimensions"][0]["id"] == "ctype"

    def test_preserves_thesis_text_when_non_empty(self, client, seeded_db):
        from database import UserConfig
        resp = client.post("/api/profile/from-template/1")
        assert resp.status_code == 200

        seeded_db.expire_all()
        row = seeded_db.query(UserConfig).filter_by(user_id=42).first()
        assert row.thesis_text == "Preserve me"

    def test_sets_domain_label_from_template(self, client, seeded_db):
        from database import UserConfig
        resp = client.post("/api/profile/from-template/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["domain_label"] == "Computer Science"

        seeded_db.expire_all()
        row = seeded_db.query(UserConfig).filter_by(user_id=42).first()
        assert row.domain_label == "Computer Science"

    def test_invalidates_prompt_cache(self, client, seeded_db):
        from database import UserConfig
        row = seeded_db.query(UserConfig).filter_by(user_id=42).first()
        row.prompt_cache_hash = "stale-hash"
        row.prompt_cache_text = "stale-text"
        seeded_db.commit()

        resp = client.post("/api/profile/from-template/1")
        assert resp.status_code == 200

        seeded_db.expire_all()
        row = seeded_db.query(UserConfig).filter_by(user_id=42).first()
        assert row.prompt_cache_hash is None
        assert row.prompt_cache_text is None

    def test_returns_404_for_nonexistent_template(self, client):
        resp = client.post("/api/profile/from-template/99999")
        assert resp.status_code == 404

    def test_unauthorized_request_rejected(self, seeded_db):
        from fastapi.testclient import TestClient
        from database import get_db
        from main import app

        if str(API_DIR) not in _sys.path:
            _sys.path.insert(0, str(API_DIR))

        app.dependency_overrides[get_db] = lambda: seeded_db
        try:
            with TestClient(app) as raw:
                resp = raw.post("/api/profile/from-template/1")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Shared fixture for AC1+2 (uses init_db directly)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(monkeypatch, tmp_path):
    if not DEPS_AVAILABLE:
        pytest.skip("API deps not available — run inside Docker")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import database as db_module

    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))

    db_file = tmp_path / "test_tmp.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(
        db_module, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    db_module.init_db()
    yield engine, db_module
    engine.dispose()
