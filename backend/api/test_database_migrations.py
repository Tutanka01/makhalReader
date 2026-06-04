"""
Tests for database migrations — Story 12.1, sources + user_source_subscriptions.

Run:
    python test_database_migrations.py
"""
from __future__ import annotations

import json
import sqlite3
import sys

sys.path.insert(0, __file__)

_PASS = 0
_FAIL = 0


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  \u2705  {name}")


def _fail(name: str, msg: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  \u274c  {name}: {msg}")


def _assert_true(name: str, cond: bool) -> None:
    if cond:
        _ok(name)
    else:
        _fail(name, f"expected True, got {cond!r}")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SETUP_SQL = [
    """CREATE TABLE IF NOT EXISTS feeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General',
        active BOOLEAN NOT NULL DEFAULT 1,
        last_fetched DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS user_feed_subscriptions (
        user_id INTEGER NOT NULL REFERENCES users(id),
        feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (user_id, feed_id)
    )""",
    """CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        provider VARCHAR(24) NOT NULL DEFAULT 'rss',
        query_json TEXT,
        label TEXT,
        category TEXT NOT NULL DEFAULT 'General',
        active BOOLEAN NOT NULL DEFAULT 1,
        last_fetched DATETIME,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS user_source_subscriptions (
        user_id INTEGER NOT NULL REFERENCES users(id),
        source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (user_id, source_id)
    )""",
]


_BACKFILL_SOURCES_SQL = """
    INSERT OR IGNORE INTO sources (id, name, provider, query_json, label, category, active, last_fetched, created_at)
    SELECT id, name, 'rss', json_object('url', url), NULL, category, active, last_fetched, datetime('now')
    FROM feeds
"""

_BACKFILL_SUBSCRIBERS_SQL = """
    INSERT OR IGNORE INTO user_source_subscriptions (user_id, source_id, created_at)
    SELECT user_id, feed_id, created_at
    FROM user_feed_subscriptions
"""


# ══════════════════════════════════════════════════════════════════════════════
# Test 1: sources table created with correct columns
# ══════════════════════════════════════════════════════════════════════════════

def test_sources_table_schema() -> None:
    conn = _memory_db()
    for s in _SETUP_SQL:
        conn.execute(s)

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(sources)").fetchall()}
    expected = {"id", "name", "provider", "query_json", "label", "category", "active", "last_fetched", "created_at"}
    diff = expected - cols
    if diff:
        _fail("sources table columns", f"missing: {diff}")
    else:
        _ok("sources table columns match spec")

    # Verify provider default
    info = {row["name"]: row for row in conn.execute("PRAGMA table_info(sources)").fetchall()}
    _assert_true("provider defaults to 'rss'", info["provider"]["dflt_value"] == "'rss'")

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Test 2: user_source_subscriptions table created with correct columns
# ══════════════════════════════════════════════════════════════════════════════

def test_user_source_subscriptions_schema() -> None:
    conn = _memory_db()
    for s in _SETUP_SQL:
        conn.execute(s)

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(user_source_subscriptions)").fetchall()}
    expected = {"user_id", "source_id", "created_at"}
    diff = expected - cols
    if diff:
        _fail("user_source_subscriptions columns", f"missing: {diff}")
    else:
        _ok("user_source_subscriptions columns match spec")

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Test 3: Backfill feeds → sources creates correct rows
# ══════════════════════════════════════════════════════════════════════════════

def test_backfill_sources() -> None:
    conn = _memory_db()
    for s in _SETUP_SQL:
        conn.execute(s)

    # Insert two feeds
    conn.execute("INSERT INTO feeds (url, name, category) VALUES ('https://example.com/rss', 'Example Feed', 'Tech')")
    conn.execute("INSERT INTO feeds (url, name, category, active) VALUES ('https://other.com/feed', 'Other Feed', 'Science', 0)")
    expected_feed_ids = {row["id"] for row in conn.execute("SELECT id FROM feeds").fetchall()}

    # Run backfill
    conn.execute(_BACKFILL_SOURCES_SQL)
    conn.commit()

    rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    _assert_true("backfill creates same number of sources as feeds", len(rows) == 2)

    for row in rows:
        _assert_true(f"source id={row['id']} matches feed id", row["id"] in expected_feed_ids)
        _assert_true(f"source provider is rss", row["provider"] == "rss")
        qj = json.loads(row["query_json"])
        _assert_true(f"query_json has url key", "url" in qj)
        _assert_true(f"provider defaults to 'rss'", row["provider"] == "rss")
        _assert_true(f"active matches feed", row["active"] in (0, 1))

    # Verify inactive feed mirrored correctly
    inactive = [r for r in rows if r["name"] == "Other Feed"][0]
    _assert_true("inactive feed mirrored as inactive source", inactive["active"] == 0)

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Test 4: Backfill user_feed_subscriptions → user_source_subscriptions
# ══════════════════════════════════════════════════════════════════════════════

def test_backfill_subscriptions() -> None:
    conn = _memory_db()
    for s in _SETUP_SQL:
        conn.execute(s)

    # Seed users, feeds, and subscriptions
    conn.execute("INSERT INTO users (id, email, password_hash) VALUES (1, 'a@b.com', 'h')")
    conn.execute("INSERT INTO feeds (id, url, name) VALUES (10, 'https://a.com/rss', 'Feed A')")
    conn.execute("INSERT INTO feeds (id, url, name) VALUES (20, 'https://b.com/rss', 'Feed B')")
    conn.execute(
        "INSERT INTO user_feed_subscriptions (user_id, feed_id, created_at) VALUES (1, 10, datetime('now'))",
    )
    conn.execute(
        "INSERT INTO user_feed_subscriptions (user_id, feed_id, created_at) VALUES (1, 20, datetime('now'))",
    )
    # Must also have sources for FK constraint
    conn.execute("INSERT INTO sources (id, name, provider) VALUES (10, 'Feed A', 'rss')")
    conn.execute("INSERT INTO sources (id, name, provider) VALUES (20, 'Feed B', 'rss')")

    conn.execute(_BACKFILL_SUBSCRIBERS_SQL)
    conn.commit()

    rows = conn.execute("SELECT * FROM user_source_subscriptions ORDER BY source_id").fetchall()
    _assert_true("both subscriptions mirrored", len(rows) == 2)
    for row in rows:
        _assert_true(f"subscription source_id={row['source_id']} matches feed_id", row["source_id"] in (10, 20))
        _assert_true(f"subscription user_id=1", row["user_id"] == 1)

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Test 5: Idempotency — re-running backfill doesn't duplicate rows
# ══════════════════════════════════════════════════════════════════════════════

def test_idempotency() -> None:
    conn = _memory_db()
    for s in _SETUP_SQL:
        conn.execute(s)

    conn.execute("INSERT INTO feeds (url, name) VALUES ('https://x.com/rss', 'X Feed')")
    conn.execute("INSERT INTO users (id, email, password_hash) VALUES (1, 'u@v.com', 'h')")
    conn.execute(
        "INSERT INTO user_feed_subscriptions (user_id, feed_id, created_at) VALUES (1, 1, datetime('now'))",
    )
    conn.commit()

    # First run: backfill sources + subscriptions
    conn.execute(_BACKFILL_SOURCES_SQL)
    conn.execute(_BACKFILL_SUBSCRIBERS_SQL)
    conn.commit()

    count_after_first = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    sub_count_after_first = conn.execute("SELECT COUNT(*) FROM user_source_subscriptions").fetchone()[0]

    # Second run: same backfills again (no-op)
    conn.execute(_BACKFILL_SOURCES_SQL)
    conn.execute(_BACKFILL_SUBSCRIBERS_SQL)
    conn.commit()

    count_after_second = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    sub_count_after_second = conn.execute("SELECT COUNT(*) FROM user_source_subscriptions").fetchone()[0]

    _assert_true("sources idempotent — no duplicates", count_after_first == count_after_second)
    _assert_true("subscriptions idempotent — no duplicates", sub_count_after_first == sub_count_after_second)

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Test 6: Dual-write simulation — feed creation writes source row
# ══════════════════════════════════════════════════════════════════════════════

def test_dual_write() -> None:
    conn = _memory_db()
    for s in _SETUP_SQL:
        conn.execute(s)

    conn.execute("INSERT INTO users (id, email, password_hash) VALUES (1, 'u@v.com', 'h')")

    # Simulate POST /api/feeds dual-write
    conn.execute(
        "INSERT INTO feeds (url, name, category) VALUES ('https://dual.com/rss', 'Dual Feed', 'General')",
    )
    feed_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO sources (id, name, provider, query_json, category, active) "
        "VALUES (?, ?, 'rss', ?, 'General', 1)",
        (feed_id, 'Dual Feed', json.dumps({"url": "https://dual.com/rss"})),
    )
    conn.execute(
        "INSERT INTO user_feed_subscriptions (user_id, feed_id, created_at) VALUES (1, ?, datetime('now'))",
        (feed_id,),
    )
    conn.execute(
        "INSERT INTO user_source_subscriptions (user_id, source_id, created_at) VALUES (1, ?, datetime('now'))",
        (feed_id,),
    )
    conn.commit()

    # Verify
    feed_row = conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
    source_row = conn.execute("SELECT * FROM sources WHERE id = ?", (feed_id,)).fetchone()
    feed_sub = conn.execute("SELECT * FROM user_feed_subscriptions WHERE feed_id = ?", (feed_id,)).fetchone()
    source_sub = conn.execute("SELECT * FROM user_source_subscriptions WHERE source_id = ?", (feed_id,)).fetchone()

    _assert_true("feed row exists", feed_row is not None)
    _assert_true("source row exists with matching id", source_row is not None)
    _assert_true("source provider is rss", source_row and source_row["provider"] == "rss")
    _assert_true("feed subscription exists", feed_sub is not None)
    _assert_true("source subscription exists", source_sub is not None)
    _assert_true("user ids match", feed_sub["user_id"] == source_sub["user_id"])

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_sources_table_schema()
    test_user_source_subscriptions_schema()
    test_backfill_sources()
    test_backfill_subscriptions()
    test_idempotency()
    test_dual_write()

    total = _PASS + _FAIL
    print(f"\n{'='*40}")
    print(f"  {_PASS}/{total} passed")
    if _FAIL:
        print(f"  {'❌'}  {_FAIL} FAILED")
        sys.exit(1)
    else:
        print(f"  ✅  ALL PASSED")
