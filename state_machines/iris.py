"""CAC ontology IRIs for PACER state machines (read from ontology, not hardcoded from memory)."""

from __future__ import annotations

import json
import re
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
STATE_MACHINES_WORKSPACE = PKG_DIR
REPO_ROOT = PKG_DIR.parent
ONTOLOGY_DIR = REPO_ROOT / "ontology"
PACER_BULK_DIR = ONTOLOGY_DIR / "PACER" / "BULK_FOLDER"
GRAPHS_DIR = PKG_DIR / "graphs"
LSTAR_JSON = PKG_DIR / "data" / "lstar_all_cases.json"

CORE_NS = "https://cacontology.projectvic.org/core#"
CAC_NS = "https://cacontology.projectvic.org#"
GROOMING_NS = "https://cacontology.projectvic.org/grooming#"
SEXTORTION_NS = "https://cacontology.projectvic.org/sextortion#"
PLATFORMS_NS = "https://cacontology.projectvic.org/platforms#"
UNDERCOVER_NS = "https://cacontology.projectvic.org/undercover#"
CASELINKER_NS = "https://caselinker.projectvic.app/cases#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
RDFS_COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
RDFS_SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"

# Must match cac-core:precedes in cacontology-core-spine.ttl (source of truth).
PRECEDES = "https://cacontology.projectvic.org/core#precedes"
HAS_STEP = f"{CAC_NS}hasStep"
CAC_INVESTIGATION = f"{CAC_NS}CACInvestigation"
PHASE = f"{CORE_NS}Phase"

INITIAL_CONTACT_PHASE = f"{GROOMING_NS}InitialContactPhase"
CONDITIONING_PHASE = f"{GROOMING_NS}ConditioningPhase"
CONDITIONING_MODE = f"{CORE_NS}conditioningMode"
# Deprecated alias retained for transitional readers.
TRUST_BUILDING_PHASE = CONDITIONING_PHASE
SEXUALIZATION_PHASE = f"{GROOMING_NS}SexualizationPhase"
EXPLOITATION_PHASE = f"{GROOMING_NS}ExploitationPhase"
MAINTENANCE_PHASE = f"{GROOMING_NS}MaintenancePhase"
THREAT_MECHANISM = f"{SEXTORTION_NS}ThreatMechanism"
COERCION_CYCLE = f"{SEXTORTION_NS}CoercionCycle"
CHANNEL_MIGRATION_EVENT = f"{PLATFORMS_NS}ChannelMigrationEvent"
STING_OPERATION = f"{UNDERCOVER_NS}StingOperation"
CONCLUSION_PHASE = f"{CAC_NS}ConclusionPhase"
DISRUPTS_CHAIN = f"{CASELINKER_NS}disruptsChain"
DISRUPTED_TARGET = f"{CASELINKER_NS}disruptedTarget"

AFFORDANCE_MISUSE = f"{PLATFORMS_NS}AffordanceMisuse"
ENABLES_TRANSITION_FROM = f"{PLATFORMS_NS}enablesTransitionFrom"
ENABLES_TRANSITION_TO = f"{PLATFORMS_NS}enablesTransitionTo"
AFFORDANCE_CLASS = f"{PLATFORMS_NS}affordanceClass"
MISUSE_DESCRIPTION = f"{PLATFORMS_NS}misuseDescription"

ANONYMITY = f"{PLATFORMS_NS}Anonymity"
EPHEMERALITY = f"{PLATFORMS_NS}Ephemerality"
UNMONITORED_COMMUNICATION = f"{PLATFORMS_NS}UnmonitoredCommunication"
CONTACT_DISCOVERY = f"{PLATFORMS_NS}ContactDiscovery"
DISTRIBUTION_INFRASTRUCTURE = f"{PLATFORMS_NS}DistributionInfrastructure"
COORDINATION = f"{PLATFORMS_NS}Coordination"
COERCION_LEVERAGE = f"{PLATFORMS_NS}CoercionLeverage"

