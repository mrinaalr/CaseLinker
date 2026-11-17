"""Duplicate audit: URL classes, PDF verdicts, and the page-drop guard."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from caselinker_mcp.clean_and_validate import (
    _anchor_pages,
    find_ingested_duplicates,
    headline_needle,
    judge_locations,
    url_kind,
    verify_duplicate_pdf_pages,
)
from caselinker_mcp.collector_tools import drop_collected_pdf_pages


def test_url_kind_matches_layla_fallbacks_and_listings():
    assert url_kind("https://report.cybertip.org/") == "fallback"
    assert url_kind("https://report.cybertip.org") == "fallback"
    assert url_kind("https://gbi.georgia.gov/submit-tips-online") == "fallback"
    assert url_kind("https://www.justice.gov/psc") == "fallback"
    assert url_kind("http://www.missingkids.com/home") == "fallback"
    assert url_kind("https://www.missingkids.org/HOME") == "fallback"
    assert url_kind("https://www.ag.idaho.gov/newsroom/category/icac/?showall=true") == "listing"
    assert url_kind("https://www.missingkids.org/gethelpnow/cybertipline/cybertiplinedata") == "listing"
    assert url_kind("https://www.wrex.com/news/crime/rockford-man-arrested") == "article"


def test_same_pdf_twice_keeps_earliest_page():
    verdict = judge_locations(
        url_class="article",
        n_cases=2,
        min_row_jaccard=0.98,
        max_row_jaccard=0.98,
        copies=[
            {"pdf": "2022 NCMEC.pdf", "page": 364, "page_jaccard": 1.0},
            {"pdf": "2022 NCMEC.pdf", "page": 365, "page_jaccard": 0.97},
        ],
    )
    assert verdict["verdict"] == "same_pdf_twice"
    assert verdict["cut_from_pdf"] is True
    assert verdict["keep_page"]["page"] == 364
    assert verdict["drop_pages"] == [
        {"pdf": "2022 NCMEC.pdf", "page": 365, "page_jaccard": 0.97}
    ]


def test_cross_source_suggests_cutting_the_ncmec_copy():
    verdict = judge_locations(
        url_class="article",
        n_cases=2,
        min_row_jaccard=0.8,
        max_row_jaccard=0.8,
        copies=[
            {"pdf": "2024 NCMEC.pdf", "page": 12, "page_jaccard": 1.0},
            {"pdf": "SCAG_ICAC_All.pdf", "page": 40, "page_jaccard": 0.9},
        ],
    )
    assert verdict["verdict"] == "cross_pdf"
    assert verdict["cross_pdf_kind"] == "ncmec_vs_other_source"
    assert verdict["drop_pages"][0]["pdf"] == "2024 NCMEC.pdf"
    assert verdict["keep_page"]["pdf"] == "SCAG_ICAC_All.pdf"


def test_shared_url_with_different_stories_is_not_a_cut():
    verdict = judge_locations(
        url_class="article",
        n_cases=2,
        min_row_jaccard=0.1,
        max_row_jaccard=0.1,
        copies=[{"pdf": "2024 NCMEC.pdf", "page": 80, "page_jaccard": 1.0}],
    )
    assert verdict["verdict"] == "shared_url_different_stories"
    assert verdict["cut_from_pdf"] is False


def test_one_pdf_hit_is_not_a_cut_even_when_rows_match():
    verdict = judge_locations(
        url_class="article",
        n_cases=2,
        min_row_jaccard=0.95,
        max_row_jaccard=0.95,
        copies=[{"pdf": "2024 NCMEC.pdf", "page": 10, "page_jaccard": 1.0}],
    )
    assert verdict["verdict"] == "pdf_once_rows_match"
    assert verdict["cut_from_pdf"] is False


def test_url_slug_drops_template_headline_pages():
    anchors = _anchor_pages(
        {"2022 NCMEC.pdf": [15, 56, 206]},
        {"2022 NCMEC.pdf": [15], "SCAG_ICAC_All.pdf": [437]},
        {},
    )
    assert anchors == {"2022 NCMEC.pdf": [15], "SCAG_ICAC_All.pdf": [437]}


def test_headline_needle_skips_url_lines():
    text = "https://example.com/story\nRockford man arrested on several child pornography charges\n"
    needle = headline_needle(text)
    assert "rockford" in needle
    assert "example" not in needle


def _write_two_page_pdf(path: Path, page_one: str, page_two: str) -> None:
    pdf = canvas.Canvas(str(path))
    for text in (page_one, page_two):
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()


def test_verify_finds_back_to_back_copy_in_a_temp_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    title = "Rockford man arrested on several child pornography charges after a long case"
    pdf_path = tmp_path / "2022 NCMEC.pdf"
    _write_two_page_pdf(pdf_path, title, title)
    db_path = tmp_path / "caselinker.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE cases (
            id TEXT PRIMARY KEY,
            source TEXT,
            source_url TEXT,
            raw_data TEXT
        )
        """
    )
    url = "https://www.wrex.com/news/crime/rockford-man-arrested-on-several-child-pornography-charges"
    for case_id in ("ncmec_2022_310", "ncmec_2022_311"):
        conn.execute(
            "INSERT INTO cases (id, source, source_url, raw_data) VALUES (?, ?, ?, ?)",
            (
                case_id,
                "NCMEC",
                url,
                '{"source_file": "2022 NCMEC.pdf", "case_text": "%s"}' % title,
            ),
        )
    conn.commit()
    conn.close()

    listed = find_ingested_duplicates(db_path=str(db_path), source="NCMEC", limit=0)
    assert listed["group_count"] == 1
    assert listed["mutated"] is False

    verified = verify_duplicate_pdf_pages(
        db_path=str(db_path),
        repo_root=str(tmp_path),
        source="NCMEC",
        max_groups=0,
    )
    assert verified["mutated"] is False
    group = verified["groups"][0]
    assert group["verdict"] == "same_pdf_twice"
    assert group["keep_page"]["page"] == 1
    assert group["drop_pages"][0]["page"] == 2


def test_drop_pages_preview_does_not_rewrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pdf_path = tmp_path / "sample.pdf"
    _write_two_page_pdf(pdf_path, "alpha article about a sentencing", "beta article about a sentencing")
    before = pdf_path.read_bytes()
    monkeypatch.setattr(
        "caselinker_mcp.collector_tools._REPO",
        tmp_path,
    )
    preview = drop_collected_pdf_pages(str(pdf_path), "2", dry_run=True, confirm_write=False)
    assert preview["mutated"] is False
    assert preview["drop_pages"] == [2]
    assert pdf_path.read_bytes() == before

    refused = drop_collected_pdf_pages(str(pdf_path), "2", dry_run=True, confirm_write=True)
    assert refused["mutated"] is False
    assert pdf_path.read_bytes() == before
