"""Tests for /api/internal/provider-sources and poll endpoints (Story 12-6)."""

import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock

os.environ["DB_PATH"] = "/tmp/test_provider_sources_internal.db"
os.environ["AUTH_EMAIL"] = "admin@basira.local"
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")

_api_dir = os.path.join(os.path.dirname(__file__))
_extractor_dir = os.path.join(_api_dir, "..", "extractor")
for p in [_api_dir, _extractor_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Save real httpx
import httpx as _real_httpx
sys.modules["httpx"] = MagicMock()

from database import Base, SessionLocal, engine, init_db
from sqlalchemy import text
from datetime import datetime, timezone

import net_guard
net_guard.check_url = MagicMock()

# Build minimal test app with internal router
from fastapi import FastAPI

from routers.internal import router as internal_router

app = FastAPI()
app.include_router(internal_router)

# Restore real httpx for TestClient
sys.modules["httpx"] = _real_httpx
from fastapi.testclient import TestClient

API_SECRET = "changeme"

def _reset_db():
    Base.metadata.drop_all(bind=engine)
    init_db()

def _get_client():
    return TestClient(app)

def _auth_headers(override_secret: str | None = None) -> dict:
    return {"X-Internal-Secret": override_secret or API_SECRET}

def _seed_user(user_id: int):
    db = SessionLocal()
    try:
        existing = db.execute(text("SELECT id FROM users WHERE id=:id"), {"id": user_id}).fetchone()
        if not existing:
            db.execute(
                text("INSERT INTO users (id, email, password_hash, display_name, role, onboarding_done, created_at) VALUES (:id, :email, '', :name, 'user', 1, :now)"),
                {"id": user_id, "email": f"user{user_id}@test.local", "name": f"User{user_id}", "now": datetime.now(timezone.utc)},
            )
            db.commit()
    finally:
        db.close()

def _seed_source(source_id: int, provider: str = "arxiv", name: str = "Test Source", category: str = "preprint"):
    db = SessionLocal()
    try:
        db.execute(
            text("""INSERT OR IGNORE INTO sources (id, name, provider, query_json, category, active, created_at) VALUES (:id, :name, :provider, :qjson, :cat, 1, :now)"""),
            {"id": source_id, "name": name, "provider": provider, "qjson": json.dumps({"search_query": "cat:cs.AI"}), "cat": category, "now": datetime.now(timezone.utc)},
        )
        db.commit()
    finally:
        db.close()

def _seed_rss_source(source_id: int):
    """Create an RSS-type source (provider='rss') for the 'cannot poll RSS via this endpoint' test."""
    db = SessionLocal()
    try:
        feed = db.execute(text("SELECT id FROM feeds WHERE id=:id"), {"id": source_id}).fetchone()
        if not feed:
            db.execute(
                text("INSERT INTO feeds (id, url, name, category, active) VALUES (:id, :url, :name, :cat, 1)"),
                {"id": source_id, "url": "https://example.com/rss", "name": "RSS Feed", "cat": "General"},
            )
            db.commit()
        db.execute(
            text("""INSERT OR IGNORE INTO sources (id, name, provider, query_json, category, active, created_at) VALUES (:id, :name, 'rss', :qjson, :cat, 1, :now)"""),
            {"id": source_id, "name": "RSS Feed", "qjson": json.dumps({"url": "https://example.com/rss"}), "cat": "General", "now": datetime.now(timezone.utc)},
        )
        db.commit()
    finally:
        db.close()

def _seed_user_subscription(user_id: int, source_id: int):
    _seed_user(user_id)
    db = SessionLocal()
    try:
        db.execute(
            text("INSERT OR IGNORE INTO user_source_subscriptions (user_id, source_id, created_at) VALUES (:uid, :sid, :now)"),
            {"uid": user_id, "sid": source_id, "now": datetime.now(timezone.utc)},
        )
        db.commit()
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_provider_sources_list_empty():
    _reset_db()
    client = _get_client()
    resp = client.get("/api/internal/provider-sources", headers=_auth_headers())
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    assert len(data) == 0, f"Expected empty, got {len(data)}"


def test_provider_sources_list_has_sources():
    _reset_db()
    _seed_source(101, provider="arxiv", name="arXiv cs.AI")
    _seed_source(102, provider="openalex", name="OpenAlex ICSE")
    _seed_user_subscription(1, 101)

    client = _get_client()
    resp = client.get("/api/internal/provider-sources", headers=_auth_headers())
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    names = {s["name"] for s in data}
    assert "arXiv cs.AI" in names, f"Missing arXiv source: {names}"
    assert "OpenAlex ICSE" in names, f"Missing OpenAlex source: {names}"


def test_provider_sources_list_excludes_rss():
    _reset_db()
    _seed_rss_source(201)
    client = _get_client()
    resp = client.get("/api/internal/provider-sources", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 0, f"RSS source should be excluded, got {len(data)}"


def test_provider_sources_list_requires_auth():
    _reset_db()
    client = _get_client()
    resp = client.get("/api/internal/provider-sources", headers={"X-Internal-Secret": "wrong"})
    assert resp.status_code == 403


def test_poll_provider_source_requires_auth():
    _reset_db()
    client = _get_client()
    resp = client.post("/api/internal/sources/1/poll", headers={"X-Internal-Secret": "wrong"})
    assert resp.status_code == 403


def test_poll_provider_source_not_found():
    _reset_db()
    client = _get_client()
    resp = client.post("/api/internal/sources/999/poll", headers=_auth_headers())
    assert resp.status_code == 404


def test_poll_provider_source_rejects_rss():
    _reset_db()
    _seed_rss_source(301)
    client = _get_client()
    resp = client.post("/api/internal/sources/301/poll", headers=_auth_headers())
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    assert "RSS" in resp.text


def test_poll_arxiv_source_creates_articles():
    """Mock ArxivProvider.fetch() to return sample articles, verify they're created."""
    _reset_db()
    _seed_source(401, provider="arxiv", name="arXiv cs.AI")
    _seed_user_subscription(1, 401)

    from providers.arxiv import ArxivProvider
    original_fetch = ArxivProvider.fetch

    async def mock_fetch(self, source):
        from types import SimpleNamespace
        return [
            SimpleNamespace(external_id="1", title="Paper A", url="https://arxiv.org/abs/2401.00001", summary="Abstract A", author="Author A", published_at="2024-01-01T00:00:00Z"),
            SimpleNamespace(external_id="2", title="Paper B", url="https://arxiv.org/abs/2401.00002", summary="Abstract B", author="Author B", published_at="2024-01-02T00:00:00Z"),
        ]

    ArxivProvider.fetch = mock_fetch
    try:
        client = _get_client()
        resp = client.post("/api/internal/sources/401/poll", headers=_auth_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["total"] == 2, f"Expected 2 created, got {data}"
        assert len(data["created"]) == 2
        assert data["created"][0]["title"] == "Paper A"
        assert data["created"][1]["title"] == "Paper B"
    finally:
        ArxivProvider.fetch = original_fetch

    # Verify articles exist in DB
    from database import SessionLocal as _sl
    db = _sl()
    try:
        articles = db.execute(text("SELECT id, title, url, source_id FROM articles WHERE source_id=401")).fetchall()
        assert len(articles) == 2, f"Expected 2 articles in DB, got {len(articles)}"
        titles = {r[1] for r in articles}
        assert "Paper A" in titles
        assert "Paper B" in titles
    finally:
        db.close()


def test_poll_provider_source_dedup():
    """Second poll with same articles should not create duplicates."""
    _reset_db()
    _seed_source(501, provider="arxiv", name="arXiv cs.AI")
    _seed_user_subscription(1, 501)

    from providers.arxiv import ArxivProvider
    original_fetch = ArxivProvider.fetch

    async def mock_fetch(self, source):
        from types import SimpleNamespace
        return [
            SimpleNamespace(external_id="1", title="Paper A", url="https://arxiv.org/abs/2401.00001", summary="Abstract A", author="Author A", published_at=None),
        ]

    ArxivProvider.fetch = mock_fetch
    try:
        client = _get_client()

        # First poll
        resp1 = client.post("/api/internal/sources/501/poll", headers=_auth_headers())
        assert resp1.status_code == 200
        assert resp1.json()["total"] == 1

        # Second poll — should return 0 new
        resp2 = client.post("/api/internal/sources/501/poll", headers=_auth_headers())
        assert resp2.status_code == 200
        assert resp2.json()["total"] == 0, f"Expected 0 new, got {resp2.json()}"
    finally:
        ArxivProvider.fetch = original_fetch


if __name__ == "__main__":
    tests = [
        test_provider_sources_list_empty,
        test_provider_sources_list_has_sources,
        test_provider_sources_list_excludes_rss,
        test_provider_sources_list_requires_auth,
        test_poll_provider_source_requires_auth,
        test_poll_provider_source_not_found,
        test_poll_provider_source_rejects_rss,
        test_poll_arxiv_source_creates_articles,
        test_poll_provider_source_dedup,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  \u2705  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  \u274c  {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    total = passed + failed
    print(f"\n{'='*40}")
    print(f"  {passed}/{total} passed")
    if failed:
        print(f"  \u274c  {failed} FAILED")
        sys.exit(1)
    else:
        print(f"  \u2705  ALL PASSED")