ANCHOR_CASE_IDS = (
    "enticement",
    "production",
    "sextortion",
    "enterprise",
    "trafficking",
)

EXPANSION_CASE_IDS = (
    "doj_ceos_2025_014",  # Gastelo — production
    "usss_2021_019",      # Lyons — trafficking
    "doj_ceos_2026_012",  # Hounsell — enticement
    "ncis_2023_001",      # Leggett — enticement
    "usss_2017_006",      # Saucedo — production
    "doj_ceos_2025_031",  # McIntosh — enterprise (Grayskull)
    "ky_sp_2025_038",     # Stafford — sextortion (E.D. Ky. PACER)
    "texas_ag_2019_013",  # Duron — sextortion (W.D. Tex. PACER)
    "wy_dci_2023_005",    # Smith — production (D. Wyo. PACER)
    "usss_2023_004",      # Earnest — trafficking sting (W.D. Ky. PACER)
    "doj_ceos_2025_023",  # Werner — extraterritorial production (E.D. Ky. PACER)
    "svicac_2022_009",   # Garcia-De Leon — Kik Hogwarts gateway enterprise (N.D. Cal. PACER)
    "ncmec_2023_224",    # Daniels — Kik enticement / false-age grooming (S.D. W. Va. PACER)
    "ncmec_2023_190",    # Velez — multi-persona Snapchat production (E.D. Va. PACER)
    "ncmec_2022_586",    # Muckelroy — Snapchat directed production (E.D. Va. PACER)
    "anchorage_pd_2022_006", # Grant — Adultlook minor sex trafficking enterprise (D. Alaska PACER)
    "anchorage_pd_2022_004", # Moore — Snapchat / SkipTheGames minor sex trafficking (D. Alaska PACER)
    "doj_ceos_2025_004", # Dalton — text/email enticement (E.D. Va. PACER)
    "doj_ceos_2026_007", # Parker — Subject Website dark-web CSAM enterprise (M.D. Ala. PACER)
    "ncis_2022_002",     # Lofaro — false-identity production / CSAM enterprise (E.D. Va. PACER)
    "doj_ceos_2026_008", # Puente — Facebook paid transnational production (D. Md. PACER)
    "doj_ceos_2026_003", # Mara — extraterritorial embassy residence abuse (D. Md. PACER)
    "doj_ceos_2025_025", # Mendonsa — four-site dark-web CSAM enterprise (E.D. Cal. PACER)
    "ncmec_2025_1116",    # David — production / multi-account Kik distribution (D. Wyo. PACER)
    "external_extortion", # Murphy — serial multi-persona Snapchat sextortion (D. Mass. PACER) — last
)

CASE_FILES = (
    *(f"{case_id}.jsonld" for case_id in ANCHOR_CASE_IDS),
    *(f"{case_id}.jsonld" for case_id in EXPANSION_CASE_IDS),
)

MODALITY_LABELS = {
    "enticement": "ENTICEMENT",
    "production": "PRODUCTION",
    "sextortion": "SEXTORTION",
    "enterprise": "ENTERPRISE",
    "trafficking": "TRAFFICKING",
}

