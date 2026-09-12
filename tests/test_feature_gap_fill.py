"""Gap-fill extractors: PSC topic, USAO agency, careful RSO/prior, of-anchored ages."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROC = REPO / "src" / "Processing Layer"
PATTERN = PROC / "Pattern Processing Layer"
AI_PATTERNS = PATTERN / "ai_extraction_patterns.py"
PROCESSING = PATTERN / "processing.py"
NORMALIZE = PROC / "agency_label_normalize.py"
FEATURES_TO_CAC = REPO / "ontology" / "features_to_cac.py"


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


ai = _load("ai_patterns_gap_fill", AI_PATTERNS, [PATTERN])
proc = _load("processing_gap_fill", PROCESSING, [PATTERN, PROC])
norm = _load("agency_normalize_gap_fill", NORMALIZE, [PROC])
cac = _load("features_to_cac_gap_fill", FEATURES_TO_CAC, [REPO / "ontology"])


class TestProjectSafeChildhoodTopic(unittest.TestCase):
    def test_boilerplate_hits(self):
        text = (
            "This case was brought as part of Project Safe Childhood, a nationwide "
            "initiative launched in May 2006 by the Department of Justice."
        )
        self.assertTrue(ai.PROJECT_SAFE_CHILDHOOD_TOPIC_RE.search(text))
        topics = proc.extract_topics({"case_text": text})
        self.assertIn("project_safe_childhood", topics)

    def test_no_false_friend(self):
        text = "Officers took the child to a safe childhood advocacy center nearby."
        self.assertIsNone(ai.PROJECT_SAFE_CHILDHOOD_TOPIC_RE.search(text))
        topics = proc.extract_topics({"case_text": text})
        self.assertNotIn("project_safe_childhood", topics)

    def test_topic_map_wired(self):
        self.assertIn("project_safe_childhood", cac.TOPIC_MAP)
        self.assertEqual(
            cac.TOPIC_MAP["project_safe_childhood"]["class"],
            cac.CAC_MULTI.ProjectSafeChildhoodOperation,
        )


class TestUsaoAgency(unittest.TestCase):
    def test_assistant_us_attorney_case_action(self):
        text = (
            "HSI began the investigation in 2024. Assistant U.S. Attorney Kyle Bateman "
            "prosecuted the case."
        )
        info = proc.extract_investigation_info({"case_text": text})
        self.assertIsNotNone(info)
        self.assertIn("U.S. Attorney's Office", info["agencies"])

    def test_named_us_attorney(self):
        text = (
            "Following an online investigation, U.S. Attorney Erik S. Siebert for the "
            "Eastern District of Virginia announced the charges."
        )
        info = proc.extract_investigation_info({"case_text": text})
        self.assertIsNotNone(info)
        self.assertIn("U.S. Attorney's Office", info["agencies"])

    def test_psc_boilerplate_plural_offices_not_enough(self):
        """Plural Attorneys' Offices in PSC boilerplate alone must not tag USAO."""
        text = (
            "The investigation remains ongoing. Led by U.S. Attorneys’ Offices and CEOS, "
            "Project Safe Childhood marshals federal resources."
        )
        info = proc.extract_investigation_info({"case_text": text})
        # may be None (no inv type) or unknown with CEOS — but not USAO from plural alone
        agencies = (info or {}).get("agencies") or []
        self.assertNotIn("U.S. Attorney's Office", agencies)

    def test_normalize_person_byline_to_office(self):
        out = norm.canonicalize_agency_label_for_storage(
            "Assistant U.S. Attorney Kyle Bateman"
        )
        self.assertEqual(out, "U.S. Attorney's Office")
        out2 = norm.canonicalize_agency_label_for_storage("USAO")
        self.assertEqual(out2, "U.S. Attorney's Office")


