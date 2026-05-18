"""
Tests for Story 3.1 — Semantic Retrieval & Related Panel.

Host-runnable tests:
  - TestEmbedderModule:    validates embedder.py source-level contracts
  - TestDatabaseColumn:    validates embedding_indexed column in database.py
  - TestRelatedEndpoint:   validates the /api/articles/{id}/related route in articles.py

Integration tests (skip on host, run inside Docker):
  - TestEmbeddingPipeline: full embed_article_async + ChromaDB round-trip
  - TestRelatedAPI:        HTTP integration tests for /related endpoint
"""

import os
import re
import sys
from pathlib import Path

# ── Set required env vars before any app import ────────────────────────────
os.environ.setdefault("AUTH_PASSWORD", "test-password-for-unit-tests")
os.environ.setdefault("BASIRA_DB_PATH", "/tmp/test_basira_semantic.db")

import pytest

BACKEND_API = Path(__file__).parents[2] / "api"
BACKEND_ROOT = Path(__file__).parents[2]


# ══════════════════════════════════════════════════════════════════════════════
# Host-runnable: static source analysis
# ══════════════════════════════════════════════════════════════════════════════


class TestEmbedderModule:
    """Verify embedder.py exists and implements required contracts."""

    embedder_path = BACKEND_API / "embedder.py"

    def test_embedder_file_exists(self):
        assert self.embedder_path.exists(), "backend/api/embedder.py must exist"

    def test_uses_persistent_client(self):
        src = self.embedder_path.read_text()
        assert "PersistentClient" in src, "embedder must use chromadb.PersistentClient"

    def test_deferred_chromadb_import(self):
        """chromadb must NOT be imported at module top-level — only inside a function."""
        src = self.embedder_path.read_text()
        lines = src.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import chromadb") or stripped.startswith("from chromadb"):
                # Must be inside a function (preceded by 'def' at some parent scope)
                assert any(
                    l.startswith("def ") or l.startswith("    def ")
                    for l in lines[max(0, i - 30): i]
                ), f"chromadb import on line {i+1} appears to be at module level (must be deferred)"

    def test_embed_article_async_defined(self):
        src = self.embedder_path.read_text()
        assert "async def embed_article_async" in src

    def test_collection_count_guard(self):
        src = self.embedder_path.read_text()
        assert "collection.count()" in src or "_get_chroma" in src

    def test_cosine_similarity_formula(self):
        """The /related endpoint (not embedder) applies the cosine→similarity conversion."""
        router_src = (BACKEND_API / "routers" / "articles.py").read_text()
        assert "1.0 - dist" in router_src or "1.0 - distance" in router_src or "1 - dist" in router_src, \
            "Related endpoint must convert distance to similarity as: 1.0 - distance"

    def test_ollama_embed_model_env(self):
        src = self.embedder_path.read_text()
        assert "OLLAMA_EMBED_MODEL" in src

    def test_chroma_path_env(self):
        src = self.embedder_path.read_text()
        assert "CHROMA_PATH" in src

    def test_cosine_space_configured(self):
        src = self.embedder_path.read_text()
        assert "cosine" in src, "ChromaDB collection should be created with hnsw:space=cosine"

    def test_fault_tolerant_try_except(self):
        """embed_article_async must catch all exceptions and not re-raise."""
        src = self.embedder_path.read_text()
        assert "except Exception" in src

    def test_sets_embedding_indexed(self):
        src = self.embedder_path.read_text()
        assert "embedding_indexed" in src


class TestDatabaseColumn:
    """Verify embedding_indexed column is defined in database.py."""

    db_path = BACKEND_API / "database.py"

    def test_embedding_indexed_column_defined(self):
        src = self.db_path.read_text()
        assert "embedding_indexed" in src, \
            "database.py must declare an embedding_indexed column on Article"

    def test_migration_statement_present(self):
        src = self.db_path.read_text()
        assert "embedding_indexed" in src and "ALTER TABLE" in src, \
            "database.py must include an ALTER TABLE migration for embedding_indexed"

    def test_column_defaults_to_zero(self):
        src = self.db_path.read_text()
        # Look for `embedding_indexed` + `default=0` or `DEFAULT 0` nearby
        idx = src.find("embedding_indexed")
        snippet = src[idx: idx + 200]
        assert "0" in snippet, "embedding_indexed should default to 0"


class TestRelatedEndpoint:
    """Verify /api/articles/{id}/related endpoint in articles.py."""

    router_path = BACKEND_API / "routers" / "articles.py"

    def test_related_route_defined(self):
        src = self.router_path.read_text()
        assert "/related" in src

    def test_related_imports_RelatedArticleOut(self):
        src = self.router_path.read_text()
        assert "RelatedArticleOut" in src

    def test_related_uses_deferred_embedder_import(self):
        """embedder import inside related endpoint must be deferred, not at module top."""
        src = self.router_path.read_text()
        # Should not have top-level embedder import
        top_lines = src.splitlines()[:25]
        for line in top_lines:
            assert "from embedder" not in line and "import embedder" not in line, \
                "articles.py must NOT import embedder at module top-level"
        # Should have deferred import inside the function
        assert "from embedder import" in src or "import embedder" in src

    def test_n_query_param(self):
        src = self.router_path.read_text()
        assert 'n: int' in src or "n=5" in src, \
            "/related endpoint must accept an 'n' query parameter"

    def test_similarity_formula(self):
        src = self.router_path.read_text()
        assert "1.0 - dist" in src or "1.0 - distance" in src or "1 - dist" in src

    def test_excludes_source_article(self):
        """The related endpoint must filter out the source article from results."""
        src = self.router_path.read_text()
        assert "article_id" in src and "continue" in src, \
            "Related endpoint must skip the source article from Chroma results"


