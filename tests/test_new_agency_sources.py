"""Louisiana SP, Ocean County Prosecutor, Kentucky AG, Maricopa County Attorney and Sacramento SO as sources.

Filename routing, release split, state, Sources page. No network. The layout copies the
build_press_pdf output; the people and slugs are made up.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("src/Ingestion Layer", "src/Processing Layer"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

from batching import case_batching  # noqa: E402
from ingestion import detect_source_from_content  # noqa: E402
from location_grounding import SOURCE_TO_STATE  # noqa: E402

SOURCES = [
    # label, pdf name, id prefix, state, release url stem, sources.html display name
    ("LA SP", "LASP_ICAC_All.pdf", "la_sp", "LA", "https://lsp.org/community-outreach/news/example-release-{n}/",
     "Louisiana State Police"),
    ("OCPO", "OCPO_ICAC_All.pdf", "ocpo", "NJ", "https://ocponj.gov/example-release-{n}/",
     "Ocean County Prosecutor\\'s Office"),
    ("KY AG", "KYAG_ICAC_All.pdf", "ky_ag", "KY", "https://www.kentucky.gov/Pages/Activity-stream.aspx?n=AttorneyGeneral&prId={n}",
     "Kentucky Attorney General"),
    ("MCAO", "MCAO_ICAC_All.pdf", "mcao", "AZ", "https://maricopacountyattorney.org/m/newsflash/home/detail/{n}",
     "Maricopa County Attorney\\'s Office"),
    ("SACRAMENTO SO", "SACSO_ICAC_All.pdf", "sacramento_so", "CA", "https://www.sacsheriff.com/pages/release.php?id={n}",
     "Sacramento County Sheriff"),
]


def _merged(stem: str) -> str:
    first, second = stem.format(n=1001), stem.format(n=1002)
    return f"""Man Arrested on Child Sexual Abuse Material Charges
March 3, 2025
Publication date: 2025-03-03
Source: {first}
Corin Ashcombe, 34, was arrested and charged with possession of child sexual abuse material after a
CyberTip from the National Center for Missing and Exploited Children.

Woman Sentenced for Soliciting a Minor Online
June 9, 2026
Publication date: 2026-06-09
Source: {second}
Reese Thistlewood, 41, was sentenced to 8 years in prison for soliciting a minor online, following an
Internet Crimes Against Children Task Force investigation.
"""


@pytest.mark.parametrize("label, pdf, prefix, state, stem, display", SOURCES)
def test_pdf_routes_to_its_own_source(label, pdf, prefix, state, stem, display):
    assert detect_source_from_content("", pdf) == label
    assert detect_source_from_content(_merged(stem), "unnamed_scrape.pdf") == label


@pytest.mark.parametrize("label, pdf, prefix, state, stem, display", SOURCES)
def test_ncmec_reports_citing_the_agency_stay_ncmec(label, pdf, prefix, state, stem, display):
    assert detect_source_from_content(_merged(stem), "2025 NCMEC.pdf") == "NCMEC"


@pytest.mark.parametrize("label, pdf, prefix, state, stem, display", SOURCES)
def test_each_release_is_one_case_with_its_own_prefix_and_url(label, pdf, prefix, state, stem, display):
    cases = case_batching(_merged(stem), org_name=label.lower(), source=label, source_file=pdf)
    assert [c["case_id"] for c in cases] == [f"{prefix}_2025_001", f"{prefix}_2026_001"]
    assert [c["source_url"] for c in cases] == [stem.format(n=1001), stem.format(n=1002)]
    assert "possession" in cases[0]["case_text"] and "soliciting" not in cases[0]["case_text"]


@pytest.mark.parametrize("label, pdf, prefix, state, stem, display", SOURCES)
def test_cases_ground_to_the_agency_state(label, pdf, prefix, state, stem, display):
    assert SOURCE_TO_STATE[label] == state


@pytest.mark.parametrize("label, pdf, prefix, state, stem, display", SOURCES)
def test_sources_page_lists_the_agency(label, pdf, prefix, state, stem, display):
    html = (ROOT / "visualization" / "sources.html").read_text(encoding="utf-8")
    assert f"['{display}', ['{label}']]" in html


def _cards_and_rules():
    import re

    html = (ROOT / "visualization" / "sources.html").read_text(encoding="utf-8")
    static = html[html.index("const staticSources = ["):html.index("const SOURCE_MATCH = [")]
    cards = re.findall(r'^\s{20}name: "([^"]+)"', static, re.M)
    block = html[html.index("const SOURCE_MATCH = ["):]
    block = block[:block.index("];")]
    rules = [
        (part.replace("\\'", "'"), re.findall(r"'([^']+)'", keys))
        for part, keys in re.findall(r"\[\s*'((?:[^'\\]|\\.)+)',\s*\[([^\]]*)\]", block)
    ]
    return cards, rules


@pytest.mark.parametrize("label", [row[0] for row in SOURCES] + ["NASHVILLE PD"])
def test_a_sources_card_counts_the_label(label):
    """The page gives each card the first SOURCE_MATCH rule whose text is in the card name."""
    cards, rules = _cards_and_rules()
    counted = set()
    for name in cards:
        rule = next((keys for part, keys in rules if part in name), None)
        counted.update(rule or [])
    assert label in counted
