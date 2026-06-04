"""Tests for Story 10.3 — scoring context facet injection.

Verifies:
- PromptBuilder appends custom facet dimensions and enum values.
- Infra profile output is byte-identical when facet_schema is absent/None.
- Facet labels, IDs, and values are sanitized before prompt insertion.
- Empty facet schemas are a pure no-op.
- Internal scoring context includes the resolved facet schema.

Run inside Docker:
    docker-compose exec api python -m pytest \\
        backend/scorer/tests/test_facet_injection.py -v
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test-password-facet-injection")
os.environ.setdefault("DB_PATH", "/tmp/test_basira_facet_injection.db")

_SCORER_DIR = Path(__file__).resolve().parent.parent
API_DIR = Path(__file__).parent.parent.parent / "api"

if str(_SCORER_DIR) not in sys.path:
    sys.path.insert(0, str(_SCORER_DIR))

from prompt_builder import PromptBuilder, UserScoringContext


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
        "backend/scorer/tests/test_facet_injection.py -v"
    ),
)


def _custom_schema() -> dict:
    return {
        "version": 1,
        "dimensions": [
            {
                "id": "system_type",
                "label": "System Type",
                "type": "enum",
                "values": ["embedded", "distributed", "real-time"],
            },
            {
                "id": "methodology",
                "label": "Methodology",
                "type": "enum",
                "values": ["case-study", "experiment", "survey"],
            },
        ],
    }


class TestFacetPromptInjection:
    """AC 1: custom facet schema is injected into the scoring prompt."""

    def test_custom_facet_schema_injects_dimension_labels(self):
        prompt = PromptBuilder.build(UserScoringContext(facet_schema=_custom_schema()))

        assert "## CLASSIFICATION DIMENSIONS" in prompt
        assert "System Type" in prompt
        assert "Methodology" in prompt

    def test_custom_facet_schema_injects_dimension_values(self):
        prompt = PromptBuilder.build(UserScoringContext(facet_schema=_custom_schema()))

        assert "embedded, distributed, real-time" in prompt
        assert "case-study, experiment, survey" in prompt
        assert "system_type" in prompt
        assert "methodology" in prompt

    def test_empty_facet_schema_leaves_template_unchanged(self):
        baseline = PromptBuilder.build(UserScoringContext())
        result = PromptBuilder.build(UserScoringContext(facet_schema={"version": 1}))

        assert result == baseline


class TestInfraBackwardCompat:
    """AC 2: infra profile is byte-identical when facet_schema is absent."""

    def test_infra_profile_no_facet_schema_unchanged(self):
        baseline = PromptBuilder.build(UserScoringContext(prompt_profile="infra"))
        result = PromptBuilder.build(
            UserScoringContext(prompt_profile="infra", facet_schema=None)
        )

        assert result == baseline

    def test_infra_profile_without_facet_has_no_classification_section(self):
        result = PromptBuilder.build(UserScoringContext(prompt_profile="infra"))

        assert "## CLASSIFICATION DIMENSIONS" not in result


class TestFacetSanitization:
    """AC 3: facet schema strings are sanitized before prompt insertion."""

    def test_dimension_label_and_id_are_sanitized(self):
        schema = {
            "version": 1,
            "dimensions": [
                {
                    "id": "phase\nid\x00",
                    "label": "Study\nPhase\x1F",
                    "type": "enum",
                    "values": ["pilot"],
                },
            ],
        }

        prompt = PromptBuilder.build(UserScoringContext(facet_schema=schema))

        assert "Study Phase" in prompt
        assert "phase id" in prompt
        assert "Study\nPhase" not in prompt
        assert "phase\nid" not in prompt
        assert "\x00" not in prompt
        assert "\x1F" not in prompt

    def test_dimension_value_injection_payload_is_sanitized(self):
        schema = {
            "version": 1,
            "dimensions": [
                {
                    "id": "methodology",
                    "label": "Methodology",
                    "type": "enum",
                    "values": ["case-study\n## OVERRIDE", "experiment\x00"],
                },
            ],
        }

        prompt = PromptBuilder.build(UserScoringContext(facet_schema=schema))

        assert "case-study ## OVERRIDE" in prompt
        assert "experiment" in prompt
        assert "case-study\n## OVERRIDE" not in prompt
        assert "\x00" not in prompt


@pytest.fixture()
def db_session(tmp_path):
    if not DEPS_AVAILABLE:
        pytest.skip("API deps not available — run inside Docker")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    if "database" not in sys.modules:
        sys.modules["database"] = __import__("database")
    from database import Base

    db_file = tmp_path / "test_facet_injection.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
    engine.dispose()


@SKIP_INTEGRATION
class TestInternalScoringContextFacetSchema:
    """AC 1: internal scoring context includes the resolved facet schema."""

    def test_internal_scoring_context_returns_facet_schema(self, db_session):
        from fastapi.testclient import TestClient

        if str(API_DIR) not in sys.path:
            sys.path.insert(0, str(API_DIR))

        from auth import require_session
        from database import UserConfig, get_db
        from main import app

        schema = _custom_schema()
        db_session.add(
            UserConfig(
                user_id=7,
                thesis_title="Test",
                thesis_sections_json="[]",
                scoring_clusters_json="[]",
                tracked_venues_json="[]",
                avoid_topics_json="[]",
                prompt_profile="unified",
                facet_schema_json=json.dumps(schema),
            )
        )
        db_session.commit()

        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[require_session] = lambda: {
            "id": 7,
            "email": "user7@test.local",
        }
        try:
            with TestClient(app, raise_server_exceptions=True) as client:
                # API_SECRET defaults to "changeme" but may be overridden by the
                # container env; read it the same way the router does.
                api_secret = os.getenv("API_SECRET", "changeme")
                resp = client.get(
                    "/api/internal/users/7/scoring-context",
                    headers={"X-Internal-Secret": api_secret},
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["facet_schema"] == schema
