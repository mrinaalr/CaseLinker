"""Processing gate: skip an obvious cross-source duplicate, keep same-source rows."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_PROC = Path(__file__).resolve().parents[1] / "src" / "Processing Layer"
if str(_PROC) not in sys.path:
    sys.path.insert(0, str(_PROC))

from source_url_gate import article_url_key, drop_obvious_duplicate_cases


ARTICLE = "https://www.scag.gov/about-the-office/news/lexington-county-man-arrested/"


def test_canonical_key_ignores_trailing_slash_fragment_and_whitespace():
    wrapped = (
        "https://www.scag.gov/about-the-office/news/lexington-county-man-arrested/\n"
        "#:~:text=hello"
    )
    assert article_url_key(wrapped) == article_url_key(ARTICLE)


def test_placeholder_and_listing_urls_are_not_article_keys():
    assert article_url_key("https://report.cybertip.org/") is None
    assert article_url_key("https://www.justice.gov/psc") is None
    assert article_url_key("https://www.missingkids.org/HOME") is None
    assert article_url_key("https://www.ag.idaho.gov/newsroom/category/icac/?showall=true") is None
    assert article_url_key(ARTICLE) is not None


def test_cross_source_match_is_skipped_and_names_the_existing_row():
    existing = [{"id": "scag_icac_2025_001", "source": "SCAG ICAC", "source_url": ARTICLE + "#section"}]
    incoming = [{
        "id": "ncmec_2025_010",
        "source": "NCMEC",
        "source_url": ARTICLE,
    }]
    kept, skipped = drop_obvious_duplicate_cases(incoming, existing)
    assert kept == []
    assert skipped[0]["duplicate_of_case_id"] == "scag_icac_2025_001"
    assert skipped[0]["duplicate_of_source"] == "SCAG ICAC"


def test_same_source_codefendants_both_stay():
    incoming = [
        {"id": "ncmec_2024_101", "source": "NCMEC", "source_url": ARTICLE},
        {"id": "ncmec_2024_102", "source": "NCMEC", "source_url": ARTICLE},
    ]
    kept, skipped = drop_obvious_duplicate_cases(incoming, [])
    assert [row["id"] for row in kept] == ["ncmec_2024_101", "ncmec_2024_102"]
    assert skipped == []


def test_later_other_source_in_the_same_batch_is_skipped():
    incoming = [
        {"id": "vt_ag_2024_006", "source": "VT AG", "source_url": ARTICLE},
        {"id": "ncmec_2024_1137", "source": "NCMEC", "source_url": ARTICLE},
    ]
    kept, skipped = drop_obvious_duplicate_cases(incoming, [])
    assert [row["id"] for row in kept] == ["vt_ag_2024_006"]
    assert skipped[0]["id"] == "ncmec_2024_1137"
    assert skipped[0]["duplicate_of_case_id"] == "vt_ag_2024_006"


def test_reingest_of_the_same_id_is_kept():
    existing = [{"id": "ncmec_2024_1137", "source": "NCMEC", "source_url": ARTICLE}]
    incoming = [{"id": "ncmec_2024_1137", "source": "NCMEC", "source_url": ARTICLE}]
    # An agency row also holds the URL. Refreshing the NCMEC id still updates that row.
    existing.append({"id": "vt_ag_2024_006", "source": "VT AG", "source_url": ARTICLE})
    kept, skipped = drop_obvious_duplicate_cases(incoming, existing)
    assert [row["id"] for row in kept] == ["ncmec_2024_1137"]
    assert skipped == []


def test_shared_placeholder_does_not_block_a_different_source():
    url = "https://report.cybertip.org/"
    existing = [{"id": "ncmec_2022_127", "source": "NCMEC", "source_url": url}]
    incoming = [{"id": "gbi_2024_001", "source": "GBI", "source_url": url}]
    kept, skipped = drop_obvious_duplicate_cases(incoming, existing)
    assert [row["id"] for row in kept] == ["gbi_2024_001"]
    assert skipped == []


def test_store_cases_does_not_insert_the_cross_source_row(tmp_path: Path, monkeypatch):
    from tests.test_main_provenance_paths import _load_main

    main = _load_main(monkeypatch)
    db_path = tmp_path / "gate.db"
    url = "https://ago.vermont.gov/blog/2024/01/23/colchester-resident-arrested"
    first = {
        "id": "vt_ag_2024_006",
        "source": "VT AG",
        "source_url": url,
        "raw_data": {"source_file": "VTAG_ICAC_All.pdf", "case_text": "one"},
    }
    assert main.store_cases([first], str(db_path)) == 1

    second = {
        "id": "ncmec_2024_1137",
        "source": "NCMEC",
        "source_url": url + "/",
        "raw_data": {"source_file": "2024 NCMEC.pdf", "case_text": "two"},
    }
    assert main.store_cases([second], str(db_path)) == 0

    conn = sqlite3.connect(db_path)
    ids = [row[0] for row in conn.execute("SELECT id FROM cases ORDER BY id")]
    conn.close()
    assert ids == ["vt_ag_2024_006"]
