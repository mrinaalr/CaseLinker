"""
Case Batching Module

Purpose: Split text corpus into individual cases based on source format.
Handles batching for NCMEC and AZICAC cases (and can be extended for other formats).

This module is shared by both Pattern Processing Layer and ML Processing Layer.
Both layers can ingest the batched cases and process them independently.
"""

import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

_suc_path = Path(__file__).resolve().parent / "source_url_continuations.py"
_suc_spec = importlib.util.spec_from_file_location("_case_linker_source_url_cont", _suc_path)
_suc_mod = importlib.util.module_from_spec(_suc_spec)
_suc_spec.loader.exec_module(_suc_mod)
try_append_source_url_continuation = _suc_mod.try_append_source_url_continuation
consume_same_line_slug_after_url = _suc_mod.consume_same_line_slug_after_url


def clean_artifacts_from_text(text: str, remove_urls: bool = True) -> str:
    """
    Remove artifacts from case text including URLs, page numbers, and other PDF extraction artifacts.
    
    Handles:
    - URLs (http://, https://, www.) - optional, controlled by remove_urls parameter
    - URLs split across lines
    - Page numbers at end of text
    - AZICAC-specific artifacts (azicac.org references, URL fragments)
    - Multiple consecutive spaces
    - Leading/trailing whitespace
    
    Args:
        text: Case text that may contain artifacts
        remove_urls: If True, remove URLs. If False, keep URLs in text (default: True)
        
    Returns:
        Cleaned text with artifacts removed
    """
    if not text:
        return text
    
    cleaned_text = text
    
    # Only remove URLs if requested (for NCMEC media cases, we want to keep URLs)
    if remove_urls:
        # Pattern 1: Match full URLs (http:// or https://) - handles URLs split across lines
        # Continuation lines must be URL path segments (not prose datelines starting with a capital).
        pattern1 = (
            r"https?://[^\s\n]+"
            r"(?:\s*\n\s*(?![A-Z])[a-zA-Z0-9\-./_%?#&=]+)*"
        )
        cleaned_text = re.sub(pattern1, '', cleaned_text, flags=re.IGNORECASE)
        
        # Pattern 2: Match www. URLs (without http://)
        # Matches: "www.example.com/path" - handles split across lines
        pattern2 = r'www\.[^\s\n]+(?:\s*\n\s*[^\s\n]+)*'
        cleaned_text = re.sub(pattern2, '', cleaned_text, flags=re.IGNORECASE)
        
        # Pattern 3: Match URLs with fragments/anchors (e.g., #:~:text=...)
        # These often appear split across lines in PDFs
        pattern3 = r'[^\s]+\.(com|org|gov|net|edu|io|co)[^\s\n]*(?:#|/)[^\s\n]*(?:\s*\n\s*[^\s\n]+)*'
        cleaned_text = re.sub(pattern3, '', cleaned_text, flags=re.IGNORECASE)
    
    # Pattern 4: AZICAC-specific patterns
    # Match from http/https to AZICAC.ORG (case-insensitive)
    pattern4 = r'https?://.*?azicac\.org'
    cleaned_text = re.sub(pattern4, '', cleaned_text, flags=re.IGNORECASE)
    
    # Pattern 5: Match page numbers/date patterns that lead to AZICAC.ORG
    pattern5 = r'\d+/\d+\s+\d+/\d+/\d+.*?azicac\.org'
    cleaned_text = re.sub(pattern5, '', cleaned_text, flags=re.IGNORECASE)
    
    # Pattern 6: Match URL path fragments like "/2011-cases-and-arrests/"
    pattern6 = r'/\d{4}-cases-and-arrests/'
    cleaned_text = re.sub(pattern6, '', cleaned_text, flags=re.IGNORECASE)
    
    # Pattern 7: Match standalone "azicac.org" or "AZICAC.ORG" (without http://)
    pattern7 = r'\bazicac\.org\b'
    cleaned_text = re.sub(pattern7, '', cleaned_text, flags=re.IGNORECASE)
    
    # Pattern 8: Remove page numbers at end of text (standalone numbers on last line)
    # Matches: "42", "65", "74", "115", "165" etc. at end of text
    # Only remove if it's a standalone number (1-4 digits) at the very end
    cleaned_text = re.sub(r'\n\s*\d{1,4}\s*$', '', cleaned_text)
    cleaned_text = re.sub(r'^\s*\d{1,4}\s*$', '', cleaned_text, flags=re.MULTILINE)
    
    # Pattern 9: Remove trailing page numbers that appear after content
    # Matches patterns like "text.\n42" or "text\n65" where number is on separate line
    cleaned_text = re.sub(r'\n\s*(\d{1,4})\s*(?=\n|$)', '', cleaned_text)
    
    # Clean up whitespace artifacts
    # Replace multiple spaces with single space
    cleaned_text = re.sub(r' +', ' ', cleaned_text)
    # Replace multiple newlines with single newline (but preserve paragraph breaks)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    # Remove trailing whitespace from each line
    cleaned_text = re.sub(r'[ \t]+$', '', cleaned_text, flags=re.MULTILINE)
    # Remove leading/trailing whitespace from entire text
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text


