"""The /visualization AfH 2.0 release file (numbers/platform_map.py) counts what numbers.md counts."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAE = ROOT / "ontology" / "platform_affordance_evidence"
PINNED = PAE / "platform_affordance_evidence_afh-2.0.json"
BUILD = PAE / "afh_manifest" / "numbers" / "build"

# Top 12 by stated-tier cases in the AfH 2.0 release, analysis DB (exclusions v1): (platform, stated cases, total cases).
# Before the 23 exclusions: Kik 424 / 550, Facebook 129 / 295; the rest are unchanged.
TOP12 = [
    ("Kik", 423, 549), ("Snapchat", 318, 411), ("Facebook", 128, 294), ("Dropbox", 86, 147),
    ("Discord", 79, 128), ("Instagram", 77, 149), ("Telegram", 48, 83), ("WhatsApp", 47, 58),
    ("Twitter / X", 39, 105), ("Facebook Messenger", 35, 45), ("BitTorrent", 28, 36), ("Google Drive", 27, 53),
]


def _counts(records):
    tiers = defaultdict(lambda: defaultdict(set))
    for r in records:
        tiers[r["platform"]][r["stated_vs_inferred"]].add(r["case_id"])
    return {p: (len(t["stated"]), len(set().union(*t.values()))) for p, t in tiers.items()}


def test_release_file_matches_the_pinned_top12_and_the_build():
    data = json.loads(PINNED.read_text())
    got = _counts(data["records"])
    for platform, stated, total in TOP12:
        assert got[platform] == (stated, total), platform
    built = _counts({"platform": r["platform"], "stated_vs_inferred": r["tier_linewrap"], "case_id": r["case_id"]}
                    for r in csv.DictReader(open(BUILD / "records.csv", newline="")))
    assert got == built
    ranked = sorted(got, key=lambda p: (-got[p][0], -got[p][1], p))
    specific = set(data["_meta"]["label_status"]["specific"])
    assert [p for p in ranked if p in specific][:12] == [p for p, _, _ in TOP12]


def test_release_file_has_52_named_platforms_and_no_text():
    data = json.loads(PINNED.read_text())
    meta = data["_meta"]
    assert meta["named_platforms"] == 52 == len(meta["label_status"]["specific"])
    assert meta["release"] == "afh2.0" and meta["afh_inputs"]["afh_2_0_snapshot"] is True
    assert meta["afh_inputs"]["db_sha256"].startswith("867e2a57")
    assert meta["ids_only"] is True
    assert all(set(r) == {"case_id", "platform", "platform_type", "stated_vs_inferred"} for r in data["records"])


def test_page_footer_and_label_sets_follow_the_registry():
    """The page's non-named labels are exactly the registry's non-specific statuses, so its footer reads 52 named."""
    html = (ROOT / "visualization" / "visualization.html").read_text()
    labels = json.loads(PINNED.read_text())["_meta"]["label_status"]
    non_named = {x for k, v in labels.items() if k != "specific" for x in v}
    line = next(l for l in html.splitlines() if "const NON_NAMED_LABELS = new Set(" in l)
    assert set(json.loads("[" + line.split("new Set([", 1)[1].split("])", 1)[0] + "]")) == non_named
    assert "alias / technology labels" in html and 'RELEASE_FILES' in html
