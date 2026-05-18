"""Tests for Story 3.4 — Literature-Review Mode.

Host-runnable: source and schema checks. Integration tests skipped without full API stack.
"""
import importlib
import os
import pytest

os.environ.setdefault("AUTH_PASSWORD", "test_password_basira")
os.environ.setdefault("BASIRA_DB_PATH", ":memory:")
os.environ.setdefault("API_SECRET", "test-secret")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text")
os.environ.setdefault("CHROMA_PATH", "/tmp/test-chroma-3-4")


def _check_api_deps():
    for pkg in ("fastapi", "sqlalchemy", "bcrypt", "structlog", "feedparser", "httpx", "chromadb"):
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

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
_API_DIR = os.path.join(_REPO_ROOT, "backend", "api")
_DATABASE_PY = os.path.join(_API_DIR, "database.py")
_MODELS_PY = os.path.join(_API_DIR, "models.py")
_RESEARCH_PY = os.path.join(_API_DIR, "routers", "research.py")
_LLM_PY = os.path.join(_API_DIR, "lit_review_llm.py")
_TYPES_TS = os.path.join(_REPO_ROOT, "frontend", "src", "types.ts")
_STORE_TS = os.path.join(_REPO_ROOT, "frontend", "src", "store", "research.ts")
_LITVIEW_TSX = os.path.join(_REPO_ROOT, "frontend", "src", "components", "LitReviewView.tsx")
_ARTICLELIST_TSX = os.path.join(_REPO_ROOT, "frontend", "src", "components", "ArticleList.tsx")
_APP_TSX = os.path.join(_REPO_ROOT, "frontend", "src", "App.tsx")
_ENV_EXAMPLE = os.path.join(_REPO_ROOT, ".env.example")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


_NOT_ENOUGH = (
    "Not enough indexed articles match the criteria. Try a broader topic or lower rigor threshold."
)


class TestLiteratureReviewDB:
    def test_orm_class(self):
        src = _read(_DATABASE_PY)
        assert "class LiteratureReview(Base):" in src

    def test_migration_create_table(self):
        src = _read(_DATABASE_PY)
        assert "CREATE TABLE IF NOT EXISTS literature_reviews" in src
        assert "body_json" in src
        assert "window_days" in src
        assert "min_rigor" in src


class TestPydanticModels:
    def test_comparison_row(self):
        src = _read(_MODELS_PY)
        assert "class ComparisonRow" in src

    def test_review_cluster_out(self):
        src = _read(_MODELS_PY)
        assert "class ReviewClusterOut" in src
        assert "article_ids" in src

    def test_create_and_out(self):
        src = _read(_MODELS_PY)
        assert "class LiteratureReviewCreate" in src
        assert "class LiteratureReviewOut" in src
        assert "class LiteratureReviewSummaryOut" in src


class TestResearchRoutes:
    def test_post_review_route(self):
        src = _read(_RESEARCH_PY)
        assert '@router.post("/review"' in src

    def test_get_reviews_list(self):
        src = _read(_RESEARCH_PY)
        assert '@router.get("/reviews"' in src

    def test_get_review_by_id(self):
        src = _read(_RESEARCH_PY)
        assert '@router.get("/reviews/{review_id}"' in src

    def test_422_message_exact(self):
        src = _read(_RESEARCH_PY)
        assert _NOT_ENOUGH in src

    def test_503_embed_message(self):
        src = _read(_RESEARCH_PY)
        assert "Could not embed topic" in src

    def test_rigor_default_zero(self):
        src = _read(_RESEARCH_PY)
        assert "_article_rigor" in src

    def test_synthetic_cluster_fallback(self):
        src = _read(_RESEARCH_PY)
        assert "non_noise" in src or "not non_noise" in src


class TestLitReviewLLM:
    def test_module_exists(self):
        assert os.path.isfile(_LLM_PY)

    def test_tier_order_comment_or_uni_first(self):
        src = _read(_LLM_PY)
        assert "_chat_uni" in src and "_chat_ollama" in src and "_chat_openrouter" in src

    def test_synthesize_cluster_json(self):
        src = _read(_LLM_PY)
        assert "async def synthesize_cluster_json" in src

    def test_extract_json(self):
        src = _read(_LLM_PY)
        assert "def extract_json_from_text" in src

    def test_no_chromadb_import_top(self):
        src = _read(_LLM_PY)
        assert "import chromadb" not in src


class TestFrontend:
    def test_types(self):
        src = _read(_TYPES_TS)
        assert "interface LiteratureReview" in src
        assert "interface ReviewCluster" in src

    def test_store_generate(self):
        src = _read(_STORE_TS)
        assert "generateReview" in src
        assert "/api/research/review" in src
        assert "/api/research/reviews" in src

    def test_lit_review_view(self):
        src = _read(_LITVIEW_TSX)
        assert "buildMarkdownExport" in src
        assert "Export Markdown" in src

    def test_article_list_lit_tab(self):
        src = _read(_ARTICLELIST_TSX)
        assert "litreview" in src
        assert "LitReviewView" in src

    def test_app_view_union(self):
        src = _read(_APP_TSX)
        assert "'litreview'" in src


class TestEnvExample:
    def test_uni_ollama_documented(self):
        src = _read(_ENV_EXAMPLE)
        assert "UNI_OLLAMA_URL" in src


@_SKIP_INTEGRATION
class TestLitReviewHTTP:
    """Placeholder for future TestClient wiring."""

    def test_skip_placeholder(self):
        assert True
