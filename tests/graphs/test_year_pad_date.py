"""A year-only date is stored as YYYY-01-01. The graph must not call that January."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from rdflib import XSD

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))
_spec = importlib.util.spec_from_file_location(
    "features_to_cac", ROOT / "ontology" / "pipeline" / "features_to_cac.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_year_pad_is_a_year():
    lit = mod._date_at_stated_precision("2024-01-01", None)
    assert (str(lit), lit.datatype) == ("2024", XSD.gYear)


def test_stated_january_first_stays_a_day():
    lit = mod._date_at_stated_precision("2024-01-01", "2024-01-01")
    assert (str(lit), lit.datatype) == ("2024-01-01", XSD.date)


def test_a_firearm_count_is_not_a_csam_charge():
    warnings: list = []
    cls, _cluster, _generic = mod.CaseToCAC._match_charge("possession of a firearm", warnings)
    assert "CSAM" not in str(cls)
    cls, _cluster, _generic = mod.CaseToCAC._match_charge("reproduction of child pornography", warnings)
    assert "Production" not in str(cls)
    cls, _cluster, _generic = mod.CaseToCAC._match_charge("possession of child pornography", warnings)
    assert "Possession" in str(cls)


def test_month_pad_stays_a_month():
    lit = mod._date_at_stated_precision("2017-03-01", None)
    assert (str(lit), lit.datatype) == ("2017-03", XSD.gYearMonth)


def test_luring_keeps_online_enticement_and_a_firearm_gets_no_csam_class():
    warnings: list = []
    for charge in ("luring", "enticement"):
        cls, _cluster, generic = mod.CaseToCAC._match_charge(charge, warnings)
        assert str(cls).endswith("OnlineEnticement"), (charge, cls)
        assert generic is False
    cls, _cluster, _generic = mod.CaseToCAC._match_charge("possession of a firearm", warnings)
    assert "CSAM" not in str(cls)
    cls, _cluster, _generic = mod.CaseToCAC._match_charge("drug trafficking", warnings)
    assert "SexTrafficking" not in str(cls)
