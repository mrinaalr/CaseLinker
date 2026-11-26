"""AfH 2.0 Q1 eligibility, capability levels and outputs. Synthetic text only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "platform_affordance_evidence" / "afh_manifest"))

from afhq1 import citations, pipeline as pl  # noqa: E402
from afhq1 import snapshot  # noqa: E402

REG = pl.platform_registry()
CB = pl.Codebook.load()
OUT = ROOT / "ontology" / "platform_affordance_evidence" / "afh_manifest" / "numbers" / "build"   # shipped AfH 2.0 build


def run(text: str, platforms, year=2024, topics=()):
    case = {"id": "synthetic_2024_001", "source": "SYNTH", "pub_year": year, "text": text,
            "platforms": list(platforms), "topics": list(topics)}
    recs, excluded = pl.classify_case(case, "fp", REG, CB)
    return {r.platform: r for r in recs}, excluded


HEAD = "Synthetic Man Sentenced\nMarch 3, 2024\n\nA synthetic county man was sentenced today in federal court. "


# --- eligibility ------------------------------------------------------------

def test_generic_labels_are_broad_not_strict_and_online_is_excluded():
    recs, excluded = run(HEAD + "He used social media and chat apps to contact a minor online.", ["social media", "chat", "online"])
    assert {r.status for r in recs.values()} == {"generic"}
    assert {e["reason"] for e in excluded} == {"generic_excluded"}
    t = pl.tier_counts(list(recs.values()), lambda r: r.status == "specific")
    assert t["cases"] == 0


def test_unknown_label_is_not_silently_specific():
    assert pl.platform_info("BrandNewApp", REG).status == "unregistered"


def test_every_label_in_the_published_candidate_pool_is_registered():
    cand = json.loads((ROOT / "ontology/platform_affordance_evidence/candidates.json").read_text())
    missing = [e["platform"] for e in cand["flat"] if pl.platform_info(e["platform"], REG).status == "unregistered"]
    assert missing == []


def test_tiers_are_mutually_exclusive_and_sum():
    a = pl.Record("c1", "f", "S", 2024, "Kik", "specific", "messaging", "stated", True)
    b = pl.Record("c1", "f", "S", 2024, "Snapchat", "specific", "messaging", "named_only", True)
    c = pl.Record("c2", "f", "S", 2024, "Kik", "specific", "messaging", "inferred", True)
    t = pl.tier_counts([a, b, c])
    assert (t["cases"], t["cases_stated"], t["cases_inferred"], t["cases_named_only"]) == (2, 1, 1, 0)
    assert t["records"] == 3


# --- capability levels ------------------------------------------------------

def test_capability_is_dated_by_publication_year():
    text = HEAD + "He used WhatsApp to send sexually explicit images to the minor."
    before, _ = run(text, ["WhatsApp"], year=2019)
    after, _ = run(text, ["WhatsApp"], year=2024)
    edge, _ = run(text, ["WhatsApp"], year=2021)
    assert before["WhatsApp"].available["Ephemerality"] is False
    assert after["WhatsApp"].available["Ephemerality"] is True
    assert edge["WhatsApp"].period_uncertain["Ephemerality"] is True


def test_platform_identity_alone_never_makes_instrumental_use():
    recs, _ = run(HEAD + "Investigators later learned the defendant had a Kik account.", ["Kik"])
    r = recs["Kik"]
    assert r.available["Anonymity"] is True
    assert not any(r.instrumental.values())


def test_conduct_on_ephemeral_platform_is_action_relevant_not_instrumental():
    recs, _ = run(HEAD + "He used Snapchat to solicit nude images from a 13-year-old girl.", ["Snapchat"])
    r = recs["Snapchat"]
    assert r.tier == "stated"
    assert r.available["Ephemerality"] and r.action_relevant["Ephemerality"]
    assert r.instrumental["Ephemerality"] is False


def test_stated_ephemerality_is_instrumental():
    recs, _ = run(HEAD + "He used Snapchat to solicit images, telling the girl the photos would disappear after viewing.", ["Snapchat"])
    assert recs["Snapchat"].instrumental["Ephemerality"] is True


def test_offender_persona_is_anonymity_but_undercover_persona_is_not():
    offender, _ = run(HEAD + "He contacted the girl on Snapchat while posing as a 15-year-old boy.", ["Snapchat"])
    agent, _ = run(HEAD + "An undercover agent posing as a 14-year-old girl chatted with him on Kik.", ["Kik"])
    wrapped, _ = run(HEAD + "An HSI agent,\nposing as a buyer, contacted him through his Telegram account.", ["Telegram"])
    assert offender["Snapchat"].instrumental["Anonymity"] is True
    assert agent["Kik"].instrumental["Anonymity"] is False
    assert wrapped["Telegram"].instrumental["Anonymity"] is False


def test_description_of_the_app_is_not_instrumental():
    recs, _ = run(HEAD + "He sought images from his uncle over Telegram, an encrypted messaging application.", ["Telegram"])
    assert recs["Telegram"].instrumental["UnmonitoredCommunication"] is False
    recs, _ = run(HEAD + "Kik is a file-sharing and social media platform that lets users stay anonymous and he distributed files there.", ["Kik"])
    assert recs["Kik"].instrumental["DistributionInfrastructure"] is False


def test_group_distribution_is_instrumental():
    recs, _ = run(HEAD + "He shared child pornography within a public chat group on the Kik messaging application.", ["Kik"])
    assert recs["Kik"].instrumental["DistributionInfrastructure"] is True


def test_official_quote_about_ai_is_not_generative_use():
    recs, _ = run(HEAD + "We confront new threats like AI-generated abuse material, the Gen AI era demands it.", ["Gen AI"], year=2025)
    r = recs.get("Gen AI")
    assert r is None or r.instrumental["GenerativeSynthesis"] is False


# --- outputs (need the pinned snapshot) ----------------------------------------

# The full-text snapshot holds case text and is never shipped; numbers/run_all.sh exports it from the
# frozen caselinker.db. Tests that compare outputs with case text need it.
needs_snapshot = pytest.mark.skipif(not snapshot.SNAPSHOT.is_file(), reason="full-text snapshot is local-only (numbers/run_all.sh)")


def test_committed_outputs_reconcile():
    inv = json.loads((OUT / "inventory.json").read_text())
    assert all(inv["reconciliation"].values()), inv["reconciliation"]


@needs_snapshot
def test_every_committed_citation_resolves_to_the_same_content():
    con = snapshot.connect()
    fps = dict(con.execute("SELECT case_id, fingerprint FROM fingerprints"))
    verdicts = citations.verify(citations.load(OUT / "citations.json"), fps)
    assert {v.status for v in verdicts} == {"ok"}


@needs_snapshot
def test_committed_outputs_match_the_snapshot_they_name():
    con = snapshot.connect()
    have = snapshot.snapshot_meta(con)["dataset_identity"]
    want = json.loads((OUT / "RUN_IDENTITY.json").read_text())["dataset_identity"]
    assert have == want, "the local snapshot is not the corpus the shipped AfH 2.0 build names"


@needs_snapshot
def test_outputs_hold_no_source_text():
    """No string of 25+ characters in any output appears in any release (hashes aside)."""
    import csv
    import re
    hexish = re.compile(r"^[0-9a-f]{16,64}$")
    strings = set()
    for path in OUT.glob("*.json"):
        strings |= {v for v in _walk(json.loads(path.read_text())) if isinstance(v, str)}
    with (OUT / "records.csv").open() as f:
        for row in csv.reader(f):
            strings |= set(row)
    long_ = {s.strip() for s in strings if len(s.strip()) >= 25 and not hexish.match(s.strip())}
    con = snapshot.connect()
    texts = [t.lower() for (t,) in con.execute("SELECT case_text FROM cases")]
    leaked = [s for s in long_ if any(s.lower() in t for t in texts)]
    assert leaked == []


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


# --- 2026-11-17: five levels and dated registry ----------------------------------

def test_levels_nest():
    """C <= I <= B <= A_any (`available`). A (default_on, window open) is also within A_any, but is not
    part of the chain: a C can sit on an opt-in feature."""
    recs, _ = run(HEAD + "He contacted the 14-year-old girl on Kik and asked her for nude photos.", ["Kik"])
    r = recs["Kik"]
    for c in pl.CLASSES:
        assert r.instrumental[c] <= r.inferred[c] <= r.action_relevant[c] <= r.available[c], c
        assert r.default_on_open[c] <= r.available[c], c


OMEGLE_USE = "He contacted the 14-year-old girl on Omegle and asked her for nude photos."


def test_level_i_and_a_close_at_registry_end():
    """Omegle's capabilities end in 2023: a 2024 release has no level at all (every level closes at `ended`)."""
    open_, _ = run(HEAD + OMEGLE_USE, ["Omegle"], year=2022)
    closed, _ = run(HEAD + OMEGLE_USE, ["Omegle"], year=2024)
    for c in ("Anonymity", "ContactDiscovery"):
        assert open_["Omegle"].default_on_open[c] and open_["Omegle"].inferred[c], c
        r = closed["Omegle"]
        assert not (r.available[c] or r.action_relevant[c] or r.default_on_open[c] or r.inferred[c]), c


