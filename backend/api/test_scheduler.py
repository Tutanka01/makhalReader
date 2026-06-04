"""
Tests for scheduler.py — Story 6.1 Background Task Scheduler.

Run from inside the api container:
    python test_scheduler.py
"""
from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest import mock

# Ensure /app is on the path when running inside the container
sys.path.insert(0, os.path.dirname(__file__))

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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_db_module(set_setting_mock: mock.MagicMock, session_mock: mock.MagicMock) -> mock.MagicMock:
    """Build a fake 'database' module with SessionLocal + set_setting."""
    m = mock.MagicMock()
    m.SessionLocal = session_mock
    m.set_setting = set_setting_mock
    m.User = mock.MagicMock()
    return m


# ══════════════════════════════════════════════════════════════════════════════
# Task 1: _run_citation_index_job stores citation_index_last_run_at
# ══════════════════════════════════════════════════════════════════════════════

def test_citation_index_job_stores_last_run_at() -> None:
    """_run_citation_index_job must call set_setting with 'citation_index_last_run_at'."""
    set_setting_mock = mock.MagicMock()
    db_mock = mock.MagicMock()
    session_mock = mock.MagicMock(return_value=db_mock)
    index_mock = mock.AsyncMock(return_value={"indexed_papers": 3, "total_citation_links": 12})

    ci_module = mock.MagicMock()
    ci_module.index_citations = index_mock

    saved = dict(sys.modules)
    sys.modules["database"] = _make_db_module(set_setting_mock, session_mock)
    sys.modules["citation_indexer"] = ci_module

    try:
        import importlib
        import scheduler as sched
        importlib.reload(sched)  # reload so lazy-import uses our mocked modules

        asyncio.run(sched._run_citation_index_job())
    finally:
        sys.modules.update(saved)

    called_keys = [c.args[1] for c in set_setting_mock.call_args_list]
    if "citation_index_last_run_at" in called_keys:
        _ok("citation_index_job stores citation_index_last_run_at")
    else:
        _fail(
            "citation_index_job stores citation_index_last_run_at",
            f"set_setting NOT called with 'citation_index_last_run_at'. Calls: {called_keys}",
        )


def test_citation_index_job_value_is_iso_utc() -> None:
    """The value stored by set_setting must be a valid ISO-8601 UTC timestamp."""
    set_setting_mock = mock.MagicMock()
    db_mock = mock.MagicMock()
    session_mock = mock.MagicMock(return_value=db_mock)
    index_mock = mock.AsyncMock(return_value={"indexed_papers": 1, "total_citation_links": 5})

    ci_module = mock.MagicMock()
    ci_module.index_citations = index_mock

    saved = dict(sys.modules)
    sys.modules["database"] = _make_db_module(set_setting_mock, session_mock)
    sys.modules["citation_indexer"] = ci_module

    try:
        import importlib
        import scheduler as sched
        importlib.reload(sched)

        asyncio.run(sched._run_citation_index_job())
    finally:
        sys.modules.update(saved)

    stored_value: str | None = None
    for c in set_setting_mock.call_args_list:
        if len(c.args) >= 2 and c.args[1] == "citation_index_last_run_at":
            stored_value = c.args[2]
            break

    if stored_value is None:
        _fail("citation_index_job value is ISO UTC", "set_setting was not called with that key")
        return

    try:
        dt = datetime.fromisoformat(stored_value)
        # Must be UTC-aware
        if dt.tzinfo is None:
            _fail("citation_index_job value is ISO UTC", f"timestamp has no timezone: {stored_value}")
        else:
            _ok("citation_index_job value is ISO UTC")
    except ValueError as e:
        _fail("citation_index_job value is ISO UTC", f"not a valid ISO datetime: {stored_value!r} ({e})")


def test_citation_index_job_db_closed_on_error() -> None:
    """DB must be closed even when index_citations raises an exception."""
    set_setting_mock = mock.MagicMock()
    db_mock = mock.MagicMock()
    session_mock = mock.MagicMock(return_value=db_mock)
    # Simulate a failure in index_citations
    index_mock = mock.AsyncMock(side_effect=RuntimeError("SS API down"))

    ci_module = mock.MagicMock()
    ci_module.index_citations = index_mock

    saved = dict(sys.modules)
    sys.modules["database"] = _make_db_module(set_setting_mock, session_mock)
    sys.modules["citation_indexer"] = ci_module

    try:
        import importlib
        import scheduler as sched
        importlib.reload(sched)

        asyncio.run(sched._run_citation_index_job())  # should NOT raise
    finally:
        sys.modules.update(saved)

    if db_mock.close.called:
        _ok("citation_index_job closes DB on error")
    else:
        _fail("citation_index_job closes DB on error", "db.close() was never called after exception")


# ══════════════════════════════════════════════════════════════════════════════
# Task 2: Citation index job has 1-hour offset from author radar
# ══════════════════════════════════════════════════════════════════════════════

