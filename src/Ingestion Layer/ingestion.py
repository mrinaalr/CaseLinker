"""
Ingestion Layer

Purpose: Handle diverse, messy data sources and normalize them into a consistent format for processing.

Design Ideas from Architecture:
- Keep it very simple: parse file (start with text-based), simple pre-processing
- Nothing too fancy - just take the info from the source to the data processing layer
- Data validation & sanitization
- Basic cleaning, pandas-based
- Modular so can upload website/pdf
"""

import importlib.util
import pandas as pd
from pathlib import Path

_EXTERNAL_PDF_NAME = "external.pdf"

_suc_path = Path(__file__).resolve().parents[1] / "Processing Layer" / "source_url_continuations.py"
_suc_spec = importlib.util.spec_from_file_location("source_url_continuations", _suc_path)
_suc_mod = importlib.util.module_from_spec(_suc_spec)
_suc_spec.loader.exec_module(_suc_mod)
try_append_source_url_continuation = _suc_mod.try_append_source_url_continuation
consume_same_line_slug_after_url = _suc_mod.consume_same_line_slug_after_url

_provenance_path = Path(__file__).resolve().parents[1] / "Storage Layer" / "provenance.py"
_provenance_spec = importlib.util.spec_from_file_location("caselinker_provenance", _provenance_path)
_provenance_mod = importlib.util.module_from_spec(_provenance_spec)
_provenance_spec.loader.exec_module(_provenance_mod)

from typing import Dict, List, Any, Optional
import warnings
import logging
import re
from functools import lru_cache

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
    logging.getLogger("pdfplumber").setLevel(logging.ERROR)
    # pdfplumber → pdfminer: suppress FontBBox / font descriptor noise on malformed PDFs
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", category=UserWarning)
except ImportError:
    PDFPLUMBER_AVAILABLE = False


def _load_provenance_records(path: Path) -> List[Dict[str, Any]]:
    """Load an optional scraper sidecar; legacy PDFs deliberately return an empty list."""
    try:
        return _provenance_mod.load_capture_manifest(path)
    except (OSError, TypeError, ValueError) as exc:
        warnings.warn(f"Ignoring invalid provenance sidecar for {path.name}: {exc}")
        return []