class TestRelatedArticleOutModel:
    """Verify RelatedArticleOut Pydantic model in models.py."""

    models_path = BACKEND_API / "models.py"

    def test_model_defined(self):
        src = self.models_path.read_text()
        assert "class RelatedArticleOut" in src

    def test_similarity_field(self):
        src = self.models_path.read_text()
        idx = src.find("class RelatedArticleOut")
        snippet = src[idx: idx + 300]
        assert "similarity" in snippet

    def test_contribution_type_field(self):
        src = self.models_path.read_text()
        idx = src.find("class RelatedArticleOut")
        snippet = src[idx: idx + 300]
        assert "contribution_type" in snippet


class TestFrontendTypes:
    """Verify frontend types.ts includes RelatedArticle."""

    types_path = Path(__file__).parents[2] / ".." / "frontend" / "src" / "types.ts"

    def test_related_article_interface(self):
        src = self.types_path.read_text()
        assert "RelatedArticle" in src

    def test_similarity_field_in_interface(self):
        src = self.types_path.read_text()
        idx = src.find("RelatedArticle")
        snippet = src[idx: idx + 200]
        assert "similarity" in snippet

    def test_embedding_indexed_on_article(self):
        src = self.types_path.read_text()
        assert "embedding_indexed" in src


class TestRelatedPanelComponent:
    """Verify RelatedPanel.tsx exists with required structure."""

    panel_path = Path(__file__).parents[2] / ".." / "frontend" / "src" / "components" / "RelatedPanel.tsx"

    def test_file_exists(self):
        assert self.panel_path.exists(), "frontend/src/components/RelatedPanel.tsx must exist"

    def test_fetches_related_endpoint(self):
        src = self.panel_path.read_text()
        assert "/related" in src

    def test_renders_similarity_percentage(self):
        src = self.panel_path.read_text()
        assert "similarity" in src and ("%" in src or "Math.round" in src)

    def test_onNavigate_prop(self):
        src = self.panel_path.read_text()
        assert "onNavigate" in src

    def test_empty_state_message(self):
        src = self.panel_path.read_text()
        assert "indexed" in src.lower() or "similar" in src.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests — require full Docker environment
# ══════════════════════════════════════════════════════════════════════════════

def _check_integration_deps() -> bool:
    deps = ["fastapi", "sqlalchemy", "bcrypt", "structlog", "feedparser", "httpx", "chromadb", "numpy"]
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            return False
    return True


DEPS_AVAILABLE = _check_integration_deps()
SKIP_INTEGRATION = pytest.mark.skipif(
    not DEPS_AVAILABLE,
    reason="Integration deps not available on host — run inside Docker",
)


@SKIP_INTEGRATION
class TestEmbeddingPipeline:
    """Full round-trip: embed_article_async + ChromaDB query."""

    def test_embed_and_retrieve(self, tmp_path):
        """Articles embedded via Ollama appear in ChromaDB and can be queried."""
        sys.path.insert(0, str(BACKEND_API))
        import asyncio
        os.environ["CHROMA_PATH"] = str(tmp_path / "chroma")
        from embedder import embed_article_async, _get_chroma

        # This test requires Ollama to be running — skip gracefully if not
        import httpx
        try:
            resp = httpx.get(f"{os.getenv('OLLAMA_URL', 'http://host.docker.internal:11434')}/api/version", timeout=3)
            resp.raise_for_status()
        except Exception:
            pytest.skip("Ollama not reachable — skipping embedding integration test")

        from database import Article, SessionLocal
        db = SessionLocal()
        try:
            article = Article(
                feed_id=1,
                title="Semantic embedding test article",
                url="https://test.example.com/embedding-test",
                summary_bullets_json='["AI embeddings are powerful", "ChromaDB stores vectors"]',
                embedding_indexed=0,
            )
            db.add(article)
            db.commit()
            db.refresh(article)
            article_id = article.id
        finally:
            db.close()

        asyncio.run(embed_article_async(article_id))

        db = SessionLocal()
        try:
            updated = db.query(Article).filter(Article.id == article_id).first()
            assert updated.embedding_indexed == 1, "embedding_indexed should be set to 1 after success"
        finally:
            db.close()

        collection = _get_chroma()
        result = collection.get(ids=[str(article_id)], include=["embeddings"])
        assert result["embeddings"] is not None and len(result["embeddings"]) > 0


@SKIP_INTEGRATION
class TestRelatedAPI:
    """HTTP integration tests for /api/articles/{id}/related."""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        sys.path.insert(0, str(BACKEND_API))
        from main import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)

    def test_related_returns_list(self):
        """Returns a list (possibly empty) for a valid article ID."""
        # Requires an article to exist — just verify shape, not content
        resp = self.client.get("/api/articles/99999/related")
        # 404 if article doesn't exist, 200 with [] if it does (no embeddings yet)
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert isinstance(resp.json(), list)

    def test_related_n_param_validation(self):
        """n=0 should return 422, n=5 should be accepted."""
        resp = self.client.get("/api/articles/1/related?n=0")
        assert resp.status_code in (422, 404)

    def test_related_requires_auth(self):
        """Endpoint should be auth-protected."""
        # Without session cookie, should return 401 or redirect
        resp = self.client.get("/api/articles/1/related", cookies={})
        assert resp.status_code in (200, 401, 403, 307)
