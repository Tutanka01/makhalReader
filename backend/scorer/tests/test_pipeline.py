import asyncio
import json
import sys
import time
import unittest
from pathlib import Path

import httpx
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scorer
from scorer import LlmUsage, ScoreRequest, build_user_message, parse_retry_after


ANALYSIS = {
    "topic_fit": 2.5,
    "technical_depth": 2.0,
    "operational_value": 2.2,
    "strategic_value": 1.0,
    "novelty": 1.5,
    "noise_penalty": 0.4,
    "confidence": 0.85,
    "content_type": "tutorial",
    "reading_lenses": ["practical"],
    "tags": ["kubernetes"],
    "summary_bullets": ["Shows a concrete debugging workflow."],
    "reason": "Concrete operational guidance.",
}


def _request(**overrides) -> ScoreRequest:
    fields = {
        "article_id": 1,
        "title": "Debugging CNI latency",
        "content_text": "word " * 200,
        "feed_name": "r/kubernetes",
        "feed_category": "Communities",
    }
    fields.update(overrides)
    return ScoreRequest(**fields)


class UserMessageTest(unittest.TestCase):
    def test_source_is_named_and_empty_rss_summary_is_omitted(self):
        message, article_words, summary_words = build_user_message(_request(), "")

        self.assertIn("Source: r/kubernetes (feed category: Communities)", message)
        self.assertNotIn("RSS summary", message)
        self.assertEqual(article_words, 200)
        self.assertEqual(summary_words, 0)

    def test_rss_summary_is_kept_when_provided(self):
        message, _, summary_words = build_user_message(_request(rss_summary="short teaser text"), "")

        self.assertIn("RSS summary word count: 3", message)
        self.assertIn("RSS summary:\nshort teaser text", message)
        self.assertEqual(summary_words, 3)

    def test_message_without_source_keeps_legacy_shape(self):
        message, _, _ = build_user_message(_request(feed_name="", feed_category=""), "\n\n## Preference profile")

        self.assertTrue(message.startswith("Title: Debugging CNI latency\nArticle word count in provided text: 200\n\n"))
        self.assertTrue(message.endswith("## Preference profile"))


class UsageTest(unittest.TestCase):
    def test_openrouter_usage_is_accumulated_across_calls(self):
        usage = LlmUsage()
        payload = {
            "usage": {
                "prompt_tokens": 2400,
                "completion_tokens": 300,
                "prompt_tokens_details": {"cached_tokens": 1300},
                "completion_tokens_details": {"reasoning_tokens": 120},
                "cost": 0.0004,
            }
        }
        usage.record_openai_usage(payload)
        usage.record_openai_usage(payload)
        usage.record_openai_usage({"choices": []})

        details = usage.as_details()
        self.assertEqual(details["prompt_tokens"], 4800)
        self.assertEqual(details["completion_tokens"], 600)
        self.assertEqual(details["cached_tokens"], 2600)
        self.assertEqual(details["reasoning_tokens"], 240)
        self.assertAlmostEqual(details["cost"], 0.0008)

    def test_cost_is_absent_when_provider_does_not_report_it(self):
        usage = LlmUsage()
        usage.record_ollama_usage({"prompt_eval_count": 900, "eval_count": 200})

        details = usage.as_details()
        self.assertEqual(details["prompt_tokens"], 900)
        self.assertEqual(details["completion_tokens"], 200)
        self.assertNotIn("cost", details)


class RetryAfterTest(unittest.TestCase):
    def test_retry_after_seconds(self):
        self.assertEqual(parse_retry_after(httpx.Headers({"Retry-After": "17"})), 17)

    def test_ratelimit_reset_epoch_ms(self):
        reset_ms = int((time.time() + 120) * 1000)
        seconds = parse_retry_after(httpx.Headers({"X-RateLimit-Reset": str(reset_ms)}))
        self.assertTrue(115 <= seconds <= 120, seconds)

    def test_default_when_no_hint(self):
        self.assertEqual(parse_retry_after(httpx.Headers()), scorer.DEFAULT_RATE_LIMIT_RETRY_SECONDS)


class ScoreEndpointTest(unittest.TestCase):
    def setUp(self):
        self.saved = {
            name: getattr(scorer, name)
            for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_DISABLE_FALLBACK", "OPENROUTER_API_KEY", "OLLAMA_URL")
        }
        scorer.LLM_BASE_URL = "http://llm.test/v1"
        scorer.LLM_MODEL = "test/model"
        scorer.LLM_DISABLE_FALLBACK = True
        scorer.OPENROUTER_API_KEY = ""
        scorer.OLLAMA_URL = ""
        scorer._preference_cache = None
        self.posted_scores = []
        self.feedback_calls = 0

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(scorer, name, value)
        scorer._http_client = None
        scorer._preference_cache = None

    def _install_transport(self, llm_handler):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/internal/feedback-examples":
                self.feedback_calls += 1
                return httpx.Response(200, json={"total_liked": 0})
            if request.url.path.startswith("/api/internal/articles/"):
                self.posted_scores.append(json.loads(request.content))
                return httpx.Response(200, json={"status": "ok"})
            return llm_handler(request)

        scorer._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def test_usage_is_persisted_with_the_score(self):
        def llm(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.assertIn("Source: r/kubernetes", body["messages"][1]["content"])
            return httpx.Response(
                200,
                json={
                    "model": "test/model",
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(ANALYSIS)}}],
                    "usage": {"prompt_tokens": 2500, "completion_tokens": 250, "cost": 0.001},
                },
            )

        self._install_transport(llm)

        async def run():
            await scorer.score_article(_request(article_id=1))
            await scorer.score_article(_request(article_id=2))

        asyncio.run(run())

        self.assertEqual(len(self.posted_scores), 2)
        usage = self.posted_scores[0]["score_details"]["llm_usage"]
        self.assertEqual(usage["calls"], 1)
        self.assertEqual(usage["prompt_tokens"], 2500)
        self.assertEqual(usage["completion_tokens"], 250)
        self.assertAlmostEqual(usage["cost"], 0.001)
        self.assertEqual(self.posted_scores[0]["score_details"]["scoring_version"], 4)
        # The preference profile is fetched once, then served from cache.
        self.assertEqual(self.feedback_calls, 1)

    def test_provider_429_is_reported_as_429_with_retry_after(self):
        def llm(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "42"}, json={"error": {"message": "Rate limit exceeded"}})

        self._install_transport(llm)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(scorer.score_article(_request()))

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.headers, {"Retry-After": "42"})
        self.assertEqual(self.posted_scores, [])

    def test_unparseable_answer_is_still_a_503(self):
        def llm(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "no json here"}}]})

        self._install_transport(llm)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(scorer.score_article(_request()))

        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