def test_shipped_records_a_matches_the_harm_release_window_rule():
    """records.csv A must equal harm_release._on_at, the rule the harm tables and recurrence use."""
    import csv
    from afhq1 import harm_release as hr
    with (OUT / "records.csv").open() as f:
        rows = list(csv.DictReader(f))
    bad = [(r["case_id"], r["platform"], c) for r in rows for c in pl.CLASSES
           if (r[f"{c}.A"] == "1") != (r[f"{c}.A_any"] == "1" and hr._on_at(pl.platform_info(r["platform"], REG),
                                                                           CB.classes[c]["capability"], int(r["pub_year"])))]
    assert bad == []


def test_by_design_feature_gives_inferred_not_explicit():
    recs, _ = run(HEAD + "He contacted the 14-year-old girl on Kik and asked her for nude photos.", ["Kik"])
    r = recs["Kik"]
    assert r.action_relevant["Anonymity"] and r.inferred["Anonymity"]
    assert r.instrumental["Anonymity"] is False


def test_opt_in_feature_does_not_give_inferred():
    # WhatsApp disappearing messages are opt-in: conduct there is B, not I.
    recs, _ = run(HEAD + "He used WhatsApp to solicit nude images from a 13-year-old girl.", ["WhatsApp"], year=2024)
    r = recs["WhatsApp"]
    assert r.action_relevant["Ephemerality"] and not r.inferred["Ephemerality"]


