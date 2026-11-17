"""AfH 2.0 Q1 eligibility, capability levels and outputs. Synthetic text only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "afh_q1"))

from afhq1 import citations, pipeline as pl  # noqa: E402
from afhq1 import snapshot  # noqa: E402

REG = pl.platform_registry()
CB = pl.Codebook.load()
OUT = ROOT / "research" / "afh_q1" / "outputs"


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

needs_snapshot = pytest.mark.skipif(not snapshot.SNAPSHOT.is_file(), reason="pinned snapshot not exported")


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
    if have != want:
        pytest.skip("local snapshot is a different corpus than the committed outputs")
    import subprocess
    res = subprocess.run([sys.executable, str(ROOT / "research/afh_q1/run_all.py"), "--verify"], capture_output=True, text=True)
    assert res.stdout.strip() == "identical", res.stdout + res.stderr


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
    strings |= set((OUT / "TABLES.md").read_text().split("|"))
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
    recs, _ = run(HEAD + "He contacted the 14-year-old girl on Kik and asked her for nude photos.", ["Kik"])
    r = recs["Kik"]
    for c in pl.CLASSES:
        assert r.instrumental[c] <= r.inferred[c] <= r.action_relevant[c] <= r.available[c], c


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
    cfg = yaml.safe_load((ROOT / "research/afh_q1/config/platforms.yaml").read_text())
    assert cfg["version"] == "platforms-2"
    for label, row in cfg["platforms"].items():
        for key, cap in (row.get("capabilities") or {}).items():
            assert isinstance(cap, dict) and cap["since"] and cap["confidence"], (label, key)
            assert row.get("basis"), label


def test_live_voice_and_expiring_links_are_not_ephemerality():
    for label in ("Roblox", "Xbox Live", "Dropbox", "Omegle"):
        assert "ephemerality" not in REG[label].capabilities, label
    assert REG["Snapchat"].default_on["ephemerality"] is True
    assert REG["WhatsApp"].default_on["ephemerality"] is False


def test_contact_discovery_default_only_for_stranger_meeting_platforms():
    assert REG["Omegle"].default_on.get("contact_discovery") is True
    assert REG["Facebook"].default_on.get("contact_discovery", False) is False


def test_generative_capability_needs_production_conduct():
    recs, _ = run(HEAD + "He shared child sexual abuse material with other users on Instagram.", ["Instagram"], year=2025)
    assert recs["Instagram"].available["GenerativeSynthesis"] is True
    assert recs["Instagram"].action_relevant["GenerativeSynthesis"] is False


# --- Decision 1: line-wrap repair ---------------------------------------------------

def test_additive_linewrap_never_demotes_in_committed_outputs():
    t = json.loads((OUT / "tier_variants.json").read_text())
    moves = t["variants"]["Bplus_unwrap_additive"]["record_moves_from_A"]
    rank = {"dropped": -1, "named_only": 0, "inferred": 1, "stated": 2}
    assert moves and all(rank[m.split("->")[1]] > rank[m.split("->")[0]] for m in moves), moves


def test_published_denominator_is_the_original_rule():
    inv = json.loads((OUT / "inventory.json").read_text())
    t = json.loads((OUT / "tier_variants.json").read_text())["variants"]
    s = inv["tiers"]["strict"]
    assert s["cases_stated"] + s["cases_inferred"] == t["A_original"]["use_documented_cases"]
    alt = inv["tiers_linewrap_alternative"]["strict"]
    assert alt["cases_stated"] + alt["cases_inferred"] == t["Bplus_unwrap_additive"]["use_documented_cases"]


def test_record_linewrap_tier_never_below_published():
    import csv
    rank = {"named_only": 0, "inferred": 1, "stated": 2}
    with (OUT / "records.csv").open() as f:
        for row in csv.DictReader(f):
            assert rank[row["tier_linewrap"]] >= rank[row["tier"]], row["case_id"]


# --- codebook-5, exemplars, LaTeX ------------------------------------------------

def test_synthesis_needs_an_ai_instrument_and_an_actor():
    rx = CB.harms["h6_likeness_synthesized"]
    def hit(t):
        return bool(rx["_cue"].search(t) and not rx["_exclude"].search(t) and rx["_require"].search(t))
    assert not hit("He produced child pornography using the Snapchat app.")
    assert not hit("Officers found possession of images created by artificial intelligence.")
    assert hit("He used an AI app to create explicit images of a classmate.")
    assert hit("He admitted taking photos from Instagram to morph into nude images.")


def test_every_manifest_exemplar_has_a_blind_review():
    ex = json.loads((OUT / "exemplar_inventory.json").read_text())
    assert ex["exemplars"] > 0
    assert all(r["verdict"] != "unreviewed" for r in ex["rows"])


def test_latex_tables_compile():
    import shutil
    import subprocess
    import tempfile
    tex = shutil.which("pdflatex") or ("/Library/TeX/texbin/pdflatex" if Path("/Library/TeX/texbin/pdflatex").exists() else None)
    if not tex:
        pytest.skip("pdflatex not installed")
    tables = sorted((OUT / "latex").glob("*.tex"))
    assert tables
    with tempfile.TemporaryDirectory() as d:
        doc = Path(d) / "check.tex"
        doc.write_text("\\documentclass{article}\\usepackage{booktabs}\\usepackage[margin=1in]{geometry}\\begin{document}\n"
                       + "\n".join(f"\\input{{{t}}}\\par" for t in tables) + "\n\\end{document}\n")
        res = subprocess.run([tex, "-interaction=nonstopmode", "-halt-on-error", "check.tex"], cwd=d, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout[-800:]
