"""Filename routing and Source:-layout batching for AFP, QPS, and Brazil PF. No network."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INGEST = ROOT / "src" / "Ingestion Layer"
PROC = ROOT / "src" / "Processing Layer"
for p in (INGEST, PROC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from batching import case_batching  # noqa: E402
from ingestion import detect_source_from_content  # noqa: E402


def test_filenames_map_to_new_sources():
    assert detect_source_from_content("", "AFP_CSEA_All.pdf") == "AFP"
    assert detect_source_from_content("", "QPS_CSEA_All.pdf") == "QPS"
    assert detect_source_from_content("", "BRAZIL_PF_CSEA_All.pdf") == "BRAZIL PF"
    assert detect_source_from_content("", "EUROPOL_CSEA_All.pdf") == "EUROPOL"
    assert detect_source_from_content("", "NCA_CSEA_All.pdf") == "NCA"


def test_merged_layout_splits_on_source_lines():
    text = """
Queensland man jailed
Publication date: 2026-08-07
Source: https://www.afp.gov.au/news-centre/media-release/queensland-man-jailed
He was sentenced for child exploitation offences.
Child exploitation material charges, Gold Coast
Publication date: 2026-07-24
Source: https://mypolice.qld.gov.au/news/2026/07/24/child-exploitation-material-charges-gold-coast/
A man was charged with child exploitation material offences.
"""
    cases = case_batching(text, org_name="afp", source="AFP", source_file="AFP_CSEA_All.pdf")
    assert len(cases) == 2
    assert cases[0]["source_url"].startswith("https://www.afp.gov.au/")
    assert cases[0]["case_id"] == "afp_2026_001"
    assert cases[1]["source_url"].startswith("https://mypolice.qld.gov.au/")
    assert cases[1]["year"] == "2026"