def test_named_only_never_reaches_b_or_i():
    recs, _ = run(HEAD + "Tips came from several companies including Snapchat.", ["Snapchat"])
    r = recs["Snapchat"]
    assert not any(r.action_relevant.values()) and not any(r.inferred.values())


def test_registry_rows_are_dated_and_sourced():
    import yaml
    cfg = yaml.safe_load((ROOT / "ontology/platform_affordance_evidence/afh_manifest/config/platforms.yaml").read_text())
    assert cfg["version"] == "platforms-3"
    for label, row in cfg["platforms"].items():
        for key, cap in (row.get("capabilities") or {}).items():
            assert isinstance(cap, dict) and cap["since"] and cap["confidence"], (label, key)
            assert row.get("basis"), label


def test_live_voice_and_expiring_links_are_not_ephemerality():
    for label in ("Roblox", "Xbox Live", "Dropbox", "Omegle"):
        assert "ephemerality" not in REG[label].capabilities, label
    assert REG["Snapchat"].default_on["ephemerality"] is True
    assert REG["WhatsApp"].default_on["ephemerality"] is False


def test_contact_discovery_default_follows_the_research_row():
    for label in ("Facebook", "Instagram", "TikTok", "Snapchat", "Twitter / X", "Omegle"):
        assert REG[label].default_on.get("contact_discovery") is True, label
    assert REG["Discord"].default_on.get("contact_discovery") is False


def test_generative_capability_needs_production_conduct():
    recs, _ = run(HEAD + "He shared child sexual abuse material with other users on Instagram.", ["Instagram"], year=2025)
    assert recs["Instagram"].available["GenerativeSynthesis"] is True
    assert recs["Instagram"].action_relevant["GenerativeSynthesis"] is False


# --- Decision 1: line-wrap repair ---------------------------------------------------

def test_record_linewrap_tier_never_below_published():
    import csv
    rank = {"named_only": 0, "inferred": 1, "stated": 2}
    with (OUT / "records.csv").open() as f:
        for row in csv.DictReader(f):
            assert rank[row["tier_linewrap"]] >= rank[row["tier"]], row["case_id"]


# --- codebook-5, exemplars, LaTeX ------------------------------------------------

