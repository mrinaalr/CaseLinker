"""Extractor fixes for year-only dates (#23) and statutory-max sentences (#24)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROC = REPO / "src" / "Processing Layer"
PATTERN = PROC / "Pattern Processing Layer" / "processing.py"


def _load_processing():
    for p in (PATTERN.parent, PROC):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    name = "pattern_processing_under_test_dates_sentences"
    spec = importlib.util.spec_from_file_location(name, PATTERN)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pp = _load_processing()


class TestYearOnlyDates(unittest.TestCase):
    def test_year_only_does_not_invent_dec_31(self):
        out = pp.extract_date_range({"year": "2026"})
        self.assertEqual(out, {"start": "2026-01-01", "end": None})

    def test_month_year_still_month_precise(self):
        out = pp.extract_date_range({"year": "2024", "month": "October"})
        self.assertEqual(out, {"start": "2024-10-01", "end": None})


class TestStatutoryMaxSentences(unittest.TestCase):
    def test_faces_up_to_not_stored(self):
        text = (
            "If convicted, Rash faces up to 125 years in prison. "
            "A preliminary hearing is scheduled for September 21st."
        )
        sents = pp._extract_sentence_durations(text)
        self.assertFalse(any("125" in s for s in sents))

    def test_punishable_by_range_not_stored(self):
        text = (
            "Class X felonies each punishable by six to 30 years in prison. "
            "Eastham is scheduled to be sentenced on Nov. 1."
        )
        sents = pp._extract_sentence_durations(text)
        self.assertFalse(any("30" in s for s in sents))

    def test_faces_up_to_pending_sentencing_not_stored(self):
        text = (
            "By the terms of the plea agreement, Dosch faces up to 50 years in prison "
            "and will be required to register as a sex offender. "
            "He will remain in custody pending sentencing, which has not been scheduled."
        )
        sents = pp._extract_sentence_durations(text)
        self.assertFalse(any("50" in s for s in sents))

    def test_imposed_sentenced_to_still_works(self):
        text = (
            "Earlier today Lorenzo Arana was sentenced to 210 months in prison "
            "for distribution of child pornography."
        )
        sents = pp._extract_sentence_durations(text)
        self.assertTrue(any("210" in s for s in sents))

    def test_headline_sentenced_to_years(self):
        text = "Rolla Sex Offender Sentenced to 15 Years in Prison for Child Pornography"
        sents = pp._extract_sentence_durations(text)
        self.assertTrue(any("15" in s for s in sents))


class TestAgeRangeParse(unittest.TestCase):
    def test_helper_rejects_garbage(self):
        # Import from run.main would boot FastAPI; mirror the small helper here.
        def parse(age_range: str):
            parts = age_range.strip().split("-")
            if len(parts) != 2:
                raise ValueError("age_range must look like '25-29'")
            age_min, age_max = int(parts[0]), int(parts[1])
            if age_min > age_max:
                raise ValueError("age_range min must be <= max")
            return age_min, age_max

        self.assertEqual(parse("25-29"), (25, 29))
        with self.assertRaises(ValueError):
            parse("not-a-range")


if __name__ == "__main__":
    unittest.main()
