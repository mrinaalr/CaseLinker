#!/usr/bin/env python3
"""Authority grounding for location *mentions* → US Census FIPS entities.

Sits **after** extraction settle (NER/locations list), **not** as a resolve_v3.0
witness. Witnesses decide what the text said; this linker decides which real-world
place that string denotes.

Pipeline:
  merge_processing → ``location_grounds`` on the case dict
  features_to_cac.map_locations → mint readable ``location/{name}-{st}`` IRIs when grounded

State hints (priority):
  1. State named in the same sentence as the mention
  2. Trailing ", ST" / state name on the string
  3. USAO district in case text
  4. Default from case ``source`` (state AG / ICAC / …)

Gazetteer: ``data/gazetteer/`` (see ``scripts/run/fetch_gazetteer.sh``) or
``CASELINKER_GAZETTEER_DIR``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
GAZ_DIR = Path(os.environ.get("CASELINKER_GAZETTEER_DIR", "") or (ROOT / "data" / "gazetteer"))
OUT_DIR = ROOT / "scripts" / "explore" / "_grounding_out"
MANIFEST_NAME = "MANIFEST.json"
_HINT_POLICY_PATH = ROOT / "scripts" / "verify" / "extraction" / "hint_source_policy.json"


class GazetteerError(RuntimeError):
    """Pinned Census gazetteer missing, incomplete, or checksum mismatch."""


def demoted_hint_sources() -> frozenset[str]:
    """Hint sources demoted after precision < 95% on the frozen sample."""
    if not _HINT_POLICY_PATH.is_file():
        return frozenset()
    try:
        data = json.loads(_HINT_POLICY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return frozenset()
    return frozenset(data.get("demoted_hint_sources") or [])

STATE_NAME_TO_USPS = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "puerto rico": "PR",
}
USPS_TO_NAME = {v: k.title() for k, v in STATE_NAME_TO_USPS.items()}
USPS_SET = set(STATE_NAME_TO_USPS.values())

# Postal + AP / press abbreviations (after lowercasing + stripping periods)
ABBREV_TO_USPS = {
    "ala": "AL",
    "ariz": "AZ",
    "ark": "AR",
    "calif": "CA",
    "colo": "CO",
    "conn": "CT",
    "del": "DE",
    "fla": "FL",
    "ga": "GA",  # also USPS
    "ill": "IL",
    "ind": "IN",
    "kan": "KS",
    "kans": "KS",
    "ky": "KY",
    "la": "LA",
    "md": "MD",
    "mass": "MA",
    "mich": "MI",
    "minn": "MN",
    "miss": "MS",
    "mo": "MO",
    "mont": "MT",
    "neb": "NE",
    "nebr": "NE",
    "nev": "NV",
    "okla": "OK",
    "ore": "OR",
    "oreg": "OR",
    "pa": "PA",
    "penn": "PA",
    "tenn": "TN",
    "tex": "TX",
    "vt": "VT",
    "va": "VA",
    "wash": "WA",
    "wis": "WI",
    "wisc": "WI",
    "wyo": "WY",
    "dc": "DC",
    "d c": "DC",
    # dotted forms collapse to these after period strip / space
    "n j": "NJ",
    "n y": "NY",
    "n c": "NC",
    "n d": "ND",
    "n h": "NH",
    "n m": "NM",
    "s c": "SC",
    "s d": "SD",
    "w va": "WV",
    "w v": "WV",
    "r i": "RI",
}

# Explicit CaseLinker ``source`` → USPS (state AG / ICAC / state police / DPS).
SOURCE_TO_STATE: dict[str, str] = {
    "NJ AG": "NJ",
    "PA AG": "PA",
    "DE AG": "DE",
    "VT AG": "VT",
    "WA AG": "WA",
    "UT AG": "UT",
    "FL AG": "FL",
    "HI AG": "HI",
    "LA AG": "LA",
    "MS AG": "MS",
    "NM AG": "NM",
    "RI AG": "RI",
    "SD AG": "SD",
    "Texas AG": "TX",
    "ILLINOIS AG": "IL",
    "OHIO AG": "OH",
    "SCAG ICAC": "SC",
    "Idaho ICAC": "ID",
    "Michigan ICAC": "MI",
    "SOUTH FLORIDA ICAC": "FL",
    "NOVA ICAC": "VA",
    "SVICAC": "CA",  # Silicon Valley ICAC (San Jose)
    "AZICAC": "AZ",
    "TBI ICAC": "TN",
    "KY SP": "KY",
    "NEWYORK SP": "NY",
    "NE SP": "NE",
    "MDSP": "MD",
    "IA DCI": "IA",
    "WY DCI": "WY",
    "WI DOJ": "WI",
    "MT DOJ": "MT",
    "OREGON DOJ": "OR",
    "ARKANSAS DPS": "AR",
    "NC SBI": "NC",
    "MN BCA": "MN",
    "GBI": "GA",
    "ALEA": "AL",
    "ANCHORAGE PD": "AK",
    "NASHVILLE PD": "TN",
    "LA SP": "LA",
    "OCPO": "NJ",
    "KY AG": "KY",
    "MCAO": "AZ",
    "SACRAMENTO SO": "CA",
    "FRESNO SO": "CA",
    "LAPD": "CA",
    "SJPD": "CA",
    "SPD": "WA",
    "SDPD": "CA",  # San Diego PD (corpus usage)
    "CSPD": "CO",
    "LVMPD": "NV",
    "OSCEOLA SO": "FL",
    "SEDGWICK SO": "KS",
    "WCSO": "OR",  # Washington County SO (OR corpus cluster)
    "CCSAO": "IL",  # Cook County SAO
}

# Non-US press sources — locations counted as ``international``, not failures.
INTERNATIONAL_SOURCES = frozenset(
    {
        "NZ DIA",
        "BRAZIL PF",
        "SCOTLAND POLICE",
        "EUROPOL",
        "NBI",
        "AFP",
        "QPS",
        "GARDA",
        "NCA",
    }
)

# Federal / multi-state US sources — no default USPS; sentence / string / USAO only.
FEDERAL_SOURCES = frozenset(
    {
        "NCMEC",
        "DOJ SAFE CHILDHOOD",
        "DOJ CEOS",
        "DOJ ARCHIVES",
        "DOJ AI CSAM",
        "US MARSHALS",
        "USSS",
        "ICE",
        "ALERT ICE",
        "CBP",
        "AF OSI",
        "ARMY CID",
        "NCIS",
    }
)

_PLACE_SUFFIXES = (
    " city",
    " town",
    " village",
    " borough",
    " cdp",
    " municipality",
    " county",
    " parish",
)

_USAO_DISTRICT_RE = re.compile(
    r"(?i)\b(?:U\.?S\.?\s*Attorney(?:'s)?\s*(?:Office)?\s*(?:for\s+)?(?:the\s+)?"
    r"|USAO\s+(?:for\s+)?(?:the\s+)?)"
    r"(?:Southern|Northern|Eastern|Western|Middle|Central|District)?\s*"
    r"(?:District\s+of\s+)?"
    r"([A-Za-z .]+?)(?:\b|$)"
)

# Longest state names first for sentence scan
_STATE_NAMES_LONGEST = sorted(STATE_NAME_TO_USPS.keys(), key=len, reverse=True)


def _norm(text: str) -> str:
    s = text.strip().lower()
    s = s.replace("’", "'").replace("`", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"[.]", "", s)
    s = re.sub(r"[^a-z0-9'/\s-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip("'-").strip()
    return s


def strip_possessive(text: str) -> str:
    """New Jersey's → New Jersey; states' → states (caller re-norms)."""
    s = text.strip()
    s = re.sub(r"(?i)([A-Za-z])'s\b", r"\1", s)
    s = re.sub(r"(?i)([A-Za-z]s)'\b", r"\1", s)
    return s


def resolve_abbrev_token(tok: str) -> str | None:
    """Map a state token (name or AP/postal abbrev) to USPS."""
    tn = _norm(tok)
    if tn in STATE_NAME_TO_USPS:
        return STATE_NAME_TO_USPS[tn]
    if tn.endswith("'s"):
        base = tn[:-2].strip()
        if base in STATE_NAME_TO_USPS:
            return STATE_NAME_TO_USPS[base]
    compact = tn.replace(" ", "").upper()
    if compact in USPS_SET:
        return compact
    if tn in ABBREV_TO_USPS:
        return ABBREV_TO_USPS[tn]
    spaced = " ".join(tn)
    # N.J. → nj after period strip; already handled. Ky. → ky.
    return ABBREV_TO_USPS.get(tn)


def _strip_place_suffix(name: str) -> str:
    n = name
    for suf in _PLACE_SUFFIXES:
        if n.endswith(suf):
            return n[: -len(suf)].strip()
    return n


def _slug(label: str) -> str:
    s = label.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


@dataclass
class GazEntity:
    kind: str
    usps: str
    geoid: str
    name: str
    name_norm: str
    name_core: str


@dataclass
class MatchResult:
    raw: str
    slug: str
    state_hint: str | None
    status: str  # grounded | ungrounded | ambiguous | international
    reason: str
    fips: str | None = None
    entity_name: str | None = None
    entity_kind: str | None = None
    candidates: list[str] | None = None
    case_id: str | None = None
    hint_source: str | None = None  # sentence | string | source | usao | none


def gazetteer_dir(gaz_dir: Path | None = None) -> Path:
    if gaz_dir is not None:
        return Path(gaz_dir)
    env = os.environ.get("CASELINKER_GAZETTEER_DIR", "").strip()
    return Path(env) if env else GAZ_DIR


def gazetteer_available(gaz_dir: Path | None = None) -> bool:
    try:
        require_gazetteer(gaz_dir)
        return True
    except GazetteerError:
        return False


def require_gazetteer(gaz_dir: Path | None = None) -> dict:
    """Load and verify the pinned gazetteer MANIFEST + file checksums.

    Raises GazetteerError when anything is missing or the SHA-256 does not match.
    """
    import hashlib

    d = gazetteer_dir(gaz_dir)
    manifest_path = d / MANIFEST_NAME
    if not manifest_path.is_file():
        raise GazetteerError(
            f"Pinned gazetteer MANIFEST missing: {manifest_path}. "
            "Run scripts/run/fetch_gazetteer.sh or restore data/gazetteer/."
        )
    try:
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GazetteerError(f"Invalid gazetteer MANIFEST: {exc}") from exc
    files = meta.get("files") or {}
    if not files:
        raise GazetteerError("Gazetteer MANIFEST has no files entries.")
    for name, info in files.items():
        path = d / name
        if not path.is_file():
            raise GazetteerError(f"Pinned gazetteer file missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = (info.get("sha256") or "").strip().lower()
        if digest != expected:
            raise GazetteerError(
                f"Gazetteer checksum mismatch for {name}: "
                f"got {digest}, expected {expected}"
            )
        expected_bytes = info.get("bytes")
        if expected_bytes is not None and path.stat().st_size != int(expected_bytes):
            raise GazetteerError(
                f"Gazetteer size mismatch for {name}: "
                f"got {path.stat().st_size}, expected {expected_bytes}"
            )
    return meta


@lru_cache(maxsize=2)
def _load_gazetteer_cached(gaz_dir_str: str) -> dict[str, list[GazEntity]]:
    require_gazetteer(Path(gaz_dir_str))
    return load_gazetteer(Path(gaz_dir_str))


def load_gazetteer(gaz_dir: Path) -> dict[str, list[GazEntity]]:
    by_core: dict[str, list[GazEntity]] = defaultdict(list)

    def add(kind: str, usps: str, geoid: str, name: str) -> None:
        nn = _norm(name)
        core = _strip_place_suffix(nn)
        ent = GazEntity(kind, usps, geoid, name.strip(), nn, core)
        by_core[core].append(ent)
        if nn != core:
            by_core[nn].append(ent)

    with (gaz_dir / "2024_Gaz_state_national.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            usps = (row.get("USPS") or "").strip()
            geoid = (row.get("GEOID") or "").strip()
            name = (row.get("NAME") or "").strip()
            if usps and name:
                add("state", usps, geoid, name)
                by_core[_norm(usps)].append(
                    GazEntity("state", usps, geoid, name, _norm(name), _norm(usps))
                )

    with (gaz_dir / "2024_Gaz_counties_national.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            usps = (row.get("USPS") or "").strip()
            geoid = (row.get("GEOID") or "").strip()
            name = (row.get("NAME") or "").strip()
            if usps and geoid and name:
                add("county", usps, geoid, name)

    with (gaz_dir / "2024_Gaz_place_national.txt").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            usps = (row.get("USPS") or "").strip()
            geoid = (row.get("GEOID") or "").strip()
            name = (row.get("NAME") or "").strip()
            if usps and geoid and name:
                add("place", usps, geoid, name)

    return by_core


def detect_state_token(text: str) -> tuple[str | None, str]:
    """Return (USPS or None, remainder after stripping trailing state token)."""
    raw = strip_possessive(text.strip())
    m = re.search(r",\s*([A-Za-z .']+)$", raw)
    if m:
        usps = resolve_abbrev_token(m.group(1))
        if usps:
            return usps, raw[: m.start()].strip()
    tn = _norm(raw)
    usps = resolve_abbrev_token(raw)
    if usps and (
        tn in STATE_NAME_TO_USPS
        or tn.replace(" ", "").upper() in USPS_SET
        or tn in ABBREV_TO_USPS
        or (tn.endswith("'s") and tn[:-2].strip() in STATE_NAME_TO_USPS)
    ):
        return usps, raw
    return None, raw


def state_in_sentence(sentence: str) -> str | None:
    """Extract a state hint from a press sentence.

    Never treat bare two-letter postal codes as English whole words — ``in``
    is Indiana's USPS code and appears constantly as a preposition. Prefer
    full state names, AP abbreviations (``Ill.``, ``Ky.``), and dateline
    patterns (``City, ST`` / ``City, ST.``).
    """
    if not sentence:
        return None
    # District of Columbia before "Washington" state-name match
    if re.search(r"(?i)\b(?:washington\s*,\s*)?d\.?\s*c\.?\b|\bdistrict of columbia\b", sentence):
        return "DC"
    low = _norm(sentence)
    for name in _STATE_NAMES_LONGEST:
        if name == "washington" and re.search(r"\bd c\b|\bdistrict of columbia\b", low):
            continue
        if re.search(rf"\b{re.escape(name)}\b", low):
            return STATE_NAME_TO_USPS[name]
    # AP / postal abbreviations with letters (Ill., Ky., Calif.) — not 2-letter USPS
    for abbr, usps in ABBREV_TO_USPS.items():
        if len(abbr) <= 2:
            # Skip bare "la"/"or"/"me"/"ct"/… in running text; dateline handled below.
            # Also skip cybertip ids: "CT 190503924"
            continue
        if re.search(rf"\b{re.escape(abbr)}\b", low):
            return usps
    # Dateline / trailing ", ST" or ", ST." (original casing for 2-letter codes)
    m = re.search(
        r",\s*([A-Z]{2})\.?(?:\s|$|[—–\-]|\)|])",
        sentence,
    )
    if m and m.group(1).upper() in USPS_SET:
        return m.group(1).upper()
    # "COLUMBIA, S.C." already covered by AP; "Hanover, Va." via abbrev path
    m2 = re.search(r",\s*([A-Za-z]{2,})\.?(?:\s|$|[—–\-])", sentence)
    if m2:
        usps = resolve_abbrev_token(m2.group(1))
        if usps:
            return usps
    return None


def sentence_containing(text: str, needle: str) -> str | None:
    if not text or not needle:
        return None
    # Split on . ! ? keeping rough press sentences
    parts = re.split(r"(?<=[.!?])\s+", text)
    needle_l = needle.lower()
    for part in parts:
        if needle_l in part.lower():
            return part
    # fallback: window around first index
    idx = text.lower().find(needle_l)
    if idx < 0:
        return None
    start = max(0, idx - 160)
    end = min(len(text), idx + len(needle) + 160)
    return text[start:end]


def usao_state_from_text(text: str) -> str | None:
    if not text:
        return None
    m = _USAO_DISTRICT_RE.search(text)
    if not m:
        # looser: "Southern District of New York"
        m2 = re.search(
            r"(?i)\b(?:Southern|Northern|Eastern|Western|Middle|Central)\s+"
            r"District\s+of\s+([A-Za-z ]+)",
            text,
        )
        if not m2:
            return None
        return resolve_abbrev_token(m2.group(1).strip())
    return resolve_abbrev_token(m.group(1).strip())


def source_default_state(source: str | None) -> str | None:
    if not source:
        return None
    if source in SOURCE_TO_STATE:
        return SOURCE_TO_STATE[source]
    # fuzzy: "XX AG", "XX ICAC", "XX SP"
    su = source.strip()
    m = re.match(r"^([A-Z]{2})\s+(AG|ICAC|SP|DOJ|DPS|DCI|SBI|BCA)\b", su, re.I)
    if m and m.group(1).upper() in USPS_SET:
        return m.group(1).upper()
    return None


def is_international_source(source: str | None) -> bool:
    return (source or "") in INTERNATIONAL_SOURCES


def resolve_state_hint(
    *,
    loc: str,
    source: str | None,
    text: str,
) -> tuple[str | None, str]:
    """Return (USPS|None, hint_source). Sentence > string token > USAO > source."""
    sent = sentence_containing(text, loc)
    if sent:
        usps = state_in_sentence(sent)
        if usps:
            return usps, "sentence"
    usps_str, _ = detect_state_token(loc)
    if usps_str:
        return usps_str, "string"
    usps_usao = usao_state_from_text(text)
    if usps_usao:
        return usps_usao, "usao"
    usps_src = source_default_state(source)
    if usps_src:
        return usps_src, "source"
    return None, "none"


def classify_ungrounded(raw: str) -> str:
    tn = _norm(strip_possessive(raw))
    if not tn or len(tn) < 2:
        return "too_short"
    if re.fullmatch(r"[a-z]\s*[a-z]", tn) or re.fullmatch(r"[a-z]{1,2}", tn):
        # bare AP tokens like "ky" are states — not fragments
        if resolve_abbrev_token(tn):
            return "no_gazetteer_hit"
        return "abbreviation_fragment"
    if any(x in tn for x in ("http", "www", "@", "email")):
        return "non_geo_noise"
    if re.search(r"\d{3,}", tn):
        return "has_digits"
    if " " not in tn and len(tn) <= 3 and not resolve_abbrev_token(tn):
        return "fragment"
    return "no_gazetteer_hit"


def match_location(
    raw: str,
    by_core: dict[str, list[GazEntity]],
    state_hint: str | None = None,
    *,
    case_id: str | None = None,
    hint_source: str | None = None,
    international: bool = False,
) -> MatchResult:
    cleaned = strip_possessive(raw)
    slug = _slug(raw)
    if international:
        return MatchResult(
            raw,
            slug,
            state_hint,
            "international",
            "non_us_source",
            case_id=case_id,
            hint_source=hint_source,
        )

    usps_in_string, remainder = detect_state_token(cleaned)
    hint = (state_hint or usps_in_string or "").upper() or None
    if hint and hint not in USPS_SET:
        hint = resolve_abbrev_token(hint)

    tn = _norm(cleaned)
    # Bare "United States"/"USA"/"US" are usually title fragments
    # ("United States Attorney"), not country locations — abstain.
    if tn in {"united states", "usa", "us", "u s", "america"}:
        return MatchResult(
            raw,
            slug,
            hint,
            "ungrounded",
            "national_too_ambiguous",
            case_id=case_id,
            hint_source=hint_source,
        )
    if tn in {"united states of america", "u s a"}:
        return MatchResult(
            raw,
            slug,
            hint,
            "grounded",
            "national_entity",
            fips="US",
            entity_name="United States",
            entity_kind="country",
            case_id=case_id,
            hint_source=hint_source,
        )

    probe = _norm(remainder if (remainder != cleaned or usps_in_string) else cleaned)
    probe = strip_possessive(probe)
    probe = _norm(probe)
    # "Washington, D.C." / hint DC + "Washington" → District of Columbia, not WA
    dc_probe = bool(
        re.search(r"\bwashington\b", probe)
        and re.search(r"\b(d\.?\s*c\.?|district of columbia)\b", probe)
    ) or (hint == "DC" and probe in {"washington", "district of columbia", "d c", "dc"})
    if dc_probe:
        dc = [
            e
            for e in by_core.get("district of columbia", [])
            if e.kind == "state" or e.usps == "DC"
        ]
        if not dc:
            dc = [e for e in by_core.get("washington", []) if e.usps == "DC"]
        if dc:
            e = dc[0]
            return MatchResult(
                raw,
                slug,
                "DC",
                "grounded",
                "district_of_columbia",
                e.geoid,
                e.name,
                e.kind,
                case_id=case_id,
                hint_source=hint_source,
            )
    probe_core = _strip_place_suffix(probe)
    wants_county = bool(re.search(r"\bcounty\b", probe)) or bool(
        re.search(r"\bcounty\b", tn)
    )

    # Pure state / abbrev string
    usps_only = resolve_abbrev_token(cleaned) if not usps_in_string else usps_in_string
    if usps_only and (
        probe in STATE_NAME_TO_USPS
        or probe in ABBREV_TO_USPS
        or probe.replace(" ", "").upper() in USPS_SET
        or _norm(cleaned) in STATE_NAME_TO_USPS
        or _norm(cleaned) in ABBREV_TO_USPS
    ):
        # whole-string state
        whole = resolve_abbrev_token(cleaned)
        if whole and (
            _norm(cleaned) in STATE_NAME_TO_USPS
            or _norm(cleaned) in ABBREV_TO_USPS
            or _norm(cleaned).replace(" ", "").upper() in USPS_SET
        ):
            cands = [
                e
                for e in by_core.get(_norm(USPS_TO_NAME.get(whole, "")), [])
                if e.kind == "state"
            ]
            if not cands:
                cands = [e for e in by_core.get(_norm(whole), []) if e.kind == "state"]
            if cands:
                e = cands[0]
                return MatchResult(
                    raw,
                    slug,
                    whole,
                    "grounded",
                    "state_name",
                    e.geoid,
                    e.name,
                    e.kind,
                    case_id=case_id,
                    hint_source=hint_source,
                )

    candidates = list(by_core.get(probe_core, [])) + list(by_core.get(probe, []))
    # Census often stores "Boise City city" under core "boise city", not "boise".
    # Pull those place rows so bare "Boise" is not forced onto Boise County.
    for alt in (f"{probe_core} city", f"{probe} city", f"{probe_core} town", f"{probe} town"):
        candidates.extend(by_core.get(alt) or [])
    seen: set[str] = set()
    uniq: list[GazEntity] = []
    for e in candidates:
        if e.geoid in seen:
            continue
        seen.add(e.geoid)
        uniq.append(e)
    candidates = uniq

    if hint:
        filtered = [e for e in candidates if e.usps == hint]
        if filtered:
            candidates = filtered
        elif candidates:
            return MatchResult(
                raw,
                slug,
                hint,
                "ungrounded",
                "state_mismatch",
                candidates=[f"{e.geoid}:{e.name} ({e.usps})" for e in candidates[:5]],
                case_id=case_id,
                hint_source=hint_source,
            )

    # Explicit "… County" mentions must resolve to a county entity, never a city/CDP.
    if wants_county:
        counties = [e for e in candidates if e.kind == "county"]
        if len(counties) == 1:
            e = counties[0]
            return MatchResult(
                raw,
                slug,
                hint or e.usps,
                "grounded",
                "county_explicit",
                e.geoid,
                e.name,
                e.kind,
                case_id=case_id,
                hint_source=hint_source,
            )
        if len(counties) > 1:
            return MatchResult(
                raw,
                slug,
                hint,
                "ambiguous",
                "multi_county",
                candidates=[
                    f"{e.geoid}:{e.name} ({e.usps}/{e.kind})" for e in counties[:8]
                ],
                case_id=case_id,
                hint_source=hint_source,
            )
        return MatchResult(
            raw,
            slug,
            hint,
            "ungrounded",
            "county_no_gazetteer_hit",
            case_id=case_id,
            hint_source=hint_source,
        )

    if not candidates:
        reason = classify_ungrounded(cleaned)
        if reason == "no_gazetteer_hit" and not hint:
            reason = "no_state_hint"
        return MatchResult(
            raw,
            slug,
            hint,
            "ungrounded",
            reason,
            case_id=case_id,
            hint_source=hint_source,
        )

    if len(candidates) > 1:
        places = [e for e in candidates if e.kind == "place"]
        counties = [e for e in candidates if e.kind == "county"]
        # Bare "Boise"/"Peoria"/"Albany" must not silently become the county.
        # Prefer a unique place in-state; otherwise abstain.
        if places:
            if len(places) == 1:
                e = places[0]
                return MatchResult(
                    raw,
                    slug,
                    hint,
                    "grounded",
                    "place_in_state" if hint else "place_match",
                    e.geoid,
                    e.name,
                    e.kind,
                    case_id=case_id,
                    hint_source=hint_source,
                )
            return MatchResult(
                raw,
                slug,
                hint,
                "ambiguous",
                "multi_place",
                candidates=[
                    f"{e.geoid}:{e.name} ({e.usps}/{e.kind})" for e in places[:8]
                ],
                case_id=case_id,
                hint_source=hint_source,
            )
        if len(counties) == 1 and hint:
            e = counties[0]
            return MatchResult(
                raw,
                slug,
                hint,
                "grounded",
                "county_in_state",
                e.geoid,
                e.name,
                e.kind,
                case_id=case_id,
                hint_source=hint_source,
            )
        return MatchResult(
            raw,
            slug,
            hint,
            "ambiguous",
            "multi_fips",
            candidates=[f"{e.geoid}:{e.name} ({e.usps}/{e.kind})" for e in candidates[:8]],
            case_id=case_id,
            hint_source=hint_source,
        )

    e = candidates[0]
    why = f"{e.kind}_in_state" if hint else f"{e.kind}_match"
    return MatchResult(
        raw,
        slug,
        hint,
        "grounded",
        why,
        e.geoid,
        e.name,
        e.kind,
        case_id=case_id,
        hint_source=hint_source,
    )


def ground_to_dict(
    result: MatchResult,
    *,
    gazetteer_version: str,
    readable_slug: str | None = None,
) -> Dict[str, Any]:
    """JSON-serializable ground record stored on the case as ``location_grounds``."""
    return {
        "mention": result.raw,
        "slug": readable_slug or result.slug,
        "status": result.status,
        "reason": result.reason,
        "fips": result.fips,
        "geoid": result.fips,
        "entity_name": result.entity_name,
        "entity_kind": result.entity_kind,
        "state_hint": result.state_hint,
        "hint_source": result.hint_source,
        "gazetteer_version": gazetteer_version,
    }


def readable_location_slug(
    *,
    entity_name: str | None,
    mention: str,
    state_hint: str | None,
    fips: str | None,
    entity_kind: str | None,
    collision_slugs: set[str] | None = None,
) -> str:
    """Build ``cumberland-county-nj`` (append GEOID when still colliding)."""
    if (fips or "").upper() in {"US", "USA"}:
        return "united-states"
    label = (entity_name or mention or "").strip()
    core = _slug(label).replace("_", "-")
    # Drop trailing -county duplication when kind is county and name already has it
    st = (state_hint or "").strip().lower()
    if st and not core.endswith(f"-{st}"):
        base = f"{core}-{st}"
    else:
        base = core
    collisions = collision_slugs or set()
    if base in collisions and fips:
        return f"{base}-{fips}"
    return base


def ground_case_locations(
    locations: List[Any],
    *,
    source: Optional[str] = None,
    case_text: str = "",
    case_id: Optional[str] = None,
    gaz_dir: Path | None = None,
) -> List[Dict[str, Any]]:
    """Ground each location mention for one case.

    Requires the pinned gazetteer (raises GazetteerError if missing/corrupt).
    Demoted hint sources never finalize — they become ``ambiguous``.
    """
    d = gazetteer_dir(gaz_dir)
    meta = require_gazetteer(d)
    version = str(meta.get("version") or "unknown")
    intl = is_international_source(source)
    clean = [str(x).strip() for x in (locations or []) if x and str(x).strip()]
    if not clean:
        return []
    by_core = _load_gazetteer_cached(str(d.resolve()))
    demoted = demoted_hint_sources()
    out: List[Dict[str, Any]] = []
    used_slugs: set[str] = set()
    for loc in clean:
        hint, hsrc = resolve_state_hint(loc=loc, source=source, text=case_text or "")
        # Demoted hint sources cannot supply the only state signal — fall back.
        if hsrc in demoted:
            hint2, hsrc2 = None, None
            usps_str, _ = detect_state_token(loc)
            if usps_str and "string" not in demoted:
                hint2, hsrc2 = usps_str, "string"
            if hint2 is None:
                usps_usao = usao_state_from_text(case_text or "")
                if usps_usao and "usao" not in demoted:
                    hint2, hsrc2 = usps_usao, "usao"
            if hint2 is None:
                usps_src = source_default_state(source)
                if usps_src and "source" not in demoted:
                    hint2, hsrc2 = usps_src, "source"
            if hint2 is not None:
                hint, hsrc = hint2, hsrc2
            elif resolve_abbrev_token(loc):
                # Mention is itself a state abbrev/name — match without a demoted hint.
                hint, hsrc = None, "none"
            else:
                mr = MatchResult(
                    loc,
                    _slug(loc),
                    hint,
                    "ambiguous",
                    "demoted_hint_source",
                    case_id=case_id,
                    hint_source=hsrc,
                )
                out.append(ground_to_dict(mr, gazetteer_version=version))
                continue
        mr = match_location(
            loc,
            by_core,
            state_hint=hint,
            case_id=case_id,
            hint_source=hsrc,
            international=intl,
        )
        # If the winning hint source is demoted, refuse to ground
        if mr.status == "grounded" and (mr.hint_source or "") in demoted:
            mr = MatchResult(
                mr.raw,
                mr.slug,
                mr.state_hint,
                "ambiguous",
                "demoted_hint_source",
                fips=mr.fips,
                entity_name=mr.entity_name,
                entity_kind=mr.entity_kind,
                case_id=case_id,
                hint_source=mr.hint_source,
            )
        slug = None
        if mr.status == "grounded" and mr.fips:
            slug = readable_location_slug(
                entity_name=mr.entity_name,
                mention=mr.raw,
                state_hint=mr.state_hint,
                fips=mr.fips,
                entity_kind=mr.entity_kind,
                collision_slugs=used_slugs,
            )
            used_slugs.add(slug)
        out.append(ground_to_dict(mr, gazetteer_version=version, readable_slug=slug))
    return out


def load_corpus_locations(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, source, extracted_features, raw_data FROM cases "
        "WHERE extracted_features IS NOT NULL"
    ).fetchall()
    out = []
    for r in rows:
        try:
            feats = json.loads(r["extracted_features"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(feats, dict):
            continue
        parsed = feats.get("locations") or []
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError:
                parsed = [parsed]
        if not isinstance(parsed, list):
            continue
        text = ""
        raw = r["raw_data"]
        if isinstance(raw, str) and raw:
            try:
                blob = json.loads(raw)
                if isinstance(blob, dict):
                    text = (
                        blob.get("case_text")
                        or blob.get("text")
                        or blob.get("full_text")
                        or ""
                    )
                else:
                    text = raw[:8000]
            except json.JSONDecodeError:
                text = raw[:8000]
        clean = [str(x).strip() for x in parsed if x and str(x).strip()]
        if not clean:
            continue
        out.append(
            {
                "case_id": r["id"],
                "source": r["source"],
                "locations": clean,
                "text": text,
                "international": is_international_source(r["source"]),
            }
        )
    conn.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=ROOT / "caselinker.db")
    ap.add_argument("--gaz-dir", type=Path, default=GAZ_DIR)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if not args.gaz_dir.is_dir():
        print(f"Missing gazetteer dir: {args.gaz_dir}", file=sys.stderr)
        return 1
    if not args.db.is_file():
        print(f"Missing db: {args.db}", file=sys.stderr)
        return 1

    by_core = load_gazetteer(args.gaz_dir)
    cases = load_corpus_locations(args.db)

    # --- Prior split-risk set (v1 report style, ~1.5k slugs):
    # slug seen under ≥2 distinct old-style case hints, excluding pure state strings.
    def _old_case_hint(case: dict) -> str | None:
        src = source_default_state(case["source"])
        if src:
            return src
        m = re.match(r"^([a-z]{2})[_-]", (case["source"] or "").lower())
        if m and m.group(1).upper() in USPS_SET:
            return m.group(1).upper()
        for loc in case["locations"]:
            usps, _ = detect_state_token(loc)
            if usps:
                return usps
        low = (case["text"] or "").lower()
        for name, usps in STATE_NAME_TO_USPS.items():
            if name in low:
                return usps
        return None

    def _is_state_string(raw: str) -> bool:
        tn = _norm(strip_possessive(raw))
        if tn in {"united states", "usa", "us", "u s", "america"}:
            return True
        return bool(
            resolve_abbrev_token(raw)
            and (
                tn in STATE_NAME_TO_USPS
                or tn in ABBREV_TO_USPS
                or tn.replace(" ", "").upper() in USPS_SET
            )
        )

    slug_old_hints: dict[str, Counter] = defaultdict(Counter)
    slug_raws: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        if case["international"]:
            continue
        hint = _old_case_hint(case)
        for loc in case["locations"]:
            slug = _slug(loc)
            slug_raws[slug].add(loc)
            if hint:
                slug_old_hints[slug][hint] += 1
    prior_split_slugs: set[str] = set()
    for slug, hints in slug_old_hints.items():
        if len(hints) < 2:
            continue
        raw = sorted(slug_raws[slug], key=lambda s: (-len(s), s))[0]
        if _is_state_string(raw):
            continue
        prior_split_slugs.add(slug)

    # --- Per (case, location) matching
    per_case: list[MatchResult] = []
    hint_source_counts: Counter[str] = Counter()
    for case in cases:
        for loc in case["locations"]:
            hint, hsrc = resolve_state_hint(
                loc=loc, source=case["source"], text=case["text"]
            )
            hint_source_counts[hsrc] += 1
            per_case.append(
                match_location(
                    loc,
                    by_core,
                    state_hint=hint,
                    case_id=case["case_id"],
                    hint_source=hsrc,
                    international=case["international"],
                )
            )

    status_counts = Counter(r.status for r in per_case)
    reason_counts = Counter(
        r.reason for r in per_case if r.status not in {"grounded", "international"}
    )

    # Split-risk resolution: among prior_split_slugs, how many have every
    # US case-occurrence grounded to exactly one FIPS?
    slug_case_fips: dict[str, dict[str, set[str | None]]] = defaultdict(
        lambda: defaultdict(set)
    )
    slug_case_status: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for r in per_case:
        if r.status == "international":
            continue
        if r.slug not in prior_split_slugs:
            continue
        cid = r.case_id or "?"
        slug_case_fips[r.slug][cid].add(r.fips if r.status == "grounded" else None)
        slug_case_status[r.slug][cid].add(r.status)

    resolved_one_place_per_case = 0
    still_split = 0
    for slug in prior_split_slugs:
        cases_map = slug_case_status.get(slug, {})
        if not cases_map:
            continue
        ok = True
        for cid, statuses in cases_map.items():
            if statuses != {"grounded"}:
                ok = False
                break
            fips_set = slug_case_fips[slug][cid]
            if len(fips_set) != 1 or None in fips_set:
                ok = False
                break
        if ok:
            resolved_one_place_per_case += 1
        else:
            still_split += 1

    # Distinct FIPS per resolved split slug (should often be >1 across cases)
    multi_fips_after: list[tuple[str, int]] = []
    for slug in prior_split_slugs:
        all_fips = {
            f
            for cid, fs in slug_case_fips.get(slug, {}).items()
            for f in fs
            if f
        }
        if len(all_fips) > 1 and slug in {
            s
            for s in prior_split_slugs
            if all(
                slug_case_status[s][c] == {"grounded"}
                for c in slug_case_status.get(s, {})
            )
        }:
            multi_fips_after.append((slug, len(all_fips)))

    print(f"cases_with_locations: {len(cases)}")
    print(f"case_location_rows: {len(per_case)}")
    print(f"status (per case×location): {dict(status_counts)}")
    print(f"hint_sources: {dict(hint_source_counts)}")
    print("ungrounded/ambiguous reasons (excl. international):")
    for reason, n in reason_counts.most_common(15):
        print(f"  {n:5d}  {reason}")
    print(f"prior_split_risk_slugs: {len(prior_split_slugs)}")
    print(
        f"split_slugs_now_one_place_per_case: {resolved_one_place_per_case} "
        f"/ {len(prior_split_slugs)} (still unresolved: {still_split})"
    )
    print(f"resolved_split_slugs_with_multiple_fips_across_cases: {len(multi_fips_after)}")
    for slug, n in sorted(multi_fips_after, key=lambda x: -x[1])[:8]:
        print(f"  {slug}: {n} distinct FIPS")

    # Cumberland sanity
    cumberland = [r for r in per_case if "cumberland" in r.slug][:12]
    if cumberland:
        print("cumberland sample:")
        for r in cumberland:
            print(
                f"  {r.case_id} {r.raw!r} → {r.status}/{r.reason} "
                f"fips={r.fips} hint={r.state_hint}/{r.hint_source}"
            )

    if args.report:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "cases_with_locations": len(cases),
            "case_location_rows": len(per_case),
            "status_counts": dict(status_counts),
            "hint_source_counts": dict(hint_source_counts),
            "reason_counts": dict(reason_counts),
            "prior_split_risk_slugs": len(prior_split_slugs),
            "split_slugs_resolved_one_place_per_case": resolved_one_place_per_case,
            "split_slugs_still_unresolved": still_split,
            "sample_international": [
                asdict(r) for r in per_case if r.status == "international"
            ][:40],
            "sample_ungrounded": [
                asdict(r) for r in per_case if r.status == "ungrounded"
            ][:60],
            "sample_grounded": [
                asdict(r) for r in per_case if r.status == "grounded"
            ][:40],
        }
        (OUT_DIR / "location_grounding.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        g = status_counts.get("grounded", 0)
        a = status_counts.get("ambiguous", 0)
        u = status_counts.get("ungrounded", 0)
        intl = status_counts.get("international", 0)
        md = [
            "# Location grounding prototype report (v2)",
            "",
            f"- Cases with locations: **{len(cases)}**",
            f"- Case×location rows: **{len(per_case)}**",
            f"- Grounded: **{g}**",
            f"- Ambiguous: **{a}**",
            f"- Ungrounded (US failures): **{u}**",
            f"- International (excluded from failures): **{intl}**",
            f"- Prior split-risk slugs: **{len(prior_split_slugs)}**",
            f"- Of those, now one place per case: **{resolved_one_place_per_case}** "
            f"(still unresolved: **{still_split}**)",
            "",
            "## Hint sources",
            "",
        ]
        for k, n in hint_source_counts.most_common():
            md.append(f"- `{k}` — {n}")
        md.extend(["", "## Top failure reasons (US only)", ""])
        for reason, n in reason_counts.most_common(20):
            ex = next((r.raw for r in per_case if r.reason == reason), "")
            md.append(f"- `{reason}` — {n} (e.g. {ex!r})")
        (OUT_DIR / "location_grounding.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"wrote {OUT_DIR / 'location_grounding.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
