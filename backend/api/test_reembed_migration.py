"""Tests for Story 14-2 — Per-tenant re-embed migration.

Verifies:
- POST /api/admin/reindex without force_model preserves legacy behavior (AC4).
- POST /api/admin/reindex with force_model returns started (AC1).
- _get_chroma returns old collection during re-embed in progress (AC2).
- _get_chroma returns versioned collection after embed_model set (AC3).
- _resolve_collection_name reads embed_model from DB correctly.
"""

import os
import sys
import types
from unittest.mock import MagicMock

os.environ["DB_PATH"] = "/tmp/test_reembed_migration.db"
os.environ["AUTH_PASSWORD"] = "testpass"
os.environ["AUTH_EMAIL"] = "admin@basira.local"
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")

_api_dir = os.path.join(os.path.dirname(__file__))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

# Mock chromadb before any embedder import to avoid No module error
_chromadb_mod = types.ModuleType("chromadb")
_chromadb_mod.PersistentClient = MagicMock()


def _fake_get_or_create(name, **kw):
    col = MagicMock()
    col.name = name
    col.upsert = MagicMock()
    col.get = MagicMock(return_value={"ids": [], "embeddings": [], "metadatas": []})
    return col


_chromadb_mod.PersistentClient.return_value.get_or_create_collection = _fake_get_or_create
_chromadb_mod.PersistentClient.return_value.get_collection = MagicMock(side_effect=ValueError("not found"))
_chromadb_mod.PersistentClient.return_value.delete_collection = MagicMock()
sys.modules["chromadb"] = _chromadb_mod

from database import Base, SessionLocal, engine, init_db, UserConfig
from auth import create_session
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.admin import router as admin_router

app = FastAPI()
app.include_router(admin_router)

client = TestClient(app)

_PASS = 0
_FAIL = 0


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  ✅  {name}")


def _fail(name: str, msg: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  ❌  {name}: {msg}")


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_db()


def _auth_cookies(user_id: int = 1) -> dict:
    sid = create_session(user_id=user_id, remember=False, user_agent="test")
    return {"basira_sid": sid}


# ── Tests ──────────────────────────────────────────────────────────────────


def test_reindex_without_force_model_legacy():
    """POST /api/admin/reindex without body keeps legacy behavior (AC4)."""
    resp = client.post("/api/admin/reindex", cookies=_auth_cookies())
    data = resp.json()
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {data}"
    assert "migrated" in data, f"Expected 'migrated' in {data}"
    _ok("reindex_without_force_model_legacy")


def test_reindex_with_force_model_returns_started():
    """POST /api/admin/reindex with force_model returns started (AC1)."""
    db = SessionLocal()
    try:
        config = db.query(UserConfig).filter(UserConfig.user_id == 1).first()
        config.pending_embed_model = None
        db.commit()
    finally:
        db.close()

    resp = client.post(
        "/api/admin/reindex",
        json={"force_model": "paraphrase-multilingual-mpnet-base-v2"},
        cookies=_auth_cookies(),
    )
    data = resp.json()
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {data}"
    assert data["status"] == "started", f"Expected started, got {data}"
    assert data["model"] == "paraphrase-multilingual-mpnet-base-v2"
    _ok("reindex_with_force_model_returns_started")


def test_get_chroma_uses_base_during_reembed():
    """_get_chroma returns old collection during re-embed in progress (AC2)."""
    from embedder import _get_chroma, _reembed_in_progress

    _reembed_in_progress[999] = True
    try:
        collection = _get_chroma(user_id=999)
        name = collection.name
        assert "_v2" not in name, f"Expected base collection during reembed, got {name}"
    finally:
        _reembed_in_progress.pop(999, None)

    _ok("get_chroma_uses_base_during_reembed")


def test_get_chroma_uses_versioned_after_migration():
    """_get_chroma returns versioned collection after embed_model set (AC3)."""
    from embedder import _get_chroma, _chroma_collections

    db = SessionLocal()
    try:
        config = db.query(UserConfig).filter(UserConfig.user_id == 1).first()
        original = config.embed_model
        config.embed_model = "test-model-v2"
        db.commit()
    finally:
        db.close()

    # Clear cache for user 1 so it re-resolves
    _chroma_collections.pop("articles_u1", None)
    _chroma_collections.pop("articles_u1_v2", None)

    try:
        collection = _get_chroma(user_id=1)
        name = collection.name
        assert name == "articles_u1_v2", f"Expected versioned collection, got {name}"
    finally:
        db = SessionLocal()
        try:
            config = db.query(UserConfig).filter(UserConfig.user_id == 1).first()
            config.embed_model = None
            db.commit()
        finally:
            db.close()
        _chroma_collections.pop("articles_u1", None)
        _chroma_collections.pop("articles_u1_v2", None)

    _ok("get_chroma_uses_versioned_after_migration")


def test_no_force_model_for_user1_preserves_old_behavior():
    """user_id=1 without force_model does NOT trigger re-embed (AC4/NFR-DA1)."""
    resp = client.post("/api/admin/reindex", json={}, cookies=_auth_cookies())
    data = resp.json()
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {data}"
    assert "migrated" in data, f"Expected 'migrated' in {data}"
    assert data.get("status") != "started"
    _ok("no_force_model_for_user1_preserves_old_behavior")


# ── Runner ─────────────────────────────────────────────────────────────────


def run_tests():
    global _PASS, _FAIL
    _PASS = 0
    _FAIL = 0

    setup_module()

    tests = [
        ("reindex_without_force_model_legacy", test_reindex_without_force_model_legacy),
        ("reindex_with_force_model_returns_started", test_reindex_with_force_model_returns_started),
        ("get_chroma_uses_base_during_reembed", test_get_chroma_uses_base_during_reembed),
        ("get_chroma_uses_versioned_after_migration", test_get_chroma_uses_versioned_after_migration),
        ("no_force_model_for_user1_preserves_old_behavior", test_no_force_model_for_user1_preserves_old_behavior),
    ]
    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            _fail(name, str(e))

    print(f"\n{'='*40}")
    print(f"  {_PASS}/{_PASS + _FAIL} passed")
    if _FAIL:
        print(f"  ❌  {_FAIL} FAILED")
    else:
        print(f"  ✅  ALL PASSED")


if __name__ == "__main__":
    run_tests()