def test_synthesis_needs_an_ai_instrument_and_an_actor():
    rx = CB.harms["h2_depicted_in_abuse_imagery"]
    def hit(t):
        return bool(rx["_guarded"].search(t) and not rx["_exclude"].search(t) and rx["_require"].search(t))
    assert not hit("He produced child pornography using the Snapchat app.")
    assert not hit("Officers found possession of images created by artificial intelligence.")
    assert hit("He used an AI app to create explicit images of a classmate.")
    assert hit("He admitted taking photos from Instagram to morph into nude images.")


def test_every_manifest_exemplar_is_labelled_automatically_coded():
    """AfH 2.0 is machine-coded: no exemplar claims validation. Earlier blind-review verdicts (codebooks
    4 and 6) stay only as historical_review, tagged with their codebook."""
    ex = json.loads((OUT / "exemplar_inventory.json").read_text())
    assert ex["exemplars"] > 0
    assert all(r["coding"] == "automatically coded" for r in ex["rows"])
    assert all("verdict" not in r for r in ex["rows"])
    assert all(r["historical_review"] is None or r["historical_review"]["codebook"] for r in ex["rows"])


# --- Hardy review: one tier drives every downstream level ------------------------------

WRAPPED_USE = (HEAD + "\n\nAccording to court documents, the defendant uploaded child sexual abuse material to\n"
               "Dropbox accounts, investigators said in the affidavit.\n")


def test_linewrap_promotion_reaches_downstream_levels():
    recs, _ = run(WRAPPED_USE, ["Dropbox"])
    r = recs["Dropbox"]
    assert r.tier == "named_only" and r.primary_tier == "stated"   # promoted only by the repair
    assert r.action_relevant["DistributionInfrastructure"]          # B follows the primary tier
    assert r.instrumental["DistributionInfrastructure"]             # C follows the primary tier
    assert r.harm_direct["h3_imagery_circulated"]                   # documented harm follows it too


def test_committed_levels_never_rest_on_named_only_primary_tier():
    import csv
    with (OUT / "records.csv").open() as f:
        for row in csv.DictReader(f):
            if row["tier_linewrap"] == "named_only":
                assert not any(row[f"{c}.B"] == "1" for c in pl.CLASSES), row["case_id"]
                assert not any(row[k] == "1" for k in row if k.endswith(".direct")), row["case_id"]


def test_manifest_use_documented_matches_primary_tier():
    man = json.loads((OUT / "manifest.json").read_text())["platforms"]
    import csv
    with (OUT / "records.csv").open() as f:
        rows = list(csv.DictReader(f))
    for p in ("Kik", "Snapchat", "Dropbox"):
        want = len({r["case_id"] for r in rows if r["platform"] == p and r["tier_linewrap"] in ("stated", "inferred")})
        assert man[p]["use_documented_cases"] == want, p


def test_h1_live_conduct_stays_in_the_sentence_and_skips_the_production_charge():
    import re
    h1 = "h1_contact_sexual_abuse"
    harm = CB.harms[h1]
    same = "He directed her on a webcam to perform sexual acts."
    assert h1 in pl.case_harm_set(same, set(), CB)
    assert pl.h1_form(same, set(), harm) == "online"
    crossed = "He used a webcam. She was later told to perform sexual acts."
    assert h1 not in pl.case_harm_set(crossed, set(), CB)
    assert harm["_live"].search(crossed) is None
    assert re.compile(r"webcam(?:\W+\w+){0,16}\W+perform", re.I).search(crossed)
    charge = ("He was charged for the purpose of producing a visual depiction "
              "of a minor engaged in sexually explicit conduct on a webcam.")
    assert harm["_live"].search(charge)
    assert h1 not in pl.case_harm_set(charge, set(), CB)
    kept = charge + " He also directed her on a webcam to perform sexual acts."
    assert h1 in pl.case_harm_set(kept, set(), CB)


def test_h5_restitution_is_not_a_commercial_sex_mark():
    h5 = "h5_commercial_sexual_exploitation"
    harm = CB.harms[h5]
    assert harm["_cue"].search("paid restitution to the child")
    assert not pl.harm_case_hit("He paid restitution to the child.", {"trafficking"}, harm)
    assert pl.harm_case_hit("He paid the child for sex.", {"trafficking"}, harm)
    both = "He was charged with sex trafficking and the court said he paid restitution to the child."
    assert pl.harm_case_hit(both, {"trafficking"}, harm)
    assert not pl.harm_case_hit("He paid the child for sex.", set(), harm)


