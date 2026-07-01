import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scorer import (
    SCORING_VERSION,
    ScoreAnalysis,
    build_result,
    build_result_from_llm_content,
    extract_openai_chat_content,
    health,
    normalize_llm_content,
)


class ScoringCalibrationTest(unittest.TestCase):
    def test_practical_opinion_gets_reading_priority_floor(self):
        analysis = ScoreAnalysis(
            topic_fit=2.5,
            technical_depth=1.0,
            operational_value=1.5,
            strategic_value=1.0,
            novelty=0.5,
            noise_penalty=0.5,
            confidence=0.9,
            content_type="opinion",
            tags=["ai-agents"],
            summary_bullets=["Provides concrete autonomy tips for coding agents."],
            reason="Provides actionable tips to increase autonomy of coding agents, but offers little technical depth.",
        )

        result = build_result(analysis, article_words=450, summary_words=35)

        self.assertEqual(result.score, 6.2)
        self.assertEqual(result.score_details["scoring_version"], SCORING_VERSION)
        self.assertEqual(result.score_details["scoring_version"], 3)
        self.assertEqual(result.score_details["adjustments"], ["practical-note", "practical-floor"])
        self.assertEqual(result.score_details["caps"], [])

    def test_vague_ai_opinion_stays_low_value(self):
        analysis = ScoreAnalysis(
            topic_fit=2.0,
            technical_depth=0.5,
            operational_value=0.6,
            strategic_value=0.7,
            novelty=0.4,
            noise_penalty=2.4,
            confidence=0.8,
            content_type="opinion",
            tags=["ai"],
            summary_bullets=["Argues AI agents will improve productivity."],
            reason="Generic AI-agent optimism with little concrete engineering advice.",
        )

        result = build_result(analysis, article_words=450, summary_words=35)

        self.assertLess(result.score, 5.0)
        self.assertEqual(result.score_details["adjustments"], [])

    def test_health_exposes_scoring_version(self):
        payload = asyncio.run(health())

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["scoring_version"], 3)

    def test_malformed_json_with_prose_is_recovered(self):
        content = """
        Here is the score:
        ```json
        {
          "topic_fit": 2.5,
          "technical_depth": 1.6,
          "operational_value": 2.2,
          "strategic_value": IE 0.8,
          "novelty": 1.4,
          "noise_penalty": 0.6,
          "confidence": 0.82,
          "content_type": "tutorial",
          "tags": ["kubernetes", "debugging"],
          "summary_bullets": ["Shows concrete debugging steps."],
          "reason": "Concrete operational guidance with modest novelty.",
        }
        ```
        """

        result = build_result_from_llm_content(
            "OpenRouter",
            content,
            article_words=700,
            summary_words=50,
            metadata={"provider": "OpenRouter", "provider_model": "test/model"},
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.score_details["provider"], "OpenRouter")
        self.assertEqual(result.score_details["provider_model"], "test/model")
        self.assertEqual(result.score_details["content_type"], "tutorial")
        self.assertGreater(result.score, 5.0)

    def test_openai_payload_helper_handles_fragment_content_and_metadata(self):
        content, metadata = extract_openai_chat_content(
            {
                "model": "served/model",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": [
                                {"type": "text", "text": '{"topic_fit": 2.0}'},
                                {"type": "text", "text": '\n'},
                            ]
                        },
                    }
                ],
            },
            "OpenAI-compatible",
            configured_model="configured/model",
        )

        self.assertEqual(content, '{"topic_fit": 2.0}')
        self.assertEqual(metadata["provider"], "OpenAI-compatible")
        self.assertEqual(metadata["provider_model"], "served/model")
        self.assertEqual(metadata["provider_configured_model"], "configured/model")
        self.assertEqual(metadata["provider_finish_reason"], "stop")

    def test_openai_payload_helper_handles_empty_choices_without_raising(self):
        content, metadata = extract_openai_chat_content(
            {"choices": []},
            "OpenAI-compatible",
            configured_model="configured/model",
        )

        self.assertIsNone(content)
        self.assertEqual(metadata["provider_model"], "configured/model")

    def test_non_string_content_dict_can_be_scored(self):
        content = normalize_llm_content(
            {
                "topic_fit": 2.0,
                "technical_depth": 1.5,
                "operational_value": 1.8,
                "strategic_value": 1.1,
                "novelty": 1.0,
                "noise_penalty": 0.7,
                "confidence": 0.75,
                "content_type": "tutorial",
                "tags": ["ops"],
                "summary_bullets": ["Contains practical steps."],
                "reason": "Useful practical note.",
            }
        )

        self.assertIsInstance(content, str)
        assert content is not None
        result = build_result_from_llm_content("OpenAI-compatible", content, article_words=350, summary_words=40)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
