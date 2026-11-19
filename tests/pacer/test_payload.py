"""The /lifecycle payload: what the page can show, and what it never carries."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from state_machines.evidence import vocab as V
from tests.pacer import fixtures as F

REPO = Path(__file__).resolve().parents[2]


def test_action_groups_partition_the_offender_actions():
    grouped = [c for codes in V.ACTION_GROUPS.values() for c in codes]
    assert len(grouped) == len(set(grouped)), "an action sits in two groups"
    assert set(grouped) == set(V.ACTION_FAMILIES["offender"])


def test_page_columns_match_the_codebook_groups():
    js = (REPO / "visualization" / "assets" / "lifecycle.js").read_text(encoding="utf-8")
    block = re.search(r"const GROUPS = \[(.*?)\];", js, re.S).group(1)
    assert re.findall(r'\["(\w+)",', block) == list(V.ACTION_GROUPS)


def _release(tmp_path, adjudicated: bool):
    pytest.importorskip("case_uco")
    from state_machines.graphs.release import build
    from tests.pacer.test_release import _adjudicated, _release as stage
    bundle = F.build()[0]
    root = stage(tmp_path, _adjudicated(bundle) if adjudicated else bundle)
    build("test-v1", data_root=root, text_root=tmp_path / "text", allow_unreviewed=not adjudicated)
    return root


def test_payload_carries_codes_and_provenance_but_no_text(tmp_path):
    from state_machines.trajectories.payload import build_payload
    root = _release(tmp_path, adjudicated=True)
    p = build_payload(root / "test-v1")
    assert p["release"]["adjudicated"] is True
    (case,) = p["cases"]
    ev = case["events"]["e01"]
    assert ev["group"] == "access" and ev["standing"] == "ADMITTED"
    assert ev["provenance"] and all(set(x) == {"doc_type", "page", "standing", "verification"} for x in ev["provenance"])
    assert all(re.fullmatch(r"P\d+", x["ref"]) for x in case["participants"])
    _, quotes = F.build()
    text = json.dumps(p)
    assert "description" not in text
    assert not any(q in text for q in quotes.values())
    track = case["tracks"][0]
    assert ["e05", "e06"] not in track["views"]["DIRECT"]["date_order"]   # undated e05: no date order
    assert track["views"]["INFERRED"]["chains"]


def test_only_adjudicated_releases_are_served_by_default(tmp_path, monkeypatch):
    from state_machines.trajectories import payload
    root = _release(tmp_path, adjudicated=False)
    monkeypatch.delenv("CASELINKER_PACER_RELEASE", raising=False)
    monkeypatch.setattr(payload, "DATA", root)
    assert payload.release_dir() is None
    assert payload.build_payload() == {"release": None, "cases": []}
    monkeypatch.setenv("CASELINKER_PACER_RELEASE", str(root / "test-v1"))   # an explicit preview
    assert payload.build_payload()["release"]["adjudicated"] is False


def test_page_and_analysis_need_only_committed_release_files(tmp_path):
    """A clean checkout has no cases/ (bundles stay local): the payload and the AfH analysis
    must come from derived/ and lifecycle.json alone, and agree with the bundles."""
    import shutil
    from state_machines.trajectories import afh
    from state_machines.trajectories.derive import derive
    from state_machines.trajectories.payload import build_payload
    root = _release(tmp_path, adjudicated=True) / "test-v1"
    bundle = json.loads(next((root / "cases").glob("*.json")).read_text(encoding="utf-8"))
    expected = {thr: (sorted(afh.case_affordances(derive(bundle, thr))), sorted(afh.case_harms(bundle, thr)))
                for thr in ("DIRECT", "INFERRED")}
    shutil.rmtree(root / "cases")
    assert build_payload(root)["cases"][0]["case_id"] == bundle["case_id"]
    for thr, (affs, harms) in expected.items():
        (case,) = afh.release_analysis(root, thr)["cases"]
        assert (case["aff"], case["h0"]) == (affs, harms)
        assert harms, "the fixture records minor-directed harms"
    with pytest.raises(LookupError):                       # an id the release does not hold is an error, never an empty success
        afh.release_analysis(root, "INFERRED", case_id="some_other_id")


def test_machine_coded_releases_are_served_and_labelled(tmp_path, monkeypatch):
    pytest.importorskip("case_uco")
    from state_machines.graphs.release import build
    from state_machines.trajectories import payload
    from tests.pacer.test_release import _release as stage
    bundle = F.build()[0]
    for e in bundle["events"]:
        e["review"] = {"status": "agreed", "coders": ["coder_A", "coder_B"], "adjudicator": None}
    root = stage(tmp_path, bundle)
    m = build("test-v1", data_root=root, text_root=tmp_path / "text", mode="machine")
    assert m["review_mode"] == "machine" and m["adjudicated"] is False
    monkeypatch.delenv("CASELINKER_PACER_RELEASE", raising=False)
    monkeypatch.setattr(payload, "DATA", root)
    assert payload.release_dir() == root / "test-v1"
    assert payload.build_payload()["release"]["review_mode"] == "machine"
