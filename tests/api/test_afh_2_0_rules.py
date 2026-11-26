"""AfH 2.0 locked rules: harm rows closed at end dates, the Facebook-in-Messenger correction,
co-occurrence boilerplate patterns, and the enterprise charge used for the coordination family."""
import re
import sys
from pathlib import Path

import yaml

AFH = Path(__file__).resolve().parents[2] / "ontology" / "platform_affordance_evidence" / "afh_manifest"
sys.path.insert(0, str(AFH))

from afhq1 import harm_release as hr  # noqa: E402
from afhq1 import pipeline as pl  # noqa: E402
from afhq1.labels import correct_platform_labels, names_enterprise_charge  # noqa: E402

CODEBOOK = pl.Codebook.load()
CAP = CODEBOOK.classes["UnmonitoredCommunication"]["capability"]


def _chat(ended):
    meta = {CAP: {"since": 1998, "ended": ended}}
    return pl.PlatformInfo("Chat", "specific", "messaging", {CAP: 1998}, None, {CAP: True}, meta)


def test_harm_rows_close_at_registry_end(monkeypatch):
    monkeypatch.setattr(hr, "CLOSE_AT_END", True)
    assert "UnmonitoredCommunication" in hr._default_on(_chat(2012), CODEBOOK, 2012)
    assert "UnmonitoredCommunication" not in hr._default_on(_chat(2012), CODEBOOK, 2013)


def test_open_tables_keep_the_row_after_end(monkeypatch):
    monkeypatch.setattr(hr, "CLOSE_AT_END", False)
    assert "UnmonitoredCommunication" in hr._default_on(_chat(2012), CODEBOOK, 2013)


def test_closing_is_the_committed_default():
    import importlib
    assert importlib.reload(hr).CLOSE_AT_END is True


def test_facebook_only_inside_messenger_becomes_messenger():
    text = "He contacted the victim through Facebook Messenger and sent images."
    assert correct_platform_labels(["Facebook", "Snapchat"], text) == ["Snapchat", "Facebook Messenger"]
    assert correct_platform_labels(["Facebook", "Facebook Messenger"], text) == ["Facebook Messenger"]


def test_standalone_facebook_is_kept():
    text = "He found her on Facebook, then moved to Facebook Messenger."
    assert correct_platform_labels(["Facebook", "Facebook Messenger"], text) == ["Facebook", "Facebook Messenger"]
    assert correct_platform_labels(["Facebook"], "He posted on Facebook.") == ["Facebook"]


def test_boilerplate_patterns_match_the_list_sentences_only():
    cfg = yaml.safe_load((AFH / "config" / "cooc_boilerplate_sentences.yaml").read_text())
    rx = [re.compile(p["regex"], re.I) for p in cfg["patterns"]]
    hit = lambda s: any(r.search(s) for r in rx)  # noqa: E731
    # invented app names: the test must not quote corpus text
    assert hit("Common apps used by suspects include ExampleChat and DemoGram.")
    assert hit("Arrests also have been made involving the gaming apps ExampleQuest.")
    # a conduct sentence naming apps (as in nj_ag_2018_001) must stay an edge
    assert not hit("The defendant used ExampleChat and DemoGram to message the minor.")


def test_enterprise_charge_singular_only():
    assert names_enterprise_charge("He pleaded guilty to engaging in a child exploitation enterprise.")
    assert names_enterprise_charge("charged under 18 U.S.C. § 2252A(g)")
    assert not names_enterprise_charge("Holding those who engage in child exploitation enterprises accountable.")


def test_every_manifest_exemplar_carries_the_coding_label():
    import json
    man = json.loads((AFH / "numbers" / "build" / "manifest.json").read_text())["platforms"]
    exemplars = [x for row in man.values() for x in row["exemplars"]]
    assert exemplars and all(x.get("coding") == "automatically coded" for x in exemplars)


