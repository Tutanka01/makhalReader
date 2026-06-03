"""Tests for threat scan user-scoped thesis_contribution (Story 5.7, FR-MT-32).

NOTE: Must NOT be run in the same process as tests that import shared/database.py
(as 'database') due to sys.modules collision. Run this file in isolation:
    python -m pytest backend/scorer/tests/test_threat_scan.py -v
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_API_DIR = Path(__file__).resolve().parent.parent.parent / "api"

# Force-load API database module and register it as 'database' in sys.modules
# BEFORE any code tries to import 'routers.research'
_api_database_path = str(_API_DIR / "database.py")
_spec = importlib.util.spec_from_file_location("database", _api_database_path)
_api_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_api_db)
sys.modules["database"] = _api_db

Article = _api_db.Article
UserConfig = _api_db.UserConfig
init_db = _api_db.init_db

_API_SRC = str(_API_DIR)
if _API_SRC not in sys.path:
    sys.path.insert(0, _API_SRC)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def sync_await(coro):
    return asyncio.run(coro)


@pytest.fixture()
def tmp_db(monkeypatch):
    """Fresh SQLite DB with all tables created."""
    import tempfile
    db_file = Path(tempfile.mktemp(suffix=".db"))
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    monkeypatch.setattr(_api_db, "engine", engine)
    monkeypatch.setattr(
        _api_db,
        "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=engine),
    )

    init_db()

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        db_file.unlink(missing_ok=True)


def seed_article(db, article_id=1, score=8.0):
    article = Article(
        id=article_id,
        title=f"Test Article {article_id}",
        url=f"https://example.com/{article_id}",
        content_text="Some research content about AI alignment.",
        score=score,
        created_at=datetime.now(timezone.utc),
        feed_id=1,
    )
    db.add(article)
    db.commit()
    return article


def seed_user_config(db, user_id, thesis_contribution):
    config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if config:
        config.thesis_contribution = thesis_contribution
    else:
        config = UserConfig(user_id=user_id, thesis_contribution=thesis_contribution)
        db.add(config)
    db.commit()
    return config


class TestThreatScanUserScoped:

    def test_reads_thesis_contribution_from_user_config(self, tmp_db, monkeypatch):
        """_run_threat_scan reads thesis_contribution from UserConfig, not singleton table."""
        from routers.research import _run_threat_scan, _llm_assess_threat

        db = tmp_db
        seed_article(db)
        seed_user_config(db, user_id=1, thesis_contribution="User 1's contribution")

        mock_llm = AsyncMock(return_value={"overlap_score": 0.3, "positioning_note": "Some overlap"})
        monkeypatch.setattr("routers.research._llm_assess_threat", mock_llm)

        result = sync_await(_run_threat_scan(db, user_id=1, window_days=30))

        assert result.scanned == 1
        assert result.alerts_created == 1
        assert result.skipped == 0
        call_statement = mock_llm.await_args[0][0]
        assert "User 1's contribution" in call_statement

    def test_different_user_gets_different_contribution(self, tmp_db, monkeypatch):
        """Different user_id reads different thesis_contribution from UserConfig."""
        from routers.research import _run_threat_scan, _llm_assess_threat

        db = tmp_db
        seed_article(db)
        seed_user_config(db, user_id=1, thesis_contribution="User 1's contribution")
        seed_user_config(db, user_id=2, thesis_contribution="User 2's contribution")

        mock_llm = AsyncMock(return_value={"overlap_score": 0.3, "positioning_note": "Some overlap"})
        monkeypatch.setattr("routers.research._llm_assess_threat", mock_llm)

        result = sync_await(_run_threat_scan(db, user_id=2, window_days=30))

        call_statement = mock_llm.await_args[0][0]
        assert "User 2's contribution" in call_statement
        assert "User 1's contribution" not in call_statement

    def test_raises_400_if_no_contribution(self, tmp_db):
        """Missing thesis_contribution raises 400."""
        from routers.research import _run_threat_scan
        from fastapi import HTTPException

        db = tmp_db
        seed_article(db)

        with pytest.raises(HTTPException) as exc:
            sync_await(_run_threat_scan(db, user_id=99, window_days=30))
        assert exc.value.status_code == 400

    def test_fallback_to_seed_user(self, tmp_db, monkeypatch):
        """Scheduler call (no user_id) defaults to user_id=1."""
        from routers.research import _run_threat_scan, _llm_assess_threat

        db = tmp_db
        seed_article(db)
        seed_user_config(db, user_id=1, thesis_contribution="Seed user contribution")

        mock_llm = AsyncMock(return_value={"overlap_score": 0.3, "positioning_note": "Some overlap"})
        monkeypatch.setattr("routers.research._llm_assess_threat", mock_llm)

        result = sync_await(_run_threat_scan(db, window_days=30))

        assert result.scanned == 1
        assert result.alerts_created == 1
        call_statement = mock_llm.await_args[0][0]
        assert "Seed user contribution" in call_statement
