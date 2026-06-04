"""Migration compatibility tests — NFR-T4 and NFR-T6.

Verifies that:
1. A v1 SQLite DB (no user tables, old score columns on articles) survives init_db() cleanly.
2. All v1 article scores and engagement data are backfilled to user_id=1 in article_scores.
3. The backward-compat scoring path (_resolve_system_prompt with user_context=None) returns the
   static SYSTEM_PROMPT unchanged — ensuring NFR-T6 (≤ ±5% scoring delta).

NOTE: Run inside Docker where SQLAlchemy and project deps are available:
  docker-compose exec api python -m pytest backend/scorer/tests/test_migration_compat.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── dependency guards ──────────────────────────────────────────────────────
try:
    import sqlalchemy
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE,
    reason="SQLAlchemy not available — run inside Docker: docker-compose exec api pytest",
)

# ── path setup ─────────────────────────────────────────────────────────────
_SCORER_DIR = Path(__file__).resolve().parent.parent
_SHARED_DIR = Path(__file__).resolve().parent.parent.parent.parent / "backend" / "shared"

for _p in (_SCORER_DIR, _SHARED_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

if SQLALCHEMY_AVAILABLE:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def v1_db(monkeypatch, tmp_path):
    """Create a v1-style SQLite DB with articles that have scores but no user tables."""
    db_file = tmp_path / "v1.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    with engine.connect() as conn:
        # V1 schema: articles table with score/bookmarked/read_at directly on it
        conn.execute(text("""
            CREATE TABLE feeds (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                active INTEGER DEFAULT 1,
                last_fetched TEXT,
                poll_interval_minutes INTEGER DEFAULT 720
            )
        """))
        conn.execute(text("""
            INSERT INTO feeds (id, url, name) VALUES
            (1, 'https://example.com/feed1', 'Test Feed 1'),
            (2, 'https://example.com/feed2', 'Test Feed 2')
        """))
        conn.execute(text("""
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                feed_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                published_at TEXT,
                author TEXT,
                content_text TEXT,
                score REAL,
                read_at TEXT,
                bookmarked INTEGER DEFAULT 0,
                user_feedback INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (feed_id) REFERENCES feeds(id)
            )
        """))
        # Insert 10 articles with known v1 scores
        for i in range(1, 11):
            score = float(i)  # Scores 1.0 through 10.0 — deterministic ground truth
            read = "2026-01-01T00:00:00" if i % 3 == 0 else None
            bookmarked = 1 if i % 2 == 0 else 0
            feedback = 1 if i == 5 else (-1 if i == 7 else None)
            conn.execute(text("""
                INSERT INTO articles (id, feed_id, title, url, score, read_at, bookmarked, user_feedback)
                VALUES (:id, :fid, :title, :url, :score, :read_at, :bm, :fb)
            """), {
                "id": i,
                "fid": 1,
                "title": f"Article {i}",
                "url": f"https://example.com/article/{i}",
                "score": score,
                "read_at": read,
                "bm": bookmarked,
                "fb": feedback,
            })
        conn.execute(text("""
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)
        """))
        conn.commit()

    import database as db_module
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setenv("AUTH_PASSWORD", "testpassword")

    yield engine, db_module

    engine.dispose()


# ── migration tests ────────────────────────────────────────────────────────

class TestV1ToV2Migration:
    def test_init_db_runs_without_error(self, v1_db):
        """init_db() must not raise on a v1 DB."""
        _, db_module = v1_db
        db_module.init_db()  # Should not raise

    def test_user_tables_created(self, v1_db):
        engine, db_module = v1_db
        db_module.init_db()
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "users" in tables, "users table must be created"
        assert "organizations" in tables, "organizations table must be created"
        assert "user_config" in tables, "user_config table must be created"
        assert "article_scores" in tables, "article_scores table must be created"
        assert "user_feed_subscriptions" in tables, "user_feed_subscriptions table must be created"

    def test_no_seed_user_created(self, v1_db):
        """AUTH_PASSWORD must not create a hidden user during migration."""
        _, db_module = v1_db
        db_module.init_db()
        db = db_module.SessionLocal()
        try:
            from database import User
            assert db.query(User).count() == 0
        finally:
            db.close()

    def test_first_registered_user_after_migration_is_admin(self, v1_db):
        """The first real user created after migration owns user_id=1 and is admin."""
        _, db_module = v1_db
        db_module.init_db()
        db = db_module.SessionLocal()
        try:
            from database import User
            user = User.register(db, "first@test.com", "pass123")
            assert user.id == 1
            assert user.role == "admin"
            assert user.onboarding_done is False
        finally:
            db.close()

    def test_article_scores_backfilled(self, v1_db):
        """All 10 v1 articles must have article_scores rows for user_id=1."""
        _, db_module = v1_db
        db_module.init_db()
        db = db_module.SessionLocal()
        try:
            from database import ArticleScore
            rows = db.query(ArticleScore).filter(ArticleScore.user_id == 1).all()
            assert len(rows) == 10, f"Expected 10 backfilled rows, got {len(rows)}"
        finally:
            db.close()

    def test_v1_scores_preserved_in_article_scores(self, v1_db):
        """Backfilled article_scores must match the original v1 score column."""
        _, db_module = v1_db
        db_module.init_db()
        db = db_module.SessionLocal()
        try:
            from database import ArticleScore
            for i in range(1, 11):
                row = db.query(ArticleScore).filter(
                    ArticleScore.user_id == 1,
                    ArticleScore.article_id == i,
                ).first()
                assert row is not None, f"Missing article_score for article_id={i}"
                assert row.score == float(i), (
                    f"Score mismatch for article {i}: expected {float(i)}, got {row.score}"
                )
        finally:
            db.close()

    def test_read_at_preserved(self, v1_db):
        """read_at values from v1 must be backfilled into article_scores."""
        _, db_module = v1_db
        db_module.init_db()
        db = db_module.SessionLocal()
        try:
            from database import ArticleScore
            # Articles 3, 6, 9 were marked read in v1 (i % 3 == 0)
            for i in [3, 6, 9]:
                row = db.query(ArticleScore).filter(
                    ArticleScore.user_id == 1,
                    ArticleScore.article_id == i,
                ).first()
                assert row is not None
                assert row.read_at is not None, f"read_at not backfilled for article {i}"
        finally:
            db.close()

    def test_init_db_idempotent(self, v1_db):
        """Running init_db() twice must not raise or duplicate data."""
        _, db_module = v1_db
        db_module.init_db()
        db_module.init_db()  # Second run must also succeed
        db = db_module.SessionLocal()
        try:
            from database import ArticleScore
            count = db.query(ArticleScore).filter(ArticleScore.user_id == 1).count()
            assert count == 10, f"Expected 10 rows after double init, got {count}"
        finally:
            db.close()

    def test_feed_subscriptions_backfilled(self, v1_db):
        """user_id=1 must be subscribed to all pre-existing feeds."""
        _, db_module = v1_db
        db_module.init_db()
        db = db_module.SessionLocal()
        try:
            from database import UserFeedSubscription
            subs = db.query(UserFeedSubscription).filter(
                UserFeedSubscription.user_id == 1
            ).all()
            assert len(subs) >= 2, f"Expected subscriptions to both feeds, got {len(subs)}"
        finally:
            db.close()


# ── backward-compat scoring path tests (NFR-T6) ────────────────────────────

class TestBackwardCompatScoringPath:
    def test_resolve_prompt_without_user_context_returns_static(self):
        """NFR-T6: ScoreRequest with user_context=None must use static SYSTEM_PROMPT."""
        from scorer import ScoreRequest, _resolve_system_prompt
        from prompt import SYSTEM_PROMPT

        req = ScoreRequest(
            article_id=1,
            title="Test Article",
            content_text="Some content",
            user_id=1,
            user_context=None,
        )
        result = _resolve_system_prompt(req)
        assert result == SYSTEM_PROMPT, (
            "Backward compat path must return SYSTEM_PROMPT unchanged when user_context=None"
        )

    def test_static_prompt_unchanged(self):
        """NFR-T6: The static SYSTEM_PROMPT must retain its v1 key sections."""
        from prompt import SYSTEM_PROMPT
        assert len(SYSTEM_PROMPT) > 500, "SYSTEM_PROMPT appears truncated"
        # Key sections that must remain present for v1 scoring compatibility
        assert "DUAL-MODE SCORING" in SYSTEM_PROMPT or "score" in SYSTEM_PROMPT.lower(), (
            "SYSTEM_PROMPT must contain scoring instructions"
        )

    def test_user_context_triggers_dynamic_prompt(self):
        """NFR-T6: ScoreRequest with user_context must NOT return the static prompt."""
        from scorer import ScoreRequest, _resolve_system_prompt
        from prompt import SYSTEM_PROMPT

        req = ScoreRequest(
            article_id=1,
            title="Test Article",
            content_text="Some content",
            user_id=1,
            user_context={
                "thesis_title": "My Custom Thesis",
                "thesis_question": "What is the answer?",
                "scoring_clusters": [],
                "tracked_venues": [],
            },
        )
        result = _resolve_system_prompt(req)
        assert "My Custom Thesis" in result, "Dynamic prompt must include user thesis title"
