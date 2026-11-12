"""Metro Nashville PD as its own source: filename routing, release split, state. No network.

Wording copies the nashville.gov release layout; the people are made up.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("src/Ingestion Layer", "src/Processing Layer"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

from batching import case_batching  # noqa: E402
from ingestion import detect_source_from_content  # noqa: E402
from location_grounding import SOURCE_TO_STATE  # noqa: E402

GROK = "https://www.nashville.gov/departments/police/news/man-charged-using-grok-ai-generate-child-sex-abuse-images"
DISCORD = (
    "https://www.nashville.gov/departments/police/news/convicted-sex-offender-charged-after-uploading-ai-generated-child-sex-abuse-image"
)

MERGED = f"""Man Charged with Using Grok AI to Generate Child Sex Abuse Images
April 21, 2026
Publication date: 2026-04-21
Source: {GROK}
Corin Ashcombe, 47, is charged with sexual exploitation of a minor after he was identified as the suspect who
utilized Grok AI to generate images of child sex abuse. Special Victims Division detectives executed a search
warrant following an Internet Crimes Against Children Unit investigation.

Convicted Sex Offender Charged After Uploading AI Generated Child
Sex Abuse Image
August 19, 2026
Publication date: 2026-08-19
Source: {DISCORD[:107]}
{DISCORD[107:]}
Special Victims Division detectives arrested Reese Thistlewood, 44, who was found to have uploaded an AI
generated child sex abuse image to Discord, based on a CyberTip from the National Center for Missing and
Exploited Children.
"""


def test_nashville_pdf_routes_to_its_own_source():
    assert detect_source_from_content("", "NASHVILLEPD_ICAC_All.pdf") == "NASHVILLE PD"
    assert detect_source_from_content(MERGED, "unnamed_scrape.pdf") == "NASHVILLE PD"


def test_ncmec_reports_citing_nashville_stay_ncmec():
    assert detect_source_from_content(MERGED, "2025 NCMEC.pdf") == "NCMEC"


def test_each_release_is_one_case_with_its_full_source_url():
    cases = case_batching(
        MERGED, org_name="nashville pd", source="NASHVILLE PD", source_file="NASHVILLEPD_ICAC_All.pdf",
    )
    assert [c["case_id"] for c in cases] == ["nashville_pd_2026_001", "nashville_pd_2026_002"]
    assert [c["source_url"] for c in cases] == [GROK, DISCORD]
    assert "Grok AI" in cases[0]["case_text"] and "Discord" not in cases[0]["case_text"]
    assert "Discord" in cases[1]["case_text"]


def test_nashville_cases_ground_to_tennessee():
    assert SOURCE_TO_STATE["NASHVILLE PD"] == "TN"


def test_sources_page_lists_the_agency():
    html = (ROOT / "visualization" / "sources.html").read_text(encoding="utf-8")
    assert "['Metropolitan Nashville Police Department', ['NASHVILLE PD']]" in html
