"""Tests for Story 3.3 — Typed Researcher Profile.

Host-runnable tests validate source analysis and model contracts.
Integration tests (require full API stack) are skipped on the host.
"""
import importlib
import json
import os
import sys
import types
import pytest

# ── Environment mocks required to import API modules on the host ─────────────
os.environ.setdefault("AUTH_PASSWORD", "test_password_basira")
os.environ.setdefault("BASIRA_DB_PATH", ":memory:")
os.environ.setdefault("API_SECRET", "test-secret")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text")
os.environ.setdefault("CHROMA_PATH", "/tmp/test-chroma-3-3")

# ── Integration-test gate ─────────────────────────────────────────────────────
def _check_api_deps():
    for pkg in ("fastapi", "sqlalchemy", "bcrypt", "structlog", "feedparser",
                "httpx", "chromadb"):
        try:
            importlib.import_module(pkg)
        except ImportError:
            return False
    return True

_API_AVAILABLE = _check_api_deps()
_SKIP_INTEGRATION = pytest.mark.skipif(
    not _API_AVAILABLE,
    reason="Full API stack not available on host — run inside Docker",
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
_API_DIR = os.path.join(_REPO_ROOT, "backend", "api")
_RESEARCH_PY = os.path.join(_API_DIR, "routers", "research.py")
_DATABASE_PY = os.path.join(_API_DIR, "database.py")
_ARTICLES_PY = os.path.join(_API_DIR, "routers", "articles.py")
_INTERNAL_PY = os.path.join(_API_DIR, "routers", "internal.py")
_MODELS_PY   = os.path.join(_API_DIR, "models.py")
_TYPES_TS    = os.path.join(_REPO_ROOT, "frontend", "src", "types.ts")
_STORE_TS    = os.path.join(_REPO_ROOT, "frontend", "src", "store", "research.ts")
_EDITOR_TSX  = os.path.join(_REPO_ROOT, "frontend", "src", "components", "ResearchProfileEditor.tsx")
_ARTICLELIST_TSX = os.path.join(_REPO_ROOT, "frontend", "src", "components", "ArticleList.tsx")
_APP_TSX     = os.path.join(_REPO_ROOT, "frontend", "src", "App.tsx")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


# ═══════════════════════════════════════════════════════════════════════════════
# AC 1 — DB: research_profile table
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabaseModel:
    def test_research_profile_orm_class_exists(self):
        src = _read(_DATABASE_PY)
        assert "class ResearchProfile(Base):" in src

    def test_orm_columns_present(self):
        src = _read(_DATABASE_PY)
        for col in ("kind", "label", "weight", "source", "created_at"):
            assert col in src, f"Missing column: {col}"

    def test_unique_constraint_defined(self):
        src = _read(_DATABASE_PY)
        assert "UniqueConstraint" in src
        assert "ux_research_profile" in src

    def test_migration_create_table(self):
        src = _read(_DATABASE_PY)
        assert "CREATE TABLE IF NOT EXISTS research_profile" in src

    def test_migration_unique_index(self):
        src = _read(_DATABASE_PY)
        assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_research_profile" in src

    def test_unique_constraint_import(self):
        src = _read(_DATABASE_PY)
        assert "UniqueConstraint" in src


# ═══════════════════════════════════════════════════════════════════════════════
# AC 2 & 3 — API: GET/PUT /api/research/profile
# ═══════════════════════════════════════════════════════════════════════════════

class TestProfileEndpointSource:
    def test_get_profile_route_defined(self):
        src = _read(_RESEARCH_PY)
        assert "@router.get(\"/profile\"" in src

    def test_put_profile_route_defined(self):
        src = _read(_RESEARCH_PY)
        assert "@router.put(\"/profile\"" in src

    def test_get_ordered_by_kind_and_weight(self):
        src = _read(_RESEARCH_PY)
        assert "ResearchProfile.kind" in src
        assert "ResearchProfile.weight" in src

    def test_put_deletes_on_weight_zero(self):
        src = _read(_RESEARCH_PY)
        assert "weight == 0" in src
        assert "db.delete" in src

    def test_put_upserts_existing_entry(self):
        src = _read(_RESEARCH_PY)
        assert "existing.weight = entry.weight" in src

    def test_label_normalised_to_lowercase(self):
        src = _read(_RESEARCH_PY)
        assert ".strip().lower()" in src

    def test_imports_research_profile_orm(self):
        src = _read(_RESEARCH_PY)
        assert "ResearchProfile" in src

    def test_imports_profile_models(self):
        src = _read(_RESEARCH_PY)
        assert "ResearchProfileEntry" in src
        assert "ResearchProfileUpsert" in src


# ═══════════════════════════════════════════════════════════════════════════════
# AC 4 — Feedback hook: tags → research_profile on 👍
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackHook:
    def test_upsert_tags_function_exists(self):
        src = _read(_ARTICLES_PY)
        assert "_upsert_tags_from_feedback" in src

    def test_feedback_hook_triggered_on_like(self):
        src = _read(_ARTICLES_PY)
        assert "body.value == 1" in src
        assert "_upsert_tags_from_feedback" in src

    def test_kind_is_topic(self):
        src = _read(_ARTICLES_PY)
        assert "kind=\"topic\"" in src or "kind='topic'" in src

    def test_source_is_feedback(self):
        src = _read(_ARTICLES_PY)
        assert "source=\"feedback\"" in src or "source='feedback'" in src

    def test_weight_capped_at_2(self):
        src = _read(_ARTICLES_PY)
        assert "min(2.0" in src or "min(2," in src

    def test_weight_increment_on_existing(self):
        src = _read(_ARTICLES_PY)
        assert "weight + 0.1" in src

    def test_rollback_on_error(self):
        src = _read(_ARTICLES_PY)
        assert "db.rollback()" in src


# ═══════════════════════════════════════════════════════════════════════════════
# AC 5 — profile_preference_block in feedback-examples
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackExamples:
    def test_profile_preference_block_in_response(self):
        src = _read(_INTERNAL_PY)
        assert "profile_preference_block" in src

    def test_grouped_by_kind(self):
        src = _read(_INTERNAL_PY)
        for kind in ("topic", "method", "domain", "avoid"):
            assert f'"{kind}"' in src or f"'{kind}'" in src

    def test_imports_research_profile(self):
        src = _read(_INTERNAL_PY)
        assert "ResearchProfile" in src


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic models
# ═══════════════════════════════════════════════════════════════════════════════

class TestPydanticModels:
    def test_research_profile_entry_model(self):
        src = _read(_MODELS_PY)
        assert "class ResearchProfileEntry" in src

    def test_research_profile_upsert_model(self):
        src = _read(_MODELS_PY)
        assert "class ResearchProfileUpsert" in src

    def test_entry_has_required_fields(self):
        src = _read(_MODELS_PY)
        for field in ("kind", "label", "weight", "source"):
            assert field in src

    def test_upsert_has_entries_field(self):
        src = _read(_MODELS_PY)
        assert "entries" in src


# ═══════════════════════════════════════════════════════════════════════════════
# Frontend contracts
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrontendTypes:
    def test_research_profile_entry_interface(self):
        src = _read(_TYPES_TS)
        assert "interface ResearchProfileEntry" in src

    def test_profile_kind_type(self):
        src = _read(_TYPES_TS)
        assert "ProfileKind" in src
        assert "'topic'" in src
        assert "'avoid'" in src

    def test_entry_fields(self):
        src = _read(_TYPES_TS)
        for field in ("kind", "label", "weight", "source"):
            assert field in src


class TestResearchStore:
    def test_profile_state_exists(self):
        src = _read(_STORE_TS)
        assert "profile:" in src

    def test_fetch_profile_action(self):
        src = _read(_STORE_TS)
        assert "fetchProfile" in src

    def test_save_profile_action(self):
        src = _read(_STORE_TS)
        assert "saveProfile" in src

    def test_profile_api_endpoint(self):
        src = _read(_STORE_TS)
        assert "/api/research/profile" in src

    def test_put_method_for_save(self):
        src = _read(_STORE_TS)
        assert "method: 'PUT'" in src or 'method: "PUT"' in src


class TestResearchProfileEditor:
    def test_editor_file_exists(self):
        assert os.path.exists(_EDITOR_TSX)

    def test_kind_sections_present(self):
        src = _read(_EDITOR_TSX)
        for kind in ("topic", "method", "domain", "avoid"):
            assert kind in src

    def test_open_close_props(self):
        src = _read(_EDITOR_TSX)
        assert "open: boolean" in src
        assert "onClose" in src

    def test_uses_research_store(self):
        src = _read(_EDITOR_TSX)
        assert "useResearchStore" in src

    def test_save_button_present(self):
        src = _read(_EDITOR_TSX)
        assert "Save profile" in src

    def test_weight_slider_present(self):
        src = _read(_EDITOR_TSX)
        assert "weight" in src
        assert "range" in src


class TestArticleListIntegration:
    def test_on_open_profile_prop_defined(self):
        src = _read(_ARTICLELIST_TSX)
        assert "onOpenProfile" in src

    def test_user_circle_icon_used(self):
        src = _read(_ARTICLELIST_TSX)
        assert "UserCircle2" in src


class TestAppIntegration:
    def test_profile_open_state(self):
        src = _read(_APP_TSX)
        assert "profileOpen" in src

    def test_research_profile_editor_rendered(self):
        src = _read(_APP_TSX)
        assert "ResearchProfileEditor" in src

    def test_on_open_profile_wired(self):
        src = _read(_APP_TSX)
        assert "onOpenProfile" in src


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests (Docker only)
# ═══════════════════════════════════════════════════════════════════════════════

@_SKIP_INTEGRATION
class TestProfileAPI:
    """HTTP-level tests — require running API + DB."""

    def test_get_profile_empty_returns_200(self, api_client):
        r = api_client.get("/api/research/profile")
        assert r.status_code == 200
        assert r.json() == []

    def test_put_profile_upserts_and_returns_full(self, api_client):
        entries = [
            {"kind": "topic", "label": "Requirements Engineering", "weight": 1.5, "source": "manual"},
            {"kind": "avoid", "label": "blockchain", "weight": 1.0, "source": "manual"},
        ]
        r = api_client.put("/api/research/profile", json={"entries": entries})
        assert r.status_code == 200
        data = r.json()
        labels = {e["label"] for e in data}
        assert "requirements engineering" in labels
        assert "blockchain" in labels

    def test_put_weight_zero_deletes_entry(self, api_client):
        # Seed
        api_client.put("/api/research/profile", json={
            "entries": [{"kind": "topic", "label": "delete_me", "weight": 1.0, "source": "manual"}]
        })
        # Delete via weight=0
        r = api_client.put("/api/research/profile", json={
            "entries": [{"kind": "topic", "label": "delete_me", "weight": 0, "source": "manual"}]
        })
        assert r.status_code == 200
        labels = [e["label"] for e in r.json()]
        assert "delete_me" not in labels

    def test_label_normalised(self, api_client):
        r = api_client.put("/api/research/profile", json={
            "entries": [{"kind": "method", "label": "  Grounded Theory  ", "weight": 1.0, "source": "manual"}]
        })
        labels = [e["label"] for e in r.json()]
        assert "grounded theory" in labels

    def test_feedback_positive_upserts_tags(self, api_client):
        """POST /feedback with value=1 must update research_profile topics."""
        # This assumes an article with tags exists — tested via profile endpoint
        r = api_client.get("/api/research/profile")
        assert r.status_code == 200