def detect_source_from_content(text: str, filename: str) -> str:
    """
    Detect source organization from file content and filename.
    Checks for NCMEC patterns (CT numbers, state headers) and AZICAC patterns.
    
    Args:
        text: Extracted text content
        filename: Name of the file
        
    Returns:
        Source organization name ('NCMEC', 'AZICAC', 'Idaho ICAC', 'Michigan ICAC', 'GBI', 'Texas AG', 'SVICAC',
        'TBI ICAC', 'SCAG ICAC', 'WCSO', 'FRESNO SO', 'OSCEOLA SO', 'ANCHORAGE PD', 'SEDGWICK SO', 'LAPD', 'CSPD', 'SPD', 'SDPD', 'SOUTH FLORIDA ICAC', 'NJ AG', 'PA AG', 'VT AG', 'OHIO AG', 'DE AG', 'UT AG',
        'WA AG', 'OREGON DOJ', 'MS AG', 'MT DOJ', 'NM AG', 'NC SBI', 'LA AG', 'HI AG', 'CCSAO', 'IA DCI', 'WY DCI', 'SD AG', 'RI AG', 'FL AG', 'KY SP', 'NE SP', 'ARMY CID', 'USSS', 'ICE', 'LVMPD', 'SJPD', 'ALEA', 'FBI', 'Other', or defaults to Other).
    """
    text_sample = text[:5000]  # Check first 5000 chars for efficiency
    filename_lower = filename.lower()
    
    # Default mixed-scrape PDF: canonical name → source Other (Case 1 : … batching)
    if Path(filename).name.lower() == _EXTERNAL_PDF_NAME:
        return "Other"

    # Check filename first
    if 'ncmec' in filename_lower or 'cybertipline' in filename_lower or 'cyber-tipline' in filename_lower:
        return 'NCMEC'
    elif 'gbi' in filename_lower:
        return 'GBI'
    elif 'texas' in filename_lower:
        return 'Texas AG'
    elif 'azicac' in filename_lower:
        return 'AZICAC'
    elif 'idaho' in filename_lower and 'icac' in filename_lower:
        return 'Idaho ICAC'
    elif 'michigan' in filename_lower and 'icac' in filename_lower:
        return 'Michigan ICAC'
    elif 'svicac' in filename_lower:
        return 'SVICAC'
    elif 'tbi' in filename_lower and 'icac' in filename_lower:
        return 'TBI ICAC'
    elif 'scag' in filename_lower and 'icac' in filename_lower:
        return 'SCAG ICAC'
    elif 'nysp' in filename_lower and 'icac' in filename_lower:
        return 'NEWYORK SP'
    elif ('illinois' in filename_lower or 'illnois' in filename_lower) and 'icac' in filename_lower:
        return 'ILLINOIS AG'
    elif 'wcso' in filename_lower:
        return 'WCSO'
    elif 'washoe' in filename_lower and 'icac' in filename_lower:
        return 'WCSO'
    elif ('fresnoso' in filename_lower or 'fresno_so' in filename_lower or 'fresno' in filename_lower) and 'icac' in filename_lower:
        return 'FRESNO SO'
    elif (
        ('osceolaso' in filename_lower or 'osceola_so' in filename_lower or 'osceola' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'OSCEOLA SO'
    elif (
        ('sedgwickso' in filename_lower or 'sedgwick_so' in filename_lower or 'sedgwick' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'SEDGWICK SO'
    elif ('anchoragepd' in filename_lower or 'anchorage_pd' in filename_lower) and 'icac' in filename_lower:
        return 'ANCHORAGE PD'
    elif 'lapd' in filename_lower:
        return 'LAPD'
    elif ('cspd' in filename_lower or 'colorado_springs' in filename_lower) and 'icac' in filename_lower:
        return 'CSPD'
    elif ('spd_blotter' in filename_lower or 'spd blotter' in filename_lower) and 'icac' in filename_lower:
        return 'SPD'
    elif (
        ('sdpd' in filename_lower or 'sandiego' in filename_lower or 'san_diego' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'SDPD'
    elif 'southflorida' in filename_lower and 'icac' in filename_lower:
        return 'SOUTH FLORIDA ICAC'
    elif ('njoag' in filename_lower or 'njag' in filename_lower) and 'icac' in filename_lower:
        return 'NJ AG'
    elif (
        ('paag' in filename_lower or 'pa_ag' in filename_lower or 'paoag' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'PA AG'
    elif 'pennsylvania' in filename_lower and 'icac' in filename_lower:
        return 'PA AG'
    elif (
        ('vtag' in filename_lower or 'vt_ag' in filename_lower or 'vtoag' in filename_lower or 'vermont' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'VT AG'
    elif ('ohioag' in filename_lower or 'ohio_ag' in filename_lower) and 'icac' in filename_lower:
        return 'OHIO AG'
    elif (
        ('deag' in filename_lower or 'de_ag' in filename_lower or 'delaware' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'DE AG'
    elif ('utag' in filename_lower or 'ut_ag' in filename_lower or 'utoag' in filename_lower) and 'icac' in filename_lower:
        return 'UT AG'
    elif (
        ('waag' in filename_lower or 'wa_ag' in filename_lower or 'wa_oag' in filename_lower or 'washington_atg' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'WA AG'
    elif (
        ('oregondoj' in filename_lower or 'oregon_doj' in filename_lower or 'or_doj' in filename_lower)
        or ('oregon' in filename_lower and 'doj' in filename_lower and 'icac' in filename_lower)
    ) and 'icac' in filename_lower:
        return 'OREGON DOJ'
    elif ('msag' in filename_lower or 'ms_ag' in filename_lower or 'mississippi' in filename_lower) and 'icac' in filename_lower:
        return 'MS AG'
    elif ('mtdoj' in filename_lower or 'mt_doj' in filename_lower or 'dojmt' in filename_lower) and 'icac' in filename_lower:
        return 'MT DOJ'
    elif ('nmag' in filename_lower or 'nm_ag' in filename_lower or 'nmdoj' in filename_lower) and 'icac' in filename_lower:
        return 'NM AG'
    elif ('ncsbi' in filename_lower or 'nc_sbi' in filename_lower) and 'icac' in filename_lower:
        return 'NC SBI'
    elif ('laag' in filename_lower or 'la_ag' in filename_lower or 'louisiana_ag' in filename_lower) and 'icac' in filename_lower:
        return 'LA AG'
    elif (
        ('hiag' in filename_lower or 'hi_ag' in filename_lower or 'hioag' in filename_lower or 'hawaii' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'HI AG'
    elif (
        ('ccsao' in filename_lower or 'cook_county' in filename_lower or 'cookcounty' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'CCSAO'
    elif ('wydci' in filename_lower or 'wy_dci' in filename_lower or 'wyoming_dci' in filename_lower) and 'icac' in filename_lower:
        return 'WY DCI'
    elif ('iadci' in filename_lower or 'ia_dci' in filename_lower or 'iowa_dci' in filename_lower) and 'icac' in filename_lower:
        return 'IA DCI'
    elif ('sdag' in filename_lower or 'sd_ag' in filename_lower or 'south_dakota' in filename_lower) and 'icac' in filename_lower:
        return 'SD AG'
    elif ('riag' in filename_lower or 'ri_ag' in filename_lower or 'rhode_island' in filename_lower) and 'icac' in filename_lower:
        return 'RI AG'
    elif (
        ('flag' in filename_lower or 'fl_ag' in filename_lower or 'florida_ag' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'FL AG'
    elif ('kysp' in filename_lower or 'ksp_icac' in filename_lower or 'kentucky_sp' in filename_lower) and 'icac' in filename_lower:
        return 'KY SP'
    elif (
        ('nesp' in filename_lower or 'ne_sp' in filename_lower or 'nebraska_sp' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'NE SP'
    elif (
        ('armycid' in filename_lower or 'army_cid' in filename_lower or 'cid_army' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'ARMY CID'
    elif (
        ('usss' in filename_lower or 'uss_icac' in filename_lower or 'secret_service' in filename_lower)
        and 'icac' in filename_lower
    ):
        return 'USSS'
    elif 'ice_child' in filename_lower or (
        'ice' in filename_lower and 'child' in filename_lower
    ):
        return 'ICE'
    elif 'af_osi' in filename_lower or (
        'osi' in filename_lower and 'child' in filename_lower
    ):
        return 'AF OSI'
    elif 'ncis' in filename_lower and 'child' in filename_lower:
        return 'NCIS'
    elif 'cbp' in filename_lower and 'child' in filename_lower:
        return 'CBP'
    elif 'usms' in filename_lower or (
        'marshals' in filename_lower and 'child' in filename_lower
    ):
        return 'US MARSHALS'
    elif ('lvmpd' in filename_lower or 'las_vegas_metro' in filename_lower) and 'icac' in filename_lower:
        return 'LVMPD'
    elif ('sjpd' in filename_lower or 'san_jose' in filename_lower) and 'icac' in filename_lower:
        return 'SJPD'
    elif ('arkdps' in filename_lower or 'arkansas_dps' in filename_lower or 'arkansas_dps_icac' in filename_lower) and 'icac' in filename_lower:
        return 'ARKANSAS DPS'
    elif 'alea' in filename_lower and 'icac' in filename_lower:
        return 'ALEA'
    elif 'doj_ceos' in filename_lower or ('doj' in filename_lower and 'ceos' in filename_lower):
        return 'DOJ CEOS'
    elif 'doj_archives' in filename_lower or ('doj' in filename_lower and 'archive' in filename_lower):
        return 'DOJ ARCHIVES'
    elif 'fbi' in filename_lower:
        return 'FBI'

    # Washoe County Sheriff site / newsroom ICAC scrape (merged PDF)
    if re.search(r'washoesheriff\.com', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children', text_sample, re.I
    ):
        return 'WCSO'

    # Fresno County Sheriff-Coroner's Office media releases (merged ICAC search PDF)
    if re.search(r'\bfresnosheriff\.org\b', text_sample, re.I) and re.search(
        r'Fresno County Sheriff|Central California Internet Crimes Against Children|\bICAC\b|'
        r'Internet Crimes Against Children|child (?:sexual abuse material|pornography)|\bCSAM\b',
        text_sample,
        re.I,
    ):
        return 'FRESNO SO'

    # Osceola County Sheriff's Office site search (merged ICAC news PDF)
    if re.search(r'\bosceolasheriff\.org\b', text_sample, re.I) and re.search(
        r'Osceola County Sheriff|Internet Crimes Against Children|\bICAC\b|'
        r'child (?:sexual abuse material|pornography)|\bCSAM\b',
        text_sample,
        re.I,
    ):
        return 'OSCEOLA SO'

    # LAPD Online site search (merged ICAC news PDF)
    if re.search(r'lapdonline\.org', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children', text_sample, re.I
    ):
        return 'LAPD'

    # Colorado Springs Police Department — city site search (merged ICAC news PDF)
    if re.search(r'coloradosprings\.gov', text_sample, re.I) and re.search(
        r'Colorado\s+Springs\s+Police|\bCSPD\b|Internet\s+Crimes\s+Against\s+Children|\bICAC\b|'
        r'Colorado\s+(?:Springs\s+)?ICAC|City\s+of\s+Colorado\s+Springs',
        text_sample,
        re.I,
    ):
        return 'CSPD'

    # Seattle Police Department — SPD Blotter (WordPress; merged ICAC search PDF)
    if re.search(r'spdblotter\.seattle\.gov', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children|Washington State ICAC|WA\s+ICAC', text_sample, re.I
    ):
        return 'SPD'

    # San Diego Police Department — city site search / SDICAC press PDFs
    if re.search(r'sandiego\.gov', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children|San Diego (?:Internet Crimes|ICAC)', text_sample, re.I
    ):
        return 'SDPD'

    # South Florida ICAC news index (merged external-article PDF)
    if re.search(r'southfloridaicac\.org', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children', text_sample, re.I
    ):
        return 'SOUTH FLORIDA ICAC'

    # New Jersey Office of Attorney General site search / press (merged ICAC news PDF)
    if re.search(r'njoag\.gov', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children', text_sample, re.I
    ):
        return 'NJ AG'

    # Vermont Attorney General (ago.vermont.gov — site search / press; merged ICAC news PDF)
    if re.search(r'ago\.vermont\.gov', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children|Child Predator|child exploitation',
        text_sample,
        re.I,
    ):
        return 'VT AG'

    # Ohio Attorney General (ohioattorneygeneral.gov — news releases; merged ICAC news PDF)
    if re.search(r'ohioattorneygeneral\.gov', text_sample, re.I) and re.search(
        r'Attorney General|Internet Crimes|\bICAC\b|Human Trafficking|child pornography|Child Predator|exploitation',
        text_sample,
        re.I,
    ):
        return 'OHIO AG'

    # Delaware Department of Justice (attorneygeneral.delaware.gov — press; merged ICAC news PDF)
    if re.search(r'attorneygeneral\.delaware\.gov', text_sample, re.I) and re.search(
        r'Delaware Department of Justice|Attorney General|Child Predator|Internet Crimes|\bICAC\b|'
        r'child pornography|child exploitation|child solicitation',
        text_sample,
        re.I,
    ):
        return 'DE AG'

    # Anchorage Police Department news (merged ReportLab scrape; AK ICAC task force host agency).
    if re.search(r'anchoragepolice\.com', text_sample, re.I) and re.search(
        r'Anchorage\s+Police|District\s+(?:Attorney|of\s+Alaska)|Anchorage\b|Federal\s+Bureau\s+of\s+Investigation|Internet\s+Crimes|\bICAC\b|\bminor\b|\bCSAM\b|'
        r'child\s+porn(?:ography)?|child\s+sex|child\s+exploitation|sex\s+trafficking|sexual\s+abuse\s+of\s+a\s+minor',
        text_sample,
        re.I,
    ):
        return 'ANCHORAGE PD'

    # Sedgwick County District Attorney criminal media releases (merged scrape; source key SEDGWICK SO for KS TF).
    if re.search(r'sedgwickcounty\.org', text_sample, re.I) and re.search(
        r'District Attorney|Sedgwick County|Criminal Division|Media Releases|FOR IMMEDIATE RELEASE',
        text_sample,
        re.I,
    ):
        return 'SEDGWICK SO'

    # Utah Attorney General (attorneygeneral.utah.gov — WordPress search / press; merged ICAC news PDF)
    if re.search(r'attorneygeneral\.utah\.gov', text_sample, re.I) and re.search(
        r'\bICAC\b|Internet Crimes Against Children|Attorney General|child exploitation|Child Predator',
        text_sample,
        re.I,
    ):
        return 'UT AG'

    # Washington State Office of the Attorney General (atg.wa.gov — news search; merged ICAC news PDF)
    if re.search(r'atg\.wa\.gov', text_sample, re.I) and re.search(
        r'Washington\s+State|Office\s+of\s+the\s+Attorney\s+General|Attorney\s+General|'
        r'\bICAC\b|Internet\s+Crimes\s+Against\s+Children|child\s+porn|Child\s+Predator|'
        r'child\s+exploitation|CSAM|sexual\s+abuse\s+material',
        text_sample,
        re.I,
    ):
        return 'WA AG'

    # Oregon Department of Justice (doj.state.or.us — site search / media; merged ICAC news PDF)
    if re.search(r'\bdoj\.state\.or\.us\b', text_sample, re.I) and re.search(
        r'Oregon\s+Department\s+of\s+Justice|Attorney\s+General|Internet\s+Crimes\s+Against\s+Children|\bICAC\b|'
        r'child\s+sexual|child\s+exploitation|CSAM|child\s+abuse\s+material',
        text_sample,
        re.I,
    ):
        return 'OREGON DOJ'

    # Mississippi Attorney General (attorneygenerallynnfitch.com — press; merged ICAC news PDF)
    if re.search(r'attorneygenerallynnfitch\.com', text_sample, re.I) and re.search(
        r'Attorney General|Lynn Fitch|child exploitation|Child Exploitation|Internet Crimes|\bICAC\b',
        text_sample,
        re.I,
    ):
        return 'MS AG'

    # Montana Department of Justice (dojmt.gov — press releases; merged ICAC news PDF)
    if re.search(r'\bdojmt\.gov\b', text_sample, re.I) and re.search(
        r'Montana Department of Justice|Attorney General|Knudsen|\bHELENA\b|Division of Criminal Investigation|\bDCI\b|'
        r'Internet Crimes Against Children|\bICAC\b|sexual abuse of children|CSAM|child exploitation|child assault',
        text_sample,
        re.I,
    ):
        return 'MT DOJ'

    # New Mexico Department of Justice / Attorney General (nmdoj.gov — press releases; merged ICAC news PDF)
    if re.search(r'\bnmdoj\.gov\b', text_sample, re.I) and re.search(
        r'New Mexico Department of Justice|\bNMDOJ\b|Attorney General|Internet Crimes Against Children|\bICAC\b|'
        r'child exploitation|Child Predator|CSAM|child pornography|sexual abuse material',
        text_sample,
        re.I,
    ):
        return 'NM AG'

    # North Carolina State Bureau of Investigation (ncsbi.gov — news releases; merged ICAC news PDF)
    if re.search(r'ncsbi\.gov', text_sample, re.I) and re.search(
        r'State Bureau of Investigation|\bSBI\b|Internet Crimes Against Children|\bICAC\b|child exploitation|Child Exploitation',
        text_sample,
        re.I,
    ):
        return 'NC SBI'

    # Louisiana Office of the Attorney General (ag.state.la.us — news; merged ICAC news PDF)
    if re.search(r'ag\.state\.la\.us', text_sample, re.I) and re.search(
        r'Louisiana Bureau of Investigation|\bLBI\b|Attorney General|Murrill|child|Child Sexual|exploitation|ICAC|Cyber Crimes',
        text_sample,
        re.I,
    ):
        return 'LA AG'

    # Hawaii Department of the Attorney General (ag.hawaii.gov / HICAC — press; merged ICAC news PDF)
    if re.search(r'ag\.hawaii\.gov', text_sample, re.I) and re.search(
        r'Hawaii.*Attorney General|Department of the Attorney General|\bHICAC\b|'
        r'Internet Crimes Against Children|\bICAC\b|Operation Keiki Shield|child exploitation|child pornography',
        text_sample,
        re.I,
    ):
        return 'HI AG'

    # Cook County State's Attorney (cookcountystatesattorney.org — ICAC unit press; merged news PDF)
    if re.search(r'cookcountystatesattorney\.org', text_sample, re.I) and re.search(
        r"Cook County State'?s Attorney|\bCCSAO\b|Internet Crimes Against Children|\bICAC\b|"
        r'child sexual abuse|child pornography|child exploitation',
        text_sample,
        re.I,
    ):
        return 'CCSAO'

    # Wyoming Division of Criminal Investigation (wyomingdci.wyo.gov — news; merged ICAC news PDF)
    if re.search(r'wyomingdci\.wyo\.gov', text_sample, re.I) and re.search(
        r'Division of Criminal Investigation|\bDCI\b|Wyoming|Computer Crime|\bICAC\b|Internet Crimes Against Children|'
        r'child exploitation|Child Porn|CSAM',
        text_sample,
        re.I,
    ):
        return 'WY DCI'

    # Iowa Division of Criminal Investigation (dps.iowa.gov — DPS site search / releases; merged ICAC news PDF)
    if re.search(r'\bdps\.iowa\.gov\b', text_sample, re.I) and re.search(
        r'Iowa\s+Department\s+of\s+Public\s+Safety|Division\s+of\s+Criminal\s+Investigation|\bDCI\b|\bICAC\b|'
        r'Internet\s+Crimes\s+Against\s+Children|Iowa\s+Division\s+of\s+Criminal\s+Investigation',
        text_sample,
        re.I,
    ):
        return 'IA DCI'

    # South Dakota Office of the Attorney General (atg.sd.gov — press releases; merged ICAC news PDF)
    if re.search(r'atg\.sd\.gov', text_sample, re.I) and re.search(
        r'South Dakota Attorney General|Attorney General Jackley|\bICAC\b|Internet Crimes Against Children|'
        r'Division of Criminal Investigation|\bDCI\b|Child Porn|child pornography|Child Exploitation',
        text_sample,
        re.I,
    ):
        return 'SD AG'

    # Kentucky State Police (kentuckystatepolice.ky.gov — WordPress news; merged ICAC news PDF)
    if re.search(r'kentuckystatepolice\.ky\.gov', text_sample, re.I) and re.search(
        r'Kentucky State Police|\bKSP\b|Electronic Crime Branch|\bICAC\b|Internet Crimes Against Children',
        text_sample,
        re.I,
    ):
        return 'KY SP'

    # Nebraska State Patrol (statepatrol.nebraska.gov — Drupal news; merged child-exploitation search PDF)
    if re.search(r'statepatrol\.nebraska\.gov', text_sample, re.I) and re.search(
        r'Nebraska State Patrol|\bNSP\b|Technical Crimes Unit|child exploitation|'
        r'child pornography|child sexual abuse material|\bCSAM\b|\bICAC\b',
        text_sample,
        re.I,
    ):
        return 'NE SP'

    # U.S. Army Criminal Investigation Division (cid.army.mil — ICAC task force releases; merged news PDF)
    if re.search(r'\bcid\.army\.mil\b', text_sample, re.I) and re.search(
        r'Army Criminal Investigation Division|\bArmy CID\b|Criminal Investigation Division|'
        r'\bICAC\b|Internet Crimes Against Children|child exploitation|child sexual abuse material',
        text_sample,
        re.I,
    ):
        return 'ARMY CID'

    # U.S. Secret Service (secretservice.gov — ICAC task force press releases; merged news PDF)
    if re.search(r'\bsecretservice\.gov\b', text_sample, re.I) and re.search(
        r'United States Secret Service|\bUSSS\b|Internet Crimes Against Children|\bICAC\b|'
        r'child (?:sexual abuse material|pornography)|\bCSAM\b|Project Safe Childhood|NCMEC',
        text_sample,
        re.I,
    ):
        return 'USSS'

    # U.S. Immigration and Customs Enforcement / HSI (ice.gov — child exploitation press releases)
    if re.search(r'\bice\.gov\b', text_sample, re.I) and re.search(
        r'Homeland Security Investigations|\bHSI\b|Immigration and Customs Enforcement|\bICE\b|'
        r'child (?:sexual abuse material|pornography|exploitation)|\bCSAM\b|Project Safe Childhood',
        text_sample,
        re.I,
    ):
        return 'ICE'

    # Air Force Office of Special Investigations (osi.af.mil)
    if re.search(r'\bosi\.af\.mil\b', text_sample, re.I) and re.search(
        r'Air Force Office of Special Investigations|\bAFOSI\b|\bAF OSI\b|'
        r'child (?:sexual abuse material|pornography|exploitation)|\bCSAM\b',
        text_sample,
        re.I,
    ):
        return 'AF OSI'

    # Naval Criminal Investigative Service (ncis.navy.mil)
    if re.search(r'\bncis\.navy\.mil\b', text_sample, re.I) and re.search(
        r'\bNCIS\b|Naval Criminal Investigative Service|child (?:exploitation|pornography|sexual abuse)',
        text_sample,
        re.I,
    ):
        return 'NCIS'

    # U.S. Customs and Border Protection (cbp.gov)
    if re.search(r'\bcbp\.gov\b', text_sample, re.I) and re.search(
        r'Customs and Border Protection|\bCBP\b|'
        r'child (?:sexual|exploitation|pornography|abuse)|\bCSAM\b',
        text_sample,
        re.I,
    ):
        return 'CBP'

    # U.S. Marshals Service (usmarshals.gov)
    if re.search(r'\busmarshals\.gov\b', text_sample, re.I) and re.search(
        r'U\.?S\.? Marshals|\bUSMS\b|child (?:sex|predator|exploitation|pornography)|sexual assault.*minor',
        text_sample,
        re.I,
    ):
        return 'US MARSHALS'

    # Las Vegas Metropolitan Police Department (lvmpd.com — ICAC task force press releases)
    if re.search(r'\blvmpd\.com\b', text_sample, re.I) and re.search(
        r'Las Vegas Metropolitan Police Department|\bLVMPD\b|Internet Crimes Against Children|\bICAC\b|'
        r'child sex predator|child exploitation|Luring a Child',
        text_sample,
        re.I,
    ):
        return 'LVMPD'

    # San Jose Police Department (sjpd.org — ICAC / CED press releases; merged ICAC search PDF)
    if re.search(r'\bsjpd\.org\b', text_sample, re.I) and re.search(
        r'San Jos[eé] Police Department|\bSJPD\b|Internet Crimes Against Children|'
        r'Child Exploitation Detail|\bICAC\b|child sexual abuse material|\bCSAM\b|sextortion',
        text_sample,
        re.I,
    ):
        return 'SJPD'

    # Rhode Island Office of the Attorney General (riag.ri.gov — ICAC press releases)
    if re.search(r'\briag\.ri\.gov\b', text_sample, re.I) and re.search(
        r'Rhode Island Attorney General|Attorney General Peter|Internet Crimes Against Children|\bICAC\b|'
        r'child (?:sexual abuse material|pornography)|child sex trafficking',
        text_sample,
        re.I,
    ):
        return 'RI AG'

    # Florida Office of the Attorney General (myfloridalegal.com — statewide ICAC press releases)
    if re.search(r'\bmyfloridalegal\.com\b', text_sample, re.I) and re.search(
        r'Florida Attorney General|Attorney General James|Office of Statewide Prosecution|'
        r'Internet Crimes Against Children|\bICAC\b|child predator|child pornography',
        text_sample,
        re.I,
    ):
        return 'FL AG'

    # Arkansas Department of Public Safety (dps.arkansas.gov — ICAC / CSAM news; merged ICAC news PDF)
    if re.search(r'dps\.arkansas\.gov', text_sample, re.I) and re.search(
        r'Arkansas State Police|\bASP\b|\bICAC\b|Internet Crimes Against Children|\bCSAM\b|child porn',
        text_sample,
        re.I,
    ):
        return 'ARKANSAS DPS'

    # Alabama Law Enforcement Agency (www.alea.gov — news releases; merged SBI/ICAC news PDF)
    if re.search(r'\balea\.gov\b', text_sample, re.I) and re.search(
        r'\bALEA\b|Alabama Law Enforcement|State Bureau of Investigation|\bSBI\b|'
        r'\bICAC\b|Internet Crimes Against Children|child exploitation|Child Porn|CSAM',
        text_sample,
        re.I,
    ):
        return 'ALEA'

    # U.S. DOJ CEOS news (federal child exploitation press releases; supplemental source)
    if re.search(r'justice\.gov', text_sample, re.I) and re.search(
        r'Child Exploitation\s*&\s*Obscenity Section|CEOS|Press Release',
        text_sample,
        re.I,
    ):
        return 'DOJ CEOS'

    # U.S. DOJ archived CEOS pages (legacy archive domain path)
    if re.search(r'justice\.gov/archives/criminal', text_sample, re.I) and re.search(
        r'Child Exploitation|Obscenity Section|Press Release|child pornography|sexual abuse material',
        text_sample,
        re.I,
    ):
        return 'DOJ ARCHIVES'

    # Pennsylvania Office of Attorney General (attorneygeneral.gov — exclude other state AG domains)
    if re.search(r'attorneygeneral\.gov', text_sample, re.I) and not re.search(
        r'illinoisattorneygeneral|texasattorneygeneral|njoag\.gov|ohioattorneygeneral|attorneygeneral\.utah\.gov',
        text_sample,
        re.I,
    ) and re.search(
        r'Child Predator|Internet Crimes Against Children|\bICAC\b|Taking Action',
        text_sample,
        re.I,
    ):
        return 'PA AG'

    # Delimited "Case 1 : ... Case 2 : ..." scrapes (news, LinkedIn PDFs, etc.)
    if re.search(r'(?m)(?:^|\n)\s*Case\s+1\s*:', text_sample, re.IGNORECASE):
        return 'Other'

    # Default fallback
    return 'Other'  # Default to Other


def _clean_url(url: str) -> str:
    """Normalize and trim trailing punctuation from extracted URLs."""
    if not isinstance(url, str):
        return ""
    return url.strip().rstrip('.,);]')


_SOURCE_FIELD_BREAK_RE = re.compile(r"^(?:[A-Za-z][A-Za-z ]{0,40}:|Case\s+\d+\s*:)", re.IGNORECASE)


def _extract_source_url_marker_value(text: str) -> Optional[str]:
    """
    Extract `Source: <url>` with support for PDF-wrapped URL lines.
    Example:
      Source: https://...-who-disse
      minated-child...   -> joined into one URL.
    Spaced path fragments after a date slug (e.g. ``.../202109-16`` + next line title) are
    hyphenated and appended.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*Source:\s*(https?://\S*)", line, flags=re.IGNORECASE)
        if not m:
            continue
        url = m.group(1).strip()
        spaced_slug_segments = 0
        extra, add = consume_same_line_slug_after_url(url, line[m.end() :])
        url = extra
        spaced_slug_segments += add
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                break
            if _SOURCE_FIELD_BREAK_RE.match(nxt):
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
        return _clean_url(url)
    return None


def extract_source_url_from_text(text: str) -> Optional[str]:
    """
    Extract canonical source URL from text using only `Source: <url>`.
    """
    return _extract_source_url_marker_value(text)


@lru_cache(maxsize=1)
def _load_source_url_fallbacks_from_sources_html() -> Dict[str, str]:
    """
    Parse `visualization/sources.html` staticSources and build source->url fallbacks.
    This avoids hardcoding per-agency links in ingestion scripts.
    """
    mapping: Dict[str, str] = {}
    try:
        sources_path = Path(__file__).resolve().parents[2] / "visualization" / "sources.html"
        html = sources_path.read_text(encoding="utf-8")
    except Exception:
        return mapping

    objects = re.findall(
        r'name:\s*"([^"]+)"\s*,\s*url:\s*"([^"]+)"',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for name, url in objects:
        n = name.lower()
        url_clean = _clean_url(url)
        if "arizona internet crimes against children" in n:
            mapping["AZICAC"] = url_clean
        elif "national center for missing" in n:
            mapping["NCMEC"] = url_clean
        elif "georgia bureau of investigation" in n:
            mapping["GBI"] = url_clean
        elif "idaho office of attorney general" in n:
            mapping["IDAHO ICAC"] = url_clean
        elif "texas office of the attorney general" in n:
            mapping["TEXAS AG"] = url_clean
        elif "michigan state police" in n:
            mapping["MICHIGAN ICAC"] = url_clean
        elif "silicon valley icac" in n:
            mapping["SVICAC"] = url_clean
        elif "tennessee bureau of investigation" in n:
            mapping["TBI ICAC"] = url_clean
        elif "south carolina attorney general" in n:
            mapping["SCAG ICAC"] = url_clean
        elif "new york state police" in n:
            mapping["NEWYORK SP"] = url_clean
        elif "illinois attorney general" in n:
            mapping["ILLINOIS AG"] = url_clean
        elif "washoe county sheriff" in n:
            mapping["WCSO"] = url_clean
        elif "fresno county sheriff" in n:
            mapping["FRESNO SO"] = url_clean
        elif "osceola county sheriff" in n:
            mapping["OSCEOLA SO"] = url_clean
        elif "anchorag" in n and "police" in n:
            mapping["ANCHORAGE PD"] = url_clean
        elif "sedgwick county sheriff" in n:
            mapping["SEDGWICK SO"] = url_clean
        elif "los angeles police department" in n:
            mapping["LAPD"] = url_clean
        elif "colorado springs police" in n:
            mapping["CSPD"] = url_clean
        elif "seattle police department" in n:
            mapping["SPD"] = url_clean
        elif "san diego police department" in n:
            mapping["SDPD"] = url_clean
        elif "south florida icac" in n:
            mapping["SOUTH FLORIDA ICAC"] = url_clean
        elif "new jersey office of the attorney general" in n:
            mapping["NJ AG"] = url_clean
        elif "pennsylvania office of the attorney general" in n:
            mapping["PA AG"] = url_clean
        elif "vermont office of the attorney general" in n:
            mapping["VT AG"] = url_clean
        elif "ohio attorney general" in n:
            mapping["OHIO AG"] = url_clean
        elif "delaware department of justice" in n or "delaware attorney general" in n:
            mapping["DE AG"] = url_clean
        elif "utah attorney general" in n:
            mapping["UT AG"] = url_clean
        elif "washington state office of the attorney general" in n:
            mapping["WA AG"] = url_clean
        elif "oregon department of justice" in n:
            mapping["OREGON DOJ"] = url_clean
        elif "mississippi attorney general" in n:
            mapping["MS AG"] = url_clean
        elif "montana department of justice" in n:
            mapping["MT DOJ"] = url_clean
        elif "new mexico attorney general" in n or "new mexico department of justice" in n:
            mapping["NM AG"] = url_clean
        elif "north carolina state bureau of investigation" in n:
            mapping["NC SBI"] = url_clean
        elif "louisiana office of the attorney general" in n:
            mapping["LA AG"] = url_clean
        elif "hawaii department of the attorney general" in n or "hawaii office of the attorney general" in n:
            mapping["HI AG"] = url_clean
        elif "cook county state" in n and "attorney" in n:
            mapping["CCSAO"] = url_clean
        elif "wyoming division of criminal investigation" in n:
            mapping["WY DCI"] = url_clean
        elif "iowa division of criminal investigation" in n:
            mapping["IA DCI"] = url_clean
        elif "south dakota office of the attorney general" in n:
            mapping["SD AG"] = url_clean
        elif "rhode island" in n and "attorney general" in n:
            mapping["RI AG"] = url_clean
        elif "florida" in n and "attorney general" in n and "south florida" not in n:
            mapping["FL AG"] = url_clean
        elif "kentucky state police" in n:
            mapping["KY SP"] = url_clean
        elif "nebraska state patrol" in n:
            mapping["NE SP"] = url_clean
        elif "army criminal investigation" in n or "army cid" in n:
            mapping["ARMY CID"] = url_clean
        elif "secret service" in n and "icac" in n:
            mapping["USSS"] = url_clean
        elif "immigration and customs enforcement" in n or ("ice" in n and "child" in n):
            mapping["ICE"] = url_clean
        elif "air force" in n and ("osi" in n or "special investigations" in n):
            mapping["AF OSI"] = url_clean
        elif "naval criminal" in n or ("ncis" in n and "child" in n):
            mapping["NCIS"] = url_clean
        elif "customs and border" in n or ("cbp" in n and "child" in n):
            mapping["CBP"] = url_clean
        elif "marshals" in n and "child" in n:
            mapping["US MARSHALS"] = url_clean
        elif "las vegas metropolitan" in n or "lvmpd" in n:
            mapping["LVMPD"] = url_clean
        elif "san jose police" in n or "sjpd" in n:
            mapping["SJPD"] = url_clean
        elif "arkansas department of public safety" in n:
            mapping["ARKANSAS DPS"] = url_clean
        elif "alabama law enforcement agency" in n:
            mapping["ALEA"] = url_clean
        elif "child exploitation & obscenity section news" in n:
            mapping["DOJ CEOS"] = url_clean
        elif "u.s. doj archives" in n or (
            "doj archives" in n and "obscenity" in n
        ) or "child exploitation and obscenity section archive" in n:
            mapping["DOJ ARCHIVES"] = url_clean
    return mapping


def get_source_url_fallback(source: str) -> Optional[str]:
    """Lookup source URL fallback from `visualization/sources.html` by source label."""
    key = (source or "").strip().upper()
    if not key:
        return None
    return _load_source_url_fallbacks_from_sources_html().get(key)


def extract_pdf_text(pdf_path: str) -> str:
    """
    Extract all text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text as a string
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber is required for PDF extraction. Install with: pip install pdfplumber")
    
    text_content = []
    
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content.append(page_text)
        
        return "\n".join(text_content)
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")


def ingest_file(file_path: str, file_type: Optional[str] = None, source_url: Optional[str] = None) -> pd.DataFrame:
    """
    Ingest a file and return a DataFrame.
    Supports PDF files (extracts text) and other formats as needed.
    
    Args:
        file_path: Path to the file to ingest
        file_type: Optional file type hint (e.g., 'pdf', 'csv', 'txt')
                   If None, will be inferred from file extension
        source_url: Optional canonical source URL for custom/manual PDFs
        
    Returns:
        DataFrame with ingested data
    """
    path = Path(file_path)
    
    if file_type is None:
        file_type = path.suffix.lower().lstrip('.')
    
    if file_type == 'pdf':
        text = extract_pdf_text(str(path))
        source = detect_source_from_content(text, path.name)
        detected_source_url = extract_source_url_from_text(text)
        resolved_source_url = source_url or detected_source_url or get_source_url_fallback(source)
        
        df = pd.DataFrame({
            'source_file': [path.name],
            'extracted_text': [text],
            'source': [source],
            'source_url': [resolved_source_url],
            'provenance_records': [_load_provenance_records(path)],
        })
        
        return df
    
    elif file_type == 'csv':
        return pd.read_csv(file_path)
    
    elif file_type == 'txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        df = pd.DataFrame({
            'source_file': [path.name],
            'extracted_text': [text],
            'source': ['unknown'],
        })
        
        return df
    
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


def ingest_multiple_pdfs(
    pdf_paths: List[str],
    source_urls_by_file: Optional[Dict[str, str]] = None,
    default_source_url: Optional[str] = None,
) -> pd.DataFrame:
    """
    Ingest multiple PDF files and return a combined DataFrame.
    Each PDF is processed separately and combined into a single DataFrame.
    
    Args:
        pdf_paths: List of paths to PDF files
        source_urls_by_file: Optional mapping of filename or full path to source URL
        default_source_url: Optional fallback source URL for files not in mapping
        
    Returns:
        DataFrame with ingested data from all PDFs
    """
    if not pdf_paths:
        raise ValueError("No PDF paths provided")
    
    all_data = []
    
    for pdf_path in pdf_paths:
        path = Path(pdf_path)
        
        if not path.exists():
            print(f"⚠️  Warning: File not found, skipping: {pdf_path}")
            continue
        
        if not path.suffix.lower() == '.pdf':
            print(f"⚠️  Warning: Not a PDF file, skipping: {pdf_path}")
            continue
        
        try:
            text = extract_pdf_text(str(path))
            
            # Detect source from content and filename
            org_name = detect_source_from_content(text, path.name)
            detected_source_url = extract_source_url_from_text(text)
            resolved_source_url = (
                (source_urls_by_file or {}).get(str(path))
                or (source_urls_by_file or {}).get(path.name)
                or default_source_url
                or detected_source_url
                or get_source_url_fallback(org_name)
            )
            
            all_data.append({
                'source_file': path.name,
                'extracted_text': text,
                'source': org_name,
                'source_url': resolved_source_url,
                'provenance_records': _load_provenance_records(path),
            })
            print(f"✓ Ingested: {path.name} ({len(text):,} characters) - Detected source: {org_name}")
            
        except Exception as e:
            print(f"❌ Error processing {path.name}: {e}")
            continue
    
    if not all_data:
        raise ValueError("No PDFs were successfully ingested")
    
    df = pd.DataFrame(all_data)
    return df



