"""AI-CSAM topic extraction: lexical only; no embedding-only promotion."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROC = REPO / "src" / "Processing Layer"
AI_PATTERNS = PROC / "Pattern Processing Layer" / "ai_extraction_patterns.py"
MERGE = PROC / "merge_processing.py"


def _load(name: str, path: Path, extra_paths: list[Path] | None = None):
    for p in extra_paths or []:
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ai = _load("ai_extraction_patterns_under_test", AI_PATTERNS, [AI_PATTERNS.parent])


class TestAiCsamLexical(unittest.TestCase):
    def test_artificially_generated_matches(self):
        self.assertTrue(
            ai.AI_CSAM_TOPIC_RE.search("Artificially-Generated Files of CSAM")
        )
        self.assertTrue(
            ai.AI_CSAM_TOPIC_RE.search(
                "possession of artificially generated child sexual abuse material"
            )
        )

    def test_true_genai_still_matches(self):
        self.assertTrue(
            ai.AI_CSAM_TOPIC_RE.search(
                "used artificial intelligence to create child sexual abuse material"
            )
        )
        self.assertTrue(ai.AI_CSAM_TOPIC_RE.search("possessing AI-generated images"))
        self.assertTrue(
            ai.AI_CSAM_TOPIC_RE.search(
                "images were created using artificial intelligence"
            )
        )

    def test_generic_ai_speech_does_not_match(self):
        speech = (
            "The advent of artificial intelligence has additionally made CSAM "
            "much easier to produce and obtain."
        )
        self.assertIsNone(ai.AI_CSAM_TOPIC_RE.search(speech))


class TestNoSemanticPromotion(unittest.TestCase):
    def test_merge_does_not_add_ai_csam_from_embedding(self):
        merge_mod = _load(
            "merge_processing_under_test",
            MERGE,
            [PROC, AI_PATTERNS.parent],
        )
        mp = merge_mod.MergeProcessing()
        merged = mp._merge_semantic_concepts(
            {
                "case_topics": ["possession", "csam"],
                "ml_features": {
                    "semantic_severity": {
                        "scores": {
                            "ai_and_internet_tools": 0.95,
                            "possession_csam": 0.2,
                        }
                    }
                },
            }
        )
        self.assertNotIn("ai_csam", merged.get("case_topics") or [])


if __name__ == "__main__":
    unittest.main()
