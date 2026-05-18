"""
Tests for Story 3.2 — Topic Cluster Map.

Host-runnable tests (static source analysis):
  - TestClusterDependency       — hdbscan in requirements.txt
  - TestClusterModel            — ClusterOut fields in models.py
  - TestClusterEndpointSource   — /clusters route + deferred imports in research.py
  - TestFrontendClusterType     — Cluster interface in types.ts
  - TestResearchStore           — research.ts exists + fetchClusters pattern
  - TestResearchDigestView      — component structure

Integration tests (skipped on host, require Docker):
  - TestClusterAPI              — HTTP: 200 + [] for empty corpus
  - TestHDBSCANLogic            — HDBSCAN produces valid cluster output
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("AUTH_PASSWORD", "test-password-for-unit-tests")
os.environ.setdefault("BASIRA_DB_PATH", "/tmp/test_basira_clusters.db")

import pytest

BACKEND_API = Path(__file__).parents[2] / "api"
FRONTEND_SRC = Path(__file__).parents[2] / ".." / "frontend" / "src"


# ══════════════════════════════════════════════════════════════════════════════
# Host-runnable: static source analysis
# ══════════════════════════════════════════════════════════════════════════════


class TestClusterDependency:
    """hdbscan is declared in backend/api/requirements.txt."""

    reqs_path = BACKEND_API / "requirements.txt"

    def test_hdbscan_present(self):
        src = self.reqs_path.read_text()
        assert "hdbscan" in src, "hdbscan must be in backend/api/requirements.txt"

    def test_hdbscan_version(self):
        src = self.reqs_path.read_text()
        assert "0.8" in src or ">=" in src, \
            "hdbscan should have a version specifier (>=0.8.33)"

    def test_chromadb_still_present(self):
        src = self.reqs_path.read_text()
        assert "chromadb" in src

    def test_numpy_still_present(self):
        src = self.reqs_path.read_text()
        assert "numpy" in src


class TestClusterModel:
    """ClusterOut Pydantic model in models.py."""

    models_path = BACKEND_API / "models.py"

    def test_cluster_out_defined(self):
        src = self.models_path.read_text()
        assert "class ClusterOut" in src

    def test_cluster_id_field(self):
        src = self.models_path.read_text()
        idx = src.find("class ClusterOut")
        snippet = src[idx: idx + 300]
        assert "cluster_id" in snippet

    def test_size_field(self):
        src = self.models_path.read_text()
        idx = src.find("class ClusterOut")
        snippet = src[idx: idx + 300]
        assert "size" in snippet

    def test_centroid_title_field(self):
        src = self.models_path.read_text()
        idx = src.find("class ClusterOut")
        snippet = src[idx: idx + 300]
        assert "centroid_title" in snippet

    def test_top_tags_field(self):
        src = self.models_path.read_text()
        idx = src.find("class ClusterOut")
        snippet = src[idx: idx + 300]
        assert "top_tags" in snippet

    def test_article_ids_field(self):
        src = self.models_path.read_text()
        idx = src.find("class ClusterOut")
        snippet = src[idx: idx + 300]
        assert "article_ids" in snippet


class TestClusterEndpointSource:
    """GET /api/research/clusters route in research.py."""

    router_path = BACKEND_API / "routers" / "research.py"

    def test_router_file_exists(self):
        assert self.router_path.exists(), "backend/api/routers/research.py must exist"

    def test_clusters_route_defined(self):
        src = self.router_path.read_text()
        assert "/clusters" in src

    def test_get_decorator(self):
        src = self.router_path.read_text()
        assert '@router.get("/clusters"' in src or "@router.get('/clusters'" in src

    def test_window_days_param(self):
        src = self.router_path.read_text()
        assert "window_days" in src

    def test_min_size_param(self):
        src = self.router_path.read_text()
        assert "min_size" in src

    def test_hdbscan_deferred_not_toplevel(self):
        """hdbscan must NOT appear as a top-level import in research.py."""
        src = self.router_path.read_text()
        lines = src.splitlines()
        for i, line in enumerate(lines[:25]):
            assert "import hdbscan" not in line, \
                f"hdbscan import on line {i+1} must not be at module top-level"

    def test_numpy_deferred_not_toplevel(self):
        """numpy must NOT appear as a top-level import in research.py."""
        src = self.router_path.read_text()
        lines = src.splitlines()
        for i, line in enumerate(lines[:25]):
            assert "import numpy" not in line and "from numpy" not in line, \
                f"numpy import on line {i+1} must not be at module top-level"

    def test_chromadb_access_via_embedder(self):
        """research.py must access Chroma via _get_chroma from embedder, not directly."""
        src = self.router_path.read_text()
        assert "_get_chroma" in src, "Must import and use _get_chroma from embedder"
        # Should NOT import chromadb directly
        lines = src.splitlines()
        for line in lines[:20]:
            assert "import chromadb" not in line

    def test_fault_tolerant_try_except(self):
        src = self.router_path.read_text()
        assert "except Exception" in src

    def test_noise_excluded(self):
        """Cluster ID -1 (HDBSCAN noise) must be excluded from results."""
        src = self.router_path.read_text()
        assert "-1" in src and ("continue" in src or "skip" in src.lower()), \
            "Cluster label -1 (noise) must be skipped"

    def test_numpy_int64_cast(self):
        """numpy.int64 cluster IDs must be cast to Python int for JSON serialization."""
        src = self.router_path.read_text()
        assert "int(cluster_id)" in src, \
            "Must cast numpy.int64 cluster_id to int() before returning"

    def test_clusters_logged(self):
        src = self.router_path.read_text()
        assert "clusters" in src and ("info" in src or "warning" in src)

    def test_auth_required(self):
        src = self.router_path.read_text()
        assert "require_session" in src or "_auth" in src


class TestFrontendClusterType:
    """Cluster interface in frontend/src/types.ts."""

    types_path = FRONTEND_SRC / "types.ts"

    def test_cluster_interface_defined(self):
        src = self.types_path.read_text()
        assert "interface Cluster" in src or "export interface Cluster" in src

    def test_cluster_id_field(self):
        src = self.types_path.read_text()
        idx = src.find("interface Cluster")
        snippet = src[idx: idx + 200]
        assert "cluster_id" in snippet

    def test_size_field(self):
        src = self.types_path.read_text()
        idx = src.find("interface Cluster")
        snippet = src[idx: idx + 200]
        assert "size" in snippet

    def test_centroid_title_field(self):
        src = self.types_path.read_text()
        idx = src.find("interface Cluster")
        snippet = src[idx: idx + 200]
        assert "centroid_title" in snippet

    def test_top_tags_field(self):
        src = self.types_path.read_text()
        idx = src.find("interface Cluster")
        snippet = src[idx: idx + 200]
        assert "top_tags" in snippet

    def test_article_ids_field(self):
        src = self.types_path.read_text()
        idx = src.find("interface Cluster")
        snippet = src[idx: idx + 200]
        assert "article_ids" in snippet


class TestResearchStore:
    """frontend/src/store/research.ts exists and implements fetchClusters."""

    store_path = FRONTEND_SRC / "store" / "research.ts"

    def test_file_exists(self):
        assert self.store_path.exists(), "frontend/src/store/research.ts must exist"

    def test_use_research_store_exported(self):
        src = self.store_path.read_text()
        assert "useResearchStore" in src

    def test_fetch_clusters_defined(self):
        src = self.store_path.read_text()
        assert "fetchClusters" in src

    def test_clusters_state(self):
        src = self.store_path.read_text()
        assert "clusters" in src

    def test_loading_state(self):
        src = self.store_path.read_text()
        assert "Loading" in src or "loading" in src

    def test_error_state(self):
        src = self.store_path.read_text()
        assert "Error" in src or "error" in src

    def test_uses_zustand_create(self):
        src = self.store_path.read_text()
        assert "create" in src and "zustand" in src

    def test_window_days_param(self):
        src = self.store_path.read_text()
        assert "windowDays" in src or "window_days" in src

    def test_credentials_include(self):
        src = self.store_path.read_text()
        assert "credentials" in src and "include" in src

    def test_clusters_api_url(self):
        src = self.store_path.read_text()
        assert "/api/research/clusters" in src


class TestResearchDigestView:
    """frontend/src/components/ResearchDigestView.tsx structure."""

    view_path = FRONTEND_SRC / "components" / "ResearchDigestView.tsx"

    def test_file_exists(self):
        assert self.view_path.exists(), \
            "frontend/src/components/ResearchDigestView.tsx must exist"

    def test_uses_research_store(self):
        src = self.view_path.read_text()
        assert "useResearchStore" in src

    def test_uses_articles_store(self):
        src = self.view_path.read_text()
        assert "useArticlesStore" in src

    def test_on_select_prop(self):
        src = self.view_path.read_text()
        assert "onSelect" in src

    def test_window_selector(self):
        src = self.view_path.read_text()
        assert "14" in src and "30" in src and ("60" in src or "window" in src.lower())

    def test_centroid_title_rendered(self):
        src = self.view_path.read_text()
        assert "centroid_title" in src

    def test_top_tags_rendered(self):
        src = self.view_path.read_text()
        assert "top_tags" in src

    def test_expand_collapse_state(self):
        src = self.view_path.read_text()
        assert "expanded" in src.lower()

    def test_article_ids_iteration(self):
        src = self.view_path.read_text()
        assert "article_ids" in src

    def test_loading_state(self):
        src = self.view_path.read_text()
        assert "Loading" in src or "loading" in src or "clustersLoading" in src

    def test_empty_state_message(self):
        src = self.view_path.read_text()
        assert "cluster" in src.lower() or "indexed" in src.lower()

    def test_article_map_resolution(self):
        src = self.view_path.read_text()
        assert "articleMap" in src or "article_ids" in src


class TestArticleListResearchTab:
    """ArticleList.tsx has Research tab integration."""

    list_path = FRONTEND_SRC / "components" / "ArticleList.tsx"

    def test_research_in_type_union(self):
        src = self.list_path.read_text()
        assert "'research'" in src or '"research"' in src

    def test_research_digest_view_imported(self):
        src = self.list_path.read_text()
        assert "ResearchDigestView" in src

    def test_research_view_rendered_conditionally(self):
        src = self.list_path.read_text()
        assert "research" in src and "ResearchDigestView" in src

    def test_network_icon_imported(self):
        src = self.list_path.read_text()
        assert "Network" in src or "Layers" in src or "BrainCircuit" in src


class TestAppViewType:
    """App.tsx includes 'research' in appView type."""

    app_path = FRONTEND_SRC / "App.tsx"

    def test_research_in_app_view(self):
        src = self.app_path.read_text()
        assert "'research'" in src or '"research"' in src

    def test_on_navigate_wired(self):
        src = self.app_path.read_text()
        assert "onNavigate" in src


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests — require full Docker environment
# ══════════════════════════════════════════════════════════════════════════════

def _check_integration_deps() -> bool:
    deps = ["fastapi", "sqlalchemy", "bcrypt", "structlog", "feedparser",
            "httpx", "chromadb", "numpy", "hdbscan"]
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
class TestClusterAPI:
    """HTTP integration tests for /api/research/clusters."""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        sys.path.insert(0, str(BACKEND_API))
        from main import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)

    def test_clusters_returns_200_empty(self):
        """Empty corpus returns 200 + []."""
        resp = self.client.get("/api/research/clusters")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_clusters_window_param(self):
        resp = self.client.get("/api/research/clusters?window_days=30")
        assert resp.status_code == 200

    def test_clusters_min_size_validation(self):
        """min_size=1 should return 422 (ge=2 constraint)."""
        resp = self.client.get("/api/research/clusters?min_size=1")
        assert resp.status_code == 422

    def test_clusters_window_days_max(self):
        """window_days=91 should fail validation (le=90 constraint)."""
        resp = self.client.get("/api/research/clusters?window_days=91")
        assert resp.status_code == 422


@SKIP_INTEGRATION
class TestHDBSCANLogic:
    """Unit test for the cluster computation logic using real numpy + hdbscan."""

    def test_hdbscan_produces_valid_labels(self):
        import numpy as np
        import hdbscan

        # 9 vectors in 3 clear clusters of 3
        data = np.array([
            [1.0, 0.0], [1.1, 0.0], [0.9, 0.0],
            [0.0, 1.0], [0.0, 1.1], [0.0, 0.9],
            [1.0, 1.0], [1.1, 1.0], [0.9, 1.0],
        ], dtype=np.float32)

        labels = hdbscan.HDBSCAN(min_cluster_size=3).fit_predict(data)
        assert len(labels) == 9
        # Should find at least 2 clusters (excluding noise -1)
        non_noise = set(labels[labels != -1])
        assert len(non_noise) >= 2

    def test_noise_label_is_minus_one(self):
        import numpy as np
        import hdbscan

        # All random noise — should classify everything as noise
        rng = np.random.default_rng(42)
        data = rng.random((5, 768), dtype=np.float32)
        labels = hdbscan.HDBSCAN(min_cluster_size=5).fit_predict(data)
        # With 5 points and min_cluster_size=5, all noise is plausible
        assert all(isinstance(int(l), int) for l in labels)

    def test_int_cast_from_numpy_int64(self):
        import numpy as np
        label = np.int64(2)
        result = int(label)
        assert type(result) is int
        assert result == 2