def case_batching(text: str, org_name: str = "case", source: str = None, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Router function that splits text corpus into individual cases.
    Routes to appropriate batch function based on source format.
    
    Supported formats:
    - NCMEC: Split by state headers (ALABAMA, ARIZONA, etc.) or URL patterns
    - AZICAC: Split by month patterns ("In [Month]" or "[Month] [Year],")
    - GBI: Georgia Bureau of Investigation press releases split on "# # # # #" then by release date lines
    - Texas AG: Texas Attorney General CEU releases split by date-line starts and "Back to Top"
    - SVICAC / TBI ICAC / SCAG ICAC / NEWYORK SP / ILLINOIS AG / NJ AG / PA AG / VT AG / OHIO AG / DE AG / UT AG / WA AG / OREGON DOJ / MS AG / MT DOJ / NM AG / NC SBI / LA AG / HI AG / CCSAO / IA DCI / WY DCI / SD AG / RI AG / FL AG / KY SP / NE SP / ARMY CID / USSS / ICE / LVMPD / SJPD / ARKANSAS DPS / ALEA / DOJ CEOS / DOJ ARCHIVES / WCSO / FRESNO SO / OSCEOLA SO / SEDGWICK SO / ANCHORAGE PD / LAPD / CSPD / SPD / SDPD / SOUTH FLORIDA ICAC / same-layout merged scrapes: split on ``Source: https://`` per article
    - Other / External: Delimited narratives: "Case 1 : ... Case 2 : ..." (news scrapes, LinkedIn, international, misc.)
    - Default: If text matches ``Case N :`` markers, falls back to external batching; otherwise AZICAC month-splitting
    
    To add new formats, create a _batch_[org]_cases() function and add detection logic here.
    
    Args:
        text: Large text block from PDF ingestion
        org_name: Organization name prefix for case IDs (e.g., "azicac", "ncmec")
        source: Source organization name ('NCMEC', 'AZICAC', 'FBI', etc.) - used to determine format
        source_file: Filename to extract report year from (e.g., "2022 NCMEC.pdf")
        
    Returns:
        List of case dictionaries, each with 'case_text', 'month_year', 'month', 'year', 'case_id'
    """
    # Normalize org name (lowercase, remove spaces/special chars)
    org_name = org_name.lower().replace(" ", "_").replace("-", "_")
    
    # Detect format: check source parameter first, then auto-detect from content
    is_ncmec = False
    is_idaho_icac = False
    is_michigan_icac = False
    is_gbi = False
    is_texas_ag = False
    is_svicac = False
    is_tbi_icac = False
    is_scag_icac = False
    is_newyork_sp = False
    is_illinois_ag = False
    is_wcso = False
    is_fresno_so = False
    is_osceola_so = False
    is_sedgwick_so = False
    is_anchorage_pd = False
    is_lapd = False
    is_cspd = False
    is_spd = False
    is_sdpd = False
    is_south_florida_icac = False
    is_nj_ag = False
    is_pa_ag = False
    is_vt_ag = False
    is_ohio_ag = False
    is_de_ag = False
    is_ut_ag = False
    is_wa_ag = False
    is_oregon_doj = False
    is_ms_ag = False
    is_mt_doj = False
    is_nm_ag = False
    is_nc_sbi = False
    is_la_ag = False
    is_hi_ag = False
    is_ccsao = False
    is_ia_dci = False
    is_wy_dci = False
    is_sd_ag = False
    is_ri_ag = False
    is_fl_ag = False
    is_ky_sp = False
    is_ne_sp = False
    is_army_cid = False
    is_usss = False
    is_ice = False
    is_af_osi = False
    is_ncis = False
    is_cbp = False
    is_us_marshals = False
    is_lvmpd = False
    is_sjpd = False
    is_arkansas_dps = False
    is_alea = False
    is_doj_ceos = False
    is_doj_archives = False
    is_other_external = False
    
    if source:
        source_upper = source.upper().replace("_", " ")
        if source_upper == 'NCMEC':
            is_ncmec = True
        elif source_upper == 'IDAHO ICAC':
            is_idaho_icac = True
        elif source_upper == 'MICHIGAN ICAC':
            is_michigan_icac = True
        elif source_upper == 'GBI':
            is_gbi = True
        elif source_upper == 'TEXAS AG':
            is_texas_ag = True
        elif source_upper == 'SVICAC':
            is_svicac = True
        elif source_upper == 'TBI ICAC':
            is_tbi_icac = True
        elif source_upper == 'SCAG ICAC':
            is_scag_icac = True
        elif source_upper in ('NEWYORK SP', 'NEW YORK SP'):
            is_newyork_sp = True
        elif source_upper == 'ILLINOIS AG':
            is_illinois_ag = True
        elif source_upper == 'WCSO':
            is_wcso = True
        elif source_upper == 'FRESNO SO':
            is_fresno_so = True
        elif source_upper == 'OSCEOLA SO':
            is_osceola_so = True
        elif source_upper == 'SEDGWICK SO':
            is_sedgwick_so = True
        elif source_upper == 'ANCHORAGE PD':
            is_anchorage_pd = True
        elif source_upper == 'LAPD':
            is_lapd = True
        elif source_upper == 'CSPD':
            is_cspd = True
        elif source_upper == 'SPD':
            is_spd = True
        elif source_upper == 'SDPD':
            is_sdpd = True
        elif source_upper == 'SOUTH FLORIDA ICAC':
            is_south_florida_icac = True
        elif source_upper == 'NJ AG':
            is_nj_ag = True
        elif source_upper == 'PA AG':
            is_pa_ag = True
        elif source_upper == 'VT AG':
            is_vt_ag = True
        elif source_upper == 'OHIO AG':
            is_ohio_ag = True
        elif source_upper == 'DE AG':
            is_de_ag = True
        elif source_upper == 'UT AG':
            is_ut_ag = True
        elif source_upper == 'WA AG':
            is_wa_ag = True
        elif source_upper == 'OREGON DOJ':
            is_oregon_doj = True
        elif source_upper == 'MS AG':
            is_ms_ag = True
        elif source_upper == 'MT DOJ':
            is_mt_doj = True
        elif source_upper == 'NM AG':
            is_nm_ag = True
        elif source_upper == 'NC SBI':
            is_nc_sbi = True
        elif source_upper == 'LA AG':
            is_la_ag = True
        elif source_upper == 'HI AG':
            is_hi_ag = True
        elif source_upper == 'CCSAO':
            is_ccsao = True
        elif source_upper == 'IA DCI':
            is_ia_dci = True
        elif source_upper == 'WY DCI':
            is_wy_dci = True
        elif source_upper == 'SD AG':
            is_sd_ag = True
        elif source_upper == 'RI AG':
            is_ri_ag = True
        elif source_upper == 'FL AG':
            is_fl_ag = True
        elif source_upper == 'KY SP':
            is_ky_sp = True
        elif source_upper == 'NE SP':
            is_ne_sp = True
        elif source_upper == 'ARMY CID':
            is_army_cid = True
        elif source_upper == 'USSS':
            is_usss = True
        elif source_upper == 'ICE':
            is_ice = True
        elif source_upper in ('AF OSI', 'AIR FORCE OSI'):
            is_af_osi = True
        elif source_upper == 'NCIS':
            is_ncis = True
        elif source_upper == 'CBP':
            is_cbp = True
        elif source_upper in ('US MARSHALS', 'USMS', 'U.S. MARSHALS'):
            is_us_marshals = True
        elif source_upper == 'LVMPD':
            is_lvmpd = True
        elif source_upper == 'SJPD':
            is_sjpd = True
        elif source_upper == 'ARKANSAS DPS':
            is_arkansas_dps = True
        elif source_upper == 'ALEA':
            is_alea = True
        elif source_upper == 'DOJ CEOS':
            is_doj_ceos = True
        elif source_upper == 'DOJ ARCHIVES':
            is_doj_archives = True
        elif source_upper in ('OTHER'):
            is_other_external = True
    
    # Route to appropriate batch function
    if is_ncmec:
        return _batch_ncmec_cases(text, org_name, source_file)
    elif is_idaho_icac:
        return _batch_idaho_icac_cases(text, org_name, source_file)
    elif is_michigan_icac:
        return _batch_michigan_icac_cases(text, org_name, source_file)
    elif is_gbi:
        return _batch_gbi_cases(text, org_name, source_file)
    elif is_texas_ag:
        return _batch_texas_ag_cases(text, org_name, source_file)
    elif is_svicac:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SVICAC")
    elif is_tbi_icac:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "TBI ICAC")
    elif is_scag_icac:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SCAG ICAC")
    elif is_newyork_sp:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "NEWYORK SP")
    elif is_illinois_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "ILLINOIS AG")
    elif is_wcso:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "WCSO")
    elif is_fresno_so:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "FRESNO SO")
    elif is_osceola_so:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "OSCEOLA SO")
    elif is_sedgwick_so:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SEDGWICK SO")
    elif is_anchorage_pd:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "ANCHORAGE PD")
    elif is_lapd:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "LAPD")
    elif is_cspd:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "CSPD")
    elif is_spd:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SPD")
    elif is_sdpd:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SDPD")
    elif is_south_florida_icac:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SOUTH FLORIDA ICAC")
    elif is_nj_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "NJ AG")
    elif is_pa_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "PA AG")
    elif is_vt_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "VT AG")
    elif is_ohio_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "OHIO AG")
    elif is_de_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "DE AG")
    elif is_ut_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "UT AG")
    elif is_wa_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "WA AG")
    elif is_oregon_doj:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "OREGON DOJ")
    elif is_ms_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "MS AG")
    elif is_mt_doj:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "MT DOJ")
    elif is_nm_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "NM AG")
    elif is_nc_sbi:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "NC SBI")
    elif is_la_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "LA AG")
    elif is_hi_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "HI AG")
    elif is_ccsao:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "CCSAO")
    elif is_ia_dci:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "IA DCI")
    elif is_wy_dci:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "WY DCI")
    elif is_sd_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SD AG")
    elif is_ri_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "RI AG")
    elif is_fl_ag:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "FL AG")
    elif is_ky_sp:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "KY SP")
    elif is_ne_sp:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "NE SP")
    elif is_army_cid:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "ARMY CID")
    elif is_usss:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "USSS")
    elif is_ice:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "ICE")
    elif is_af_osi:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "AF OSI")
    elif is_ncis:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "NCIS")
    elif is_cbp:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "CBP")
    elif is_us_marshals:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "US MARSHALS")
    elif is_lvmpd:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "LVMPD")
    elif is_sjpd:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "SJPD")
    elif is_arkansas_dps:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "ARKANSAS DPS")
    elif is_alea:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "ALEA")
    elif is_doj_ceos:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "DOJ CEOS")
    elif is_doj_archives:
        return _batch_merged_icac_news_cases(text, org_name, source_file, "DOJ ARCHIVES")
    elif is_other_external:
        return _batch_external_cases(text, org_name, source_file)
    else:
        # Fallback before AZICAC: delimited "Case N :" wire format (e.g. external.pdf)
        sample = text[:12000] if text else ""
        if _EXTERNAL_CASE_HEADER_RE.search(sample):
            return _batch_external_cases(text, "other", source_file)
        return _batch_azicac_cases(text, org_name)


# "Case 1 : ... Case 2 : ..." delimited wire format (external/news/LinkedIn scrapes, etc.)
_EXTERNAL_CASE_HEADER_RE = re.compile(
    r"(?m)(?:^|\n)\s*Case\s+(\d+)\s*:",
    re.IGNORECASE,
)

def _extract_wrapped_url_from_source_line(lines: List[str], source_idx: int) -> str:
    """
    Extract URL from `Source:` line and join wrapped continuation lines.
    Handles PDF line wraps in long slugs.
    """
    if source_idx < 0 or source_idx >= len(lines):
        return ""
    line = lines[source_idx]
    m = re.search(r"(https?://\S*)", line)
    if not m:
        return ""
    url = m.group(1).strip()
    spaced_slug_segments = 0
    extra, add = consume_same_line_slug_after_url(url, line[m.end() :])
    url = extra
    spaced_slug_segments += add
    j = source_idx + 1
    while j < len(lines):
        nxt = lines[j].strip()
        if not nxt:
            break
        if nxt.lower().startswith("source:"):
            break
        if nxt.lower().startswith("http://") or nxt.lower().startswith("https://"):
            break
        tup = try_append_source_url_continuation(url, nxt, spaced_slug_segments)
        if tup is None:
            break
        frag, is_spaced = tup
        url += frag
        if is_spaced:
            spaced_slug_segments += 1
        j += 1
        if url.lower().endswith(".pdf"):
            break
    return url.rstrip(".,;)")


def _batch_external_cases(
    text: str, org_name: str, source_file: str = None
) -> List[Dict[str, Any]]:
    """
    Split text on delimiters: Case 1 : ... Case 2 : ... (case label and colon flexible).

    Used for source ``Other`` / ``External``: heterogeneous narratives in one PDF where you
    control the boundary format. If no markers match, returns a single case with the full text.
    """
    from datetime import datetime

    year = str(datetime.now().year)
    if not text or not text.strip():
        return [
            {
                "case_text": "",
                "month_year": None,
                "month": None,
                "year": year,
                "case_id": f"{org_name}_{year}_001",
            }
        ]

    matches = list(_EXTERNAL_CASE_HEADER_RE.finditer(text))
    if not matches:
        cleaned = clean_artifacts_from_text(text.strip())
        return [
            {
                "case_text": cleaned,
                "month_year": None,
                "month": None,
                "year": year,
                "case_id": f"{org_name}_{year}_001",
            }
        ]

    cases: List[Dict[str, Any]] = []
    seq = 0
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        case_text = text[body_start:body_end].strip()
        case_text = clean_artifacts_from_text(case_text)
        if len(case_text) < 1:
            continue
        seq += 1
        case_id = f"{org_name}_{year}_{seq:03d}"
        cases.append(
            {
                "case_text": case_text,
                "month_year": None,
                "month": None,
                "year": year,
                "case_id": case_id,
            }
        )

    if not cases:
        cleaned = clean_artifacts_from_text(text.strip())
        return [
            {
                "case_text": cleaned,
                "month_year": None,
                "month": None,
                "year": year,
                "case_id": f"{org_name}_{year}_001",
            }
        ]

    return cases


def _batch_azicac_cases(text: str, org_name: str) -> List[Dict[str, Any]]:
    """
    Split AZICAC cases by month/year patterns.
    
    Primary pattern: "In [Month]" (e.g., "In January", "In February")
    Secondary pattern: "[Month] [Year]," (e.g., "July 2012,", "September 2012,")
    
    Args:
        text: Full text from AZICAC PDF
        org_name: Organization name prefix for case IDs (e.g., "azicac")
        
    Returns:
        List of case dictionaries with 'case_text', 'month_year', 'month', 'year', 'case_id'
    """
    cases = []
    
    months = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
    
    # Primary pattern: "In [Month]" (official method) - "In" must be uppercase
    pattern1 = rf'In {months}'
    
    # Secondary pattern: "[Month] [Year]," (with comma)
    pattern2 = rf'{months}\s+(\d{{4}}),'
    
    all_matches = []
    
    # Find all matches from primary pattern - case-sensitive for "In", case-insensitive for month
    for match in re.finditer(pattern1, text, re.IGNORECASE):
        # Check that "In" is actually uppercase (not "in")
        match_text = text[match.start():match.start()+2]
        if match_text != 'In':
            continue  # Skip if lowercase "in"
        all_matches.append({
            'pos': match.start(),
            'month': match.group(1),
            'year': None,  # Will extract from case text
            'pattern': 'primary'
        })
    
    # Find all matches from secondary pattern (with comma)
    for match in re.finditer(pattern2, text, re.IGNORECASE):
        all_matches.append({
            'pos': match.start(),
            'month': match.group(1),
            'year': match.group(2),
            'pattern': 'secondary_comma'
        })
    
    # Remove duplicates: if positions are close, keep the highest priority pattern
    # Priority: primary > secondary_comma
    # Sort by position first
    all_matches.sort(key=lambda x: x['pos'])
    
    # Deduplicate: prefer higher priority patterns if positions are close
    pattern_priority = {'primary': 2, 'secondary_comma': 1}
    unique_matches = []
    for match in all_matches:
        is_duplicate = False
        for i, existing in enumerate(unique_matches):
            if abs(match['pos'] - existing['pos']) < 15:  # Within 15 chars
                match_priority = pattern_priority.get(match['pattern'], 0)
                existing_priority = pattern_priority.get(existing['pattern'], 0)
                
                # If existing has higher priority, skip this one
                if existing_priority > match_priority:
                    is_duplicate = True
                    break
                # If this has higher priority, replace existing
                elif match_priority > existing_priority:
                    unique_matches[i] = match
                    is_duplicate = True  # Mark as handled
                    break
                # If same priority and same position, skip duplicate
                elif match_priority == existing_priority and match['pos'] == existing['pos']:
                    is_duplicate = True
                    break
        if not is_duplicate:
            unique_matches.append(match)
    
    # Sort again after deduplication
    unique_matches.sort(key=lambda x: x['pos'])
    
    if not unique_matches:
        from datetime import datetime
        year = str(datetime.now().year)
        return [{'case_text': text, 'month_year': None, 'case_id': f'{org_name}_{year}_001'}]
    
    # Track cases per year for proper numbering (resets each year)
    year_case_counts = {}
    
    for i, match_info in enumerate(unique_matches):
        month = match_info['month']
        start_pos = match_info['pos']
        
        # Determine end position
        if i + 1 < len(unique_matches):
            end_pos = unique_matches[i + 1]['pos']
        else:
            end_pos = len(text)
        
        case_text = text[start_pos:end_pos].strip()
        
        # Clean artifacts from case text before processing
        case_text = clean_artifacts_from_text(case_text)
        
        # Extract year
        if match_info['year']:
            # Year already extracted from pattern
            year = match_info['year']
        else:
            # Extract year from case text - supports any year (2013, 2014, etc.)
            # Look for 4-digit year (1900-2099) in the case text
            year_match = re.search(r'\b(19|20)\d{2}\b', case_text)
            if year_match:
                year = year_match.group(0)
            else:
                # Fallback: use current year if no year found
                from datetime import datetime
                year = str(datetime.now().year)
        
        # Track case number per year (resets each year)
        if year not in year_case_counts:
            year_case_counts[year] = 0
        year_case_counts[year] += 1
        case_number = year_case_counts[year]
        
        case_id = f"{org_name}_{year}_{case_number:03d}"
        
        cases.append({
            'case_text': case_text,
            'month_year': f"{month} {year}",
            'month': month,
            'year': year,
            'case_id': case_id
        })
    
    return cases


def _batch_ncmec_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Router function for NCMEC case batching.
    Detects format from year in filename or first 10 lines and routes to appropriate handler.
    
    Args:
        text: Full text from NCMEC PDF
        org_name: Organization name prefix for case IDs (e.g., "ncmec")
        source_file: Filename to extract report year from (e.g., "2022 NCMEC.pdf")
        
    Returns:
        List of case dictionaries with 'case_text', 'month_year', 'month', 'year', 'case_id'
    """
    # Extract year from filename first (most reliable)
    report_year = None
    if source_file:
        year_match = re.search(r'(\d{4})', source_file)
        if year_match:
            report_year = year_match.group(1)
    
    if report_year in ('2024', '2025'):
        return _batch_ncmec_2024_cases(text, org_name, source_file)
    elif report_year in ['2022', '2023']:
        # 2022 or 2023 - use media format (numbered articles)
        return _batch_ncmec_media_cases(text, org_name, source_file)
    else:
        # Try to detect from text
        lines = text.split('\n')[:10]
        first_lines_text = ' '.join(lines)
        
        # Look for year pattern (2022–2025 NCMEC anthology years)
        year_pattern = r'\b(202[2-5])\b'
        year_match = re.search(year_pattern, first_lines_text)
        
        if year_match:
            year = year_match.group(1)
            if year in ('2024', '2025'):
                return _batch_ncmec_2024_cases(text, org_name, source_file)
            else:
                return _batch_ncmec_media_cases(text, org_name, source_file)
        else:
            # No year found - default to media format
            return _batch_ncmec_media_cases(text, org_name, source_file)


def _ncmec_report_year(source_file: Optional[str]) -> Optional[str]:
    if not source_file:
        return None
    year_match = re.search(r'(\d{4})', source_file)
    return year_match.group(1) if year_match else None


def _ncmec_media_url_pattern(report_year: Optional[str]) -> str:
    """
    Regex for one press clip's https block through body text.

    Continues across wrapped URL lines and article body until a boundary line:
    - 2022–2024 PDFs: bare page number (``\\n45\\n``)
    - 2025+ PDFs: also ``Page | 38`` footers
    """
    if report_year and report_year.isdigit() and int(report_year) >= 2025:
        boundary = r'(?:\d+\s*|Page\s*\|\s*\d+\s*)'
    else:
        boundary = r'\d+\s*'
    return rf'https?://[^\n]+(?:\n(?!\s*{boundary}\n)[^\n]+)*'


_NCMEC_ARTICLE_BOUNDARY_RE = re.compile(r'\n\s*(?:Page\s*\|\s*)?(\d+)\s*\n')


def _ncmec_start_after_article_boundary(text: str, prev_url_end: int) -> int:
    """Index where the next article begins after the previous clip's page marker."""
    window = text[prev_url_end:prev_url_end + 8000]
    boundary_match = _NCMEC_ARTICLE_BOUNDARY_RE.search(window)
    if boundary_match:
        return prev_url_end + boundary_match.end()
    if prev_url_end < len(text) and text[prev_url_end] == '\n':
        return prev_url_end + 1
    return prev_url_end


def _normalize_ncmec_source_url(url_blob: str) -> str:
    """First https URL from a matched clip blob (may include wrapped slug lines)."""
    if not url_blob:
        return ""
    lines = url_blob.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r'https?://\S*', line)
        if not m:
            continue
        url = m.group(0).strip()
        spaced_slug_segments = 0
        extra, add = consume_same_line_slug_after_url(url, line[m.end():])
        url = extra
        spaced_slug_segments += add
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                break
            if _NCMEC_ARTICLE_BOUNDARY_RE.match('\n' + lines[j] + '\n'):
                break
            if re.match(r'^[A-Z0-9][A-Z0-9\s\-\'\./,&]{12,}$', nxt) and not nxt.lower().startswith('http'):
                break
            tup = try_append_source_url_continuation(url, nxt, spaced_slug_segments)
            if tup is None:
                break
            frag, is_spaced = tup
            url += frag
            if is_spaced:
                spaced_slug_segments += 1
            j += 1
        return url.rstrip('.,;)')
    return ""