def test_citation_index_job_has_start_date_offset() -> None:
    """
    Citation index job must have a start_date at least 30 min from now
    (proxy for the 1-hour offset requirement).
    """
    # We need to inspect the trigger — but we can't start the real scheduler
    # (it would spin up real jobs).  Instead, we inspect what IntervalTrigger
    # gets constructed with by patching it.
    trigger_kwargs_captured: list[dict] = []

    OriginalIntervalTrigger = None
    try:
        from apscheduler.triggers.interval import IntervalTrigger as _IT
        OriginalIntervalTrigger = _IT
    except ImportError:
        _fail("citation_index_job has start_date offset", "apscheduler not installed")
        return

    class CapturingIntervalTrigger(_IT):  # type: ignore[misc]
        def __init__(self, **kwargs):  # type: ignore[override]
            trigger_kwargs_captured.append(kwargs)
            super().__init__(**kwargs)

    saved = dict(sys.modules)
    fake_scheduler_instance = mock.MagicMock()
    fake_scheduler_cls = mock.MagicMock(return_value=fake_scheduler_instance)

    sys.modules["database"] = _make_db_module(mock.MagicMock(), mock.MagicMock())

    try:
        import importlib
        with mock.patch("apscheduler.triggers.interval.IntervalTrigger", CapturingIntervalTrigger):
            with mock.patch("apscheduler.schedulers.asyncio.AsyncIOScheduler", fake_scheduler_cls):
                import scheduler as sched
                importlib.reload(sched)
                sched.start_scheduler()
    finally:
        sys.modules.update(saved)
        # Stop the real scheduler if it somehow started
        if sched._scheduler:
            try:
                sched._scheduler.shutdown(wait=False)
            except Exception:
                pass
            sched._scheduler = None

    # Find the trigger kwargs for the 7-day (citation_index) job
    seven_day_triggers = [kw for kw in trigger_kwargs_captured if kw.get("days") == 7]

    if not seven_day_triggers:
        _fail("citation_index_job has start_date offset", f"No 7-day trigger found. Captured: {trigger_kwargs_captured}")
        return

    # The citation_index is the second 7-day trigger (author_radar is first)
    # Check if any of them has a start_date
    triggers_with_start = [t for t in seven_day_triggers if "start_date" in t]

    if not triggers_with_start:
        _fail(
            "citation_index_job has start_date offset",
            "No 7-day trigger has a 'start_date' parameter (next_run_time=None is a no-op)",
        )
        return

    # Verify start_date is at least 30 min from now (tolerance for the 1h requirement)
    now = datetime.now(timezone.utc)
    start_date = triggers_with_start[-1]["start_date"]
    if hasattr(start_date, "tzinfo") and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    delta = (start_date - now).total_seconds()
    if delta >= 30 * 60:  # at least 30 minutes
        _ok(f"citation_index_job has start_date offset ({delta / 60:.0f} min from now)")
    else:
        _fail(
            "citation_index_job has start_date offset",
            f"start_date is only {delta:.0f}s from now, expected ≥ 1800s",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Existing jobs regression: threat_scan and author_radar still store last_run_at
# ══════════════════════════════════════════════════════════════════════════════

def test_threat_scan_job_still_stores_last_run_at() -> None:
    """Regression: _run_threat_scan_job must still call set_setting with 'threat_scan_last_run_at'."""
    set_setting_mock = mock.MagicMock()
    db_mock = mock.MagicMock()
    session_mock = mock.MagicMock(return_value=db_mock)
    # User query returns empty list (no users to scan)
    db_mock.query.return_value.all.return_value = []

    fake_threat_scan = mock.AsyncMock(return_value=mock.MagicMock(scanned=0, alerts_created=0, skipped=0))

    saved = dict(sys.modules)
    sys.modules["database"] = _make_db_module(set_setting_mock, session_mock)
    sys.modules.setdefault("routers", mock.MagicMock())
    fake_research = mock.MagicMock()
    fake_research._run_threat_scan = fake_threat_scan
    sys.modules["routers.research"] = fake_research

    try:
        import importlib
        import scheduler as sched
        importlib.reload(sched)

        asyncio.run(sched._run_threat_scan_job())
    finally:
        sys.modules.update(saved)

    called_keys = [c.args[1] for c in set_setting_mock.call_args_list]
    if "threat_scan_last_run_at" in called_keys:
        _ok("threat_scan_job still stores threat_scan_last_run_at (regression)")
    else:
        _fail("threat_scan_job still stores threat_scan_last_run_at (regression)", f"Calls: {called_keys}")


def test_author_radar_job_still_stores_last_run_at() -> None:
    """Regression: _run_author_radar_job must still call set_setting with 'author_radar_last_run_at'."""
    set_setting_mock = mock.MagicMock()
    db_mock = mock.MagicMock()
    session_mock = mock.MagicMock(return_value=db_mock)
    db_mock.query.return_value.all.return_value = []

    fake_radar = mock.AsyncMock(return_value=mock.MagicMock(authors_checked=0, new_articles_queued=0, skipped=0))

    saved = dict(sys.modules)
    sys.modules["database"] = _make_db_module(set_setting_mock, session_mock)
    fake_author_radar = mock.MagicMock()
    fake_author_radar.run_author_radar_scan = fake_radar
    sys.modules["author_radar"] = fake_author_radar

    try:
        import importlib
        import scheduler as sched
        importlib.reload(sched)

        asyncio.run(sched._run_author_radar_job())
    finally:
        sys.modules.update(saved)

    called_keys = [c.args[1] for c in set_setting_mock.call_args_list]
    if "author_radar_last_run_at" in called_keys:
        _ok("author_radar_job still stores author_radar_last_run_at (regression)")
    else:
        _fail("author_radar_job still stores author_radar_last_run_at (regression)", f"Calls: {called_keys}")


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n── Story 6.1: Background Task Scheduler Tests ──\n")

    print("Task 1: _run_citation_index_job stores last_run_at")
    test_citation_index_job_stores_last_run_at()
    test_citation_index_job_value_is_iso_utc()
    test_citation_index_job_db_closed_on_error()

    print("\nTask 2: Citation index job has 1-hour offset")
    test_citation_index_job_has_start_date_offset()

    print("\nRegressions: threat_scan and author_radar unchanged")
    test_threat_scan_job_still_stores_last_run_at()
    test_author_radar_job_still_stores_last_run_at()

    print(f"\n── Results: {_PASS} passed, {_FAIL} failed ──\n")
    sys.exit(0 if _FAIL == 0 else 1)
