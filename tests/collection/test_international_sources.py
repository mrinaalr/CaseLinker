"""Filename routing and Source:-layout batching for AFP, QPS, and Brazil PF. No network."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INGEST = ROOT / "src" / "Ingestion Layer"
PROC = ROOT / "src" / "Processing Layer"
for p in (INGEST, PROC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from batching import case_batching  # noqa: E402
from ingestion import detect_source_from_content  # noqa: E402


def test_doj_ai_csam_file_mints_its_own_prefix():
    """v2.5 gave DOJ_AI_CSAM_All.pdf the doj_ai_csam_ prefix. Safe Childhood stays separate."""
    ai = detect_source_from_content(
        "justice.gov AI-generated child pornography",
        "DOJ_AI_CSAM_All.pdf",
    )
    childhood = detect_source_from_content(
        "justice.gov Project Safe Childhood",
        "DOJ_SAFE_CHILDHOOD.pdf",
    )
    assert ai == "DOJ AI CSAM"
    assert childhood == "DOJ SAFE CHILDHOOD"
    text = """
Example plea
Publication date: 2026-04-20
Source: https://www.justice.gov/usao-ndia/pr/example-plea
A man pled guilty to possession of child pornography.
"""
    ai_cases = case_batching(
        text, org_name=ai.lower(), source=ai, source_file="DOJ_AI_CSAM_All.pdf",
    )
    childhood_cases = case_batching(
        text, org_name=childhood.lower(), source=childhood, source_file="DOJ_SAFE_CHILDHOOD.pdf",
    )
    assert ai_cases[0]["case_id"] == "doj_ai_csam_2026_001"
    assert childhood_cases[0]["case_id"] == "doj_safe_childhood_2026_001"
    archives = detect_source_from_content("", "DOJ_ARCHIVES_All.pdf")
    ceos = detect_source_from_content("", "DOJ_CEOS_All.pdf")
    assert archives == "DOJ ARCHIVES"
    assert ceos == "DOJ CEOS"
    arch_cases = case_batching(
        text, org_name=archives.lower(), source=archives, source_file="DOJ_ARCHIVES_All.pdf",
    )
    ceos_cases = case_batching(
        text, org_name=ceos.lower(), source=ceos, source_file="DOJ_CEOS_All.pdf",
    )
    assert arch_cases[0]["case_id"].startswith("doj_archives_")
    assert ceos_cases[0]["case_id"] == "doj_ceos_2026_001"
    assert arch_cases[0]["case_id"] != ceos_cases[0]["case_id"]


def test_filenames_map_to_new_sources():
    assert detect_source_from_content("", "AFP_CSEA_All.pdf") == "AFP"
    assert detect_source_from_content("", "QPS_CSEA_All.pdf") == "QPS"
    assert detect_source_from_content("", "BRAZIL_PF_CSEA_All.pdf") == "BRAZIL PF"
    assert detect_source_from_content("", "EUROPOL_CSEA_All.pdf") == "EUROPOL"
    assert detect_source_from_content("", "NCA_CSEA_All.pdf") == "NCA"
    assert detect_source_from_content("", "WIDOJ_ICAC_All.pdf") == "WI DOJ"
    assert detect_source_from_content("", "NZDIA_CSEA_All.pdf") == "NZ DIA"
    assert detect_source_from_content("", "ALERT_ICE_CSEA_All.pdf") == "ALERT ICE"
    assert detect_source_from_content("", "MDSP_CSEA_All.pdf") == "MDSP"
    assert detect_source_from_content("", "SCOTLAND_POLICE_CSEA_All.pdf") == "SCOTLAND POLICE"
    assert detect_source_from_content("", "VAAG_ICAC_All.pdf") == "VA AG"
    assert detect_source_from_content("", "NOVA_ICAC_All.pdf") == "NOVA ICAC"
    assert detect_source_from_content("", "SPF_CSEA_All.pdf") == "SPF"
    assert detect_source_from_content("", "COCBI_CSEA_All.pdf") == "CO CBI"
    assert detect_source_from_content("", "MNBCA_CSEA_All.pdf") == "MN BCA"
    assert detect_source_from_content("", "NBI_CSEA_All.pdf") == "NBI"
    assert detect_source_from_content("", "GARDA_CSEA_All.pdf") == "GARDA"


def test_new_sources_use_distinct_id_prefixes():
    text = """
Example charge
Publication date: 2024-05-01
Source: https://example.gov/news/example-charge
He was charged with a child sexual offence.
"""
    expected = {
        "ALERT ICE": "alert_ice_2024_001",
        "MDSP": "mdsp_2024_001",
        "SCOTLAND POLICE": "scotland_police_2024_001",
        "VA AG": "va_ag_2024_001",
        "NOVA ICAC": "nova_icac_2024_001",
        "SPF": "spf_2024_001",
        "CO CBI": "co_cbi_2024_001",
        "MN BCA": "mn_bca_2024_001",
        "NBI": "nbi_2024_001",
        "GARDA": "garda_2024_001",
        "DOJ AI CSAM": "doj_ai_csam_2024_001",
        "DOJ SAFE CHILDHOOD": "doj_safe_childhood_2024_001",
        "ICE": "ice_2024_001",
    }
    seen: set[str] = set()
    for source, case_id in expected.items():
        cases = case_batching(
            text,
            org_name=source.lower(),
            source=source,
            source_file=f"{source.replace(' ', '_')}.pdf",
        )
        assert cases[0]["case_id"] == case_id
        prefix = case_id.rsplit("_", 2)[0]
        assert prefix not in seen
        seen.add(prefix)


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


def test_wi_and_nz_merged_layout_case_ids():
    text = """
Walworth sentencing
Publication date: 2026-06-10
Source: https://www.wisdoj.gov/PressReleases/Walworth-icac-sentencing.pdf
Sentenced to 10 years initial confinement.
Nelson sentence
Publication date: 2026-04-02
Source: https://www.dia.govt.nz/press.nsf/example!OpenDocument
Sentenced to three years and six months imprisonment.
"""
    wi = case_batching(text, org_name="wi doj", source="WI DOJ", source_file="WIDOJ_ICAC_All.pdf")
    assert [c["case_id"] for c in wi] == ["wi_doj_2026_001", "wi_doj_2026_002"]
    nz = case_batching(text, org_name="nz dia", source="NZ DIA", source_file="NZDIA_CSEA_All.pdf")
    assert [c["case_id"] for c in nz] == ["nz_dia_2026_001", "nz_dia_2026_002"]


def test_one_line_body_stays_with_its_source_line():
    """A Title Case body sentence must not become the next article's headline."""
    text = """
Ashburn Man Sentenced for Child Pornography
February 06, 2016
Publication date: 2016-02-06
Source: https://example.test/ashburn
A 31-year-old Ashburn man has been sentenced to five years for five counts of possession of child
pornography.
Winchester Man Pleads Guilty to Child Pornography Charges
November 10, 2015
Publication date: 2015-11-10
Source: https://example.test/winchester
A Winchester man pleaded guilty Monday to ten felony counts.
A 57-year-old man has been jailed for non-recent sexual offences
February 17, 2022
Publication date: 2022-02-17
Source: https://example.test/jailed
He was jailed after a trial.
"""
    cases = case_batching(text, org_name="nova_icac", source="NOVA ICAC", source_file="NOVA_ICAC_All.pdf")
    by_url = {c["source_url"]: c["case_text"] for c in cases}
    assert "five years" in by_url["https://example.test/ashburn"]
    assert "five years" not in by_url["https://example.test/winchester"]
    assert "has been jailed" in by_url["https://example.test/jailed"]
