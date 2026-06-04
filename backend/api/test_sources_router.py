"""Tests for the sources router (Story 12-5)."""

import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock

os.environ["DB_PATH"] = "/tmp/test_sources_router.db"
os.environ["AUTH_PASSWORD"] = "testpass"
os.environ["AUTH_EMAIL"] = "admin@basira.local"
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")

_api_dir = os.path.join(os.path.dirname(__file__))
_extractor_dir = os.path.join(_api_dir, "..", "extractor")
for p in [_api_dir, _extractor_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Save real httpx, then mock for app modules
import httpx as _real_httpx  # noqa: F401
_httpx_path = sys.modules["httpx"].__path__ if hasattr(sys.modules["httpx"], "__path__") else None
sys.modules["httpx"] = MagicMock()

from database import Base, SessionLocal, engine, init_db
from auth import create_session

import net_guard
net_guard.check_url = MagicMock()

# Build minimal test app
from fastapi import FastAPI

from routers.sources import router as sources_router

app = FastAPI()
app.include_router(sources_router)

# Now restore real httpx for TestClient
sys.modules["httpx"] = _real_httpx
from fastapi.testclient import TestClient

def _reset_db():
    Base.metadata.drop_all(bind=engine)
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

def _count(rows: list) -> int:
    return len(rows)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_sources_empty():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    resp = client.get("/api/sources", headers=headers)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    assert len(data) == 0, f"Expected empty list, got {len(data)} items"


def test_create_source():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    payload = {
        "name": "arXiv cs.AI",
        "provider": "rss",
        "query_json": json.dumps({"url": "https://export.arxiv.org/rss/cs.AI"}),
        "category": "Papers",
    }
    resp = client.post("/api/sources", json=payload, headers=headers)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["name"] == "arXiv cs.AI"
    assert data["provider"] == "rss"
    assert data["active"] == True
    assert data["id"] > 0


def test_create_and_list():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    client.post("/api/sources", json={"name": "S1", "provider": "rss", "category": "A"}, headers=headers)
    client.post("/api/sources", json={"name": "S2", "provider": "arxiv", "category": "B"}, headers=headers)
    resp = client.get("/api/sources", headers=headers)
    data = resp.json()
    assert len(data) == 2
    names = {s["name"] for s in data}
    assert names == {"S1", "S2"}


def test_delete_source():
    """DELETE /api/sources/{id} removes the subscription, source remains visible as unsubscribed."""
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    create_resp = client.post("/api/sources", json={"name": "ToDelete", "provider": "rss"}, headers=headers)
    sid = create_resp.json()["id"]
    del_resp = client.delete(f"/api/sources/{sid}", headers=headers)
    assert del_resp.status_code == 200
    list_resp = client.get("/api/sources", headers=headers)
    items = list_resp.json()
    assert len(items) == 1, f"Expected 1 (source still visible), got {len(items)}"
    assert items[0]["subscribed"] == False


def test_delete_nonexistent():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    resp = client.delete("/api/sources/999", headers=headers)
    assert resp.status_code == 404


def test_list_providers():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    resp = client.get("/api/sources/providers", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "rss" in data
    assert "arxiv" in data


def test_resolve_no_auth():
    _reset_db()
    client = _get_client()
    resp = client.post("/api/sources", json={"name": "Nope", "provider": "rss"})
    assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"


def test_user_isolation():
    """User 2 can see user 1's source but as unsubscribed."""
    _reset_db()
    client = _get_client()

    h1 = _auth_headers(client, user_id=1)
    h2 = _auth_headers(client, user_id=2)

    client.post("/api/sources", json={"name": "User1Source", "provider": "rss"}, headers=h1)
    r1 = client.get("/api/sources", headers=h1)
    assert len(r1.json()) == 1
    assert r1.json()[0]["subscribed"] == True
    r2 = client.get("/api/sources", headers=h2)
    assert len(r2.json()) == 1, f"Expected 1 (source visible to all), got {len(r2.json())}"
    assert r2.json()[0]["subscribed"] == False


def test_user_isolation_delete():
    """User 2 cannot delete user 1's subscription."""
    _reset_db()
    client = _get_client()

    h1 = _auth_headers(client, user_id=1)
    h2 = _auth_headers(client, user_id=2)
    cr = client.post("/api/sources", json={"name": "U1", "provider": "rss"}, headers=h1)
    sid = cr.json()["id"]
    resp = client.delete(f"/api/sources/{sid}", headers=h2)
    assert resp.status_code == 404
    r1 = client.get("/api/sources", headers=h1)
    assert len(r1.json()) == 1


def test_subscribe_unsubscribe():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    cr = client.post("/api/sources", json={"name": "Src", "provider": "rss"}, headers=headers)
    sid = cr.json()["id"]

    # Auto-subscribed on create
    r = client.get("/api/sources", headers=headers)
    assert r.json()[0]["subscribed"] == True

    # Unsubscribe
    r = client.delete(f"/api/sources/{sid}/subscribe", headers=headers)
    assert r.status_code == 200
    r = client.get("/api/sources", headers=headers)
    assert r.json()[0]["subscribed"] == False

    # Unsubscribe when not subscribed → 404
    r = client.delete(f"/api/sources/{sid}/subscribe", headers=headers)
    assert r.status_code == 404

    # Subscribe
    r = client.post(f"/api/sources/{sid}/subscribe", headers=headers)
    assert r.status_code == 200
    r = client.get("/api/sources", headers=headers)
    assert r.json()[0]["subscribed"] == True

    # Subscribe when already subscribed → idempotent 200
    r = client.post(f"/api/sources/{sid}/subscribe", headers=headers)
    assert r.status_code == 200

    # Subscribe to nonexistent source → 404
    r = client.post("/api/sources/99999/subscribe", headers=headers)
    assert r.status_code == 404


def test_subscribe_unsubscribe_isolation():
    """User 2's subscribe/unsubscribe does not affect user 1's subscription."""
    _reset_db()
    client = _get_client()
    h1 = _auth_headers(client, user_id=1)
    h2 = _auth_headers(client, user_id=2)
    cr = client.post("/api/sources", json={"name": "S", "provider": "rss"}, headers=h1)
    sid = cr.json()["id"]

    r1 = client.get("/api/sources", headers=h1)
    assert r1.json()[0]["subscribed"] == True

    r2 = client.get("/api/sources", headers=h2)
    assert r2.json()[0]["subscribed"] == False

    # User 2 subscribes
    client.post(f"/api/sources/{sid}/subscribe", headers=h2)
    r2b = client.get("/api/sources", headers=h2)
    assert r2b.json()[0]["subscribed"] == True
    # User 1 unaffected
    r1b = client.get("/api/sources", headers=h1)
    assert r1b.json()[0]["subscribed"] == True

    # User 2 unsubscribes
    client.delete(f"/api/sources/{sid}/subscribe", headers=h2)
    r2c = client.get("/api/sources", headers=h2)
    assert r2c.json()[0]["subscribed"] == False
    r1c = client.get("/api/sources", headers=h1)
    assert r1c.json()[0]["subscribed"] == True


def test_duplicate_source_create():
    _reset_db()
    client = _get_client()
    headers = _auth_headers(client)
    r1 = client.post("/api/sources", json={"name": "Dup", "provider": "rss"}, headers=headers)
    assert r1.status_code == 200
    r2 = client.post("/api/sources", json={"name": "Dup", "provider": "rss"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["id"] != r1.json()["id"]


def run_tests():
    tests = [
        ("list_sources_empty", test_list_sources_empty),
        ("create_source", test_create_source),
        ("create_and_list", test_create_and_list),
        ("delete_source", test_delete_source),
        ("delete_nonexistent", test_delete_nonexistent),
        ("list_providers", test_list_providers),
        ("resolve_no_auth", test_resolve_no_auth),
        ("user_isolation", test_user_isolation),
        ("user_isolation_delete", test_user_isolation_delete),
        ("duplicate_source_create", test_duplicate_source_create),
        ("subscribe_unsubscribe", test_subscribe_unsubscribe),
        ("subscribe_unsubscribe_isolation", test_subscribe_unsubscribe_isolation),
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