CASE_META = {
    "enticement": {
        "title": "ENTICEMENT",
        "citation": "United States v. Rehman (D.D.C. 1:23-cr-00064)",
        "modality": "enticement",
    },
    "sextortion": {
        "title": "SEXTORTION",
        "citation": "United States v. Amin (D. Alaska 3:22-cr-00055)",
        "modality": "sextortion",
    },
    "production": {
        "title": "PRODUCTION",
        "citation": "United States v. Pathmanathan (D.D.C. 1:22-cr-00150)",
        "modality": "production",
    },
    "enterprise": {
        "title": "ENTERPRISE",
        "citation": "United States v. Bermudez et al. (E.D.N.Y. 1:25-cr-00361)",
        "modality": "enterprise",
    },
    "trafficking": {
        "title": "TRAFFICKING",
        "citation": "United States v. Riley (D. Haw. 1:23-cr-00071)",
        "modality": "trafficking",
    },
    "doj_ceos_2026_012": {
        "title": "Hounsell",
        "citation": "United States v. Hounsell (E.D. Wis. 1:25-cr-00069)",
        "statute": "18 U.S.C. § 2422(b)",
        "modality": "enticement",
        "corpus_id": "doj_ceos_2026_012",
        "defendant": "Bradley D. Hounsell",
    },
    "doj_ceos_2025_014": {
        "title": "Gastelo",
        "citation": "United States v. Gastelo (E.D. Cal. 1:20-cr-00252)",
        "statute": "18 U.S.C. §§ 2251, 2252",
        "modality": "production",
        "corpus_id": "doj_ceos_2025_014",
        "defendant": "Monico Erich Gastelo",
        "conduct_tags": [],
    },
    "doj_ceos_2025_031": {
        "title": "Grayskull",
        "citation": "United States v. McIntosh (S.D. Fla. 9:24-cr-80053)",
        "statute": "18 U.S.C. §§ 2251(d),(e); 2252A(a)(2)",
        "modality": "enterprise",
        "corpus_id": "doj_ceos_2025_031",
        "defendant": "Keith Duane McIntosh & Thomas Peter Katsampes",
    },
    "usss_2017_006": {
        "title": "Saucedo",
        "citation": "United States v. Saucedo (S.D. Cal. 3:17-cr-00095)",
        "statute": "18 U.S.C. §§ 2251, 2252",
        "modality": "production",
        "corpus_id": "usss_2017_006",
        "defendant": "Joseph Daniel Saucedo",
        "conduct_tags": ["catfish", "impersonation", "threat_of_exposure"],
    },
    "ncis_2023_001": {
        "title": "Leggett",
        "citation": "United States v. Leggett (M.D. Fla. 3:23-cr-00102)",
        "statute": "18 U.S.C. § 2422(b)",
        "modality": "enticement",
        "corpus_id": "ncis_2023_001",
        "defendant": "Jeremy Wayne Leggett",
        "sting_operation": True,
    },
    "usss_2021_019": {
        "title": "Lyons",
        "citation": "United States v. Lyons (W.D. Ky. 3:20-cr-00049)",
        "statute": "18 U.S.C. §§ 1591, 2251, 2252A, 2422(b)",
        "modality": "trafficking",
        "corpus_id": "usss_2021_019",
        "defendant": "Matthew Alexander Lyons",
    },
    "ky_sp_2025_038": {
        "title": "Stafford",
        "citation": "United States v. Stafford (E.D. Ky. 3:24-cr-00008)",
        "statute": "18 U.S.C. § 2251(a)",
        "corpus_id": "ky_sp_2025_038",
        "defendant": "Austin David Stafford",
        "conduct_tags": [
            "sextortion_conduct",
            "multi_persona",
            "fake_persona",
            "catfish",
            "threat_mechanism_kg",
        ],
    },
    "texas_ag_2019_013": {
        "title": "Duron",
        "citation": "United States v. Duron (W.D. Tex. 5:19-cr-00804)",
        "statute": "18 U.S.C. §§ 2251(a), 875(d)",
        "corpus_id": "texas_ag_2019_013",
        "defendant": "Felipe Jesus Duron",
    },
    "wy_dci_2023_005": {
        "title": "Smith",
        "citation": "United States v. Smith (D. Wyo. 1:22-cr-00137)",
        "statute": "18 U.S.C. §§ 2251(a),(e)",
        "corpus_id": "wy_dci_2023_005",
        "defendant": "Kyle Bradley Smith",
    },
    "usss_2023_004": {
        "title": "Earnest",
        "citation": "United States v. Earnest (W.D. Ky. 3:23-cr-00031)",
        "statute": "18 U.S.C. §§ 1591(a)(1), 2422(b)",
        "modality": "trafficking",
        "corpus_id": "usss_2023_004",
        "defendant": "Steven B. Earnest",
        "sting_operation": True,
        "sting_only": True,
        "victim_harmed": False,
    },
    "ncmec_2025_1116": {
        "title": "David",
        "citation": "United States v. David (D. Wyo. 2:25-cr-00095)",
        "statute": "18 U.S.C. §§ 2252A(a)(2)(A), (b)(1)",
        "modality": "production",
        "corpus_id": "ncmec_2025_1116",
        "defendant": "Luke Everett David",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["multi_persona"],
    },
    "doj_ceos_2025_023": {
        "title": "Werner",
        "citation": "United States v. Werner (E.D. Ky. 2:24-cr-00047)",
        "statute": "18 U.S.C. § 2251(c)",
        "modality": "production",
        "corpus_id": "doj_ceos_2025_023",
        "defendant": "Robert Maxwell Werner",
        "victim_harmed": True,
        "sting_only": False,
    },
    "ncmec_2023_224": {
        "title": "Daniels",
        "citation": "United States v. Daniels (S.D. W. Va. 2:23-cr-00023)",
        "statute": "18 U.S.C. § 2422(b)",
        "modality": "enticement",
        "corpus_id": "ncmec_2023_224",
        "defendant": "Isaiah Harley Daniels",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["catfish", "impersonation", "multi_victim_parallel"],
    },
    "svicac_2022_009": {
        "title": "Garcia",
        "citation": "United States v. Garcia-De Leon (N.D. Cal. 4:21-cr-00052)",
        "statute": "18 U.S.C. § 2252(a)(2)",
        "modality": "enterprise",
        "corpus_id": "svicac_2022_009",
        "defendant": "Abel Garcia-De Leon",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["gateway_verification", "multi_room_admin", "organizer_leader"],
    },
    "ncmec_2023_190": {
        "title": "Velez",
        "citation": "United States v. Velez (E.D. Va. 4:22-cr-00028)",
        "statute": "18 U.S.C. § 2251(a)",
        "modality": "production",
        "corpus_id": "ncmec_2023_190",
        "defendant": "Elliott Dale Velez",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["multi_persona", "covert_recording", "multi_victim_production"],
    },
    "ncmec_2022_586": {
        "title": "Muckelroy",
        "citation": "United States v. Muckelroy (E.D. Va. 2:21-cr-00130)",
        "statute": "18 U.S.C. §§ 2251(a), 2422(b)",
        "modality": "production",
        "corpus_id": "ncmec_2022_586",
        "defendant": "Travis James Muckelroy",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["multi_platform", "snapchat_account_rotation"],
    },
    "anchorage_pd_2022_006": {
        "title": "Grant",
        "citation": "United States v. Grant (D. Alaska 3:19-cr-00003)",
        "statute": "18 U.S.C. §§ 1591(a), 1594(c)",
        "modality": "trafficking",
        "corpus_id": "anchorage_pd_2022_006",
        "defendant": "Tristan Jamal Grant",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": [
            "multi_victim_parallel",
            "co_conspirator_pimping",
            "commercial_advertising",
            "firearms_intimidation",
        ],
    },
    "anchorage_pd_2022_004": {
        "title": "Moore",
        "citation": "United States v. Moore (D. Alaska 3:20-cr-00029)",
        "statute": "18 U.S.C. § 1591(a)(1)",
        "modality": "trafficking",
        "corpus_id": "anchorage_pd_2022_004",
        "defendant": "Jayshon Moore",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": [
            "rent_quota",
            "meth_coercion",
            "skipthegames_ads",
            "firearms_intimidation",
            "snapchat_documentation",
        ],
    },
    "doj_ceos_2025_004": {
        "title": "Dalton",
        "citation": "United States v. Dalton (E.D. Va. 1:24-cr-00227)",
        "statute": "18 U.S.C. § 2422(b)",
        "modality": "enticement",
        "corpus_id": "doj_ceos_2025_004",
        "defendant": "Cash Taylor Dalton",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["authority_grooming", "directed_recording_solicitation"],
    },
    "ncis_2022_002": {
        "title": "Lofaro",
        "citation": "United States v. Lofaro (E.D. Va. 1:23-cr-00156)",
        "statute": "18 U.S.C. §§ 2422(b), 2252",
        "modality": "production",
        "corpus_id": "ncis_2022_002",
        "defendant": "Daniel Marc Lofaro",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["catfish", "impersonation", "multi_victim_parallel", "encrypted_archive"],
    },
    "doj_ceos_2026_008": {
        "title": "Puente",
        "citation": "United States v. Puente (D. Md. 8:24-cr-00332)",
        "statute": "18 U.S.C. §§ 2251(a), 2252A(a)(5)(B)",
        "modality": "production",
        "corpus_id": "doj_ceos_2026_008",
        "defendant": "Juan Carlos Puente",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": ["financial_grooming", "transnational_victim", "paid_commissioning"],
    },
    "doj_ceos_2026_003": {
        "title": "Mara",
        "citation": "United States v. Mara (D. Md. 8:24-cr-00187)",
        "statute": "18 U.S.C. §§ 2241(c), 2422(b)",
        "modality": "enticement",
        "corpus_id": "doj_ceos_2026_003",
        "defendant": "Fode Sitafa Mara",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": [
            "extraterritorial",
            "diplomatic_residence_abuse",
            "dependency_grooming",
            "hands_on_abuse",
            "whatsapp_coercive_control",
        ],
    },
    "doj_ceos_2026_007": {
        "title": "Parker",
        "citation": "United States v. Parker (M.D. Ala. 3:25-cr-00214)",
        "statute": "18 U.S.C. § 2251(d)",
        "modality": "enterprise",
        "corpus_id": "doj_ceos_2026_007",
        "defendant": "Jacob Parker",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": [
            "dark_web_forum",
            "moderator_staff",
            "link_preview_distribution",
            "promotion_via_cp_sharing",
        ],
    },
    "doj_ceos_2025_025": {
        "title": "Mendonsa",
        "citation": "United States v. Mendonsa (E.D. Cal. 2:22-cr-00243)",
        "statute": "18 U.S.C. §§ 2252(a)(2), 2252(a)(4)",
        "modality": "enterprise",
        "corpus_id": "doj_ceos_2025_025",
        "defendant": "Louis Donald Mendonsa",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": [
            "multi_site_administration",
            "global_moderator",
            "dark_web_enterprise",
            "public_wifi_operations",
        ],
    },
    "external_extortion": {
        "title": "Murphy",
        "citation": "United States v. Murphy (D. Mass. 1:19-cr-10286)",
        "statute": "18 U.S.C. § 2251(a)",
        "modality": "sextortion",
        "corpus_id": "external_extortion",
        "defendant": "Matthew Murphy",
        "victim_harmed": True,
        "sting_only": False,
        "conduct_tags": [
            "multi_persona",
            "fake_persona",
            "catfish",
            "threat_mechanism_kg",
            "snapchat_account_takeover",
            "boy_scout_leader",
            "serial_multi_victim",
        ],
    },
}