def test_feature_breakdown_follows_the_counter_and_sums_to_nfeatures():
    """Codex: five counted fields were documented as excluded. The breakdown is now generated from
    run/feature_count.py, so a field is excluded in the numbers only if the counter excludes it."""
    import json
    sys.path.insert(0, str(AFH.parents[2] / "run"))
    import feature_count as fc
    cover = json.loads((AFH / "numbers" / "numbers.json").read_text())["1_cover"]
    b = cover["NFeatures_breakdown"]
    assert set(b["excluded"]) == set(fc.EXCLUDED)
    assert not set(b["excluded"]) & (set(fc.COUNTED) | set(fc.ASSERTED_FIELDS))
    assert sum(b["counted_case_attributes"].values()) + sum(b["counted_span_checked_assertions"].values()) == cover["NFeatures"]
    for field in ("perpetrator_admission_themes", "severity_indicators", "anonymization_network", "p2p_clients", "locations"):
        assert field in b["counted_case_attributes"], field
    for field in ("perpetrator_admissions", "severity_phrases", "investigation_technology"):
        assert field in b["excluded"], field


def test_platform_label_copies_are_not_counted_twice():
    sys.path.insert(0, str(AFH.parents[2] / "run"))
    import feature_count as fc
    case = {"platforms_used": ["BitTorrent", "Kik"], "extracted_features": {"p2p_clients": ["BitTorrent", "eMule"],
                                                                         "anonymization_network": ["Tor"]}}
    base = fc.count_case_attributes({"platforms_used": ["BitTorrent", "Kik"], "extracted_features": {}})
    assert fc.count_case_attributes(case) - base == 2      # eMule and Tor; BitTorrent is a platform-label copy


def test_facebook_correction_is_case_insensitive_and_handles_url_slugs():
    """Codex round 1: the matcher tags Facebook case-insensitively; the correction must too.
    Messenger in a URL slug (facebook-messenger) is Messenger, not a separate Facebook mention."""
    assert correct_platform_labels(["Facebook", "Facebook Messenger"], "He used Facebook messenger.") == ["Facebook Messenger"]
    assert correct_platform_labels(["Facebook", "Facebook Messenger"],
                                   "See example.com/man-was-sharing-files-using-facebook-messenger/ for details. He used Facebook Messenger.") == ["Facebook Messenger"]
    assert correct_platform_labels(["Facebook", "Facebook Messenger"], "SHARED FILES ON FACEBOOK; later used Facebook Messenger.") == ["Facebook", "Facebook Messenger"]


def _ev(id=None, file=None, publication=(), event=(), biography=()):
    return {"id": id, "file": file, "publication": sorted(publication), "event": sorted(event), "biography": sorted(biography)}


def test_year_is_corrected_when_two_fields_agree_and_none_supports_it():
    from afhq1.labels import corrected_pub_year
    # ncmec_2022_506: a biography date's year (1992) was stored; id and compilation file say 2022
    assert corrected_pub_year(1992, _ev(id=2022, file=2022, event=[2022], biography=[1992])) == (2022, ["id", "file"])
    # ncmec_2023_597: an event year was stored; id, file and the stated publication date say 2023
    assert corrected_pub_year(2007, _ev(id=2023, file=2023, publication=[2023], event=[2007])) == (2023, ["id", "file", "publication"])


def test_year_is_kept_when_any_publication_evidence_supports_it():
    from afhq1.labels import corrected_pub_year
    assert corrected_pub_year(2021, _ev(id=2022, file=2022, publication=[2021]))[0] == 2021   # stated publication date
    assert corrected_pub_year(2021, _ev(id=2021, file=2022))[0] == 2021                      # id agrees
    assert corrected_pub_year(2021, _ev(id=2022, file=2022, event=[2021]))[0] == 2021         # no stated date: event supports
    assert corrected_pub_year(2021, _ev(id=2022))[0] == 2021                                  # one field is not enough
    assert corrected_pub_year(None, _ev(id=2022, file=2022)) == (None, [])


def test_shipped_numbers_carry_the_year_corrections_and_no_pre_2002_year():
    import json
    d = json.loads((AFH / "numbers" / "numbers.json").read_text())
    c, y = d["1_cover"], d["13_publication_year"]
    assert c["YearStart_publication_year"] >= 2002 and c["cases_before_2002_ids"] == []
    assert c["publication_year_corrections"]["ncmec_2022_506"] == [1992, 2022]
    assert c["publication_year_corrections"]["ncmec_2023_597"] == [2007, 2023]
    assert y["corrected_n"] == len(y["corrections"]) == len(c["publication_year_corrections"])
    assert y["sensitivity_verdict_changes"] == [], y["sensitivity_verdict_changes"]
