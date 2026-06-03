"""Tests for ScoreRequest model + prompt cache (Story 5.2-5.4, FR-MT-27-29)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

_SCORER_DIR = Path(__file__).resolve().parent.parent
if str(_SCORER_DIR) not in sys.path:
    sys.path.insert(0, str(_SCORER_DIR))

from scorer import ScoreRequest, _resolve_system_prompt
from prompt import SYSTEM_PROMPT


def sync_await(coro):
    """Run a coroutine synchronously in tests."""
    return asyncio.run(coro)


class TestUserContext:
    def test_user_context_defaults_to_none(self):
        req = ScoreRequest(
            article_id=1, title="Test", content_text="Content", user_id=1
        )
        assert req.user_context is None

    def test_user_context_accepts_dict(self):
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context={"thesis_title": "My Thesis", "thesis_question": "My Q"},
        )
        assert req.user_context == {"thesis_title": "My Thesis", "thesis_question": "My Q"}

    def test_user_context_preserves_backward_compat(self):
        """ScoreRequest must still work without user_context (NFR-T4)."""
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            rss_summary="Summary",
            paper_meta_json=None,
        )
        assert req.article_id == 1
        assert req.title == "Test"
        assert req.content_text == "Content"
        assert req.rss_summary == "Summary"
        assert req.user_id == 1
        assert req.paper_meta_json is None
        assert req.user_context is None

    def test_user_context_accepts_empty_dict(self):
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context={},
        )
        assert req.user_context == {}

    def test_user_context_accepts_nested_dict(self):
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context={
                "scoring_clusters": [
                    {"id": "Z", "name": "Cluster Z", "description": "Desc", "reward_level": "high"}
                ]
            },
        )
        assert req.user_context["scoring_clusters"][0]["id"] == "Z"

    def test_user_context_nonexplicit_default_does_not_break_serialization(self):
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
        )
        dumped = req.model_dump()
        assert dumped["user_context"] is None


class TestResolveSystemPrompt:
    def test_no_user_context_returns_static_prompt(self):
        """Backward compat: when user_context is None, return SYSTEM_PROMPT unchanged."""
        req = ScoreRequest(
            article_id=1, title="Test", content_text="Content", user_id=1
        )
        result = _resolve_system_prompt(req)
        assert result is SYSTEM_PROMPT

    def test_empty_user_context_returns_static_prompt(self):
        """Empty dict is falsy — falls through to static prompt."""
        req = ScoreRequest(
            article_id=1, title="Test", content_text="Content", user_id=1, user_context={}
        )
        result = _resolve_system_prompt(req)
        assert result is SYSTEM_PROMPT

    def test_user_context_with_thesis_generates_dynamic_prompt(self):
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context={"thesis_title": "Custom Thesis Title"},
        )
        result = _resolve_system_prompt(req)
        assert result is not SYSTEM_PROMPT
        assert "Custom Thesis Title" in result

    def test_user_context_with_question_generates_dynamic_prompt(self):
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context={"thesis_question": "Custom research question?"},
        )
        result = _resolve_system_prompt(req)
        assert "Custom research question?" in result

    def test_user_context_infra_profile_returns_infra_template(self):
        """Infra profile has no dynamic sections — PromptBuilder returns it unchanged."""
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context={"prompt_profile": "infra"},
        )
        result = _resolve_system_prompt(req)
        # infra.md has ## PRIORITY THEMES — unified.md does not
        assert "## PRIORITY THEMES" in result

    def test_user_context_with_venues_injects_venues(self):
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context={"tracked_venues": ["VenueA", "VenueB"]},
        )
        result = _resolve_system_prompt(req)
        assert "VenueA, VenueB" in result

    def test_scoring_functions_accept_system_prompt_parameter(self):
        """Verify the scoring functions accept the new system_prompt parameter."""
        from scorer import score_with_uni_server, score_with_openrouter, score_with_ollama
        import inspect

        sig_uni = inspect.signature(score_with_uni_server)
        sig_or = inspect.signature(score_with_openrouter)
        sig_ollama = inspect.signature(score_with_ollama)

        assert "system_prompt" in sig_uni.parameters
        assert "system_prompt" in sig_or.parameters
        assert "system_prompt" in sig_ollama.parameters


class TestResolveCachedPrompt:
    """Tests for _resolve_cached_prompt with mocked HTTP (FR-MT-29)."""

    @pytest.fixture
    def user_context(self):
        return {"thesis_title": "Cached Thesis"}

    @pytest.fixture
    def user_id(self):
        return 42

    @pytest.fixture
    def mock_client(self):
        return AsyncMock(spec=httpx.AsyncClient)

    def test_cache_hit_returns_cached_text(self, mock_client, user_context, user_id):
        """When hash matches, return cached text without building a new prompt."""
        import hashlib
        import json
        from scorer import _resolve_cached_prompt

        raw = json.dumps(user_context, sort_keys=True)
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

        mock_response = Mock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "hash": expected_hash,
            "text": "CACHED PROMPT TEXT",
        }
        mock_client.get.return_value = mock_response

        result = sync_await(_resolve_cached_prompt(mock_client, user_context, user_id))

        assert result == "CACHED PROMPT TEXT"
        mock_client.get.assert_awaited_once()
        mock_client.put.assert_not_awaited()

    def test_cache_miss_builds_and_stores(self, mock_client, user_context, user_id):
        """When hash differs, build via PromptBuilder and store via PUT."""
        from scorer import _resolve_cached_prompt

        mock_get = Mock()
        mock_get.is_success = True
        mock_get.json.return_value = {"hash": "oldhash", "text": "OLD TEXT"}
        mock_client.get.return_value = mock_get

        mock_put = Mock()
        mock_put.is_success = True
        mock_client.put.return_value = mock_put

        result = sync_await(_resolve_cached_prompt(mock_client, user_context, user_id))

        assert "Cached Thesis" in result
        assert result != "OLD TEXT"
        mock_client.get.assert_awaited_once()
        mock_client.put.assert_awaited_once()

    def test_cache_miss_null_hash_builds_and_stores(self, mock_client, user_context, user_id):
        """When stored hash is None, build prompt and store."""
        from scorer import _resolve_cached_prompt

        mock_get = Mock()
        mock_get.is_success = True
        mock_get.json.return_value = {"hash": None, "text": None}
        mock_client.get.return_value = mock_get

        mock_put = Mock()
        mock_put.is_success = True
        mock_client.put.return_value = mock_put

        result = sync_await(_resolve_cached_prompt(mock_client, user_context, user_id))

        assert "Cached Thesis" in result
        mock_client.put.assert_awaited_once()

    def test_api_failure_graceful_degradation(self, mock_client, user_context, user_id):
        """When API call fails, build prompt without caching (NFR-T6)."""
        from scorer import _resolve_cached_prompt

        mock_client.get.side_effect = httpx.ConnectError("No route to host")

        result = sync_await(_resolve_cached_prompt(mock_client, user_context, user_id))

        assert "Cached Thesis" in result
        mock_client.get.assert_awaited_once()
        mock_client.put.assert_awaited_once()


class TestPollerDispatchIntegration:
    """Story 5.5 (FR-MT-30) — user_context built by poller from API is correctly consumed."""

    def test_full_user_context_from_poller_produces_correct_prompt(self):
        """Simulate the dict that fetch_user_scoring_context returns."""
        user_context = {
            "thesis_title": "AI-driven MBSE for CPS",
            "thesis_question": "How can AI agents be integrated into SE?",
            "thesis_contribution": "A novel framework for AI-augmented MBSE.",
            "tracked_venues": ["ICSE", "MODELS", "CAiSE"],
            "scoring_clusters": [
                {"id": "Z", "name": "Test Cluster", "description": "A test cluster", "reward_level": "high"}
            ],
            "avoid_topics": ["DevOps", "Kubernetes"],
            "prompt_profile": "unified",
        }
        req = ScoreRequest(
            article_id=1,
            title="Test",
            content_text="Content",
            user_id=1,
            user_context=user_context,
        )
        result = _resolve_system_prompt(req)
        assert result is not SYSTEM_PROMPT
        assert "AI-driven MBSE for CPS" in result
        assert "How can AI agents be integrated into SE?" in result
        assert "ICSE, MODELS, CAiSE" in result
        assert "[Cluster Z] Test Cluster" in result
        assert "High reward" in result or "high reward" in result