def get_case_meta(case_id: str) -> dict:
    """Return CASE_META entry with sensible defaults for unknown expansion cases."""
    return CASE_META.get(
        case_id,
        {"title": case_id.upper(), "citation": case_id, "corpus_id": case_id},
    )


_STATUTE_MODALITY = (
    (re.compile(r"\b2422\b"), "enticement"),
    (re.compile(r"\b1591\b|\b2423\b"), "trafficking"),
    (re.compile(r"\bsextortion\b", re.I), "sextortion"),
    (re.compile(r"\benterprise\b", re.I), "enterprise"),
    (re.compile(r"\b2251\b|\b2252\b"), "production"),
)

_PRODUCTION_CONVICTION = re.compile(r"\b2251\b|\b2252\b")
_SEXTORTION_CONDUCT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sextortion_keyword", re.compile(r"(?<![\w#-])sextortion\b", re.I)),
    ("fake_account", re.compile(r"\bfake account\b", re.I)),
    ("false_identity", re.compile(r"\bfalse identity\b", re.I)),
    ("catfish", re.compile(r"\bcatfish(?:\b|_)", re.I)),
    ("fake_persona", re.compile(r"\bfake persona\b|\bfake personas\b", re.I)),
    (
        "threat_to_distribute",
        re.compile(
            r"threatened to (?:share|post|expose|disseminate)|"
            r"threaten(?:ed)? to (?:share|post|expose|disseminat|distribut)|"
            r"threat to injure the reputation",
            re.I,
        ),
    ),
    ("extortion_conduct", re.compile(r"\bextort(?:ion|orsion)?\b", re.I)),
    ("multi_persona", re.compile(r"\bmulti[_ -]persona", re.I)),
)


def _case_corpus_id(case_id: str, meta: dict) -> str:
    return str(meta.get("corpus_id") or case_id)


def _read_case_facts(case_id: str, meta: dict) -> str:
    corpus_id = _case_corpus_id(case_id, meta)
    facts_path = PACER_BULK_DIR / corpus_id / f"{corpus_id}_facts.txt"
    if facts_path.is_file():
        return facts_path.read_text(encoding="utf-8", errors="replace")
    return ""


def _read_jsonld_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _read_press_text(case_id: str, meta: dict) -> str:
    corpus_id = _case_corpus_id(case_id, meta)
    processed = PACER_BULK_DIR / corpus_id / "processed"
    if not processed.is_dir():
        return ""
    return _read_jsonld_text(sorted(processed.glob("*press*")))


def _jsonld_type_local_name(type_value: str) -> str:
    if ":" in type_value and "#" not in type_value:
        return type_value.rsplit(":", 1)[-1]
    return local_name(type_value)


def _jsonld_type_names(payload: object) -> set[str]:
    """Collect rdf:type local names from a jsonld document."""
    names: set[str] = set()
    if isinstance(payload, dict):
        type_value = payload.get("@type") or payload.get(RDF_TYPE)
        if isinstance(type_value, str):
            names.add(_jsonld_type_local_name(type_value))
        elif isinstance(type_value, list):
            names.update(
                _jsonld_type_local_name(value) for value in type_value if isinstance(value, str)
            )
        for value in payload.values():
            names.update(_jsonld_type_names(value))
    elif isinstance(payload, list):
        for item in payload:
            names.update(_jsonld_type_names(item))
    return names


def _scan_kg_conduct_types(case_id: str, meta: dict) -> list[str]:
    corpus_id = _case_corpus_id(case_id, meta)
    pac_jsonld = PACER_BULK_DIR / corpus_id / f"{corpus_id}.jsonld"
    tags: list[str] = []
    if not pac_jsonld.is_file():
        return tags
    try:
        payload = json.loads(pac_jsonld.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return tags
    type_names = _jsonld_type_names(payload)
    if "ThreatMechanism" in type_names:
        tags.append("threat_mechanism_kg")
    if "CoercionCycle" in type_names:
        tags.append("coercion_cycle_kg")
    return tags


def _meta_text_blob(meta: dict) -> str:
    parts = [str(meta.get(key, "")) for key in ("citation", "statute", "title", "defendant")]
    return " ".join(parts)


def _has_production_conviction_statute(meta: dict, facts_text: str) -> bool:
    conviction_fields = (
        meta.get("statute_of_conviction"),
        meta.get("statute"),
    )
    for value in conviction_fields:
        if value and _PRODUCTION_CONVICTION.search(str(value)):
            return True

    primary = re.search(
        r"primary_statute_of_conviction:\s*[\"']?([^\"'\n]+)",
        facts_text,
        re.I,
    )
    if primary:
        return bool(_PRODUCTION_CONVICTION.search(primary.group(1)))
    if re.search(r"production_convicted:\s*false", facts_text, re.I):
        return False

    if re.search(r"statute_of_conviction:.*\b(2251|2252)\b", facts_text, re.I):
        return True

    for block in re.split(r"\n\s*-\s+count:", facts_text, flags=re.I):
        if not re.search(r"disposition:\s*convicted", block, re.I):
            continue
        if re.search(r"statute:.*\b(2251|2252)\b", block, re.I):
            return True
    return False


def _scan_conduct_signals(case_id: str, meta: dict) -> list[str]:
    """Detect conduct signals from facts, press text, and jsonld graph node types."""
    facts_text = _read_case_facts(case_id, meta)
    press_text = _read_press_text(case_id, meta)
    narrative_blob = "\n".join([facts_text, press_text])

    tags: list[str] = []
    for tag, pattern in _SEXTORTION_CONDUCT_PATTERNS:
        if pattern.search(narrative_blob):
            tags.append(tag)
    for tag in _scan_kg_conduct_types(case_id, meta):
        if tag not in tags:
            tags.append(tag)
    return tags


def collect_conduct_tags(case_id: str, meta: dict | None = None) -> list[str]:
    """Return conduct signal tags detected from facts/metadata plus declared CASE_META tags."""
    meta = meta or CASE_META.get(case_id, {})
    tags = _scan_conduct_signals(case_id, meta)

    for tag in meta.get("conduct_tags") or []:
        if tag not in tags:
            tags.append(str(tag))
    return tags


def _has_sextortion_conduct(case_id: str, meta: dict) -> bool:
    return bool(_scan_conduct_signals(case_id, meta))


def infer_modality(case_id: str, meta: dict | None = None) -> str:
    """Map a case to exploitation modality (most severe charge family).

  Production/distribution convictions (2251/2252) route to sextortion when
  conduct signals are present in facts, metadata, or case jsonld graphs.
    """
    meta = meta or CASE_META.get(case_id, {})
    if case_id in ANCHOR_CASE_IDS:
        return case_id

    explicit = meta.get("modality")
    if explicit and not meta.get("infer_modality_from_conduct"):
        return str(explicit)

    facts_text = _read_case_facts(case_id, meta)
    blob = " ".join([_meta_text_blob(meta), facts_text]).lower()

    if _has_production_conviction_statute(meta, facts_text):
        if _has_sextortion_conduct(case_id, meta):
            return "sextortion"
        return "production"

    for pattern, modality in _STATUTE_MODALITY:
        if pattern.search(blob):
            return modality
    return "unknown"


def modality_label(modality: str) -> str:
    return MODALITY_LABELS.get(modality, modality.upper())


def local_name(iri: str) -> str:
    if "#" in iri:
        return iri.rsplit("#", 1)[-1]
    return iri.rstrip("/").rsplit("/", 1)[-1]


def display_type(iri: str) -> str:
    name = local_name(iri)
    if iri.startswith(GROOMING_NS):
        return f"cacontology-grooming:{name}"
    if iri.startswith(SEXTORTION_NS):
        return f"cacontology-sextortion:{name}"
    if iri.startswith(PLATFORMS_NS):
        return f"cacontology-platforms:{name}"
    if iri.startswith(UNDERCOVER_NS):
        return f"cacontology-undercover:{name}"
    if iri.startswith(CAC_NS):
        return f"cacontology:{name}"
    if iri.startswith(CORE_NS):
        return f"cac-core:{name}"
    return name
