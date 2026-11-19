#!/usr/bin/env python3
"""Authority grounding for agency *mentions* → FBI CDE ORI or federal table.

Post-extract linker (parallel to location_grounding). Requires a pinned
``data/agency_registry/`` snapshot; missing registry raises AgencyRegistryError.

Statuses: grounded | ambiguous | ungrounded | out_of_scope
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
REG_DIR = Path(
    os.environ.get("CASELINKER_AGENCY_REGISTRY_DIR", "") or (ROOT / "data" / "agency_registry")
)
MANIFEST_NAME = "MANIFEST.json"

# Hand-curated international / non-US agencies — not in FBI CDE.
# Matched before CDE; status is out_of_scope (not ungrounded).
_INTERNATIONAL: list[tuple[str, str, tuple[str, ...]]] = [
    ("NCA", "National Crime Agency", ("nca", "national crime agency", "uk nca")),
    ("Europol", "Europol", ("europol", "european police office")),
    (
        "AFP",
        "Australian Federal Police",
        ("afp", "australian federal police", "australia federal police"),
    ),
    (
        "Garda",
        "Garda Síochána",
        ("garda", "garda siochana", "garda síochána", "an garda siochana"),
    ),
    (
        "NZ_DIA",
        "NZ DIA",
        (
            "nz dia",
            "new zealand dia",
            "department of internal affairs",
            "nz department of internal affairs",
        ),
    ),
    ("Police_Scotland", "Police Scotland", ("police scotland", "scottish police")),
    (
        "Philippines_NBI",
        "Philippines NBI",
        (
            "philippines nbi",
            "nbi philippines",
            "national bureau of investigation",
            "philippine nbi",
        ),
    ),
    (
        "Brazil_PF",
        "Brazil Federal Police",
        (
            "brazil federal police",
            "brazilian federal police",
            "policia federal",
            "polícia federal",
            "pf brazil",
        ),
    ),
    (
        "Alberta_ALERT",
        "Alberta ALERT",
        ("alberta alert", "alert alberta", "alberta law enforcement response teams"),
    ),
    (
        "Queensland_Police",
        "Queensland Police",
        ("queensland police", "queensland police service", "qps"),
    ),
]

_GENERIC_EXACT = frozenset(
    {
        "sheriff s office",
        "sheriffs office",
        "sheriff s department",
        "sheriffs department",
        "sheriff office",
        "sheriff department",
        "police department",
        "police dept",
        "task force",
        "the task force",
        "local police",
        "local authorities",
        "authorities",
        "law enforcement",
    }
)


class AgencyRegistryError(RuntimeError):
    """Pinned FBI CDE / federal agency registry missing or checksum mismatch."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def require_agency_registry(reg_dir: Path | None = None) -> dict:
    d = Path(reg_dir) if reg_dir is not None else REG_DIR
    man = d / MANIFEST_NAME
    if not man.is_file():
        raise AgencyRegistryError(
            f"Agency registry MANIFEST missing at {man}. "
            "Run scripts/run/fetch_agency_registry.sh"
        )
    try:
        meta = json.loads(man.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgencyRegistryError(f"Invalid agency MANIFEST: {exc}") from exc
    files = meta.get("files") or {}
    if not files:
        raise AgencyRegistryError("Agency MANIFEST has no files entries.")
    for name, info in files.items():
        if info is None:
            continue
        path = d / name
        if not path.is_file():
            raise AgencyRegistryError(f"Pinned agency registry file missing: {path}")
        expected = (info or {}).get("sha256")
        if expected:
            got = _sha256_file(path)
            if got != expected:
                raise AgencyRegistryError(
                    f"Checksum mismatch for {path.name}: expected {expected}, got {got}"
                )
        expected_bytes = (info or {}).get("bytes")
        if expected_bytes is not None and path.stat().st_size != expected_bytes:
            raise AgencyRegistryError(
                f"Byte-size mismatch for {path.name}: "
                f"expected {expected_bytes}, got {path.stat().st_size}"
            )
    return meta


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return s or "unknown"


def normalize_agency_name(name: str) -> str:
    """Expand PD / SO abbreviations and normalize possessives for matching."""
    s = (name or "").strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\bP\.?\s*D\.?\b", "Police Department", s, flags=re.I)
    s = re.sub(r"\bPolice Dept\.?\b", "Police Department", s, flags=re.I)
    s = re.sub(r"\bS\.?\s*O\.?\b", "Sheriff's Office", s, flags=re.I)
    s = re.sub(r"\bSheriff'?s?\s+Dept\.?\b", "Sheriff's Office", s, flags=re.I)
    s = re.sub(r"\bSheriff'?s?\s+Department\b", "Sheriff's Office", s, flags=re.I)
    s = re.sub(r"\bSheriff Office\b", "Sheriff's Office", s, flags=re.I)
    s = re.sub(r"\bSO\b", "Sheriff's Office", s)
    return s.strip()


def _norm_key(name: str) -> str:
    s = normalize_agency_name(name).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s.startswith("the "):
        s = s[4:]
    # Align common press variants with CDE wording
    s = re.sub(r"\bsheriff s department\b", "sheriff s office", s)
    s = re.sub(r"\bsheriffs department\b", "sheriff s office", s)
    return s


def _lookup_keys(norm: str) -> list[str]:
    """Exact-match keys to try against the CDE index (no soft locality prefix)."""
    keys = [norm]
    # Homedale City PD ↔ Homedale PD
    keys.append(re.sub(r"\bcity police department\b", "police department", norm))
    keys.append(re.sub(r"\btownship police department\b", "police department", norm))
    # Toms River PD ↔ Toms River Township Police Department
    m = re.match(r"^(.+) police department$", norm)
    if m:
        base = m.group(1).strip()
        if base and "township" not in base:
            keys.append(f"{base} township police department")
        if base.endswith(" township"):
            keys.append(f"{base[: -len(' township')]} police department")
    # de-dupe preserving order
    out: list[str] = []
    seen: set[str] = set()
    for k in keys:
        k = re.sub(r"\s+", " ", k).strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


# Mentions that are real orgs but outside FBI CDE (prosecutors, courts, …)
_OUT_OF_REGISTRY = re.compile(
    r"(?i)\b("
    r"prosecutor|prosecuting attorney|district attorney|state'?s? attorney|"
    r"commonwealth'?s? attorney|county attorney|corporation counsel|"
    r"attorney general|office of the attorney general|"
    r"superior court|circuit court|district court|municipal court|"
    r"family court|juvenile court|supreme court|court of|"
    r"public defender|probation (department|office)|parole (board|office)|"
    r"department of corrections|department of justice|"
    r"high tech crimes? bureau|financial.?computer crimes"
    r")\b"
)


def is_generic_agency_mention(mention: str) -> bool:
    key = _norm_key(mention)
    if key in _GENERIC_EXACT:
        return True
    # bare "sheriff" / "police" without a place name
    if key in {"sheriff", "police", "deputies", "officers"}:
        return True
    return False


def match_international(mention: str) -> dict | None:
    key = _norm_key(mention)
    for code, canonical, aliases in _INTERNATIONAL:
        alias_keys = {_norm_key(a) for a in aliases} | {_norm_key(canonical), _norm_key(code)}
        if key in alias_keys:
            return {
                "mention": mention,
                "status": "out_of_scope",
                "reason": "international_agency",
                "code": code,
                "agency_name": canonical,
                "agency_kind": "international",
                "state_hint": None,
                "hint_source": "international",
                "slug": _slug(canonical).replace("_", "-"),
            }
        # Short aliases (≤4 chars: qps, afp, nca, …) are exact-match only —
        # never substring, to avoid guessing on US text.
        for ak in alias_keys:
            if len(ak) <= 4:
                continue
            if key.startswith(ak + " ") or re.search(rf"\b{re.escape(ak)}\b", key):
                return {
                    "mention": mention,
                    "status": "out_of_scope",
                    "reason": "international_agency",
                    "code": code,
                    "agency_name": canonical,
                    "agency_kind": "international",
                    "state_hint": None,
                    "hint_source": "international",
                    "slug": _slug(canonical).replace("_", "-"),
                }
    return None


_STATE_ABBREV_DOTTED = re.compile(r"\b([A-Z])\.\s?([A-Z])\.")
# National bodies the federal table does not list yet. One node each is right.
_NATIONAL_LABEL = re.compile(
    r"\bU\.?\s?S\.?(?=\s|$)|\bUnited\s+States\b|\bFederal\b|\bNational\b|\bHomeland\s+Security\b"
    r"|\bJustice\s+Department\b|^\s*(?:the\s+)?Department\s+of\s+Justice\b|\bSecret\s+Service\b"
    r"|\bBureau\s+of\s+Prisons\b|\bPostal\b|\bMarshals\b|\bCustoms\b|\bImmigration\b",
    re.IGNORECASE,
)


def _names_a_state(mention: str) -> bool:
    """True when the label carries its own state ("Kentucky State Police", "S.C. Attorney General's Office")."""
    from location_grounding import STATE_NAME_TO_USPS

    low = f" {re.sub(r'[^a-z]+', ' ', mention.lower())} "
    for name in STATE_NAME_TO_USPS:
        # "Washington County Sheriff's Office" names a county, in any of thirty states.
        if re.search(rf" {re.escape(name.lower())} (?!(?:county|parish|township|borough|city) )", low):
            return True
    codes = set(STATE_NAME_TO_USPS.values())
    return any((a + b) in codes for a, b in _STATE_ABBREV_DOTTED.findall(mention))


def ungrounded_agency_scope(mention: str, ground: Optional[Dict[str, Any]], *, federal: bool = False) -> str:
    """How far an agency label that is not grounded may be shared across cases (#58).

    ``shared``  one node for every case: federal and national bodies, international
                agencies, and labels that name their own state.
    ``state``   one node per source state, marked unverified: "Attorney General's Office"
                or "Springfield Police Department" in an NJ release. The state is where
                the release came from, not a checked fact about the agency.
    ``case``    one node per case: the source has no state (federal and aggregate
                releases), so nothing ties "Springfield Police Department" or
                "Sheriff's Department" there to the same words in another case.
    """
    gnd = ground or {}
    if federal or gnd.get("status") == "out_of_scope" or _NATIONAL_LABEL.search(mention) or _names_a_state(mention):
        return "shared"
    return "state" if (gnd.get("state_hint") or "").strip() else "case"


def unverified_state_slug(slug: str, state_hint: str) -> str:
    """``attorney-generals-office-nj-unverified``: never equal to a grounded ``{name}-{st}`` slug."""
    return f"{slug}-{state_hint.strip().lower()}-unverified"


def readable_agency_slug(
    *,
    agency_name: str,
    state_hint: str | None,
    ori: str | None,
    collision_slugs: set[str] | None = None,
) -> str:
    core = _slug(agency_name).replace("_", "-")
    st = (state_hint or "").strip().lower()
    if st and not core.endswith(f"-{st}"):
        base = f"{core}-{st}"
    else:
        base = core
    collisions = collision_slugs or set()
    if base in collisions and ori:
        return f"{base}-{_slug(ori)}"
    return base


@lru_cache(maxsize=4)
def _load_registry_cached(reg_dir_str: str) -> tuple[dict, dict, str]:
    """Return (federal_by_alias, cde_by_state_norm, version)."""
    d = Path(reg_dir_str)
    meta = require_agency_registry(d)
    version = str(meta.get("version") or "unknown")
    fed_path = d / "federal_agencies.json"
    federal_by_alias: dict[str, dict] = {}
    if fed_path.is_file():
        fed = json.loads(fed_path.read_text(encoding="utf-8"))
        for row in fed.get("agencies") or []:
            for alias in [row.get("canonical"), *(row.get("aliases") or [])]:
                if alias:
                    federal_by_alias[_norm_key(str(alias))] = row
    snap_name = None
    for name in (meta.get("files") or {}):
        if str(name).startswith("cde_agencies_") and str(name).endswith(".json"):
            snap_name = name
            break
    cde_by_state: dict[str, dict[str, list[dict]]] = {}
    if snap_name:
        snap = json.loads((d / snap_name).read_text(encoding="utf-8"))
        for ag in snap.get("agencies") or []:
            st = (ag.get("state_abbr") or "").upper()
            key = _norm_key(ag.get("agency_name") or "")
            if not st or not key:
                continue
            cde_by_state.setdefault(st, {}).setdefault(key, []).append(ag)
            short = re.sub(
                r"\b(police department|sheriff s office|sheriffs office)\b",
                "",
                key,
            ).strip()
            if short and short != key:
                cde_by_state[st].setdefault(short, []).append(ag)
    return federal_by_alias, cde_by_state, version


def _state_hint_from_source(source: Optional[str]) -> str | None:
    import importlib.util
    import sys

    path = Path(__file__).parent / "location_grounding.py"
    mod = sys.modules.get("location_grounding")
    if mod is None or not hasattr(mod, "source_default_state"):
        spec = importlib.util.spec_from_file_location("location_grounding", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        sys.modules["location_grounding"] = mod
        spec.loader.exec_module(mod)
    return mod.source_default_state(source)


def _grounded_counties(location_grounds: list | None) -> list[dict]:
    out = []
    for gnd in location_grounds or []:
        if not isinstance(gnd, dict):
            continue
        if gnd.get("status") != "grounded":
            continue
        if (gnd.get("entity_kind") or "") != "county":
            continue
        name = (gnd.get("entity_name") or "").strip()
        st = (gnd.get("state_hint") or "").strip().upper()
        if name and st:
            out.append({"entity_name": name, "state_hint": st, "fips": gnd.get("fips")})
    return out


def _try_county_sheriff(
    *,
    state_hint: str,
    counties: list[dict],
    cde_by_state: dict,
    mention: str,
) -> dict | None:
    """Resolve bare 'Sheriff's Department' via a unique grounded county in-state."""
    st = state_hint.upper()
    bucket = cde_by_state.get(st) or {}
    in_state = [c for c in counties if c["state_hint"] == st]
    if len(in_state) != 1:
        return None
    county = in_state[0]["entity_name"]
    # "Cumberland County" → try "Sheriff: Cumberland County" / "Cumberland County Sheriff's Office"
    probes = [
        f"{county} Sheriff's Office",
        f"Sheriff: {county}",
        f"Sheriff {county}",
        county.replace(" County", "") + " County Sheriff's Office",
    ]
    hits: list[dict] = []
    for probe in probes:
        hits.extend(bucket.get(_norm_key(probe)) or [])
    # Also scan keys containing county core + sheriff
    core = _norm_key(county.replace(" County", ""))
    for k, rows in bucket.items():
        if "sheriff" in k and core and core in k:
            hits.extend(rows)
    oris = {r.get("ori") for r in hits if r.get("ori")}
    if len(oris) != 1:
        return None
    hit = next(r for r in hits if r.get("ori") in oris)
    name = hit.get("agency_name") or f"{county} Sheriff's Office"
    return {
        "mention": mention,
        "status": "grounded",
        "reason": "generic_via_grounded_county",
        "ori": hit.get("ori"),
        "agency_name": name,
        "agency_type": hit.get("agency_type_name"),
        "county": hit.get("county") or hit.get("counties"),
        "agency_kind": "local",
        "state_hint": st,
        "hint_source": "county",
        "slug": readable_agency_slug(
            agency_name=name, state_hint=st, ori=hit.get("ori")
        ),
    }


_STATE_POLICE_KEY = re.compile(r"^(?:(?P<state>.+) )?state police(?: department)?$")


def _state_police_state(key: str, state_hint: str | None) -> str | None:
    """USPS code a state-police mention names, or the source state for a bare "State Police"."""
    from location_grounding import STATE_NAME_TO_USPS

    m = _STATE_POLICE_KEY.match(key)
    if not m:
        return None
    named = (m.group("state") or "").strip()
    if not named:
        return state_hint.upper() if state_hint else None
    if named in STATE_NAME_TO_USPS:
        return STATE_NAME_TO_USPS[named]
    compact = named.replace(" ", "").upper()
    return compact if len(compact) == 2 and compact in set(STATE_NAME_TO_USPS.values()) else None


def match_state_police(mention: str, *, state_hint: str | None, cde_by_state: dict) -> dict | None:
    """Ground "<State> State Police" to that state's CDE state police (#59).

    CDE lists state police three ways: one statewide row (NY, IN, IL, AR, CT, LA), a
    "Headquarters" row (DE), or posts and counties only (KY, NJ, MI, PA, ...). The first two
    ground to that row's ORI. Posts-only states ground to the statewide agency with no ORI,
    as the federal table does. A state whose CDE state police is not named "State Police"
    (a highway patrol, a state patrol) is left ungrounded: the mention does not name it.
    """
    raw = (mention or "").strip()
    key = _norm_key(raw)
    if not _STATE_POLICE_KEY.match(key):
        return None
    st = _state_police_state(key, state_hint)
    if not st:
        return None
    from location_grounding import STATE_NAME_TO_USPS

    rows: dict[str, dict] = {}
    for bucket_rows in (cde_by_state.get(st) or {}).values():
        for row in bucket_rows:
            if row.get("agency_type_name") == "State Police" and row.get("ori"):
                rows[row["ori"]] = row
    named = [r for r in rows.values() if "state police" in (r.get("agency_name") or "").lower()]
    state_name = next((n.title() for n, c in STATE_NAME_TO_USPS.items() if c == st), st)
    base = {"mention": raw, "state_hint": st, "hint_source": "mention" if _names_a_state(raw) else "source"}
    if not named:
        return {**base, "status": "ungrounded", "reason": "no_cde_state_police"}
    hit = None
    if len(named) == 1:
        hit = named[0]
    else:
        hq = [r for r in named if "headquarters" in (r.get("agency_name") or "").lower()]
        if len(hq) == 1:
            hit = hq[0]
    name = f"{state_name} State Police"
    if hit is not None:
        return {
            **base,
            "status": "grounded",
            "reason": "cde_state_police",
            "ori": hit["ori"],
            "agency_name": name,
            "cde_agency_name": (hit.get("agency_name") or "").strip(),
            "agency_type": hit.get("agency_type_name"),
            "agency_kind": "state",
            "slug": readable_agency_slug(agency_name=name, state_hint=st, ori=hit["ori"]),
        }
    return {
        **base,
        "status": "grounded",
        "reason": "state_police_statewide",
        "ori": None,
        "agency_name": name,
        "agency_type": "State Police",
        "agency_kind": "state",
        "cde_posts": len(named),
        "slug": readable_agency_slug(agency_name=name, state_hint=st, ori=None),
    }


def match_agency(
    mention: str,
    *,
    state_hint: str | None,
    federal_by_alias: dict,
    cde_by_state: dict,
    location_grounds: list | None = None,
) -> dict:
    raw = (mention or "").strip()
    if not raw:
        return {
            "mention": raw,
            "status": "ungrounded",
            "reason": "empty",
            "state_hint": state_hint,
            "hint_source": "source" if state_hint else None,
        }

    intl = match_international(raw)
    if intl is not None:
        return intl

    key = _norm_key(raw)

    # Federal / national table
    fed = federal_by_alias.get(key)
    if fed is None:
        for alias_key, row in federal_by_alias.items():
            if len(alias_key) < 3:
                continue
            # Short codes (DOJ, FBI, HSI, …): exact or prefix ("FBI Newark") only
            if len(alias_key) <= 4:
                if key == alias_key or key.startswith(alias_key + " "):
                    fed = row
                    break
                continue
            # Long aliases: exact / prefix; word-boundary only when alias is the
            # whole remaining phrase start (avoids "Wisconsin … Department of Justice")
            if key == alias_key or key.startswith(alias_key + " "):
                fed = row
                break
            if re.search(rf"^{re.escape(alias_key)}\b", key):
                fed = row
                break
    if fed is not None:
        code = fed.get("code") or _slug(fed["canonical"]).upper()
        # Prefer stable short IRIs (agency/fbi) over long canonical slugs.
        slug = (code or _slug(fed["canonical"])).lower().replace("_", "-")
        return {
            "mention": raw,
            "status": "grounded",
            "reason": "federal_table",
            "ori": fed.get("ori"),
            "code": code,
            "agency_name": fed["canonical"],
            "agency_kind": fed.get("kind") or "federal",
            "state_hint": None,
            "hint_source": "federal",
            "slug": slug,
        }

    sp = match_state_police(raw, state_hint=state_hint, cde_by_state=cde_by_state)
    if sp is not None:
        return sp

    # Generic bare labels
    if is_generic_agency_mention(raw):
        counties = _grounded_counties(location_grounds)
        if state_hint and "sheriff" in key:
            via = _try_county_sheriff(
                state_hint=state_hint,
                counties=counties,
                cde_by_state=cde_by_state,
                mention=raw,
            )
            if via is not None:
                return via
        return {
            "mention": raw,
            "status": "ambiguous",
            "reason": "generic_no_place",
            "state_hint": state_hint,
            "hint_source": "source" if state_hint else None,
        }

    # Prosecutors / courts / AG offices — real orgs, not FBI CDE rows
    if _OUT_OF_REGISTRY.search(raw):
        return {
            "mention": raw,
            "status": "out_of_registry",
            "reason": "not_in_cde_registry",
            "state_hint": state_hint,
            "hint_source": "source" if state_hint else None,
        }

    if not state_hint:
        return {
            "mention": raw,
            "status": "ungrounded",
            "reason": "no_state_hint",
            "state_hint": None,
            "hint_source": None,
        }

    st = state_hint.upper()
    bucket = cde_by_state.get(st) or {}
    norm = _norm_key(normalize_agency_name(raw))
    candidates: list[dict] = []
    for key_try in _lookup_keys(norm):
        candidates.extend(bucket.get(key_try) or [])

    oris = {r.get("ori") for r in candidates if r.get("ori")}
    if len(oris) == 1:
        hit = next(r for r in candidates if r.get("ori") in oris)
        name = hit.get("agency_name") or raw
        return {
            "mention": raw,
            "status": "grounded",
            "reason": "cde_exact",
            "ori": hit.get("ori"),
            "agency_name": name,
            "agency_type": hit.get("agency_type_name"),
            "county": hit.get("county") or hit.get("counties"),
            "agency_kind": "local",
            "state_hint": st,
            "hint_source": "source",
            "slug": readable_agency_slug(
                agency_name=name, state_hint=st, ori=hit.get("ori")
            ),
        }
    if len(oris) > 1:
        return {
            "mention": raw,
            "status": "ambiguous",
            "reason": "multiple_cde_matches",
            "state_hint": st,
            "hint_source": "source",
            "candidate_oris": sorted(oris)[:8],
        }
    return {
        "mention": raw,
        "status": "ungrounded",
        "reason": "no_cde_match",
        "state_hint": st,
        "hint_source": "source",
    }


def ground_case_agencies(
    agencies: List[Any],
    *,
    source: Optional[str] = None,
    case_id: Optional[str] = None,
    reg_dir: Path | None = None,
    location_grounds: list | None = None,
) -> List[Dict[str, Any]]:
    clean = [str(x).strip() for x in (agencies or []) if x and str(x).strip()]
    if not clean:
        return []
    d = Path(reg_dir) if reg_dir is not None else REG_DIR
    meta = require_agency_registry(d)
    version = str(meta.get("version") or "unknown")
    federal_by_alias, cde_by_state, _ = _load_registry_cached(str(d.resolve()))
    state_hint = _state_hint_from_source(source)
    out: List[Dict[str, Any]] = []
    used_slugs: set[str] = set()
    for mention in clean:
        gnd = match_agency(
            mention,
            state_hint=state_hint,
            federal_by_alias=federal_by_alias,
            cde_by_state=cde_by_state,
            location_grounds=location_grounds,
        )
        gnd["registry_version"] = version
        gnd["case_id"] = case_id
        if gnd.get("status") == "grounded" and gnd.get("slug"):
            slug = gnd["slug"]
            if slug in used_slugs and gnd.get("ori"):
                slug = readable_agency_slug(
                    agency_name=gnd.get("agency_name") or mention,
                    state_hint=gnd.get("state_hint"),
                    ori=gnd.get("ori"),
                    collision_slugs=used_slugs,
                )
                gnd["slug"] = slug
            used_slugs.add(gnd["slug"])
        out.append(gnd)
    return out