def _split_ncmec_2024_double_story_blocks(segment: str) -> List[str]:
    """
    Some 2024 state sections concatenate **two** unrelated stories: a local blurb (often no URL)
    and a federal DOJ/USAO **Press Release** with a single ``justice.gov`` link. The multi-URL
    branch only runs when ``https://`` appears more than once, so those pairs were one case.

    Split at the last paragraph break before a federal-style ``Press Release`` / ``United States
    Attorney`` block (typically after an ALL CAPS headline). Returns one or two segments.
    """
    if not segment or len(segment) < 500:
        return [segment]
    m = re.search(
        r'(?i)\n\s*Press Release\s*\n\s*(?:United States Attorney|U\.S\. Attorney)',
        segment[120:],
    )
    if not m:
        return [segment]
    cut_press = 120 + m.start()
    probe = segment[:cut_press]
    idx = probe.rfind('\n\n')
    if idx < 80:
        return [segment]
    first_line = segment[idx + 2 : idx + 2 + 240].split('\n')[0].strip()
    if len(first_line) < 10:
        return [segment]
    letters = [c for c in first_line if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio < 0.55 and len(first_line) < 35:
            return [segment]
    first = segment[:idx].strip()
    second = segment[idx:].strip()
    if len(first) < 120 or len(second) < 120:
        return [segment]
    return [first, second]


def _batch_ncmec_2024_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Split NCMEC 2024 by ALL-CAPS US state lines (primary structure — different from 2022/2023 media PDFs).

    Some sections bundle **multiple** press stories under one state (notably a long WYOMING tail and
    multi-article blocks). When a state segment contains more than one ``https://`` link, we run the
    same URL-boundary splitter used for media years **on that segment only**, then flatten and renumber.
    When only one URL is present but a second federal **Press Release** block is pasted after a local
    story, :func:`_split_ncmec_2024_double_story_blocks` splits first.

    Args:
        text: Full text from NCMEC PDF
        org_name: Organization name prefix for case IDs (e.g., "ncmec")
        source_file: Filename to extract report year from (e.g., "2024 - NCMEC Cases.pdf")

    Returns:
        List of case dictionaries with 'case_text', 'month_year', 'month', 'year', 'case_id'
    """
    # Extract report year from filename if available
    report_year = None
    if source_file:
        year_match = re.search(r'(\d{4})', source_file)
        if year_match:
            report_year = year_match.group(1)
    cases = []
    
    # List of all US states (all caps for NCMEC format)
    states = [
        'ALABAMA', 'ALASKA', 'ARIZONA', 'ARKANSAS', 'CALIFORNIA', 'COLORADO',
        'CONNECTICUT', 'DELAWARE', 'FLORIDA', 'GEORGIA', 'HAWAII', 'IDAHO',
        'ILLINOIS', 'INDIANA', 'IOWA', 'KANSAS', 'KENTUCKY', 'LOUISIANA',
        'MAINE', 'MARYLAND', 'MASSACHUSETTS', 'MICHIGAN', 'MINNESOTA',
        'MISSISSIPPI', 'MISSOURI', 'MONTANA', 'NEBRASKA', 'NEVADA',
        'NEW HAMPSHIRE', 'NEW JERSEY', 'NEW MEXICO', 'NEW YORK',
        'NORTH CAROLINA', 'NORTH DAKOTA', 'OHIO', 'OKLAHOMA', 'OREGON',
        'PENNSYLVANIA', 'RHODE ISLAND', 'SOUTH CAROLINA', 'SOUTH DAKOTA',
        'TENNESSEE', 'TEXAS', 'UTAH', 'VERMONT', 'VIRGINIA', 'WASHINGTON',
        'WEST VIRGINIA', 'WISCONSIN', 'WYOMING'
    ]
    
    # Build regex pattern to match state headers (must be at start of line).
    # PDF extraction often leaves trailing spaces on the line (e.g. "CALIFORNIA  ");
    # allow optional whitespace so sections still split.
    # Sort by length (longest first) to match "NEW YORK" before "NEW"
    states_sorted = sorted(states, key=len, reverse=True)
    state_pattern = '|'.join(re.escape(state) for state in states_sorted)
    pattern = rf'^\s*({state_pattern})\s*$'
    
    # Find all state header positions
    matches = []
    for match in re.finditer(pattern, text, re.MULTILINE):
        matches.append({
            'pos': match.start(),
            'state': match.group(1)
        })
    
    if not matches:
        # No state headers found - return entire text as one case
        from datetime import datetime
        id_year = report_year if report_year else str(datetime.now().year)
        case_date_year = report_year if report_year else str(datetime.now().year)
        return [{
            'case_text': text,
            'month_year': None,
            'month': None,
            'year': case_date_year,
            'case_id': f'{org_name}_{id_year}_001'
        }]

    def _metadata_from_text(case_text: str) -> Tuple[str, Optional[str], str]:
        """Derive month_year, month, year string from a case blob."""
        months = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        date_pattern = rf'{months}\s+(\d{{1,2}}),?\s+(\d{{4}})'
        date_match = re.search(date_pattern, case_text, re.IGNORECASE)
        if date_match:
            month = date_match.group(1)
            case_date_year = date_match.group(3)
            month_year = f"{month} {case_date_year}"
            return month_year, month, case_date_year
        year_match = re.search(r'\b(19|20)\d{2}\b', case_text)
        if year_match:
            y = year_match.group(0)
            return y, None, y
        from datetime import datetime
        y = report_year if report_year else str(datetime.now().year)
        return y, None, y

    cases: List[Dict[str, Any]] = []

    for i, match_info in enumerate(matches):
        start_pos = match_info['pos']
        state = match_info['state']
        if i + 1 < len(matches):
            end_pos = matches[i + 1]['pos']
        else:
            end_pos = len(text)

        raw_block = text[start_pos:end_pos].strip()
        pieces = _split_ncmec_2024_double_story_blocks(raw_block)

        for piece in pieces:
            url_n = piece.count('https://')

            if url_n > 1:
                subs = _batch_ncmec_media_cases(piece, org_name, source_file)
                sub_cases: List[Dict[str, Any]] = []
                for sub in subs:
                    ct = sub.get('case_text', '')
                    ct = clean_artifacts_from_text(ct, remove_urls=False)
                    if not ct or len(ct) < 40:
                        continue
                    # Local + federal DOJ blocks can share one URL in a segment (see WYOMING tail).
                    for frag in _split_ncmec_2024_double_story_blocks(ct):
                        if not frag or len(frag) < 40:
                            continue
                        my, mo, yr = _metadata_from_text(frag)
                        sub_cases.append({
                            'case_text': frag,
                            'month_year': sub.get('month_year') or my,
                            'month': sub.get('month') or mo,
                            'year': sub.get('year') or yr,
                            'case_id': '',
                            'state': state,
                            **({'source_url': sub['source_url']} if sub.get('source_url') else {}),
                        })
                if sub_cases:
                    cases.extend(sub_cases)
                    continue

            case_text = clean_artifacts_from_text(piece)
            month_year, month, case_date_year = _metadata_from_text(case_text)
            id_year = report_year if report_year else case_date_year
            single_case = {
                'case_text': case_text,
                'month_year': month_year,
                'month': month,
                'year': case_date_year,
                'case_id': f'{org_name}_{id_year}_000',
                'state': state,
            }
            source_url = _normalize_ncmec_source_url(piece)
            if source_url:
                single_case['source_url'] = source_url
            cases.append(single_case)

    id_yr = report_year
    if not id_yr and cases:
        id_yr = cases[0].get('year', '2024')
        if isinstance(id_yr, str) and len(id_yr) >= 4 and id_yr[:4].isdigit():
            id_yr = id_yr[:4]

    for idx, c in enumerate(cases, start=1):
        c['case_id'] = f"{org_name}_{id_yr}_{idx:03d}"

    return cases


def _batch_michigan_icac_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Split Michigan ICAC / Michigan State Police newsroom PDF into individual cases.
    
    Format (from Michigan ICAC.pdf):
    - Web-printed MSP Newsroom articles, each repeated 3 times with patterns like:
      "3/16/26, 2:36 PM Lake City Man Arrested for ..."
      followed by "1/3", "2/3", "3/3".
    
    Strategy (kept intentionally simple and robust):
    - Each case is the contiguous block of text from the first occurrence of
      "MSP Newsroom" to the ICAC/MissingKids footer line:
        "If you have information regarding possible child sexual exploitation, report it to the
         Cyber Tip Line at https://www.missingkids.org/cybertipline."
    - We find all such [start, end] spans and treat each as one case.
    - Year/month are extracted from the first date in the case (MM/DD/YY).
    """
    cases: List[Dict[str, Any]] = []
    
    # Define markers
    start_marker = "MSP Newsroom"
    # Footer phrase can vary in spacing/capitalization (e.g., "CyberTipLine", "Cyber tipline"),
    # and can use http/https with or without "www". The stable part is the path:
    #   missingkids.org/cybertipline
    # We therefore batch each article from "MSP Newsroom" to the *end of the first occurrence*
    # of this URL path after that header (case-insensitive).
    footer_core = "missingkids.org/cybertipline"
    lower_text = text.lower()
    
    # Find all case spans: from "MSP Newsroom" to first footer_core URL after it
    spans: List[Tuple[int, int]] = []
    pos = 0
    while True:
        start = text.find(start_marker, pos)
        if start == -1:
            break
        
        # Look for the footer URL after this header (case-insensitive)
        footer_index = lower_text.find(footer_core, start)
        if footer_index == -1:
            # No footer URL found after this header; treat the rest of the text as one span
            end = len(text)
        else:
            end = footer_index + len(footer_core)
        
        spans.append((start, end))
        pos = end
    
    if not spans:
        from datetime import datetime
        year = str(datetime.now().year)
        return [{
            'case_text': clean_artifacts_from_text(text),
            'month_year': None,
            'month': None,
            'year': year,
            'case_id': f'{org_name}_{year}_001'
        }]
    
    # Helper to map month number to name
    month_names = [
        None,
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    # Track case numbers per year
    year_case_counts: Dict[str, int] = {}
    
    # Regex to grab first date in MM/DD/YY format for month/year
    date_pattern = r'(\d{1,2})/(\d{1,2})/(\d{2})'
    
    for start_pos, end_pos in spans:
        case_text_raw = text[start_pos:end_pos].strip()
        case_text = clean_artifacts_from_text(case_text_raw)
        
        # Skip very short fragments
        if len(case_text) < 200:
            continue
        
        # Extract date from case text
        m = re.search(date_pattern, case_text)
        if m:
            mm, dd, yy = m.groups()
            year = f"20{yy}"
            month_num = int(mm)
        else:
            year = None
            month_num = None
        
        month = month_names[month_num] if month_num and 1 <= month_num <= 12 else None
        month_year = f"{month} {year}" if month else year
        
        # Case numbering per year
        if not year:
            from datetime import datetime
            year = str(datetime.now().year)
        
        if year not in year_case_counts:
            year_case_counts[year] = 0
        year_case_counts[year] += 1
        case_number = year_case_counts[year]
        
        case_id = f"{org_name}_{year}_{case_number:03d}"
        
        cases.append({
            'case_text': case_text,
            'month_year': month_year,
            'month': month,
            'year': year,
            'case_id': case_id
        })
    
    return cases


def _batch_ncmec_media_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Split NCMEC media cases (2022/2023 format) by title → text → link pattern.
    Each case starts with a title and ends with a URL link.
    Pattern: title → text → text → link
    
    Args:
        text: Full text from NCMEC PDF
        org_name: Organization name prefix for case IDs (e.g., "ncmec")
        source_file: Filename to extract report year from (e.g., "2022 NCMEC.pdf")
        
    Returns:
        List of case dictionaries with 'case_text', 'month_year', 'month', 'year', 'case_id'
    """
    # Extract report year from filename if available
    report_year = _ncmec_report_year(source_file)
    
    cases = []
    
    # Find all URLs (these mark the end of each case)
    # URLs can span multiple lines; each clip ends at a page marker line.
    url_pattern = _ncmec_media_url_pattern(report_year)
    url_matches = []
    for match in re.finditer(url_pattern, text):
        url_text = match.group(0)
        url_end_pos = match.end()
        
        url_matches.append({
            'pos': url_end_pos,
            'url': url_text
        })
    
    if not url_matches:
        # No URLs found - return entire text as one case
        from datetime import datetime
        year = report_year if report_year else str(datetime.now().year)
        return [{
            'case_text': clean_artifacts_from_text(text),
            'month_year': None,
            'month': None,
            'year': year,
            'case_id': f'{org_name}_{year}_001'
        }]
    
    # Track case numbers per year
    year_case_counts = {}
    
    # Process cases: each case is from previous URL end to current URL end
    # But skip the number marker between cases (newline → number → newline)
    for i, url_info in enumerate(url_matches):
        # Start of case: end of previous URL (or start of text for first case)
        if i == 0:
            start_pos = 0
        else:
            prev_url_end = url_matches[i - 1]['pos']
            start_pos = _ncmec_start_after_article_boundary(text, prev_url_end)
        
        # End of case: end of current URL
        end_pos = url_info['pos']
        
        case_text = text[start_pos:end_pos].strip()
        
        # Clean artifacts from case text before processing
        # Keep URLs for NCMEC media cases (they mark the end of each case)
        case_text = clean_artifacts_from_text(case_text, remove_urls=False)
        
        # Skip empty cases
        if not case_text or len(case_text) < 50:
            continue
        
        # Extract date from case text (for case metadata)
        months = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        date_pattern = rf'{months}\s+(\d{{1,2}}),?\s+(\d{{4}})'
        date_match = re.search(date_pattern, case_text, re.IGNORECASE)
        
        if date_match:
            month = date_match.group(1)
            day = date_match.group(2)
            case_date_year = date_match.group(3)
            month_year = f"{month} {case_date_year}"
        else:
            # Use report year from filename if available, otherwise try to extract from case text
            if report_year:
                case_date_year = report_year
                month = None
                month_year = case_date_year
            else:
                # Try to extract just year from case text (prefer 2022-2024 range)
                year_match = re.search(r'\b(202[234])\b', case_text)
                if year_match:
                    case_date_year = year_match.group(1)
                    month = None
                    month_year = case_date_year
                else:
                    # Fallback: use current year
                    from datetime import datetime
                    case_date_year = str(datetime.now().year)
                    month = None
                    month_year = case_date_year
        
        # Use report year for ID generation to ensure uniqueness across different report files
        # This prevents conflicts when cases from different report years have the same case date year
        id_year = report_year if report_year else case_date_year
        
        # Track case number per report year (for ID generation)
        if id_year not in year_case_counts:
            year_case_counts[id_year] = 0
        year_case_counts[id_year] += 1
        case_number = year_case_counts[id_year]
        
        # Generate case ID using report year: org_reportyear_number
        case_id = f"{org_name}_{id_year}_{case_number:03d}"
        
        # Use case_date_year for case metadata (not ID)
        year = case_date_year
        
        source_url = _normalize_ncmec_source_url(url_info['url'])
        
        case_entry = {
            'case_text': case_text,
            'month_year': month_year,
            'month': month,
            'year': year,
            'case_id': case_id
        }
        if source_url:
            case_entry['source_url'] = source_url
        cases.append(case_entry)
    
    # Handle last case: text after the last URL (if any)
    if url_matches:
        last_url_end = url_matches[-1]['pos']
        text_after_last_url = text[last_url_end:].strip()
        
        if text_after_last_url and len(text_after_last_url) >= 50:
            # This is a final case without a URL at the end
            case_text = clean_artifacts_from_text(text_after_last_url, remove_urls=False)
            
            # Extract date from case text
            months = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
            date_pattern = rf'{months}\s+(\d{{1,2}}),?\s+(\d{{4}})'
            date_match = re.search(date_pattern, case_text, re.IGNORECASE)
            
            if date_match:
                month = date_match.group(1)
                day = date_match.group(2)
                year = date_match.group(3)
                month_year = f"{month} {year}"
            else:
                # Use report year from filename if available
                if report_year:
                    year = report_year
                    month = None
                    month_year = year
                else:
                    # Try to extract just year from case text (prefer 2022-2024 range)
                    year_match = re.search(r'\b(202[234])\b', case_text)
                    if year_match:
                        year = year_match.group(1)
                        month = None
                        month_year = year
                    else:
                        # Fallback: use current year
                        from datetime import datetime
                        year = str(datetime.now().year)
                        month = None
                        month_year = year
            
            # Track case number per year
            if year not in year_case_counts:
                year_case_counts[year] = 0
            year_case_counts[year] += 1
            case_number = year_case_counts[year]
            
            # Generate case ID
            month_str = month.lower() if month else 'unknown'
            case_id = f"{org_name}_{year}_{month_str}_{case_number:03d}"
            
            cases.append({
                'case_text': case_text,
                'month_year': month_year,
                'month': month,
                'year': year,
                'case_id': case_id
            })
    
    return cases


_GBI_DATE_LINE_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2}),\s+(\d{4})\s*$",
    re.MULTILINE,
)
# Five hash marks with spaces (PDF extraction may vary spacing slightly)
_GBI_SECTION_SPLIT_RE = re.compile(r"#\s+#\s+#\s+#\s+#")
# First line starting here is site chrome after the press-release body (truncate before it)
_GBI_FOOTER_START_RE = re.compile(
    r"""
    (?P<cut>
        \nContact\sInformation:\s*\n
      | \nRelated\sFiles\s*\n
      | \nHow\s+can\s+we\s+help\?\s*\n
      | \nContact\s*\n\s*Assistant\s+Special\s+Agent\b
      | \nPrimary:\s*\(404\)\s*244-
      | \nOnline\s+Tip\s+Form\s*\n
      | \nSubmit\s+Tips\s+Online\s*\n
      | \nVisit\s*\n3121\s+Panthersville\s+Road
      | \nGeorgia\s+Bureau\s+of\s*\n\s*Investigation\s*\n\s*How\s+can\s+we\s+help
    )
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)


def _clean_gbi_case_text(text: str) -> str:
    """
    Keep press-release body only: drop GovHub footer, contact blocks, related-file links,
    and fix lines left empty when URLs are stripped from PDF extraction.
    """
    if not text:
        return text
    t = text.strip()
    m = _GBI_FOOTER_START_RE.search(t)
    if m:
        t = t[: m.start("cut")].rstrip()

    t = re.sub(r"\n(?:20\d{2}\s+Press\s+Releases\s*\n)+$", "", t, flags=re.IGNORECASE)

    # Drop the ICAC/GBI website line (URLs removed later would leave a hollow sentence)
    t = re.sub(
        r"^\s*The\s+Georgia\s+ICAC\s+Task\s+Force\s+website\s+is\s+.+$",
        "",
        t,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    t = clean_artifacts_from_text(t, remove_urls=True)

    # Hollow sentence if URL strip ran on partial text
    t = re.sub(
        r"^\s*The\s+Georgia\s+ICAC\s+Task\s+Force\s+website\s+is\s+and\s+the\s+GBI\s+website\s+is\s*$",
        "",
        t,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    # CyberTipline: domain-only line after "at" (URL patterns already stripped)
    t = re.sub(
        r"CyberTipline\s+at\s*\n\s*Cybertipline\.org\.\s*",
        "CyberTipline. ",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"CyberTipline\s+at\s*\n\s*Anonymous\s+tips",
        "CyberTipline. Anonymous tips",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\bCybertipline\.org\b\.?", "", t, flags=re.IGNORECASE)
    t = re.sub(
        r"online\s+at\s*\n\s*or\s+by\s+downloading",
        "or by downloading",
        t,
        flags=re.IGNORECASE,
    )

    t = re.sub(r"^\s*\S+@\S+\.[^\s]+\s*$", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*(?:Submit\s+Tips\s+Online|Visit)\s*$", "", t, flags=re.MULTILINE | re.IGNORECASE)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _batch_gbi_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Split GBI / CEACC press-release PDFs into individual cases.

    Most of the document uses blocks ending with "# # # # #", then contact/footer/navigation,
    then the next case starting with a standalone "Month DD, YYYY" line. The tail section may
    omit the hash row between releases; we then split on repeated standalone date lines.
    """
    cases: List[Dict[str, Any]] = []
    if not text or not text.strip():
        from datetime import datetime
        y = str(datetime.now().year)
        return [{"case_text": "", "month_year": None, "month": None, "year": y, "case_id": f"{org_name}_{y}_001"}]

    sections = _GBI_SECTION_SPLIT_RE.split(text)
    year_case_counts: Dict[str, int] = {}

    for section in sections:
        section = section.strip()
        if not section:
            continue

        date_matches = list(_GBI_DATE_LINE_RE.finditer(section))
        if not date_matches:
            continue

        for i, dm in enumerate(date_matches):
            start = dm.start()
            end = date_matches[i + 1].start() if i + 1 < len(date_matches) else len(section)
            case_text_raw = section[start:end].strip()
            if len(case_text_raw) < 80:
                continue

            month = dm.group(1)
            year = dm.group(3)
            month_year = f"{month} {year}"

            if year not in year_case_counts:
                year_case_counts[year] = 0
            year_case_counts[year] += 1
            case_number = year_case_counts[year]
            case_id = f"{org_name}_{year}_{case_number:03d}"

            case_text = _clean_gbi_case_text(case_text_raw)
            if len(case_text) < 50:
                continue

            cases.append(
                {
                    "case_text": case_text,
                    "month_year": month_year,
                    "month": month,
                    "year": year,
                    "case_id": case_id,
                }
            )

    if not cases:
        from datetime import datetime
        y = str(datetime.now().year)
        return [
            {
                "case_text": _clean_gbi_case_text(text),
                "month_year": None,
                "month": None,
                "year": y,
                "case_id": f"{org_name}_{y}_001",
            }
        ]

    return cases


# Merged ReportLab (or same-layout) news PDFs: one entry per ``Source: https://…`` line.
# Add a key + repo-relative paths for each new scrape; route ``source`` in ``case_batching``.
_MERGED_ICAC_NEWS_PDF_CANDIDATES: Dict[str, List[str]] = {
    "SVICAC": ["SVICAC_All.pdf", "svicac_output/SVICAC_All.pdf"],
    "TBI ICAC": ["TBI_ICAC_All.pdf", "TBI_ICAC_ALL.pdf"],
    "SCAG ICAC": ["SCAG_ICAC_All.pdf", "SCAG_ICAC_ALL.pdf"],
    "NEWYORK SP": ["NYSP_ICAC_All.pdf", "NEWYORK_SP_All.pdf", "newyork_sp/NEWYORK_SP_All.pdf"],
    "ILLINOIS AG": ["ILLNOISAG_ICAC_All.pdf", "ILLINOIS_AG_All.pdf", "illinois_ag/ILLINOIS_AG_All.pdf"],
    "WCSO": ["Washoe_ICAC_All.pdf", "wcso/Washoe_ICAC_All.pdf", "washoe/Washoe_ICAC_All.pdf"],
    "FRESNO SO": [
        "FRESNOSO_ICAC_All.pdf",
        "FRESNO_SO_ICAC_All.pdf",
        "fresno_so/FRESNOSO_ICAC_All.pdf",
    ],
    "OSCEOLA SO": [
        "OSCEOLASO_ICAC_All.pdf",
        "OSCEOLA_SO_ICAC_All.pdf",
        "osceola_so/OSCEOLASO_ICAC_All.pdf",
    ],
    "SEDGWICK SO": ["SEDGWICKSO_ICAC_All.pdf", "sedgwick_so/SEDGWICKSO_ICAC_All.pdf"],
    "ANCHORAGE PD": [
        "ANCHORAGEPD_ICAC_All.pdf",
        "anchorage_pd/ANCHORAGEPD_ICAC_All.pdf",
    ],
    "LAPD": ["LAPD_ICAC_ALL.pdf", "LAPD_ICAC_All.pdf", "lapd/LAPD_ICAC_All.pdf"],
    "CSPD": [
        "CSPD_ICAC_All.pdf",
        "COLORADO_SPRINGS_ICAC_All.pdf",
        "cspd/CSPD_ICAC_All.pdf",
    ],
    "SPD": [
        "SPD_Blotter_ICAC_All.pdf",
        "data/ingestion/spd_blotter/SPD_Blotter_ICAC_All.pdf",
    ],
    "SDPD": [
        "SDPD_ICAC_All.pdf",
        "data/ingestion/sdpd/SDPD_ICAC_All.pdf",
    ],
    "SOUTH FLORIDA ICAC": ["SouthFlorida_ICAC_All.pdf"],
    "NJ AG": ["NJAG_ICAC_All.pdf", "NJOAG_ICAC_All.pdf", "nj_ag/NJAG_ICAC_All.pdf"],
    "PA AG": ["PAAG_ICAC_All.pdf", "PA_AG_ICAC_All.pdf", "PAOAG_ICAC_All.pdf", "pa_ag/PAAG_ICAC_All.pdf"],
    "VT AG": ["VTAG_ICAC_All.pdf", "VTOAG_ICAC_All.pdf", "Vermont_ICAC_All.pdf", "vt_ag/VTAG_ICAC_All.pdf"],
    "OHIO AG": ["OHIOAG_ICAC_All.pdf", "Ohio_ICAC_All.pdf", "ohio_ag/OHIOAG_ICAC_All.pdf"],
    "DE AG": ["DEAG_ICAC_All.pdf", "Delaware_ICAC_All.pdf", "de_ag/DEAG_ICAC_All.pdf"],
    "UT AG": ["UTAG_ICAC_All.pdf", "UTOAG_ICAC_All.pdf", "Utah_ICAC_All.pdf", "ut_ag/UTAG_ICAC_All.pdf"],
    "WA AG": ["WAAG_ICAC_All.pdf", "Washington_AG_ICAC_All.pdf", "wa_ag/WAAG_ICAC_All.pdf"],
    "OREGON DOJ": [
        "OREGON_DOJ_ICAC_All.pdf",
        "OREGONDOJ_ICAC_All.pdf",
        "oregon_doj/OREGON_DOJ_ICAC_All.pdf",
    ],
    "MS AG": ["MSAG_ICAC_All.pdf", "Mississippi_ICAC_All.pdf", "ms_ag/MSAG_ICAC_All.pdf"],
    "MT DOJ": ["MTDOJ_ICAC_All.pdf", "data/ingestion/mt_doj/MTDOJ_ICAC_All.pdf"],
    "NM AG": ["NMAG_ICAC_All.pdf", "data/ingestion/nm_ag/NMAG_ICAC_All.pdf"],
    "NC SBI": ["NCSBI_ICAC_All.pdf", "NC_SBI_ICAC_All.pdf", "nc_sbi/NCSBI_ICAC_All.pdf"],
    "LA AG": ["LAAG_ICAC_All.pdf", "Louisiana_ICAC_All.pdf", "la_ag/LAAG_ICAC_All.pdf"],
    "HI AG": ["HIAG_ICAC_All.pdf", "Hawaii_ICAC_All.pdf", "hi_ag/HIAG_ICAC_All.pdf"],
    "CCSAO": ["CCSAO_ICAC_All.pdf", "Cook_County_SA_ICAC_All.pdf", "ccsao/CCSAO_ICAC_All.pdf"],
    "IA DCI": [
        "IADCI_ICAC_All.pdf",
        "IA_DCI_ICAC_All.pdf",
        "ia_dci/IADCI_ICAC_All.pdf",
    ],
    "WY DCI": ["WYDCI_ICAC_All.pdf", "WY_DCI_ICAC_All.pdf", "wy_dci/WYDCI_ICAC_All.pdf"],
    "SD AG": ["SDAG_ICAC_All.pdf", "South_Dakota_ICAC_All.pdf", "sd_ag/SDAG_ICAC_All.pdf"],
    "RI AG": [
        "RIAG_ICAC_All.pdf",
        "RI_AG_ICAC_All.pdf",
        "ri_ag/RIAG_ICAC_All.pdf",
    ],
    "FL AG": [
        "FLAG_ICAC_All.pdf",
        "FL_AG_ICAC_All.pdf",
        "fl_ag/FLAG_ICAC_All.pdf",
    ],
    "KY SP": ["KYSP_ICAC_All.pdf", "KSP_ICAC_All.pdf", "ky_sp/KYSP_ICAC_All.pdf"],
    "NE SP": [
        "NESP_ICAC_All.pdf",
        "NE_SP_ICAC_All.pdf",
        "ne_sp/NESP_ICAC_All.pdf",
    ],
    "ARMY CID": [
        "ARMYCID_ICAC_All.pdf",
        "ARMY_CID_ICAC_All.pdf",
        "army_cid/ARMYCID_ICAC_All.pdf",
    ],
    "USSS": [
        "USSS_ICAC_ALL.pdf",
        "USSS_ICAC_All.pdf",
        "USSS_ICAC_CSAM_All.pdf",
    ],
    "ICE": [
        "ICE_CHILD_ALL.pdf",
        "ICE_CHILD_All.pdf",
    ],
    "AF OSI": [
        "AF_OSI_CHILD_ALL.pdf",
        "AF_OSI_CHILD_All.pdf",
    ],
    "NCIS": [
        "NCIS_CHILD_ALL.pdf",
        "NCIS_CHILD_All.pdf",
    ],
    "CBP": [
        "CBP_CHILD_ALL.pdf",
        "CBP_CHILD_All.pdf",
    ],
    "US MARSHALS": [
        "USMS_CHILD_ALL.pdf",
        "USMS_CHILD_All.pdf",
    ],
    "LVMPD": [
        "LVMPD_ICAC_All.pdf",
        "lvmpd/LVMPD_ICAC_All.pdf",
    ],
    "SJPD": [
        "SJPD_ICAC_All.pdf",
        "sjpd/SJPD_ICAC_All.pdf",
    ],
    "ARKANSAS DPS": ["ARKDPS_ICAC_All.pdf", "arkansas_dps_output/ARKDPS_ICAC_All.pdf"],
    "ALEA": ["alea_icac_news.pdf", "data/ingestion/alea/alea_icac_news.pdf"],
    "DOJ CEOS": ["DOJ_CEOS_All.pdf", "doj_ceos_output/DOJ_CEOS_All.pdf"],
    "DOJ ARCHIVES": ["DOJ_ARCHIVES_All.pdf", "doj_archives_output/DOJ_ARCHIVES_All.pdf"],
}


def _merged_icac_news_pdf_search_paths(source_key: str, source_file: Optional[str]) -> List[Path]:
    """
    Repo-relative PDF paths to try for merged ``Source: https://`` scrapes (SVICAC, TBI ICAC, …).
    Order: primary corpus name, optional ingest filename basename, then alternates.
    """
    root = Path(__file__).resolve().parent.parent.parent
    rels = _MERGED_ICAC_NEWS_PDF_CANDIDATES.get(source_key, [])
    out: List[Path] = []
    if rels:
        out.append(root / rels[0])
    if source_file:
        p = root / Path(source_file).name
        if p not in out:
            out.append(p)
    for r in rels[1:]:
        rp = root / r
        if rp not in out:
            out.append(rp)
    return out


def _merged_news_text_before_source_line(chunk: str) -> str:
    """
    Headline / masthead block only: everything before the first ``Source: https://`` line.
    Avoids body text (and URL path segments) influencing the publication-year guess.
    """
    m = re.search(r"(?m)^\s*Source:\s*https?://", chunk)
    if m:
        return chunk[: m.start()].strip()
    return (chunk or "")[:8000].strip()


def _merged_news_text_after_source_line(chunk: str) -> str:
    """Body text after the ``Source: https://`` line (opening datelines often appear here)."""
    m = re.search(r"(?m)^\s*Source:\s*https?://\S+", chunk)
    if not m:
        return ""
    return chunk[m.end() :].strip()[:12000]


def _merged_news_year_from_source_url(url: str) -> Optional[str]:
    """Year from common CMS URL paths (e.g. ``/blog/2024/08/13/…``)."""
    if not url:
        return None
    for m in re.finditer(r"/((?:19|20)\d{2})/(?:\d{2}/(?:\d{2}(?:/|$))?)?", url):
        y = int(m.group(1))
        if 1990 <= y <= 2035:
            return str(y)
    return None


def _merged_news_default_year_from_source_file(source_file: Optional[str]) -> Optional[str]:
    """Optional corpus year from PDF filename (e.g. ``2024_NCMEC.pdf``)."""
    if not source_file:
        return None
    name = Path(source_file).name
    m = re.search(r"\b((?:19|20)\d{2})\b", name)
    return m.group(1) if m else None


_MERGED_NEWS_DATELINE_MONTH_DAY_YEAR_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+((?:19|20)\d{2})\b",
    re.I,
)
_MERGED_NEWS_DOB_LINE_HINT_RE = re.compile(
    r"date\s+of\s+birth|\bd\.?\s*o\.?\s*b\.?\s*:|\bborn\b|birthdate|birth\s+date",
    re.I,
)


def _merged_news_dateline_year(text: str) -> Optional[str]:
    """Month + day + year dateline (e.g. 'May 5, 2010') or CaseLinker ``Publication date: YYYY-MM-DD``."""
    if not text:
        return None
    head = text[:4000]
    iso_pub = re.search(
        r"(?i)publication\s+date:\s*((?:19|20)\d{2})-(\d{2})-(\d{2})\b",
        head,
    )
    if iso_pub:
        return iso_pub.group(1)
    for m in _MERGED_NEWS_DATELINE_MONTH_DAY_YEAR_RE.finditer(head):
        pre = head[max(0, m.start() - 120) : m.start()]
        if _MERGED_NEWS_DOB_LINE_HINT_RE.search(pre):
            continue
        return m.group(1)
    return None


# CEOS material under justice.gov/archives/criminal/... is a static-era corpus (~1990s–2008).
# Scraped PDFs sometimes pick up modern “updated” masthead dates; cap using URL path when possible.
_DOJ_ARCHIVES_MAX_PUBLICATION_YEAR = 2008


def _four_digit_years_in_string_bounded(s: str, y_min: int, y_max: int) -> List[int]:
    if not s:
        return []
    out: List[int] = []
    for m in re.finditer(r"\b((?:19|20)\d{2})\b", s):
        y = int(m.group(1))
        if y_min <= y <= y_max:
            out.append(y)
    return out


def _resolve_doj_archives_batch_year(url: str, dateline_year: str) -> str:
    """
    If masthead dateline exceeds the archive era, prefer a year embedded in the Source URL
    (common on justice.gov paths), else clamp to the archive ceiling.
    """
    cap = _DOJ_ARCHIVES_MAX_PUBLICATION_YEAR
    ds = str(dateline_year).strip() if dateline_year else ""
    if ds.isdigit() and int(ds) <= cap:
        return ds
    url_years = _four_digit_years_in_string_bounded(url or "", 1990, cap)
    if url_years:
        return str(max(url_years))
    if ds.isdigit():
        return str(cap)
    return str(cap)


_MERGED_NEWS_DATELINE_RE = re.compile(
    r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"\d{1,2},?\s+(?:19|20)\d{2}\s*$",
    re.I,
)
_MERGED_NEWS_DATELINE_WEEKDAY_RE = re.compile(
    r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"\d{1,2},?\s+(?:19|20)\d{2}\s*$",
    re.I,
)
_MERGED_NEWS_PUBLICATION_DATE_RE = re.compile(
    r"^\s*Publication\s+date:\s*\d{4}-\d{2}-\d{2}\s*$",
    re.I,
)
# ReportLab scrape_pdf titles: "Headline fragment — Agency Name" (Title Case, not ALL-CAPS).
_MERGED_NEWS_SCRAPE_MASTHEAD_SUFFIXES = (
    "police department",
    "sheriff",
    "attorney general",
    "department of justice",
    "u.s. attorney",
    "district attorney",
    "state bureau",
    "office of the",
    "bureau of investigation",
    "department of public safety",
)


def _merged_news_line_looks_like_scrape_masthead_title(line: str) -> bool:
    """Wrapped headline line ending with em-dash org masthead (Anchorage PD / scrape_pdf layout)."""
    s = line.strip()
    if len(s) < 20 or len(s) > 160:
        return False
    if not re.search(r"[—–]", s):
        return False
    low = s.lower()
    return any(m in low for m in _MERGED_NEWS_SCRAPE_MASTHEAD_SUFFIXES)


def _merged_news_line_looks_like_scrape_wrapped_title_lead(line: str, next_line: str) -> bool:
    """First line of a two-line Title Case headline when the next line carries the masthead."""
    s = line.strip()
    if not s or _merged_news_line_looks_like_scrape_masthead_title(line):
        return False
    if not _merged_news_line_looks_like_scrape_masthead_title(next_line):
        return False
    if len(s) < 12 or len(s) > 110:
        return False
    if s.endswith(".") or re.search(r"[—–]", s):
        return False
    if _merged_news_line_looks_like_dateline_above_source(s):
        return False
    if _merged_news_line_looks_like_narrative_body(s):
        return False
    if not re.match(r"^[A-Z0-9]", s):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 10:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    # Title Case wraps can be mostly lowercase (e.g. "Anchorage man arrested in Juneau, charged with …").
    if upper_ratio >= 0.58:
        return False
    return True


def _merged_news_hi_immediately_before_source(lines: List[str], si: int, prev_barrier: int) -> int:
    """
    Last non-empty line before ``Source:`` — skip ``Publication date:`` emitted by scrape_pdf.
    """
    hi = si - 1
    while hi > prev_barrier and not lines[hi].strip():
        hi -= 1
    while hi > prev_barrier and _MERGED_NEWS_PUBLICATION_DATE_RE.match(lines[hi].strip()):
        hi -= 1
        while hi > prev_barrier and not lines[hi].strip():
            hi -= 1
    return hi


def _merged_news_line_looks_like_dateline_above_source(line: str) -> bool:
    """Press-release date line directly above ``Source:`` (full month or weekday + full month)."""
    s = line.strip()
    if _MERGED_NEWS_DATELINE_RE.match(s) or _MERGED_NEWS_DATELINE_WEEKDAY_RE.match(s):
        return True
    return False


def _merged_news_line_looks_like_narrative_body(line: str) -> bool:
    """
    A line from the *previous* article's body (PDF wrap), not part of the headline block above ``Source:``.
    Used to bound the fallback upward scan so we do not pull ICAC boilerplate into the next case's title.
    """
    s = line.strip()
    if not s:
        return False
    if _merged_news_line_looks_like_scrape_masthead_title(s):
        return False
    # Wrapped continuation of a paragraph (line does not start with a digit; headline may be "19-year-old …").
    if not s[0].isdigit():
        for c in s:
            if c.isalpha():
                if c.islower() and len(s) > 12:
                    return True
                break
    if len(s) >= 118:
        return True
    nspaces = s.count(" ")
    if len(s) >= 88 and nspaces >= 14:
        return True
    if len(s) >= 72 and (s.endswith(".") or s.endswith(".’") or s.endswith(".'")) and nspaces >= 8:
        return True
    if len(s) >= 64 and ". " in s and nspaces >= 9:
        return True
    low = s.lower()
    if any(
        p in low
        for p in (
            "icac program",
            "cyber enticement",
            "child sexual abuse material",
            "internet crimes against children",
            "this support encompasses",
            "technical assistance, victim",
            "presumed innocent until proven guilty",
        )
    ):
        return True
    if low.startswith("*all persons") or low.startswith("all persons are presumed"):
        return True
    return False


def _merged_news_line_looks_like_headline(line: str) -> bool:
    """ALL-CAPS or near-ALL-CAPS lines used as press-release titles (e.g. Arkansas DPS)."""
    s = line.strip()
    if len(s) < 10:
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio >= 0.58


def _merged_news_is_likely_preface_before_date(line: str) -> bool:
    """
    Short org / masthead line immediately above the dateline (e.g. Illinois AG office line),
    not narrative body (which usually has an em dash city lead or starts with 'The ').
    """
    s = line.strip()
    if len(s) < 8 or len(s) > 140:
        return False
    if re.search(r"[—–]", s):
        return False
    low = s.lower()
    if low.startswith(("the ", "this ", "chicago ", "springfield ", "morrilton,", "viola,", "amity,", "alma,")):
        return False
    if re.search(r"\b(office of|department of|attorney general)\b", low):
        # News headlines often contain "Attorney General" (WA AG Title Case titles).
        # Only treat short org-name lines as preface, not "AG … sentenced / seeks / wins …".
        if len(s) > 70:
            return False
        if re.search(r"(?i)\b(media resource|faq)\b", s):
            return False
        if re.search(
            r"\b(sentenced|arrested|charged|wins?|seeks?|files?|announces?|"
            r"prevents?|obtains?|commits?|commitment|re-?commitment|prosecution|"
            r"conviction|predator|offender|guide)\b",
            low,
        ):
            return False
        return True
    return False


_MERGED_NEWS_CONTACT_BOILER_RE = re.compile(
    r"(?i)("
    r"contacts?:|"
    r"director of communications|"
    r"communications director|"
    r"deputy communications|"
    r"visit www\.|"
    r"learn more\.?$|"
    r"@atg\.|"
    r"\(\d{3}\)\s*\d{3}[-.]?\d{4}|"
    r"working hard to protect consumers|"
    r"chief legal office for the state|"
    r"media resource guide|"
    r"\bfaq\b"
    r")"
)


def _merged_news_line_is_contact_or_boilerplate(line: str) -> bool:
    """WA AG / similar press-release contact lines and closing blurbs above the next headline."""
    s = line.strip()
    if not s:
        return False
    return bool(_MERGED_NEWS_CONTACT_BOILER_RE.search(s))


def _merged_news_line_looks_like_title_case_headline(line: str) -> bool:
    """
    Mixed / sentence-case / Title Case press-release headline (e.g. WA AG), not ALL-CAPS body.
    First line usually starts with a capital (AG's… / Idaho man… / Opening statements…).
    """
    s = line.strip()
    if len(s) < 15 or len(s) > 140:
        return False
    if _merged_news_line_looks_like_dateline_above_source(s):
        return False
    if re.match(r"^\s*Source:\s*", s, re.I):
        return False
    if _merged_news_line_is_contact_or_boilerplate(s):
        return False
    if re.match(r"^[A-Z]{2,}(?:\s[A-Z]+)?\s*[—–-]", s):  # CITY -- lead
        return False
    # Stats / body sentences that start with a digit (e.g. "294 sexually violent…").
    if re.match(r"^\d", s) and not re.match(r"^\d{1,2}-year-old\b", s, re.I):
        return False
    if not re.match(r"^[A-Z0-9\"'“]", s):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 12:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    # ALL-CAPS handled elsewhere.
    if upper_ratio >= 0.58:
        return False
    # Full sentence body usually ends with a period.
    if s.endswith(".") and s.count(" ") >= 8:
        return False
    low = s.lower()
    if any(
        p in low
        for p in (
            "are civilly committed",
            "as of this month",
            "as of september",
            "as of late",
            "are in the state's",
        )
    ):
        return False
    return True


def _merged_news_line_looks_like_title_wrap(line: str) -> bool:
    """
    PDF-wrapped continuation of a headline (often starts lowercase or is a short
    trailing word), e.g. \"offender into community\" or \"case\" / \"Center\".
    """
    s = line.strip()
    if len(s) < 4 or len(s) > 110:
        return False
    if _merged_news_line_looks_like_dateline_above_source(s):
        return False
    if re.match(r"^\s*Source:\s*", s, re.I):
        return False
    if _merged_news_line_is_contact_or_boilerplate(s):
        return False
    if re.match(r"^[A-Z]{2,}(?:\s[A-Z]+)?\s*[—–-]", s):
        return False
    if not re.match(r"^[A-Za-z0-9\"'“]", s):
        return False
    if re.match(r"^\d", s) and not re.match(r"^\d{1,2}-year-old\b", s, re.I):
        return False
    # Short trailing fragment of a wrapped title ("case", "Center", "predator").
    if len(s) <= 40 and s.count(" ") <= 5 and not s.endswith("."):
        return True
    # Longer wrap line — reject heavy body-like wraps.
    if s.count(" ") > 14:
        return False
    if s.endswith(".") and s.count(" ") >= 6:
        return False
    if len(s) >= 118:
        return False
    return True


def _merge_merged_news_wrapped_source_url_lines(lines: List[str]) -> List[str]:
    """
    Join PDF line-wrap fragments that continue a ``Source: https://...`` URL on the next line
    (e.g. ``...targetin`` + ``g-online-child-exploitation/``).
    """
    out: List[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        out.append(ln)
        i += 1
        if not re.match(r"^\s*Source:\s*https?://", ln):
            continue
        while i < len(lines):
            raw = lines[i]
            nxt = raw.strip()
            if not nxt:
                break
            if re.match(r"^https?://", nxt) or re.match(r"^\s*Source:\s*", raw):
                break
            if len(nxt) > 140:
                break
            if not re.match(r"^[a-zA-Z0-9\-./_%?#&+=]+$", nxt):
                break
            out[-1] = out[-1].rstrip() + nxt
            i += 1
    return out


def _merged_news_title_starts(lines: List[str], sources: List[int]) -> List[int]:
    """
    For each ``Source: https://`` line, find the first line of that article (headline / masthead / date).
    Uses the dateline immediately above ``Source:`` and walks up for ALL-CAPS headlines and AG masthead lines.
    """
    title_starts: List[int] = []
    for idx, si in enumerate(sources):
        prev_barrier = sources[idx - 1] if idx > 0 else -1
        lo = prev_barrier + 1
        hi = _merged_news_hi_immediately_before_source(lines, si, prev_barrier)
        if hi <= prev_barrier:
            title_starts.append(max(0, lo))
            continue

        if _merged_news_line_looks_like_dateline_above_source(lines[hi]):
            title_start = hi
            t = hi - 1
            while t > prev_barrier and _merged_news_line_looks_like_headline(lines[t]):
                title_start = t
                t -= 1
            while t > prev_barrier and _merged_news_line_looks_like_scrape_masthead_title(lines[t]):
                title_start = t
                t -= 1
            if (
                t > prev_barrier
                and t + 1 <= hi
                and _merged_news_line_looks_like_scrape_wrapped_title_lead(lines[t], lines[t + 1])
            ):
                title_start = t
                t -= 1
            # Title Case headlines + PDF wraps (WA AG and similar): date ← wrap ← title ← contact.
            while t > prev_barrier and lines[t].strip() and _merged_news_line_looks_like_title_wrap(lines[t]):
                title_start = t
                t -= 1
            while (
                t > prev_barrier
                and lines[t].strip()
                and _merged_news_line_looks_like_title_case_headline(lines[t])
            ):
                title_start = t
                t -= 1
            while t > prev_barrier and _merged_news_is_likely_preface_before_date(lines[t]):
                title_start = t
                t -= 1
            title_starts.append(title_start)
            continue

        # No dateline above Source: — walk up from the last line before Source:, stopping at narrative body
        # (KY SP, TBI byline+headline, NCSBI/LA/PA titles). Avoids grabbing the prior article's wrapped body.
        title_start = hi
        t = hi - 1
        while t > prev_barrier:
            raw = lines[t]
            if not raw.strip():
                t -= 1
                continue
            if _merged_news_line_is_contact_or_boilerplate(raw):
                break
            if _merged_news_line_looks_like_narrative_body(raw):
                break
            title_start = t
            t -= 1
        title_starts.append(title_start)
    return title_starts


def _batch_merged_icac_news_cases(
    text: str, org_name: str, source_file: str = None, source_key: str = "SVICAC"
) -> List[Dict[str, Any]]:
    """
    Split merged ICAC news PDFs built like the SVICAC scrape: each article is
    headline (1–4 lines) → ``Source: https://…`` → body (any length).

    ``source_key`` selects which repo PDF filenames to try (see ``_MERGED_ICAC_NEWS_PDF_CANDIDATES``).
    """
    from datetime import datetime

    corpus = (text or "").strip()
    need_pdf = len(corpus) < 80 or not re.search(r"^\s*Source:\s*https?://", corpus, re.MULTILINE)
    if need_pdf:
        candidates = _merged_icac_news_pdf_search_paths(source_key, source_file)
        pdf_path = next((p for p in candidates if p.is_file()), None)
        if pdf_path is not None:
            try:
                import logging
                import pdfplumber

                logging.getLogger("pdfminer").setLevel(logging.ERROR)

                with pdfplumber.open(str(pdf_path)) as pdf:
                    corpus = "\n".join((p.extract_text() or "") for p in pdf.pages).strip()
            except Exception:
                pass

    # pdfplumber often puts "Source:" alone on one line and the URL on the next; merge so each
    # marker is one line (matches ~85 cases vs ~77 when split).
    corpus = re.sub(r"(?m)^(\s*Source:\s*)\n(\s*https?://\S+)", r"\1\2", corpus)

    lines = _merge_merged_news_wrapped_source_url_lines(corpus.splitlines())
    sources = [i for i, ln in enumerate(lines) if re.match(r"^\s*Source:\s*https?://", ln)]
    if not sources:
        year_fb = str(datetime.now().year)
        ct_fb = clean_artifacts_from_text(corpus.strip())
        if len(ct_fb) < 200 and corpus:
            ct_fb = clean_artifacts_from_text(corpus.strip(), remove_urls=False)
        return [
            {
                "case_text": ct_fb,
                "month_year": None,
                "month": None,
                "year": year_fb,
                "case_id": f"{org_name}_{year_fb}_001",
            }
        ]

    title_starts = _merged_news_title_starts(lines, sources)

    year_case_counts: Dict[str, int] = {}
    cases: List[Dict[str, Any]] = []

    for i in range(len(sources)):
        start = title_starts[i]
        end = title_starts[i + 1] if i + 1 < len(title_starts) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        case_text = clean_artifacts_from_text(chunk) if chunk else ""
        if not case_text.strip() and chunk:
            case_text = clean_artifacts_from_text(chunk, remove_urls=False)

        url = _extract_wrapped_url_from_source_line(lines, sources[i])
        pre_source = _merged_news_text_before_source_line(chunk)
        case_date_year = _merged_news_dateline_year(pre_source)
        if not case_date_year:
            case_date_year = _merged_news_dateline_year(_merged_news_text_after_source_line(chunk))
        if not case_date_year:
            case_date_year = _merged_news_default_year_from_source_file(source_file)
        if not case_date_year:
            case_date_year = _merged_news_year_from_source_url(url)
        if not case_date_year:
            case_date_year = str(datetime.now().year)

        if source_key == "DOJ ARCHIVES":
            case_date_year = _resolve_doj_archives_batch_year(url, case_date_year)

        year_case_counts.setdefault(case_date_year, 0)
        year_case_counts[case_date_year] += 1
        num = year_case_counts[case_date_year]
        case_id = f"{org_name}_{case_date_year}_{num:03d}"

        cases.append(
            {
                "case_text": case_text,
                "month_year": case_date_year,
                "month": None,
                "year": case_date_year,
                "case_id": case_id,
                "source_url": url,
            }
        )

    if not cases:
        year_fb = str(datetime.now().year)
        ct_fb = clean_artifacts_from_text(corpus.strip())
        if len(ct_fb) < 200 and corpus:
            ct_fb = clean_artifacts_from_text(corpus.strip(), remove_urls=False)
        return [
            {
                "case_text": ct_fb,
                "month_year": None,
                "month": None,
                "year": year_fb,
                "case_id": f"{org_name}_{year_fb}_001",
            }
        ]
    return cases


def _batch_svicac_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """Backward-compatible name; same as ``_batch_merged_icac_news_cases(..., \"SVICAC\")``."""
    return _batch_merged_icac_news_cases(text, org_name, source_file, "SVICAC")


def _batch_idaho_icac_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Split Idaho ICAC cases by navigation button pattern.
    
    Format: Each case ends with "« NEXT" or "PREVIOUS" or "« PREVIOUS" followed by navigation.
    Cases start with "Newsroom" or have "CATEGORY: ICAC" header.
    Year is extracted from date within each case (e.g., "March 11, 2026").
    
    Args:
        text: Full text from Idaho ICAC PDF
        org_name: Organization name prefix for case IDs (e.g., "idaho_icac")
        source_file: Filename (not used for year extraction, year comes from case text)
        
    Returns:
        List of case dictionaries with 'case_text', 'month_year', 'month', 'year', 'case_id'
    """
    cases = []
    
    # Pattern to find case end markers: « NEXT, PREVIOUS », « PREVIOUS, etc.
    # These mark the end of case content (before navigation/footer)
    case_end_pattern = r'«\s*(?:NEXT|PREVIOUS)|(?:NEXT|PREVIOUS)\s*»'
    end_matches = list(re.finditer(case_end_pattern, text, re.IGNORECASE))
    
    if not end_matches:
        # No end markers found - return entire text as one case
        from datetime import datetime
        year = str(datetime.now().year)
        return [{
            'case_text': clean_artifacts_from_text(text),
            'month_year': None,
            'month': None,
            'year': year,
            'case_id': f'{org_name}_{year}_001'
        }]
    
    # Track case numbers per year
    year_case_counts = {}
    
    # Process cases: each case is from previous end marker to current end marker
    # But we need to find the actual start of each case (skip navigation/footer)
    for i, end_match in enumerate(end_matches):
        # Find the start of this case
        # Look backwards from end marker to find where case content starts
        # Case starts after navigation/footer from previous case, or at beginning of text
        
        if i == 0:
            # First case: start from beginning
            case_start = 0
        else:
            # Find start by looking backwards from end marker
            # Look for "Newsroom" or "CATEGORY: ICAC" pattern before the end marker
            search_start = end_matches[i-1].end() if i > 0 else 0
            search_end = end_match.start()
            search_text = text[search_start:search_end]
            
            # Find case start markers
            case_start_pattern = r'(?:Newsroom|CATEGORY:\s*ICAC)'
            start_match = re.search(case_start_pattern, search_text, re.IGNORECASE)
            
            if start_match:
                # Case starts at the marker
                case_start = search_start + start_match.start()
            else:
                # Fallback: start after previous end marker + some buffer
                case_start = end_matches[i-1].end() if i > 0 else 0
                # Skip navigation/footer (usually ~200-300 chars)
                # Look for first substantial content
                buffer_text = text[case_start:case_start+500]
                # Find first line that looks like content (not navigation)
                lines = buffer_text.split('\n')
                for j, line in enumerate(lines):
                    if len(line.strip()) > 20 and 'Newsroom' not in line and 'PREVIOUS' not in line and 'NEXT' not in line:
                        # Found content start
                        case_start += sum(len(l) + 1 for l in lines[:j])
                        break
        
        # Case end is at the end marker
        case_end = end_match.start()
        
        # Extract case text
        case_text_raw = text[case_start:case_end].strip()
        
        # Clean artifacts
        case_text = clean_artifacts_from_text(case_text_raw)
        
        # Skip if too short (likely navigation/footer, not a real case)
        if len(case_text) < 200:
            continue
        
        # Extract date from case text (e.g., "March 11, 2026")
        months = r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        date_pattern = rf'{months}\s+(\d{{1,2}}),?\s+(\d{{4}})'
        date_match = re.search(date_pattern, case_text, re.IGNORECASE)
        
        if date_match:
            month = date_match.group(1)
            day = date_match.group(2)
            case_date_year = date_match.group(3)
            month_year = f"{month} {case_date_year}"
        else:
            # Try to extract just year from case text
            year_match = re.search(r'\b(20\d{2})\b', case_text)
            if year_match:
                case_date_year = year_match.group(1)
                month = None
                month_year = case_date_year
            else:
                # Fallback: use current year
                from datetime import datetime
                case_date_year = str(datetime.now().year)
                month = None
                month_year = case_date_year
        
        # Track case number per year
        if case_date_year not in year_case_counts:
            year_case_counts[case_date_year] = 0
        year_case_counts[case_date_year] += 1
        case_number = year_case_counts[case_date_year]
        
        # Generate case ID: idaho_icac_2026_001
        case_id = f"{org_name}_{case_date_year}_{case_number:03d}"
        
        cases.append({
            'case_text': case_text,
            'month_year': month_year,
            'month': month,
            'year': case_date_year,
            'case_id': case_id
        })
    
    return cases


_TX_DATE_LINE_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2}),\s+(\d{4})\s+\|.*$",
    re.MULTILINE,
)
_TX_BACK_TO_TOP_RE = re.compile(r"\bBack\s+to\s+Top\b", re.IGNORECASE)


def _batch_texas_ag_cases(text: str, org_name: str, source_file: str = None) -> List[Dict[str, Any]]:
    """
    Split Texas AG CEU press-release corpus into individual cases.

    Primary strategy:
    - Case start: standalone date line, e.g. "April 20, 2018 | Cyber Crimes ..."
    - Case end: next date line OR end of text
    - Optional trim at first "Back to Top" marker inside each case

    This supports both:
    - A merged Texas PDF (many releases in one file)
    - A single release PDF (one date line -> one case)
    """
    cases: List[Dict[str, Any]] = []
    if not text or not text.strip():
        from datetime import datetime
        y = str(datetime.now().year)
        return [{"case_text": "", "month_year": None, "month": None, "year": y, "case_id": f"{org_name}_{y}_001"}]

    starts = list(_TX_DATE_LINE_RE.finditer(text))
    if not starts:
        # Fallback: split on Back-to-Top if date-lines fail in extraction.
        chunks = re.split(r"\bBack\s+to\s+Top\b", text, flags=re.IGNORECASE)
        year_case_counts: Dict[str, int] = {}
        for chunk in chunks:
            chunk = clean_artifacts_from_text(chunk)
            if len(chunk) < 180:
                continue
            dm = re.search(
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
                r"(\d{1,2}),\s+(\d{4})",
                chunk,
                re.IGNORECASE,
            )
            if dm:
                month = dm.group(1)
                year = dm.group(3)
            else:
                from datetime import datetime
                month = None
                year = str(datetime.now().year)
            if year not in year_case_counts:
                year_case_counts[year] = 0
            year_case_counts[year] += 1
            case_id = f"{org_name}_{year}_{year_case_counts[year]:03d}"
            cases.append(
                {
                    "case_text": chunk,
                    "month_year": f"{month} {year}" if month else year,
                    "month": month,
                    "year": year,
                    "case_id": case_id,
                }
            )
        return cases if cases else _batch_azicac_cases(text, org_name)

    year_case_counts: Dict[str, int] = {}
    for i, dm in enumerate(starts):
        start = dm.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        case_text = text[start:end].strip()

        cut = _TX_BACK_TO_TOP_RE.search(case_text)
        if cut:
            case_text = case_text[: cut.start()].rstrip()

        case_text = clean_artifacts_from_text(case_text)
        if len(case_text) < 180:
            continue

        month = dm.group(1)
        year = dm.group(3)
        if year not in year_case_counts:
            year_case_counts[year] = 0
        year_case_counts[year] += 1
        case_id = f"{org_name}_{year}_{year_case_counts[year]:03d}"

        cases.append(
            {
                "case_text": case_text,
                "month_year": f"{month} {year}",
                "month": month,
                "year": year,
                "case_id": case_id,
            }
        )

    return cases