def test_h1_form_is_in_person_online_or_both():
    harm = CB.harms["h1_contact_sexual_abuse"]
    assert pl.h1_form("The abuse was hands-on.", set(), harm) == "in_person"
    assert pl.h1_form("No conduct described.", {"hands_on"}, harm) == "in_person"
    assert pl.h1_form("He sent obscene material to a minor.", set(), harm) == "online"
    both = "This was in-person abuse. He sent obscene photos to the child."
    assert pl.h1_form(both, set(), harm) == "both"
    assert pl.h1_form("He possessed files.", {"possession"}, harm) is None


def test_strict_sting_with_a_remaining_harm_stays_in_the_uncovered_base():
    h3 = {"h3_imagery_circulated"}
    assert pl.outside_uncovered_base(set(), ai_no_identifiable_child=False, attempted_contact=False, strict_sting=True)
    assert not pl.outside_uncovered_base(h3, ai_no_identifiable_child=False, attempted_contact=False, strict_sting=True)
    assert pl.outside_uncovered_base(h3, ai_no_identifiable_child=True, attempted_contact=False, strict_sting=False)


def test_visualization_named_platform_list_matches_registry():
    """The map's "named platforms" tile excludes exactly the registry's non-specific labels that occur in the evidence."""
    import re
    html = (ROOT / "visualization" / "visualization.html").read_text()
    js = set(re.findall(r'"([^"]+)"', re.search(r"NON_NAMED_LABELS = new Set\(\[(.*?)\]\)", html).group(1)))
    ev = json.loads((ROOT / "ontology/platform_affordance_evidence/platform_affordance_evidence.json").read_text())
    labels = {r["platform"] for r in ev["records"]}
    non_named = {l for l in labels if pl.platform_info(l, REG).status != "specific"}
    assert js == non_named


# --- a harm the case gates removed is never counted as direct ---------------------------

def test_harm_cleared_by_the_undercover_gate_is_not_direct():
    text = (HEAD + "He used Snapchat and sent sexually explicit images to a minor, "
            "an undercover agent posing as a 14-year-old girl. He also distributed child sexual abuse "
            "material to other users on Snapchat.")
    case = {"id": "synthetic_2024_002", "source": "SYNTH", "pub_year": 2024, "text": text,
            "platforms": ["Snapchat"], "topics": ["online_only"],
            "investigation_types": ["undercover"], "age_roles": ["decoy"]}
    recs, _ = pl.classify_case(case, "fp", REG, CB)
    r = next(x for x in recs if x.platform == "Snapchat")
    assert pl.harm_direct_hit([text], CB.harms["h1_contact_sexual_abuse"])   # the cue is there
    assert any(r.harm_case.values())                           # the case keeps another harm
    assert not r.harm_case["h1_contact_sexual_abuse"]          # the undercover gate removed it for the case
    assert not r.harm_direct["h1_contact_sexual_abuse"]        # so it is not direct either
    assert all(r.harm_case[h] for h, d in r.harm_direct.items() if d)


def test_every_level_closes_at_registry_end():
    """A_any, B, I and C all close at `ended` (publication year stands in for conduct year)."""
    r = run(HEAD + OMEGLE_USE, ["Omegle"], year=2024)[0]["Omegle"]
    for c in ("Anonymity", "ContactDiscovery", "UnmonitoredCommunication"):
        assert not (r.available[c] or r.default_on_open[c] or r.action_relevant[c] or r.inferred[c] or r.instrumental[c]), c


def test_shipped_records_have_no_level_after_registry_end():
    import csv
    with (OUT / "records.csv").open() as f:
        rows = list(csv.DictReader(f))
    late = []
    for r in rows:
        info = pl.platform_info(r["platform"], REG)
        for c in pl.CLASSES:
            ended = (info.cap_meta.get(CB.classes[c]["capability"]) or {}).get("ended")
            if ended is not None and int(r["pub_year"]) > ended and any(r[f"{c}.{lv}"] == "1" for lv in ("A_any", "A", "B", "I", "C")):
                late.append((r["case_id"], r["platform"], c))
    assert late == [], late[:5]
