"""Tests for Story 11.2 — profile bootstrap endpoint and config extension.

Verifies:
- POST /api/profile/bootstrap returns BootstrapResult JSON; user_config not
  mutated (AC1, FR-MT-53).
- Rate limiting yields HTTP 429 + Retry-After header (AC2).
- GET /api/profile/config returns thesis_text/domain_label/facet_schema
  (null when unset) (AC3).
- PUT /api/profile/config persists facet_schema_json + domain_label and
  invalidates prompt_cache_hash (AC4).

Run inside Docker:
    docker-compose exec api python -m pytest \\
        backend/scorer/tests/test_profile_bootstrap_endpoint.py -v
"""
from __future__ import annotations

import json
import os
import sys as _sys
from pathlib import Path

import pytest


os.environ.setdefault("AUTH_PASSWORD", "test-password-bootstrap-ep")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_bootstrap_ep.db")
os.environ.setdefault("BOOTSTRAP_RATE_LIMIT", "3")  # small limit for fast tests
os.environ.setdefault("BOOTSTRAP_RATE_WINDOW_SECONDS", "3600")


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
        "backend/scorer/tests/test_profile_bootstrap_endpoint.py -v"
    ),
)

API_DIR = Path(__file__).parent.parent.parent / "api"


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
    from database import Base

    db_file = tmp_path / "test_profile_bootstrap.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session, monkeypatch):
    """Build a TestClient with auth + db dependency overrides and a
    deterministic LLM stub for the bootstrap service."""
    from fastapi.testclient import TestClient
    if str(API_DIR) not in _sys.path:
        _sys.path.insert(0, str(API_DIR))
    from auth import require_session
    from database import get_db
    from main import app
    from routers import profile
    from services import config_bootstrap

    # Stub the LLM so the bootstrap service is deterministic
    async def fake_call_llm(_msg):
        return json.dumps({
            "domain_label": "Urban Mobility",
            "scoring_clusters": [
                {"name": "Modal Shift", "description": "transit substitution", "reward_level": 0.9},
            ],
            "facet_schema": {
                "version": 1,
                "dimensions": [
                    {"id": "phase", "label": "Phase", "type": "enum", "values": ["a", "b"]},
                ],
            },
            "keywords": ["mobility", "cycling"],
            "suggested_source_queries": ["urban cycling adoption"],
        })

    monkeypatch.setattr(config_bootstrap, "_call_llm", fake_call_llm)
    config_bootstrap._cache_clear()
    profile._reset_bootstrap_rate_limits()

    # Seed a user_config row for user_id=42
    from database import UserConfig
    db_session.add(
        UserConfig(
            user_id=42,
            thesis_title="Pre-existing thesis title",
            thesis_sections_json="[]",
            scoring_clusters_json="[]",
            tracked_venues_json="[]",
            avoid_topics_json="[]",
            prompt_profile="unified",
            prompt_cache_text="cached prompt",
            prompt_cache_hash="abc123",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_session] = lambda: {
        "id": 42,
        "email": "u42@test.local",
    }
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/profile/bootstrap
# ---------------------------------------------------------------------------


@SKIP_INTEGRATION
class TestBootstrapPreview:
    """AC1: bootstrap returns BootstrapResult JSON without persisting."""

    def test_returns_bootstrap_result(self, client):
        resp = client.post(
            "/api/profile/bootstrap",
            json={"thesis_text": "A study of urban mobility transitions."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["degraded"] is False
        assert body["domain_label"] == "Urban Mobility"
        assert len(body["scoring_clusters"]) == 1
        assert body["facet_schema"]["dimensions"][0]["id"] == "phase"

    def test_does_not_persist_user_config(self, client, db_session):
        from database import UserConfig
        resp = client.post(
            "/api/profile/bootstrap",
            json={"thesis_text": "Some other thesis."},
        )
        assert resp.status_code == 200
        db_session.expire_all()
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        # FR-MT-53: bootstrap is preview-only — none of the bootstrap fields
        # should be written to user_config by this endpoint.
        assert row.thesis_text is None
        assert row.domain_label is None
        assert row.facet_schema_json is None
        assert row.bootstrap_hash is None

    def test_unauthorized_request_rejected(self, db_session, monkeypatch):
        # Build a client without the require_session override → should 401/403
        from fastapi.testclient import TestClient
        if str(API_DIR) not in _sys.path:
            _sys.path.insert(0, str(API_DIR))
        from database import get_db
        from main import app

        app.dependency_overrides[get_db] = lambda: db_session
        try:
            with TestClient(app) as raw:
                resp = raw.post(
                    "/api/profile/bootstrap",
                    json={"thesis_text": "x"},
                )
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


@SKIP_INTEGRATION
class TestBootstrapRateLimit:
    """AC2: rate limit enforced; 429 + Retry-After returned beyond cap."""

    def test_rate_limit_returns_429(self, client):
        for i in range(3):  # limit = 3 (set via env)
            resp = client.post(
                "/api/profile/bootstrap",
                json={"thesis_text": f"variant {i}"},
            )
            assert resp.status_code == 200
        # 4th call should be rate-limited
        resp = client.post(
            "/api/profile/bootstrap",
            json={"thesis_text": "variant overflow"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert 1 <= retry_after <= 3600


# ---------------------------------------------------------------------------
# GET /api/profile/config — new fields
# ---------------------------------------------------------------------------


@SKIP_INTEGRATION
class TestGetConfigReturnsNewFields:
    """AC3: thesis_text/domain_label/facet_schema included; null when unset."""

    def test_get_returns_null_fields_when_unset(self, client):
        resp = client.get("/api/profile/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == 42
        assert "thesis_text" in body and body["thesis_text"] is None
        assert "domain_label" in body and body["domain_label"] is None
        assert "facet_schema" in body and body["facet_schema"] is None

    def test_get_returns_populated_facet_schema_after_set(self, client, db_session):
        from database import UserConfig
        schema = {"version": 1, "dimensions": [{"id": "x", "label": "X", "type": "enum", "values": ["a"]}]}
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        row.facet_schema_json = json.dumps(schema)
        row.thesis_text = "stored thesis"
        row.domain_label = "Stored Domain"
        db_session.commit()

        resp = client.get("/api/profile/config")
        body = resp.json()
        assert body["thesis_text"] == "stored thesis"
        assert body["domain_label"] == "Stored Domain"
        assert body["facet_schema"] == schema

    def test_get_returns_null_facet_schema_when_json_invalid(self, client, db_session):
        from database import UserConfig
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        row.facet_schema_json = "{not json"
        db_session.commit()
        resp = client.get("/api/profile/config")
        assert resp.status_code == 200
        assert resp.json()["facet_schema"] is None


# ---------------------------------------------------------------------------
# PUT /api/profile/config — persistence + cache invalidation
# ---------------------------------------------------------------------------


@SKIP_INTEGRATION
class TestPutConfigPersistsBootstrapFields:
    """AC4: PUT writes facet_schema_json + domain_label and invalidates caches."""

    def test_put_persists_facet_schema_and_domain_label(self, client, db_session):
        from database import UserConfig
        schema = {
            "version": 1,
            "dimensions": [
                {"id": "study_phase", "label": "Study Phase", "type": "enum", "values": ["pilot", "field"]},
            ],
        }
        resp = client.put(
            "/api/profile/config",
            json={"facet_schema": schema, "domain_label": "Urban Mobility"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["domain_label"] == "Urban Mobility"
        assert body["facet_schema"] == schema

        db_session.expire_all()
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        assert json.loads(row.facet_schema_json) == schema
        assert row.domain_label == "Urban Mobility"

    def test_put_invalidates_prompt_cache(self, client, db_session):
        from database import UserConfig
        # Confirm cache was pre-seeded
        row_before = db_session.query(UserConfig).filter_by(user_id=42).first()
        assert row_before.prompt_cache_hash == "abc123"
        resp = client.put(
            "/api/profile/config",
            json={"facet_schema": {"version": 1, "dimensions": []}},
        )
        assert resp.status_code == 200
        db_session.expire_all()
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        assert row.prompt_cache_hash is None
        assert row.prompt_cache_text is None

    def test_put_thesis_text_clears_bootstrap_hash(self, client, db_session):
        from database import UserConfig
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        row.bootstrap_hash = "stale-hash"
        db_session.commit()

        resp = client.put(
            "/api/profile/config",
            json={"thesis_text": "Updated thesis."},
        )
        assert resp.status_code == 200
        db_session.expire_all()
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        assert row.bootstrap_hash is None
        assert row.thesis_text == "Updated thesis."

    def test_put_does_not_touch_unrelated_fields(self, client, db_session):
        from database import UserConfig
        before = db_session.query(UserConfig).filter_by(user_id=42).first()
        original_title = before.thesis_title

        resp = client.put(
            "/api/profile/config",
            json={"domain_label": "New Domain"},
        )
        assert resp.status_code == 200
        db_session.expire_all()
        row = db_session.query(UserConfig).filter_by(user_id=42).first()
        assert row.thesis_title == original_title  # untouched
        assert row.domain_label == "New Domain"
