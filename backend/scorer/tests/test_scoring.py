import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scorer import ScoreAnalysis, build_result


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


if __name__ == "__main__":
    unittest.main()
