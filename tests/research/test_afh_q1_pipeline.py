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
