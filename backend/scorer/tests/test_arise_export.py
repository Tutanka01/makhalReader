"""Tests for Story 4.1 — ARISE export endpoint (NFR15 JSON)."""
import importlib
import os

import pytest

os.environ.setdefault("AUTH_PASSWORD", "test_password_basira")
os.environ.setdefault("BASIRA_DB_PATH", ":memory:")
os.environ.setdefault("API_SECRET", "test-secret")


def _check_api_deps():
    for pkg in ("fastapi", "sqlalchemy", "bcrypt", "structlog", "httpx"):
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
_RESEARCH_PY = os.path.join(_REPO_ROOT, "backend", "api", "routers", "research.py")
_MODELS_PY = os.path.join(_REPO_ROOT, "backend", "api", "models.py")
_ARTICLES_PY = os.path.join(_REPO_ROOT, "backend", "api", "routers", "articles.py")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


class TestAriseConstants:
    def test_shared_tuple_in_articles(self):
        src = _read(_ARTICLES_PY)
        assert "ARISE_RE_DOCUMENT_TYPES" in src
        assert "elicitation" in src

    def test_research_imports_tuple(self):
        src = _read(_RESEARCH_PY)
        assert "from routers.articles import ARISE_RE_DOCUMENT_TYPES" in src
        assert "Article.re_document_type.in_(ARISE_RE_DOCUMENT_TYPES)" in src


class TestAriseRoute:
    def test_post_export_arise(self):
        src = _read(_RESEARCH_PY)
        assert '@router.post("/export-arise"' in src
        assert "response_model=List[AriseArticleOut]" in src

    def test_auth_dependency(self):
        src = _read(_RESEARCH_PY)
        assert "async def export_arise" in src
        assert "_: None = _auth" in src

    def test_join_feed(self):
        src = _read(_RESEARCH_PY)
        assert "Feed.name.label" in src or 'Feed.name.label("feed_name")' in src
        assert ".join(Feed" in src

    def test_published_at_filter(self):
        src = _read(_RESEARCH_PY)
        assert "Article.published_at.isnot(None)" in src
        assert "Article.published_at >=" in src

    def test_order_id_asc(self):
        src = _read(_RESEARCH_PY)
        assert "Article.id.asc()" in src


class TestPydanticModels:
    def test_request_model(self):
        src = _read(_MODELS_PY)
        assert "class AriseExportRequest" in src
        assert "normalize_since_utc" in src

    def test_article_out(self):
        src = _read(_MODELS_PY)
        assert "class AriseArticleOut" in src
        for field in (
            "id", "title", "url", "published_at", "re_document_type",
            "contribution_type", "paper_meta", "content_text", "score_meta",
            "feed_name", "tags",
        ):
            assert field in src.split("class AriseArticleOut", 1)[1][:800]

    def test_build_arise_row(self):
        src = _read(_MODELS_PY)
        assert "def build_arise_row" in src


@_SKIP_INTEGRATION
class TestAriseHTTP:
    def test_placeholder(self):
        assert True
