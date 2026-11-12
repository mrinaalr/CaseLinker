"""Content-locked case ids: the text keeps the id, the URL does not."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROC = REPO / "src" / "Processing Layer"
STORAGE = REPO / "src" / "Storage Layer"
for entry in (PROC, STORAGE):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from batching import case_batching  # noqa: E402
from case_fingerprint import (  # noqa: E402
    NORMALIZATION_VERSION,
    FingerprintIndex,
    FingerprintVersionMismatch,
    assign_content_locked_ids,
    fingerprint_case_text,
    normalize_case_text,
)
from case_storage_utils import CaseIdCollision  # noqa: E402
from storage import CaseStorage  # noqa: E402


def _article(name: str, year: str = "2024") -> str:
    body = (
        f"Publication date: {year}-03-01\n"
        f"{name} man pleaded guilty to distributing child sexual abuse material. "
        "The charge was filed after a cybertip. Investigators recovered devices at his home."
    )
    return body


def _index_from(pairs, source_file="listing.pdf"):
    index = FingerprintIndex()
    for case_id, text in pairs:
        index.remember(case_id, text, source_file=source_file)
    return index


def test_reordered_pdf_keeps_every_id():
    alpha, beta, gamma = _article("Alpha"), _article("Beta"), _article("Gamma")
    index = _index_from([
        ("ice_2024_001", alpha),
        ("ice_2024_002", beta),
        ("ice_2024_003", gamma),
    ])
    incoming = [
        {"case_text": gamma, "case_id": "ice_2024_001", "year": "2024", "source_file": "listing.pdf"},
        {"case_text": alpha, "case_id": "ice_2024_001", "year": "2024", "source_file": "listing.pdf"},
        {"case_text": beta, "case_id": "ice_2024_001", "year": "2024", "source_file": "listing.pdf"},
    ]
    kept, duplicates = assign_content_locked_ids(incoming, index)
    assert [row["case_id"] for row in kept] == ["ice_2024_003", "ice_2024_001", "ice_2024_002"]
    assert duplicates == []


def test_an_inserted_article_takes_the_next_free_ordinal():
    alpha, beta = _article("Alpha"), _article("Beta")
    index = _index_from([
        ("ice_2024_001", alpha),
        ("ice_2024_003", beta),
    ])
    incoming = [
        {"case_text": alpha, "case_id": "ice_2024_001", "year": "2024", "source_file": "listing.pdf"},
        {"case_text": _article("Inserted"), "case_id": "ice_2024_002", "year": "2024", "source_file": "listing.pdf"},
        {"case_text": beta, "case_id": "ice_2024_003", "year": "2024", "source_file": "listing.pdf"},
    ]
    kept, duplicates = assign_content_locked_ids(incoming, index)
    assert [(row["case_text"][:5], row["case_id"]) for row in kept] == [
        ("Publi", "ice_2024_001"),
        ("Publi", "ice_2024_002"),
        ("Publi", "ice_2024_003"),
    ]
    assert kept[1]["case_id"] == "ice_2024_002"
    assert duplicates == []


def test_whitespace_and_line_wraps_keep_the_id():
    original = "A Celina man was sentenced to four years in prison."
    wrapped = "A Celina man was\nsentenced   to four\nyears in prison."
    curly = "A Celina man was sentenced to four years in prison.\u201d"
    straight = 'A Celina man was sentenced to four years in prison."'
    assert normalize_case_text(original) == normalize_case_text(wrapped)
    assert fingerprint_case_text(curly) == fingerprint_case_text(straight)
    index = _index_from([("ice_2024_007", original)])
    kept, _duplicates = assign_content_locked_ids(
        [{"case_text": wrapped, "case_id": "ice_2024_001", "year": "2024", "source_file": "listing.pdf"}],
        index,
    )
    assert kept[0]["case_id"] == "ice_2024_007"


def test_a_listing_header_the_extractor_sometimes_drops_keeps_the_id():
    body = "June 16, 2021 Boise police announced an arrest after a cybertip and a search of a home."
    with_header = "Newsroom\nCATEGORY: ICAC\n" + body
    assert fingerprint_case_text(with_header) == fingerprint_case_text(body)


def test_a_real_text_change_gets_a_new_id():
    original = _article("Alpha")
    changed = original + " He was also ordered to register for life."
    index = _index_from([("ice_2024_001", original), ("ice_2024_002", _article("Beta"))])
    kept, _duplicates = assign_content_locked_ids(
        [{"case_text": changed, "case_id": "ice_2024_001", "year": "2024", "source_file": "listing.pdf"}],
        index,
    )
    assert kept[0]["case_id"] == "ice_2024_003"
    assert fingerprint_case_text(changed) != fingerprint_case_text(original)


def _gbi_block(name: str, when: str) -> str:
    sentence = f"{name} was charged after a cybertip and a search of his home in Atlanta."
    return f"{when}\n" + " ".join([sentence] * 6)


def test_resplitting_a_listing_page_keeps_each_case_id():
    alpha = _gbi_block("Alpha", "March 11, 2020")
    beta = _gbi_block("Beta", "June 2, 2021")
    forward = alpha + "\n# # # # #\n" + beta
    backward = beta + "\n# # # # #\n" + alpha
    first = case_batching(forward, org_name="gbi", source="GBI", source_file="gbi.pdf")
    assert len(first) == 2
    index = FingerprintIndex()
    for row in first:
        index.remember(row["case_id"], row["case_text"], source_file="gbi.pdf")
    second = case_batching(
        backward, org_name="gbi", source="GBI", source_file="gbi.pdf", fingerprint_index=index
    )
    by_text = {fingerprint_case_text(row["case_text"]): row["case_id"] for row in first}
    assert [by_text[fingerprint_case_text(row["case_text"])] for row in second] == [
        row["case_id"] for row in second
    ]
    assert [row["case_id"] for row in second] == [first[1]["case_id"], first[0]["case_id"]]


def test_idaho_and_azicac_resplits_keep_ids():
    idaho_one = (
        "Newsroom\nCATEGORY: ICAC\nMarch 11, 2020\n"
        + " ".join(["Boise detectives arrested a man after a cybertip about uploaded files."] * 12)
        + "\n« NEXT"
    )
    idaho_two = (
        "Newsroom\nCATEGORY: ICAC\nJune 2, 2021\n"
        + " ".join(["Idaho Falls detectives arrested a different man after another cybertip."] * 12)
        + "\n« NEXT"
    )
    az_one = (
        "In January 2012, Mesa police arrested a man for possession of child sexual abuse material. "
        + ("Devices were seized from the house. " * 12)
    )
    az_two = (
        "In March 2013, Tucson police arrested a woman for distribution of child sexual abuse material. "
        + ("A search warrant was served at the apartment. " * 12)
    )
    samples = [
        ("IDAHO ICAC", "idaho_icac", "idaho.pdf", idaho_one, idaho_two),
        ("AZICAC", "azicac", "azicac.pdf", az_one, az_two),
    ]
    for source, org, filename, left, right in samples:
        forward = case_batching(left + "\n" + right, org_name=org, source=source, source_file=filename)
        assert len(forward) >= 2, source
        index = FingerprintIndex()
        for row in forward:
            index.remember(row["case_id"], row["case_text"], source_file=filename)
        backward = case_batching(
            right + "\n" + left,
            org_name=org,
            source=source,
            source_file=filename,
            fingerprint_index=index,
        )
        assert [row["case_id"] for row in backward] == [forward[-1]["case_id"], forward[0]["case_id"]]


def test_the_same_fingerprint_in_one_ingest_is_one_article():
    text = _article("Alpha")
    index = FingerprintIndex()
    kept, duplicates = assign_content_locked_ids(
        [
            {"case_text": text, "case_id": "ice_2024_001", "year": "2024", "source_file": "a.pdf"},
            {"case_text": "  " + text.replace(" ", "\n"), "case_id": "ice_2024_002", "year": "2024", "source_file": "a.pdf"},
        ],
        index,
    )
    assert [row["case_id"] for row in kept] == ["ice_2024_001"]
    assert duplicates[0]["duplicate_of_case_id"] == "ice_2024_001"
    assert "ice_2024_002" not in index.used


def test_the_same_fingerprint_from_another_file_is_a_duplicate_and_not_a_collision(tmp_path):
    text = _article("Alpha")
    storage = CaseStorage(str(tmp_path / "cases.db"))
    stored = {
        "id": "ice_2024_001",
        "source": "ICE",
        "source_url": "https://example.test/alpha",
        "date_range": {"start": "2024-03-01", "end": None},
        "raw_data": {"source_file": "first.pdf", "case_text": text, "case_id": "ice_2024_001"},
        "case_text": text,
    }
    assert storage.store_case(stored) is True
    index = storage.load_fingerprint_index()
    kept, duplicates = assign_content_locked_ids(
        [{"case_text": text, "case_id": "ice_2024_001", "year": "2024", "source_file": "second.pdf"}],
        index,
    )
    assert kept == []
    assert duplicates[0]["duplicate_of_case_id"] == "ice_2024_001"
    with pytest.raises(CaseIdCollision):
        storage.store_case({
            **stored,
            "raw_data": {"source_file": "second.pdf", "case_text": "A different article entirely.", "case_id": "ice_2024_001"},
            "case_text": "A different article entirely.",
        })


def test_a_normalization_version_change_does_not_mint_a_new_id():
    index = FingerprintIndex()
    index.remember("ice_2024_001", _article("Alpha"), source_file="a.pdf")
    index.versions.add("fp-0")
    with pytest.raises(FingerprintVersionMismatch):
        assign_content_locked_ids(
            [{"case_text": _article("Brand new"), "case_id": "ice_2024_001", "year": "2024", "source_file": "a.pdf"}],
            index,
        )
    assert index.used == {"ice_2024_001"}
    assert NORMALIZATION_VERSION


def test_sqlite_stores_the_fingerprint_without_changing_the_case_id(tmp_path):
    text = _article("Alpha")
    storage = CaseStorage(str(tmp_path / "cases.db"))
    storage.store_case({
        "id": "ice_2024_004",
        "source": "ICE",
        "source_url": "https://example.test/alpha",
        "date_range": {"start": "2024-03-01", "end": None},
        "raw_data": {"source_file": "a.pdf", "case_text": text, "case_id": "ice_2024_004"},
        "case_text": text,
    })
    rows = storage.fingerprint_rows()
    assert rows == [{
        "case_id": "ice_2024_004",
        "fingerprint": fingerprint_case_text(text),
        "normalization_version": NORMALIZATION_VERSION,
    }]
    assert storage.get_case("ice_2024_004")["id"] == "ice_2024_004"


def test_resolve_accepts_case_text_so_process_cases_can_pass_it():
    """Ingest calls resolve(..., text=case_text). That kwarg must exist on this branch."""
    import processing

    processing.assertions_module.resolve([], batch_date=None, text="a 40-year-old man")


def test_a_four_digit_ordinal_keeps_its_prefix():
    stored = [(f"ncmec_2024_{n:03d}", _article(f"Stored{n}")) for n in range(1, 1000)]
    index = _index_from(stored)
    incoming = [
        {"case_text": _article("Thousandth"), "case_id": "ncmec_2024_1000", "year": "2024", "source_file": "listing.pdf"},
        {"case_text": _article("Next"), "case_id": "ncmec_2024_1001", "year": "2024", "source_file": "listing.pdf"},
    ]
    kept, _duplicates = assign_content_locked_ids(incoming, index)
    assert [row["case_id"] for row in kept] == ["ncmec_2024_1000", "ncmec_2024_1001"]
