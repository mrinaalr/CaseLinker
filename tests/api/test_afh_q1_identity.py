"""Historical case ids are never joined to current cases by id alone."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "platform_affordance_evidence" / "afh_manifest"))

from afhq1 import citations, identity  # noqa: E402

RELEASE_A = "Synthetic Town man sentenced for distributing material through Kik messenger to an undercover officer in 2021."
RELEASE_B = "Second synthetic release about a defendant who used Snapchat to contact a minor and was arrested at a park."
RELEASE_C = "Third synthetic release about Dropbox links shared in a chat group by a defendant from another county."


def _quote(text: str) -> str:
    return text[10:80]


def test_renumbered_id_maps_by_content_not_by_id():
    # June: ncmec_2023_001 was release A. Now release A sits at ncmec_2023_002 and 001 holds B.
    texts = {"ncmec_2023_001": RELEASE_B, "ncmec_2023_002": RELEASE_A}
    old = [{"case_id": "ncmec_2023_001", "evidence_quote": _quote(RELEASE_A)}]
    (m,) = identity.build_crosswalk(old, ["ncmec_2023_001"], texts)
    assert m.cls == "exact"
    assert m.current_id == "ncmec_2023_002"
    assert m.reassigned is True
    assert m.old_id_exists_now is True


def test_same_id_same_text_is_exact_and_not_reassigned():
    texts = {"x_2022_001": RELEASE_A, "x_2022_002": RELEASE_B}
    old = [{"case_id": "x_2022_001", "evidence_quote": _quote(RELEASE_A)}]
    (m,) = identity.build_crosswalk(old, ["x_2022_001"], texts)
    assert (m.cls, m.current_id, m.reassigned) == ("exact", "x_2022_001", False)


def test_id_without_quote_is_unmatched_even_if_id_still_exists():
    texts = {"x_2022_001": RELEASE_A}
    (m,) = identity.build_crosswalk([], ["x_2022_001"], texts)
    assert m.cls == "unmatched" and m.current_id is None
    assert identity.resolve("x_2022_001", {m.old_id: m}) == (None, "unmatched")


def test_quote_found_in_two_releases_is_ambiguous():
    shared = "This case was brought as part of a synthetic nationwide initiative to protect children online."
    texts = {"x_2022_001": RELEASE_A + " " + shared, "x_2022_002": RELEASE_B + " " + shared}
    old = [{"case_id": "x_2022_001", "evidence_quote": shared}]
    (m,) = identity.build_crosswalk(old, ["x_2022_001"], texts)
    assert m.cls == "ambiguous" and m.current_id is None


def test_dissenting_quotes_downgrade_to_probable():
    texts = {"x_2022_001": RELEASE_A, "x_2022_002": RELEASE_B, "x_2022_003": RELEASE_C}
    old = [
        {"case_id": "x_2022_001", "evidence_quote": _quote(RELEASE_A)},
        {"case_id": "x_2022_001", "evidence_quote": RELEASE_A[30:95]},
        {"case_id": "x_2022_001", "evidence_quote": _quote(RELEASE_C)},
    ]
    (m,) = identity.build_crosswalk(old, ["x_2022_001"], texts)
    assert m.cls == "probable" and m.current_id == "x_2022_001"
    assert identity.resolve("x_2022_001", {m.old_id: m})[0] is None


def test_glyph_differences_still_match_as_normalized():
    texts = {"x_2022_001": "He said “I used Kik to send the files to the officer” during the interview."}
    old = [{"case_id": "x_2022_001", "evidence_quote": 'He said "I used Kik to send the files to the officer'}]
    (m,) = identity.build_crosswalk(old, ["x_2022_001"], texts)
    assert m.cls == "normalized" and m.current_id == "x_2022_001"


def test_citation_flags_reassigned_id_and_follows_fingerprint():
    fps = {"ncmec_2023_001": "fp-B", "ncmec_2023_002": "fp-A"}
    cite = citations.Citation("ncmec_2023_001", "fp-A", "manifest:Kik:0", "Kik")
    (v,) = citations.verify([cite], fps)
    assert v.status == "id_reassigned"
    assert v.current_id == "ncmec_2023_002"


def test_citation_ok_only_when_fingerprint_matches():
    fps = {"x_2022_001": "fp-A"}
    ok, gone, bare = citations.verify(
        [citations.Citation("x_2022_001", "fp-A"), citations.Citation("x_2022_009", "fp-Z"),
         citations.Citation("x_2022_001", "")], fps)
    assert ok.status == "ok"
    assert gone.status == "missing"
    assert bare.status == "no_fingerprint"