class TestRsoAndPriorConviction(unittest.TestCase):
    def test_registered_sex_offender(self):
        text = "Smith, a registered sex offender, was arrested after an investigation."
        demo = proc.extract_perpetrator_demographics({"case_text": text})
        self.assertTrue(demo and demo["is_registered"])
        prev = proc.extract_previous_conviction({"case_text": text})
        self.assertTrue(prev and prev["is_registered"])

    def test_previously_convicted_sex_offender(self):
        text = (
            "A district court judge convicted a previously convicted sex offender of "
            "distributing CSAM while on supervised release."
        )
        demo = proc.extract_perpetrator_demographics({"case_text": text})
        self.assertTrue(demo and demo["is_registered"])
        prev = proc.extract_previous_conviction({"case_text": text})
        self.assertTrue(prev["is_registered"])
        self.assertTrue(prev["has_prior_conviction"])

    def test_prior_conviction_without_rso_phrase(self):
        text = (
            "Due to his prior conviction, Gonzalez faces a mandatory minimum penalty "
            "of 15 years in prison."
        )
        demo = proc.extract_perpetrator_demographics({"case_text": text})
        # prior conviction alone must NOT flip RSO
        self.assertTrue(demo is None or demo.get("is_registered") is False)
        prev = proc.extract_previous_conviction({"case_text": text})
        self.assertIsNotNone(prev)
        self.assertTrue(prev["has_prior_conviction"])
        self.assertFalse(prev["is_registered"])

    def test_bare_sex_offender_footer_not_rso(self):
        text = (
            "HSI works every day to find sex offenders and child sex traffickers.\n"
            "Missouri man sentenced after HSI St. Louis investigation."
        )
        demo = proc.extract_perpetrator_demographics({"case_text": text})
        self.assertTrue(demo is None or demo.get("is_registered") is False)
        prev = proc.extract_previous_conviction({"case_text": text})
        self.assertIsNone(prev)

    def test_repeat_csam_offenses_is_prior(self):
        text = "Virginia Man Found Guilty of Repeat CSAM Offenses after an investigation."
        prev = proc.extract_previous_conviction({"case_text": text})
        self.assertIsNotNone(prev)
        self.assertTrue(prev["has_prior_conviction"])


class TestOfAnchoredPerpAge(unittest.TestCase):
    def test_name_age_of_was_sentenced_keeps_age(self):
        text = (
            "Homeland Security Investigations announced that Richard James Miller, 41, "
            "of St. Francois County, was sentenced to 50 years in federal prison."
        )
        ages, _ = proc._collect_perp_comma_ages(text)
        self.assertIn(41, ages)
        demo = proc.extract_perpetrator_demographics({"case_text": text})
        self.assertIsNotNone(demo)
        self.assertIn(41, demo["ages"])

    def test_sentence_years_still_filtered(self):
        text = (
            "After an investigation, the defendant was sentenced to 41 years in prison "
            "for production of child sexual abuse material."
        )
        demo = proc.extract_perpetrator_demographics({"case_text": text})
        ages = (demo or {}).get("ages") or []
        self.assertNotIn(41, ages)

    def test_doj_style_dateline(self):
        text = (
            "Further investigation revealed that the user was Antonio Rudy Gonzalez, 41, "
            "of Alexandria, who sent dozens of images. He is scheduled to be sentenced."
        )
        demo = proc.extract_perpetrator_demographics({"case_text": text})
        self.assertIsNotNone(demo)
        self.assertIn(41, demo["ages"])


class TestEndToEndSamplePress(unittest.TestCase):
    """Smoke: features that move the corpus leaf counter on real press shapes."""

    def test_doj_ceos_shaped(self):
        text = (
            "Virginia Man Found Guilty of Repeat CSAM Offenses\n"
            "A district court judge yesterday convicted a previously convicted sex offender "
            "of distributing and possessing child sexual abuse material (CSAM).\n"
            "According to court documents, law enforcement began an investigation into a "
            "Kik user. Antonio Rudy Gonzalez, 41, of Alexandria, sent dozens of images.\n"
            "Due to his prior conviction, Gonzalez faces a mandatory minimum.\n"
            "U.S. Attorney Erik S. Siebert for the Eastern District of Virginia announced "
            "the verdict. The FBI Washington Field Office investigated the case.\n"
            "This case was brought as part of Project Safe Childhood, a nationwide initiative."
        )
        feats = proc.extract_features(
            {"case_text": text, "source": "DOJ CEOS", "year": "2025"}
        )
        self.assertIn("project_safe_childhood", feats["case_topics"])
        self.assertTrue(feats["perpetrator_registered_sex_offender"])
        self.assertIn(41, feats.get("perpetrator_age") or [])
        self.assertIn("U.S. Attorney's Office", feats.get("agencies_involved") or [])
        prev = feats.get("previous_conviction") or {}
        self.assertTrue(prev.get("has_prior_conviction"))

    def test_ice_shaped(self):
        text = (
            "sex offenders and child sex traffickers.\n"
            "Missouri man sentenced to 50 years for recording child sexual abuse after "
            "HSI St. Louis investigation\n"
            "Richard James Miller, 41, of St. Francois County, was sentenced to 50 years "
            "in federal prison. Miller pleaded guilty to production of child sexual abuse "
            "material.\n"
            "Assistant U.S. Attorney Kyle Bateman prosecuted the case.\n"
            "This case was brought as part of Project Safe Childhood, a nationwide initiative."
        )
        feats = proc.extract_features(
            {"case_text": text, "source": "ICE", "year": "2026"}
        )
        self.assertIn("project_safe_childhood", feats["case_topics"])
        # footer must not flip RSO
        self.assertFalse(feats["perpetrator_registered_sex_offender"])
        self.assertIn(41, feats.get("perpetrator_age") or [])
        self.assertIn("U.S. Attorney's Office", feats.get("agencies_involved") or [])


if __name__ == "__main__":
    unittest.main()
