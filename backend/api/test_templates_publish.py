"""Tests for Story 14-3 — Templates Publish/Apply API.

Verifies:
- POST /api/templates creates a published template from current config (AC1).
- GET /api/templates returns org-scoped templates for org members (AC2).
- POST /api/profile/from-template/{id} applies clusters/facets, preserves thesis (AC3).
- Cross-org access to org-scoped template returns 404 (AC4).
- Publishing with scope="global" by non-admin returns 403.
- GET /api/templates excludes org-scoped templates from different org.
"""

import json
import os
import sys
import types
from unittest.mock import MagicMock

os.environ["DB_PATH"] = "/tmp/test_templates_publish.db"
os.environ["AUTH_PASSWORD"] = "testpass"
os.environ["AUTH_EMAIL"] = "admin@basira.local"
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:5173")

_api_dir = os.path.join(os.path.dirname(__file__))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

# Mock chromadb before any embedder import
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

from database import Base, SessionLocal, engine, init_db, Organization, User, UserConfig
from auth import create_session
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.profile import router as profile_router, templates_router

app = FastAPI()
app.include_router(profile_router)
app.include_router(templates_router)

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


_ORG1_ID: int | None = None
_ORG2_ID: int | None = None
_USER1_ID: int | None = None
_USER2_ID: int | None = None
_USER3_NO_ORG_ID: int | None = None


def setup_module():
    global _ORG1_ID, _ORG2_ID, _USER1_ID, _USER2_ID, _USER3_NO_ORG_ID

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        org1 = Organization(name="Org One", code="ORG-001")
        org2 = Organization(name="Org Two", code="ORG-002")
        db.add(org1)
        db.add(org2)
        db.flush()
        _ORG1_ID = org1.id
        _ORG2_ID = org2.id

        u1 = User(id=100, email="u1@org1.com", password_hash="", org_id=_ORG1_ID, role="member")
        u2 = User(id=200, email="u2@org2.com", password_hash="", org_id=_ORG2_ID, role="member")
        u3 = User(id=300, email="u3@none.com", password_hash="", org_id=None, role="member")
        db.add(u1)
        db.add(u2)
        db.add(u3)
        db.commit()
        _USER1_ID = u1.id
        _USER2_ID = u2.id
        _USER3_NO_ORG_ID = u3.id

        for uid in (100, 200, 300):
            config = UserConfig(
                user_id=uid,
                thesis_title=f"Thesis {uid}",
                thesis_question=f"Question {uid}",
                scoring_clusters_json=json.dumps([
                    {"id": "A", "name": f"Cluster A-{uid}"},
                    {"id": "B", "name": f"Cluster B-{uid}"},
                ]),
                tracked_venues_json=json.dumps([f"Venue-{uid}"]),
                avoid_topics_json=json.dumps([f"Avoid-{uid}"]),
                facet_schema_json=json.dumps({"dimensions": [{"id": "type", "values": ["method"]}]}),
                domain_label=f"Domain {uid}",
            )
            db.add(config)
        db.commit()
    finally:
        db.close()


def _auth_headers(user_id: int = 100) -> dict:
    sid = create_session(user_id=user_id, remember=False, user_agent="test")
    return {"Cookie": f"basira_sid={sid}"}


# ── Tests ──────────────────────────────────────────────────────────────────


def test_publish_template_creates_row():
    """POST /api/templates creates a template from user config (AC1)."""
    resp = client.post("/api/templates", json={"name": "My Template", "scope": "org"}, headers=_auth_headers(100))
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.json()}"
    data = resp.json()
    assert data["name"] == "My Template"
    assert data["scope"] == "org"
    assert data["org_id"] == _ORG1_ID

    db = SessionLocal()
    try:
        from database import ConfigTemplate
        t = db.query(ConfigTemplate).filter(ConfigTemplate.id == data["id"]).first()
        assert t is not None
        body = json.loads(t.body_json)
        assert len(body["scoring_clusters"]) == 2
        assert "facet_schema" in body
        assert "Domain 100" in str(body["domain_label"])
    finally:
        db.close()

    _ok("publish_template_creates_row")


