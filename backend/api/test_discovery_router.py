"""Tests for Story 13-3 — Discovery API Router.

Verifies:
- POST /api/discovery/expand returns ExpandResult JSON (AC1).
- Rate limiting yields HTTP 429 + Retry-After header (AC2).
- POST /api/discovery/resolve returns DiscoveryPack JSON (AC3).
- Unauthenticated requests rejected 401/403 (AC4).
- Resolve gracefully degrades on invalid input (AC5).
"""

import json
import os
import sys
from unittest.mock import AsyncMock

os.environ["DB_PATH"] = "/tmp/test_discovery_router.db"
os.environ["AUTH_PASSWORD"] = "testpass"
os.environ["AUTH_EMAIL"] = "admin@basira.local"
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")
os.environ["EXPAND_RATE_LIMIT"] = "3"  # small limit for fast tests
os.environ["EXPAND_RATE_WINDOW_SECONDS"] = "3600"

_api_dir = os.path.join(os.path.dirname(__file__))
_extractor_dir = os.path.join(_api_dir, "..", "extractor")
for p in [_api_dir, _extractor_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from database import Base, SessionLocal, engine, init_db
from auth import create_session

# Build minimal test app
from fastapi import FastAPI

from routers.discovery import router as discovery_router
from routers.discovery import _reset_expand_rate_limits
from services import source_discovery

app = FastAPI()
app.include_router(discovery_router)

from fastapi.testclient import TestClient


def _reset_db():
    from sqlalchemy import text as _t
    with engine.connect() as c:
        c.execute(_t("PRAGMA foreign_keys = OFF"))
        c.commit()
        Base.metadata.drop_all(bind=c)
        c.execute(_t("PRAGMA foreign_keys = ON"))
        c.commit()
    init_db()


def _seed_user(user_id: int):
    from datetime import datetime, timezone
    from sqlalchemy import text
    from database import engine as _eng
    with _eng.connect() as c:
        existing = c.execute(text("SELECT id FROM users WHERE id=:uid"), {"uid": user_id}).fetchone()
        if not existing:
            c.execute(
                text("INSERT INTO users (id, email, password_hash, display_name, role, onboarding_done, created_at) VALUES (:id, :email, '', :name, 'user', 1, :now)"),
                {"id": user_id, "email": f"user{user_id}@test.local", "name": f"User{user_id}", "now": datetime.now(timezone.utc)},
            )
            c.commit()


def _auth_headers(client, user_id: int = 1) -> dict:
    _seed_user(user_id)
    session = create_session(user_id=user_id, remember=False, user_agent="test")
    return {"Cookie": f"basira_sid={session}"}


def _get_client():
    return TestClient(app)


_EXPAND_RESULT = {
    "field_label": "Computational Linguistics",
    "concepts": ["NLP", "transformers", "BERT"],
    "venue_keywords": ["ACL", "EMNLP"],
    "author_keywords": ["Jurafsky", "Manning"],
    "query_terms": ["natural language processing", "deep learning"],
    "language": "en",
    "degraded": False,
}

_DISCOVERY_PACK = {
    "sources": [
        {"name": "ACL Anthology", "provider": "openalex", "query_json": {}, "provenance_url": "https://example.com/acl", "verified": True, "label": "journal", "unverifiable": False},
    ],
    "venues": [
        {"name": "ACL", "provider": "openalex", "query_json": {}, "provenance_url": "", "verified": False, "label": "venue", "unverifiable": False},
    ],
    "authors": [],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_expand_returns_result():
    _reset_db()
    _reset_expand_rate_limits()
    original = source_discovery.expand
    source_discovery.expand = AsyncMock(return_value=source_discovery.ExpandResult.model_validate(_EXPAND_RESULT))
    try:
        client = _get_client()
        headers = _auth_headers(client)
        resp = client.post("/api/discovery/expand", json={"thesis_text": "Study of NLP"}, headers=headers)
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["field_label"] == "Computational Linguistics"
        assert body["degraded"] is False
        assert len(body["concepts"]) == 3
    finally:
        source_discovery.expand = original


def test_expand_requires_auth():
    _reset_db()
    _reset_expand_rate_limits()
    client = _get_client()
    resp = client.post("/api/discovery/expand", json={"thesis_text": "x"})
    assert resp.status_code in (401, 403), f"Expected 401/403 got {resp.status_code}"


def test_expand_rate_limit():
    _reset_db()
    _reset_expand_rate_limits()
    original = source_discovery.expand
    source_discovery.expand = AsyncMock(return_value=source_discovery.ExpandResult.model_validate(_EXPAND_RESULT))
    try:
        client = _get_client()
        headers = _auth_headers(client)
        for i in range(3):
            resp = client.post("/api/discovery/expand", json={"thesis_text": f"variant {i}"}, headers=headers)
            assert resp.status_code == 200, f"Call {i} failed: {resp.status_code}"
        resp = client.post("/api/discovery/expand", json={"thesis_text": "overflow"}, headers=headers)
        assert resp.status_code == 429, f"Expected 429 got {resp.status_code}"
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert 1 <= retry_after <= 3600
    finally:
        source_discovery.expand = original


def test_expand_degraded_lives_on():
    """Even degraded results flow back to the client correctly."""
    _reset_db()
    _reset_expand_rate_limits()
    degraded = source_discovery.ExpandResult(field_label="NLP", degraded=True)
    original = source_discovery.expand
    source_discovery.expand = AsyncMock(return_value=degraded)
    try:
        client = _get_client()
        headers = _auth_headers(client)
        resp = client.post("/api/discovery/expand", json={"thesis_text": "x"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["degraded"] is True
        assert resp.json()["field_label"] == "NLP"
    finally:
        source_discovery.expand = original


def test_resolve_returns_pack():
    _reset_db()
    _reset_expand_rate_limits()
    original = source_discovery.resolve_verify_rank
    source_discovery.resolve_verify_rank = AsyncMock(
        return_value=source_discovery.DiscoveryPack.model_validate(_DISCOVERY_PACK)
    )
    try:
        client = _get_client()
        headers = _auth_headers(client)
        resp = client.post(
            "/api/discovery/resolve",
            json={"expand_result": _EXPAND_RESULT},
            headers=headers,
        )
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert len(body["sources"]) == 1
        assert body["sources"][0]["name"] == "ACL Anthology"
        assert len(body["venues"]) == 1
        assert len(body["authors"]) == 0
    finally:
        source_discovery.resolve_verify_rank = original


def test_resolve_requires_auth():
    _reset_db()
    client = _get_client()
    resp = client.post("/api/discovery/resolve", json={"expand_result": _EXPAND_RESULT})
    assert resp.status_code in (401, 403)


def test_resolve_graceful_on_bad_input():
    _reset_db()
    _reset_expand_rate_limits()
    client = _get_client()
    headers = _auth_headers(client)
    resp = client.post(
        "/api/discovery/resolve",
        json={"expand_result": {"bad": "data"}},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    # Should get an empty DiscoveryPack (graceful degradation)
    assert body["sources"] == []
    assert body["venues"] == []
    assert body["authors"] == []


def test_resolve_graceful_on_service_failure():
    _reset_db()
    _reset_expand_rate_limits()
    original = source_discovery.resolve_verify_rank
    source_discovery.resolve_verify_rank = AsyncMock(side_effect=RuntimeError("provider timeout"))
    try:
        client = _get_client()
        headers = _auth_headers(client)
        resp = client.post(
            "/api/discovery/resolve",
            json={"expand_result": _EXPAND_RESULT},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sources"] == []
        assert body["venues"] == []
        assert body["authors"] == []
    finally:
        source_discovery.resolve_verify_rank = original


def test_resolve_returns_empty_on_no_results():
    _reset_db()
    _reset_expand_rate_limits()
    original = source_discovery.resolve_verify_rank
    source_discovery.resolve_verify_rank = AsyncMock(
        return_value=source_discovery.DiscoveryPack()
    )
    try:
        client = _get_client()
        headers = _auth_headers(client)
        resp = client.post(
            "/api/discovery/resolve",
            json={"expand_result": _EXPAND_RESULT},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sources"] == []
        assert body["venues"] == []
        assert body["authors"] == []
    finally:
        source_discovery.resolve_verify_rank = original


# ===========================================================================
# Story 13-6 — GET /api/discovery/existing
# ===========================================================================


def _seed_source(name: str, canonical_id: str, provider: str = "openalex"):
    from sqlalchemy import text
    from database import engine as _eng
    with _eng.connect() as c:
        c.execute(
            text("INSERT OR IGNORE INTO sources (name, provider, query_json, label, category, active, canonical_id, created_at) VALUES (:name, :provider, '{}', :label, 'Discovery', 1, :cid, datetime('now'))"),
            {"name": name, "provider": provider, "label": name, "cid": canonical_id},
        )
        c.commit()
        row = c.execute(text("SELECT id FROM sources WHERE canonical_id = :cid"), {"cid": canonical_id}).fetchone()
        return row[0] if row else None


def _seed_venue(user_id: int, venue_name: str):
    from sqlalchemy import text
    from database import engine as _eng
    with _eng.connect() as c:
        c.execute(
            text("INSERT OR IGNORE INTO tracked_venues (user_id, venue_name) VALUES (:uid, :name)"),
            {"uid": user_id, "name": venue_name},
        )
        c.commit()


def _seed_author(user_id: int, name: str, openalex_id: str | None = None):
    from sqlalchemy import text
    from database import engine as _eng
    from sqlalchemy import text as _text
    with _eng.connect() as c:
        ss_id = f"openalex:{openalex_id.split('/')[-1]}" if openalex_id else f"author:{hash(name) % 10**8}"
        c.execute(
            _text("INSERT OR IGNORE INTO tracked_authors (user_id, name, ss_author_id, openalex_id, paper_count, avg_score, alert_count, created_at) VALUES (:uid, :name, :ss_id, :oid, 0, 0.0, 0, datetime('now'))"),
            {"uid": user_id, "name": name, "ss_id": ss_id, "oid": openalex_id},
        )
        c.commit()


def _seed_subscription(user_id: int, source_id: int):
    from sqlalchemy import text
    from database import engine as _eng
    with _eng.connect() as c:
        c.execute(
            text("INSERT OR IGNORE INTO user_source_subscriptions (user_id, source_id, created_at) VALUES (:uid, :sid, datetime('now'))"),
            {"uid": user_id, "sid": source_id},
        )
        c.commit()


def test_existing_returns_empty_for_new_user():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client, 99)
    resp = client.get("/api/discovery/existing", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_canonical_ids"] == []
    assert body["venue_names"] == []
    assert body["author_openalex_ids"] == []
    assert body["author_names"] == []


def test_existing_returns_subscribed_data():
    _reset_db()
    sid = _seed_source("ACL Anthology", "openalex:acl", "openalex")
    assert sid is not None
    _seed_subscription(1, sid)
    _seed_venue(1, "ACL")
    _seed_venue(1, "EMNLP")
    _seed_author(1, "Jane Doe", "https://openalex.org/A98765")
    _seed_author(1, "John Smith")

    client = _get_client()
    headers = _auth_headers(client, 1)
    resp = client.get("/api/discovery/existing", headers=headers)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["source_canonical_ids"] == ["openalex:acl"]
    assert sorted(body["venue_names"]) == ["ACL", "EMNLP"]
    assert body["author_openalex_ids"] == ["https://openalex.org/A98765"]
    author_names = body["author_names"]
    assert "Jane Doe" in author_names
    assert "John Smith" in author_names


def test_existing_isolation():
    """User 2 should not see user 1's subscriptions."""
    _reset_db()
    sid = _seed_source("CVPR", "openalex:cvpr", "openalex")
    assert sid is not None
    _seed_subscription(1, sid)
    _seed_venue(1, "CVPR")
    _seed_author(1, "Alice", "https://openalex.org/A1")

    client = _get_client()
    headers = _auth_headers(client, 2)
    resp = client.get("/api/discovery/existing", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_canonical_ids"] == []
    assert body["venue_names"] == []
    assert body["author_openalex_ids"] == []
    assert body["author_names"] == []


def test_existing_requires_auth():
    _reset_db()
    client = _get_client()
    resp = client.get("/api/discovery/existing")
    assert resp.status_code in (401, 403)


def run_tests():
    tests = [
        ("expand_returns_result", test_expand_returns_result),
        ("expand_requires_auth", test_expand_requires_auth),
        ("expand_rate_limit", test_expand_rate_limit),
        ("expand_degraded_lives_on", test_expand_degraded_lives_on),
        ("resolve_returns_pack", test_resolve_returns_pack),
        ("resolve_requires_auth", test_resolve_requires_auth),
        ("resolve_graceful_on_bad_input", test_resolve_graceful_on_bad_input),
        ("resolve_graceful_on_service_failure", test_resolve_graceful_on_service_failure),
        ("resolve_returns_empty_on_no_results", test_resolve_returns_empty_on_no_results),
        ("existing_returns_empty_for_new_user", test_existing_returns_empty_for_new_user),
        ("existing_returns_subscribed_data", test_existing_returns_subscribed_data),
        ("existing_isolation", test_existing_isolation),
        ("existing_requires_auth", test_existing_requires_auth),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅  {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌  {name}: {e}")
            failed += 1
    print(f"\n{'='*40}")
    print(f"  {passed}/{passed + failed} passed")
    if failed:
        print(f"  ❌  {failed} FAILED")
    else:
        print(f"  ✅  ALL PASSED")


if __name__ == "__main__":
    run_tests()