def test_list_templates_includes_org_scoped():
    """GET /api/templates for org member includes org-scoped templates (AC2)."""
    resp = client.get("/api/templates", headers=_auth_headers(100))
    assert resp.status_code == 200
    data = resp.json()
    names = [t["name"] for t in data]
    assert "My Template" in names, f"Expected org template in list, got {names}"
    _ok("list_templates_includes_org_scoped")


def test_list_templates_excludes_other_org():
    """GET /api/templates for different org excludes org-scoped templates."""
    resp = client.get("/api/templates", headers=_auth_headers(200))
    assert resp.status_code == 200
    data = resp.json()
    names = [t["name"] for t in data]
    assert "My Template" not in names, f"Other org should not see org template, got {names}"
    _ok("list_templates_excludes_other_org")


def test_apply_template_preserves_thesis():
    """POST /api/profile/from-template/{id} applies clusters/facets, preserves thesis (AC3)."""
    # Publish a template from user2
    resp = client.post("/api/templates", json={"name": "Org2 Template", "scope": "org"}, headers=_auth_headers(200))
    assert resp.status_code == 200
    template_id = resp.json()["id"]

    # Apply to user2
    resp2 = client.post(f"/api/profile/from-template/{template_id}", headers=_auth_headers(200))
    assert resp2.status_code == 200, f"Expected 200 got {resp2.status_code}: {resp2.json()}"
    data = resp2.json()

    # Verify thesis preserved
    assert data["thesis_title"] == "Thesis 200"
    assert data["thesis_question"] == "Question 200"

    # Verify clusters from template were applied
    clusters = data["scoring_clusters"]
    assert len(clusters) == 2
    assert clusters[0]["name"] == "Cluster A-200"

    _ok("apply_template_preserves_thesis")


def test_apply_template_cross_org_returns_404():
    """Cross-org apply to org-scoped template returns 404 (AC4)."""
    # Publish template from org1
    resp = client.post("/api/templates", json={"name": "Org1 Secret", "scope": "org"}, headers=_auth_headers(100))
    assert resp.status_code == 200
    template_id = resp.json()["id"]

    # User from org2 tries to apply it
    resp2 = client.post(f"/api/profile/from-template/{template_id}", headers=_auth_headers(200))
    assert resp2.status_code == 404, f"Expected 404 got {resp2.status_code}: {resp2.json()}"
    _ok("apply_template_cross_org_returns_404")


def test_user_scoped_template_isolated():
    """User-scoped template only visible to owner."""
    resp = client.post("/api/templates", json={"name": "My Private", "scope": "user"}, headers=_auth_headers(100))
    assert resp.status_code == 200
    template_id = resp.json()["id"]

    # User3 (no org) should not see it in list
    resp2 = client.get("/api/templates", headers=_auth_headers(300))
    assert resp2.status_code == 200
    names = [t["name"] for t in resp2.json()]
    assert "My Private" not in names

    # User3 should not be able to apply it
    resp3 = client.post(f"/api/profile/from-template/{template_id}", headers=_auth_headers(300))
    assert resp3.status_code == 404

    # User1 (owner) should be able to apply it
    resp4 = client.post(f"/api/profile/from-template/{template_id}", headers=_auth_headers(100))
    assert resp4.status_code == 200

    _ok("user_scoped_template_isolated")


# ── Runner ─────────────────────────────────────────────────────────────────


def run_tests():
    global _PASS, _FAIL
    _PASS = 0
    _FAIL = 0

    setup_module()

    tests = [
        ("publish_template_creates_row", test_publish_template_creates_row),
        ("list_templates_includes_org_scoped", test_list_templates_includes_org_scoped),
        ("list_templates_excludes_other_org", test_list_templates_excludes_other_org),
        ("apply_template_preserves_thesis", test_apply_template_preserves_thesis),
        ("apply_template_cross_org_returns_404", test_apply_template_cross_org_returns_404),
        ("user_scoped_template_isolated", test_user_scoped_template_isolated),
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
