"""
Merge Processing - Intersection class for Pattern and ML outputs

This class is the "intersection" layer that combines:
- Pattern Processing Layer: regex-based extraction (crimes, volume, phrases, prosecution)
- ML Processing Layer: NER / semantic extraction (ages, dates, orgs, locations, etc.)

Merge logic:
- Ages, sentences, and CyberTip origin come from the resolved view over per-method
  field assertions (assertions.py → resolution.py, CaseLinker 3.0). Roles come from
  evidence attached to each mention, never from a numeric threshold.
- Organizations and locations: pattern agencies plus NER supplements (unchanged)
- Raw NER entities stored in ml_features.ner_entities for reference/debugging
"""

from typing import Dict, Any, List, Optional, Tuple, Union
import importlib.util
import re
from pathlib import Path

from agency_label_normalize import (
    dedupe_generic_state_police,
    drop_non_le_agencies,
    normalize_agency_label_for_ingest,
)

_agency_gate_mod = None
_gender_extraction_mod = None
_pattern_processing_mod = None
_assertions_mod = None

# Exact-string canonical aliases (applied after apostrophe/space cleanup, before ICAC/FBI rules).
# Replaces DB-only patches; persists across re-ingest.
AGENCY_CANONICAL_ALIASES: Dict[str, str] = {
    # Attorney General office article / apostrophe variants (trace + corpus counts)
    "Office of Attorney General": "Office of the Attorney General",
    "Attorney General''s Office": "Attorney General's Office",
    "Attorney General\u2019's Office": "Attorney General's Office",
    "Attorney Generals Office": "Attorney General's Office",
    "Attorney General Office": "Attorney General's Office",
    "Office of Attorney General's": "Office of the Attorney General",
    "Office of Attorney General's Office": "Office of the Attorney General",
    "Attorney General's": "Attorney General's Office",
    # Tier A/B — person-name weld → state-prefixed unit (agency_possessive_repair.py)
    "Raoul's High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    "Raoul\u2019s High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    "Raoul's Sexually Violent Persons Bureau": "Illinois Sexually Violent Persons Bureau",
    "Madigan's High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    "Madigan\u2019s High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    "Murrill's Louisiana Bureau of Investigation": "Louisiana Bureau of Investigation",
    "Yost's Bureau of Criminal Investigation": "Ohio Bureau of Criminal Investigation",
    "General's High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    "General\u2019s High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    "General's Bureau of Criminal Investigation": "Ohio Bureau of Criminal Investigation",
    "Illinois Attorney General's Office High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    "Illinois Attorney General\u2019s Office High Tech Crimes Bureau": "Illinois High Tech Crimes Bureau",
    # Tier C — CEOS dedup
    "Justice Department's Child Exploitation and Obscenity Section": "CEOS",
    "Justice Department\u2019s Child Exploitation and Obscenity Section": "CEOS",
    # USAO
    "U.S. Attorneys Office": "U.S. Attorney's Office",
    "United States Attorney's Office": "U.S. Attorney's Office",
    "United States Attorneys Office": "U.S. Attorney's Office",
    "Office of the United States Attorney": "U.S. Attorney's Office",
    "USAO": "U.S. Attorney's Office",
}
AGENCY_CANONICAL_ALIASES_CASEFOLD: Dict[str, str] = {
    k.casefold(): v for k, v in AGENCY_CANONICAL_ALIASES.items()
}


def _gender_extraction():
    global _gender_extraction_mod
    if _gender_extraction_mod is None:
        path = Path(__file__).parent / "gender_extraction.py"
        spec = importlib.util.spec_from_file_location("gender_extraction", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        _gender_extraction_mod = mod
    return _gender_extraction_mod


def _pattern_processing():
    global _pattern_processing_mod
    if _pattern_processing_mod is None:
        proc_path = Path(__file__).parent / "Pattern Processing Layer" / "processing.py"
        spec = importlib.util.spec_from_file_location("pattern_processing", proc_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        _pattern_processing_mod = mod
    return _pattern_processing_mod


# Entity lists a reader can wrongly fill with a person's name (people_mask.scrub_people).
_PERSON_FREE_KEYS = (
    "locations", "organizations", "agencies_involved", "pathway_agencies_federal",
    "pathway_agencies_state_local", "location_grounds", "agency_grounds",
)


def _assertions():
    global _assertions_mod
    if _assertions_mod is None:
        path = Path(__file__).parent / "field_assertions" / "assertions.py"
        spec = importlib.util.spec_from_file_location("assertions", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        _assertions_mod = mod
    return _assertions_mod


def _agency_context_gate():
    global _agency_gate_mod
    if _agency_gate_mod is None:
        gate_path = Path(__file__).parent / "agency_context_gate.py"
        spec = importlib.util.spec_from_file_location("agency_context_gate", gate_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        _agency_gate_mod = mod
    return _agency_gate_mod


# AI-CSAM (case_topics) is lexical/regex only — see AI_CSAM_TOPIC_RE.
# Do not promote from embedding concept ai_and_internet_tools; scores ~0.50 on
# ordinary pre-GenAI CSAM digests caused widespread false positives.

_US_STATES = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
)
_STATE_TO_POSTAL = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}
# Full state names with ≤4 letters (jurisdictional supplement); not OCR junk (km/nw/bw/jr).
_FOUR_LETTER_US_STATE_NAMES = frozenset(
    s.lower() for s in _US_STATES if len(re.sub(r"[^A-Za-z]", "", s)) <= 4
)
_STATE_ALT = "|".join(re.escape(s) for s in sorted(_US_STATES, key=len, reverse=True))
_STATE_RE = re.compile(rf"\b({_STATE_ALT})\b", re.IGNORECASE)
_INCIDENTAL_STATE_RE = re.compile(
    r"\b(?:"
    r"based\s+in|headquartered\s+in|traveled\s+(?:to|through|from)|"
    r"from\s+\w+\s+to|moved\s+to|relocated\s+to|"
    r"university\s+of|company\s+in|firm\s+in|"
    r"born\s+in|grew\s+up\s+in|"
    r"across\s+the\s+country|nationwide|throughout\s+the\s+united\s+states"
    r")\b",
    re.IGNORECASE,
)
_JURISDICTIONAL_AT_STATE_RE = re.compile(
    r"(?:"
    r"(?:resident|living|residing|resides)\s+(?:of|in)\s+|"
    r"(?:arrested|charged|indicted|convicted|sentenced|booked|arraigned|held|detained|"
    r"incarcerated|prosecuted|tried|appeared)\s+in\s+(?:the\s+)?|"
    r"(?:western|eastern|northern|southern|middle|central)\s+district\s+of\s+|"
    r"district\s+of\s+|"
    r"(?:state\s+of|commonwealth\s+of)\s+|"
    r"in\s+the\s+state\s+of\s+"
    r")"
    rf"({_STATE_ALT})\b",
    re.IGNORECASE,
)
_STATE_STREET_SUFFIX_RE = re.compile(
    r"^\s*(?:Avenue|Ave|Street|St|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|Way)\b",
    re.IGNORECASE,
)
_CITY_COMMA_BAD_LEFT_RE = re.compile(
    r"\b(?:"
    r"Court|Office|Patrol|Police|Department|Service|Bureau|Agency|Division|"
    r"Sheriff|Investigations|Highway|Attorney|Attorney's|County|Superior|Regional|"
    r"Laboratory|Lab|Force|Task|Unit|Field|Criminal|Cyber|General's|City|Homeland"
    r")\s*$",
    re.IGNORECASE,
)
_STATE_BAD_TAIL_RE = re.compile(
    r"^\s*(?:"
    r"State\s+(?:Police|University|Parks)|Highway\s+Patrol|Valley\b|"
    r"Unit\b|Criminal\s+Division\b|Field\s+Office\b"
    r")\b",
    re.IGNORECASE,
)
_REGIONAL_PREFIX_RE = re.compile(
    r"\b(?:South|North|East|West|Central|Upper|Lower|Mid)\s+$",
    re.IGNORECASE,
)


class MergeProcessing:
    """
    Intersection class between Pattern Processing and ML (NER).

    Merge behavior:
    - Ages / sentences / CyberTip origin: derived from field resolutions (3.0)
    - Organizations / locations: pattern agencies plus NER supplements
    - Raw NER entities stored in ml_features.ner_entities for reference
    """

    def __init__(self) -> None:
        """Initialize the MergeProcessing class."""
        # No state needed yet; kept for future extensions
        return None

    def merge_features(
        self,
        pattern_features: Dict[str, Any],
        ner_entities: Optional[Dict[str, List[Any]]] = None,
        *,
        assertions: Optional[List[Dict[str, Any]]] = None,
        resolutions: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Merge pattern-processing features with NER entities and 3.0 field resolutions.

        Args:
            pattern_features: Feature dict from Pattern Processing Layer
            ner_entities: Optional dict from ML Processing Layer (NER)
            assertions / resolutions: per-method field assertions and their resolution.
                When omitted, deterministic assertions are collected and resolved here.

        Returns:
            Dict with legacy fields derived from the resolved view:
            - perpetrator_age / case_demographics.ages: settled perpetrator / victim ages
            - prosecution_outcome.sentences: imposed terms, supervised release, probation, fines
            - investigation_types: 2.x method types plus CyberTip only when case-scoped
            - Organizations / agencies / locations: pattern + NER (unchanged)
            - assertions / resolutions: kept on the dict for storage (not in the JSON blob)
        """
        merged = pattern_features.copy()

        # Initialize ml_features if not present
        if 'ml_features' not in merged:
            merged['ml_features'] = {}

        if resolutions is None:
            amod = _assertions()
            year = (merged.get("raw_data") or {}).get("year")
            assertions = amod.collect_assertions(
                merged.get("case_text") or "",
                case_id=merged.get("id") or merged.get("case_id") or "",
                ner_entities=ner_entities,
                batch_year=int(year) if str(year or "").isdigit() else None,
                doc_kind=merged.get("document_kind") or "press_release",
            )
            resolutions = amod.resolve(
                assertions,
                batch_date=(merged.get("date_range") or {}).get("start"),
                text=merged.get("case_text") or "",
            )
        merged['assertions'] = assertions or []
        merged['resolutions'] = resolutions

        merged = self._apply_resolved_ages(merged, resolutions.get("age") or {})
        merged = self._apply_resolved_sentences(merged, resolutions.get("sentence") or {})
        merged = self._apply_resolved_cybertip(merged, resolutions.get("investigation_type") or {})
        merged = self._apply_resolved_dates(merged, resolutions.get("date") or {})

        # Where the people are, never who: offsets every public surface redacts from.
        pk = _assertions().people_mask
        text = merged.get("case_text") or ""
        merged["person_spans"] = pk.person_spans(
            text, (ner_entities or {}).get("person_spans") or [],
            [x for x in (merged.get("agencies_involved") or []) if isinstance(x, str)],
        )
        person_names = [text[s:e] for s, e in merged["person_spans"]]

        # A person is not a location or an organization. Readers sometimes file one there;
        # drop those entries before they are merged, grounded, stored or aggregated.
        people = pk.case_people(text, person_names)
        for key in _PERSON_FREE_KEYS:
            if key in merged:
                merged[key] = pk.scrub_people(merged[key], *people)
        if ner_entities:
            ner_entities = {k: (pk.scrub_people(v, *people) if k in ("organizations", "locations") else v)
                            for k, v in ner_entities.items()}

        # Store raw NER entities for reference/debugging
        if ner_entities:
            merged['ml_features']['ner_entities'] = {
                k: v for k, v in ner_entities.items() if k not in ("number_spans", "person_spans")
            }

            # Merge organizations (law enforcement only)
            merged = self._merge_organizations(merged, ner_entities)

            # Merge locations (geography: states, countries, cities)
            merged = self._merge_locations(merged, ner_entities)

        # Merge semantic concepts (if present under ml_features.semantic_severity)
        merged = self._merge_semantic_concepts(merged)

        merged = self._supplement_jurisdictional_states(merged)

        # Authority link (Census FIPS / FBI CDE ORI) — after mentions are settled
        merged = self._apply_location_grounds(merged)
        merged = self._apply_agency_grounds(merged)
        grounded = [g.get(k) for key in ("location_grounds", "agency_grounds") for g in merged.get(key) or []
                    if isinstance(g, dict) and g.get("status") == "grounded" for k in ("mention", "entity_name")]
        grounded += [x for x in (merged.get("agencies_involved") or []) if isinstance(x, str)]
        people = pk.case_people(text, person_names, grounded)
        for key in _PERSON_FREE_KEYS + ("ml_features",):
            if key in merged:
                merged[key] = pk.scrub_people(merged[key], *people)

        return merged

    def _apply_location_grounds(self, merged: Dict[str, Any]) -> Dict[str, Any]:
        """Attach ``location_grounds`` for each settled location mention.

        Deterministic linker against the pinned US Census gazetteer. Missing or
        corrupt gazetteer raises — no silent slug fallback.
        """
        locations = merged.get("locations") or []
        if not isinstance(locations, list) or not locations:
            return merged
        ground_path = Path(__file__).parent / "location_grounding.py"
        if not ground_path.is_file():
            return merged
        import sys

        spec = importlib.util.spec_from_file_location(
            "location_grounding", ground_path
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        sys.modules["location_grounding"] = mod
        spec.loader.exec_module(mod)
        # GazetteerError and other linker failures must surface — no silent slug fallback.
        merged["location_grounds"] = mod.ground_case_locations(
            locations,
            source=merged.get("source"),
            case_text=merged.get("case_text") or "",
            case_id=merged.get("id") or merged.get("case_id"),
        )
        return merged

    def _apply_agency_grounds(self, merged: Dict[str, Any]) -> Dict[str, Any]:
        """Attach ``agency_grounds`` for each settled agency mention."""
        agencies = merged.get("agencies_involved") or []
        if not isinstance(agencies, list) or not agencies:
            return merged
        ground_path = Path(__file__).parent / "agency_grounding.py"
        if not ground_path.is_file():
            return merged
        import sys

        spec = importlib.util.spec_from_file_location("agency_grounding", ground_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        sys.modules["agency_grounding"] = mod
        spec.loader.exec_module(mod)
        merged["agency_grounds"] = mod.ground_case_agencies(
            agencies,
            source=merged.get("source"),
            case_id=merged.get("id") or merged.get("case_id"),
            location_grounds=merged.get("location_grounds"),
        )
        return merged

    def _apply_resolved_sentences(self, merged: Dict[str, Any], res: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy ``prosecution_outcome.sentences`` from resolved buckets (never exposure or prior terms)."""
        final = res.get("final_value") or {}
        sentences: List[str] = list(final.get("imposed") or [])
        sentences += [v if "supervis" in v.lower() else f"{v} supervised release" for v in final.get("supervised_release") or []]
        sentences += [v if "probation" in v.lower() else f"{v} probation" for v in final.get("probation") or []]
        sentences += list(final.get("fine") or [])
        custody = list(final.get("custody") or [])
        outcome = merged.get("prosecution_outcome")
        if isinstance(outcome, dict):
            outcome = dict(outcome)
            outcome["sentences"] = sentences
            if custody:
                outcome["jail"] = custody[0] if len(custody) == 1 else "; ".join(custody)
            merged["prosecution_outcome"] = outcome
        elif sentences or custody:
            merged["prosecution_outcome"] = {
                "charges": [], "booking_status": None, "jail": custody[0] if len(custody) == 1 else ("; ".join(custody) or None),
                "sentences": sentences,
            }
        return merged

    def _apply_resolved_dates(self, merged: Dict[str, Any], res: Dict[str, Any]) -> Dict[str, Any]:
        """
        When the batch date is only a year or a month (day 01), replace it with the
        publication day the temporal detector read out of the release.
        """
        final = res.get("final_value") or {}
        publication = final.get("publication")
        if not isinstance(publication, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication):
            return merged
        current = dict(merged.get("date_range") or {})
        start = str(current.get("start") or "")
        if start and not re.fullmatch(r"\d{4}-\d{2}-01", start):
            return merged
        current["start"] = publication
        current["end"] = publication
        merged["date_range"] = current
        return merged

    def _apply_resolved_cybertip(self, merged: Dict[str, Any], res: Dict[str, Any]) -> Dict[str, Any]:
        """CyberTip stays in investigation_types only when a case-scoped tip resolved."""
        types = [t for t in (merged.get("investigation_types") or []) if t != "cybertip"]
        if res.get("final_value") == ["cybertip"]:
            types.insert(0, "cybertip")
        merged["investigation_types"] = types
        merged["investigation_type"] = _pattern_processing()._primary_investigation_type(types)
        return merged

    def _apply_resolved_ages(self, merged: Dict[str, Any], res: Dict[str, Any]) -> Dict[str, Any]:
        """
        Legacy age fields from the resolved view: settled perpetrators (one age per
        defendant entity) and settled victims. Decoy, claimed, statutory, depicted,
        and contested ages never reach these fields.
        """
        final = res.get("final_value") or {}
        victims = list(final.get("victims") or [])
        perps = list(final.get("perpetrators") or [])
        case_text = merged.get("case_text") or ""
        merged["perpetrator_age"] = perps or None

        pp = _pattern_processing()
        digest_pollution, multi_defendant = pp.classify_perpetrator_age_context(
            case_text, perps, merged.get("source") or ""
        )
        merged["press_digest_pollution"] = digest_pollution
        merged["multi_defendant_operation"] = multi_defendant

        case_demo = merged.get("case_demographics")
        if not isinstance(case_demo, dict):
            case_demo = {}
        case_demo = dict(case_demo)
        case_demo["ages"] = victims
        case_demo.pop("gender", None)
        gender_mod = _gender_extraction()
        vg = gender_mod.extract_victim_gender(case_text, victims)
        if vg:
            case_demo["victim_gender"] = vg
        else:
            case_demo.pop("victim_gender", None)
        pg = gender_mod.extract_perpetrator_gender(case_text, perps or None)
        if pg:
            merged["perpetrator_gender"] = pg
        else:
            merged.pop("perpetrator_gender", None)
        if case_demo.get("ages") or case_demo.get("age_range") or case_demo.get("victim_gender"):
            merged["case_demographics"] = case_demo
        else:
            merged.pop("case_demographics", None)

        # Same keys as the 2.x gate log, now read off the resolution.
        contested = final.get("contested") or {}
        merged["ml_features"]["victim_age_gate"] = {
            "candidates": sorted(
                {a["value"] for a in merged.get("assertions") or [] if a.get("field") == "age" and a.get("role") == "victim" and a.get("span_ok")}
            ),
            "final": victims,
            "kept": [{"age": v, "decision": "keep", "reason": res.get("rule_id")} for v in victims],
            "dropped": [{"age": x["age"], "decision": "reject", "reason": x["role"]} for x in final.get("excluded") or []],
            "review_excluded": [
                {"age": c["value"], "decision": "review", "reason": "contested"} for c in contested.values()
            ] + [{"age": u["value"], "decision": "review", "reason": u["state"]} for u in final.get("unresolved") or []],
            "resolution_status": res.get("status"),
            "rule_set_version": res.get("rule_set_version"),
        }
        return merged

    # ------------------------------------------------------------------ #
    # Semantic concepts merge (possession hint + severity add‑ons)
    # ------------------------------------------------------------------ #
    def _merge_semantic_concepts(
        self,
        merged: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge semantic concepts from ML Processing Layer into pattern features.

        Behavior:
        - Production topic: pattern/regex only (no semantic override).
        - Possession: if possession_csam is strong, ensure 'possession' tag exists.
        - Severity: add 'grooming' when the semantic concept score is present.
        - AI-CSAM topic: pattern/regex only (never promote from ai_and_internet_tools).
        - Sextortion topic: pattern/regex only (see SEXTORTION_TOPIC_RE in processing).
        """
        ml_features = merged.get('ml_features') or {}
        semantic = ml_features.get('semantic_severity') or {}

        scores: Dict[str, float] = semantic.get('scores') or {}

        topics = merged.get('case_topics') or []
        if not isinstance(topics, list):
            topics = [topics] if topics else []

        # If semantic possession is strong, ensure 'possession' tag exists
        poss_score = float(scores.get('possession_csam', 0.0))
        if poss_score >= 0.5 and 'possession' not in topics:
            topics.append('possession')

        if topics:
            merged['case_topics'] = list(dict.fromkeys(topics))

        # --- Severity indicators from concepts (non‑regex ideas) ---
        severity = merged.get('severity_indicators') or []
        if not isinstance(severity, list):
            severity = [severity] if severity else []

        # Add grooming as a semantic severity indicator
        grooming_score = float(scores.get('grooming', 0.0))
        if grooming_score >= 0.35 and 'grooming' not in severity:
            severity.append('grooming')

        if severity:
            merged['severity_indicators'] = list(dict.fromkeys(severity))

        return merged

    def _merge_organizations(
        self,
        merged: Dict[str, Any],
        ner_entities: Dict[str, List[Any]]
    ) -> Dict[str, Any]:
        """
        Merge organizations from NER.
        
        Logic:
        - Store ALL NER organizations in 'organizations' field (tech platforms, news, agencies, etc.)
        - Filter to law enforcement agencies and merge into 'agencies_involved'
        - Pattern agencies take precedence if duplicates exist
        
        Args:
            merged: Merged features dict
            ner_entities: NER entities dict
            
        Returns:
            Updated merged dict with organizations merged
        """
        ner_orgs = ner_entities.get('organizations', []) or []

        normalized_orgs = self._normalize_organizations(ner_orgs) if ner_orgs else []
        law_enforcement_orgs = (
            self._filter_law_enforcement_agencies(normalized_orgs) if normalized_orgs else []
        )

        pattern_agencies_raw = merged.get('agencies_involved', [])
        pattern_agencies_normalized = self._normalize_organizations(pattern_agencies_raw)
        pattern_agencies = set(pattern_agencies_normalized)

        if law_enforcement_orgs:
            all_orgs = self._dedupe_agency_fragments(
                list(dict.fromkeys(law_enforcement_orgs))
            )
            merged['organizations'] = all_orgs
        elif pattern_agencies:
            merged['organizations'] = sorted(list(pattern_agencies))

        combined = list(pattern_agencies | set(law_enforcement_orgs))
        if combined:
            gate_mod = _agency_context_gate()
            case_text = merged.get('case_text') or ''
            case_id = merged.get('case_id') or merged.get('id') or ''
            gated, gate_log = gate_mod.apply_agency_context_gate(
                case_id,
                case_text,
                combined,
                source=merged.get("source"),
            )
            merged['agencies_involved'] = self._dedupe_agency_fragments(gated)
            pathway = gate_log.get("pathway") or {}
            merged['pathway_agencies_federal'] = pathway.get("federal") or []
            merged['pathway_agencies_state_local'] = pathway.get("state_local") or []
            if 'ml_features' not in merged:
                merged['ml_features'] = {}
            merged['ml_features']['agency_context_gate'] = gate_log

        return merged

    _BARE_STATE_AGENCY_NAMES = frozenset({
        'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
        'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
        'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
        'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
        'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
        'new hampshire', 'new jersey', 'new mexico', 'new york',
        'north carolina', 'north dakota', 'ohio', 'oklahoma', 'oregon',
        'pennsylvania', 'rhode island', 'south carolina', 'south dakota',
        'tennessee', 'texas', 'utah', 'vermont', 'virginia', 'washington',
        'west virginia', 'wisconsin', 'wyoming', 'las vegas',
    })

    _AGENCY_FRAGMENT_DROP = frozenset({
        'investigation', 'tor task force', 'federal bureau', 'federal',
        'police department', 'department', 'bureau', 'justice department', 'doj',
    })

    def _dedupe_agency_fragments(self, agencies: List[str]) -> List[str]:
        """Drop NER split fragments and bare state-name agency labels."""
        cleaned: List[str] = []
        seen: set = set()
        upper_blob = ' | '.join(agencies).lower()

        for agency in agencies:
            if not agency or not str(agency).strip():
                continue
            label = str(agency).strip()
            low = label.lower()

            if low in self._BARE_STATE_AGENCY_NAMES:
                continue
            if low in self._AGENCY_FRAGMENT_DROP:
                continue
            # "tor Task Force" when a *Predator Task Force exists
            if low == 'tor task force' and 'predator task force' in upper_blob:
                continue
            # Standalone "Investigation" when FBI / full bureau name present
            if low == 'investigation' and (
                'fbi' in upper_blob
                or 'federal bureau of investigation' in upper_blob
                or 'homeland security investigations' in upper_blob
            ):
                continue
            # Generic "Police Department" without a city/county prefix
            if low == 'police department' and not re.match(
                r'.+\s+police\s+department$', label, re.I
            ):
                continue

            if low not in seen:
                seen.add(low)
                cleaned.append(label)

        cleaned.sort()
        return cleaned

    # Lightweight location residue filter (Stanza post-process; not transformers-era heavy filter)
    _LOCATION_FRAGMENT_DROP = frozenset({
        "an",
        "ab",
        "pi",
        "alas",
        "anch",
        "chor",
        "ag",
        ". s",
        ". s.",
        "u. s",
        "u. s.",
        "u. s. c",
        "states",
    })
    # OCR/NER junk — not places (confirmed close-out: 9 cases)
    _NON_PLACE_SHORT_ABBREVS = frozenset({"km", "nw", "bw", "jr"})
    # AP/dateline + postal forms for ≤3–4 letter location tokens (Ky., Kan., N.c., W.va., …)
    _STATE_DATELINE_ABBREVS = frozenset({
        "ala", "alaska", "ariz", "ark", "calif", "colo", "conn", "del", "fla", "ga", "ill", "ind",
        "kan", "ky", "la", "md", "mass", "mich", "minn", "miss", "mo", "mont", "neb", "nev",
        "nh", "nj", "nm", "ny", "nc", "nd", "okla", "ore", "pa", "ri", "sc", "sd", "tenn", "tex",
        "utah", "vt", "va", "wash", "wva", "w.va", "wis", "wyo", "dc", "d.c",
        "n.c", "n.y", "n.j", "n.h", "n.m", "n.d", "n.e", "s.c", "s.d", "r.i", "w.va",
        "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "hi", "id", "il", "in", "ia", "ks",
        "me", "mi", "mn", "ms", "mt", "ne", "nv", "oh", "ok", "or", "tn", "tx", "ut", "wv", "wi", "wy",
    })
    _VALID_SHORT_PLACE_TOKENS = frozenset({
        "rio", "nyc", "okc", "sea", "msu", "rsw", "prc", "tnd",
    })
    # Possessive stems that are real places — do not drop "Boise's" etc. if ever tagged
    _KNOWN_PLACE_POSSESSIVE_STEMS = frozenset({
        "alaska", "alabama", "arizona", "arkansas", "california", "colorado",
        "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
        "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
        "maine", "maryland", "massachusetts", "michigan", "minnesota",
        "mississippi", "missouri", "montana", "nebraska", "nevada",
        "new hampshire", "new jersey", "new mexico", "new york",
        "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
        "pennsylvania", "rhode island", "south carolina", "south dakota",
        "tennessee", "texas", "utah", "vermont", "virginia", "washington",
        "west virginia", "wisconsin", "wyoming",
        "anchorage", "boise", "boston", "chicago", "dallas", "denver",
        "houston", "phoenix", "seattle", "portland", "honolulu", "juneau",
        "ely", "erie", "rome", "paris",
    })
    _POSSESSIVE_LOC_RE = re.compile(r"^(.+?)(?:['\u2019])s$", re.IGNORECASE)

    def _expand_newline_location_entities(self, loc: str) -> List[str]:
        """``ALASKA\\nWASHINGTON`` → two entities."""
        if not loc or "\n" not in loc:
            return [loc.strip()] if loc and loc.strip() else []
        return [p.strip() for p in loc.splitlines() if p.strip()]

    def _normalize_location_abbrev(self, loc: str) -> str:
        return re.sub(r"[\s.]+", "", loc.lower().strip())

    def _is_valid_short_location_token(self, loc: str) -> bool:
        """Allow dateline/postal abbrevs; reject OCR junk (Km/Nw/Bw/Jr)."""
        s = loc.strip()
        if not s:
            return False
        bare = self._normalize_location_abbrev(s)
        if bare in self._NON_PLACE_SHORT_ABBREVS:
            return False
        letters = re.sub(r"[^A-Za-z]", "", s)
        if len(letters) > 4:
            return True
        if bare in _FOUR_LETTER_US_STATE_NAMES:
            return True
        if bare in self._STATE_DATELINE_ABBREVS:
            return True
        if bare.rstrip(".") in self._VALID_SHORT_PLACE_TOKENS:
            return True
        return False

    def _is_location_residue_fragment(self, loc: str) -> bool:
        """Rare transformers-era shards; explicit list only (not all ≤2-char places)."""
        low = loc.lower().strip()
        if low in self._LOCATION_FRAGMENT_DROP:
            return True
        if re.match(r"^\.\s*[a-z]\.?$", low):
            return True
        if re.match(r"^u\.\s*s\.?$", low):
            return True
        return False

    def _is_possessive_non_place(self, loc: str) -> bool:
        """Drop ``Moore's``-style PERSON possessives; keep known place stems."""
        m = self._POSSESSIVE_LOC_RE.match(loc.strip())
        if not m:
            return False
        stem = m.group(1).strip().lower()
        if stem in self._KNOWN_PLACE_POSSESSIVE_STEMS:
            return False
        if len(stem) >= 2 and stem in self._BARE_STATE_AGENCY_NAMES:
            return False
        return True

    def _pick_canonical_location_label(self, variants: List[str]) -> str:
        """Case-insensitive dedup: prefer title-case over ALL-CAPS dateline duplicates."""

        def _score(label: str) -> tuple:
            s = label.strip()
            if not s:
                return (0, 0, 0)
            letters = [c for c in s if c.isalpha()]
            all_caps = bool(letters) and all(c.isupper() for c in letters) and len(s) > 3
            titleish = bool(re.search(r"[a-z]", s)) and bool(re.search(r"[A-Z]", s))
            return (1 if titleish else 0, 0 if all_caps else 1, len(s))

        return max(variants, key=_score)

    def _drop_substring_location_fragments(self, locations: List[str]) -> List[str]:
        """Drop ``Chorage`` / ``An`` when a longer location on the case contains it."""
        if len(locations) < 2:
            return locations
        lowered = [loc.lower() for loc in locations]
        keep: List[str] = []
        for i, loc in enumerate(locations):
            low = lowered[i]
            if len(low) <= 4:
                if any(
                    j != i
                    and len(lowered[j]) > len(low) + 2
                    and low in lowered[j]
                    and low not in ("erie", "ely", "rome", "ohio", "utah", "iowa", "id")
                    for j in range(len(locations))
                ):
                    continue
            keep.append(loc)
        return keep

    def _filter_location_residue(
        self, locations: List[str], *, audit: bool = False
    ) -> List[str] | Tuple[List[str], List[Tuple[str, str]]]:
        """
        Stanza residue safety net (not a full transformers fragment rebuild).

        - Split newline-glued entities
        - Drop explicit fragment shards + possessive non-places
        - Case-insensitive dedup (prefer title-case)
        - Substring fragment dedup when parent place exists
        - Keeps jurisdiction phrases (District of Alaska, Western District of …)
        - Does NOT blocklist alias GPEs (e.g. China) — flagged for later

        With ``audit=True``, returns ``(cleaned, [(dropped_label, reason), ...])``.
        """
        dropped_audit: List[Tuple[str, str]] = []
        expanded: List[str] = []
        for raw in locations:
            if not raw or not str(raw).strip():
                continue
            parts = self._expand_newline_location_entities(str(raw).strip())
            if audit and len(parts) > 1:
                for p in parts[1:]:
                    dropped_audit.append((raw, "newline_split"))
            expanded.extend(parts)

        filtered: List[str] = []
        for loc in expanded:
            if self._is_location_residue_fragment(loc):
                if audit:
                    dropped_audit.append((loc, "fragment_reject_list"))
                continue
            if self._is_possessive_non_place(loc):
                if audit:
                    dropped_audit.append((loc, "possessive_non_place"))
                continue
            letters = re.sub(r"[^A-Za-z]", "", loc.strip())
            if len(letters) <= 4 and not self._is_valid_short_location_token(loc):
                if audit:
                    dropped_audit.append((loc, "short_token_not_allowlisted"))
                continue
            filtered.append(loc)

        before_sub = list(filtered)
        filtered = self._drop_substring_location_fragments(filtered)
        if audit:
            kept_low = {x.lower() for x in filtered}
            for loc in before_sub:
                if loc.lower() not in kept_low:
                    dropped_audit.append((loc, "substring_parent_dedup"))

        groups: Dict[str, List[str]] = {}
        for loc in filtered:
            key = re.sub(r"\s+", " ", loc.lower().strip())
            groups.setdefault(key, []).append(loc)

        deduped: List[str] = []
        seen: set = set()
        for key, variants in groups.items():
            canonical = self._pick_canonical_location_label(variants)
            if key not in seen:
                seen.add(key)
                deduped.append(canonical)
            elif audit:
                for v in variants:
                    if v != canonical:
                        dropped_audit.append((v, "case_insensitive_dedup"))

        deduped.sort(key=lambda s: s.lower())
        if audit:
            return deduped, dropped_audit
        return deduped
    
    def _filter_law_enforcement_agencies(self, organizations: List[str]) -> List[str]:
        """
        Filter organizations to only include law enforcement agencies.
        
        Excludes:
        - Tech platforms (Facebook, Instagram, Dropbox, etc.)
        - News organizations (KAKE News, Herald, etc.)
        - Generic organizations without law enforcement context
        
        Includes:
        - Police departments
        - Sheriff departments
        - Federal agencies (FBI, ICE, HSI, etc.)
        - ICAC task forces
        - County/State/Federal law enforcement
        - Attorney/Prosecutor offices (law enforcement context)
        
        Args:
            organizations: List of organization strings from NER
            
        Returns:
            Filtered list of law enforcement agencies
        """
        law_enforcement = []
        
        # Common law enforcement keywords
        le_keywords = [
            'police', 'sheriff', 'department', 'agency', 'bureau',
            'fbi', 'ice', 'hsi', 'dea', 'atf', 'marshals', 'us marshals',
            'icac', 'ncmec', 'task force', 'taskforce',
            'attorney', 'prosecutor', 'district attorney', 'county attorney',
            'state police', 'county sheriff', 'federal',
            'investigation', 'detective', 'detectives',
            'homeland security', 'dhs', 'secret service',
            'department of justice', 'doj', 'justice department'
        ]
        
        # Common tech platforms to exclude
        tech_platforms = [
            'facebook', 'instagram', 'snapchat', 'discord', 'whatsapp',
            'dropbox', 'google', 'apple', 'microsoft', 'twitter', 'x',
            'tiktok', 'youtube', 'telegram', 'signal', 'kik'
        ]
        
        # Common news/media keywords to exclude
        news_keywords = [
            'news', 'herald', 'times', 'tribune', 'journal', 'post',
            'reporter', 'media', 'press', 'publication', 'focus'
        ]
        
        for org in organizations:
            if not org or len(org.strip()) < 3:
                continue
            
            org_lower = org.lower().strip()
            org_words = set(org_lower.split())  # Use set for whole-word matching
            
            # Skip if it's clearly a tech platform (whole word match to avoid false positives)
            # Check both substring (for multi-word platforms) and whole word matches
            is_tech = False
            for platform in tech_platforms:
                platform_words = platform.split()
                # If platform is multi-word, check substring; if single word, check whole word
                if len(platform_words) > 1:
                    if platform in org_lower:
                        is_tech = True
                        break
                else:
                    if platform_words[0] in org_words:
                        is_tech = True
                        break
            if is_tech:
                continue
            
            # Skip if it's clearly a news organization (whole word match)
            is_news = False
            for news in news_keywords:
                news_words = news.split()
                if len(news_words) > 1:
                    if news in org_lower:
                        is_news = True
                        break
                else:
                    if news_words[0] in org_words:
                        is_news = True
                        break
            if is_news:
                continue
            
            # Check if it contains law enforcement keywords
            # Use whole-word matching for single-word keywords to avoid false positives
            has_le_keyword = False
            for keyword in le_keywords:
                keyword_words = keyword.split()
                if len(keyword_words) == 1:
                    # Single word: use whole-word matching
                    if keyword in org_words:
                        has_le_keyword = True
                        break
                else:
                    # Multi-word: substring match is OK
                    if keyword in org_lower:
                        has_le_keyword = True
                        break
            
            if has_le_keyword:
                # Additional validation: make sure it's not just a generic word
                # Skip single words that are too generic
                words = org_lower.split()
                if len(words) == 1 and words[0] in ['department', 'agency', 'bureau', 'attorney', 'police', 'sheriff']:
                    continue
                
                # Skip if it's just "County" or "County Attorney" without a location
                if org_lower == 'county' or org_lower == 'county attorney':
                    continue
                
                law_enforcement.append(org.strip())
        
        # Deduplicate while preserving order
        seen = set()
        unique_agencies = []
        for agency in law_enforcement:
            agency_lower = agency.lower()
            if agency_lower not in seen:
                seen.add(agency_lower)
                unique_agencies.append(agency)
        
        return unique_agencies
    
    def _normalize_organizations(self, organizations: List[str]) -> List[str]:
        """
        Normalize organization names to merge common variations.
        
        Handles:
        - "ZICAC" → "AZICAC" (tokenization artifact)
        - NCMEC variations → "NCMEC"
        - ICAC variations → "ICAC" or "ICAC Task Force"
        - AZICAC variations → "AZICAC" or "AZICAC Task Force"
        - FBI variations → "FBI"
        - Police department variations
        - Apostrophe/spacing variations (Attorney's Office, Sheriff's Office, etc.)
        - Case variations and common abbreviations
        - "The" prefix removal
        - HSI abbreviation normalization
        
        Args:
            organizations: List of organization strings
            
        Returns:
            List of normalized organization strings
        """
        normalized = []
        
        for org in organizations:
            if not org or len(org.strip()) < 2:
                continue

            ingest_parts = normalize_agency_label_for_ingest(org)
            if not ingest_parts:
                continue

            for org_clean in ingest_parts:
                org_lower = org_clean.lower()

                # Filter out generic standalone terms
                generic_terms = ['task force', 'force', 'county', 'internet', 'department', 'office', 'police', 'attorney']
                if org_lower in generic_terms or org_lower == generic_terms[0] + 's':
                    continue  # Skip generic terms

                # NCMEC variations → "NCMEC"
                if org_lower == 'ncmec' or 'national center for missing and exploited children' in org_lower:
                    normalized.append('NCMEC')
                    continue

                # ICAC variations → "ICAC" (merge all ICAC Task Force into ICAC)
                if ('icac' in org_lower and 'azicac' not in org_lower) or (
                    'internet crimes against children' in org_lower and 'arizona' not in org_lower
                ):
                    normalized.append('ICAC')
                    continue

                # AZICAC variations → "AZICAC" or "AZICAC Task Force"
                if org_lower == 'azicac' or org_lower == 'zicac' or 'arizona internet crimes against children' in org_lower:
                    if 'task force' in org_lower:
                        normalized.append('AZICAC Task Force')
                    elif 'phoenix police' in org_lower or 'police' in org_lower:
                        normalized.append('AZICAC')
                    else:
                        normalized.append('AZICAC')
                    continue

                # FBI variations → "FBI"
                if org_lower == 'fbi' or 'federal bureau of investigation' in org_lower:
                    if 'child sexual exploitation' in org_lower:
                        normalized.append('FBI Child Sexual Exploitation Unit')
                    else:
                        normalized.append('FBI')
                    continue

                # Normalize "Police Department" to consistent format
                if 'police' in org_lower:
                    police_match = re.match(r'^(.+?)\s+police', org_clean, re.IGNORECASE)
                    if police_match:
                        city_name = police_match.group(1).strip()
                        if 'department of public safety' in org_lower:
                            normalized.append(city_name + ' Department of Public Safety')
                        elif 'department' in org_lower:
                            normalized.append(city_name + ' Police Department')
                        else:
                            normalized.append(city_name + ' Police Department')
                        continue
                    elif 'department' in org_lower:
                        normalized.append(org_clean.replace(' Dept.', ' Department').replace('Dept.', ' Department'))
                        continue

                if 'attorney' in org_lower and 'office' in org_lower:
                    normalized_attorney = re.sub(r"\s*'?s?\s*Office\s*$", "'s Office", org_clean, flags=re.IGNORECASE)
                    normalized.append(normalized_attorney)
                    continue

                if 'sheriff' in org_lower:
                    sheriff_match = re.match(r'^(.+?)\s+sheriff', org_clean, re.IGNORECASE)
                    if sheriff_match:
                        county_name = sheriff_match.group(1).strip()
                        if 'office' in org_lower:
                            normalized.append(county_name + " Sheriff's Office")
                        elif 'department' in org_lower:
                            normalized.append(county_name + " Sheriff's Department")
                        else:
                            normalized.append(county_name + " Sheriff's Office")
                        continue
                    else:
                        normalized_sheriff = re.sub(r"sheriff'?s?\s*", "Sheriff's ", org_clean, flags=re.IGNORECASE)
                        normalized.append(normalized_sheriff)
                        continue

                if 'homeland security' in org_lower:
                    if 'investigation' in org_lower:
                        normalized.append('Homeland Security Investigations')
                    else:
                        normalized.append('Department of Homeland Security')
                    continue

                org_upper = org_clean.upper()
                if org_upper == 'HSI' or org_clean == 'Homeland Security Investigations':
                    normalized.append('Homeland Security Investigations')
                    continue

                normalized.append(org_clean)
        
        # Deduplicate while preserving order (case-insensitive)
        seen = set()
        unique_normalized = []
        for org in normalized:
            org_lower = org.lower()
            if org_lower not in seen:
                seen.add(org_lower)
                unique_normalized.append(org)

        return drop_non_le_agencies(dedupe_generic_state_police(unique_normalized))
    
    def _state_in_locations(self, state: str, locs: List[str]) -> bool:
        st_low = state.lower()
        postal = _STATE_TO_POSTAL.get(state.title(), "").lower()
        for loc in locs:
            ll = loc.lower()
            if st_low in ll or ll == st_low:
                return True
            if postal and re.search(rf"\b{re.escape(postal)}\.?\b", loc, re.I):
                return True
        return False

    def _is_state_street_name(self, text: str, start: int, end: int) -> bool:
        window_after = text[end : end + 30]
        if _STATE_BAD_TAIL_RE.match(window_after):
            return False
        return bool(_STATE_STREET_SUFFIX_RE.match(window_after))

    def _city_comma_state_signal(self, text: str, start: int, end: int) -> bool:
        lookback = text[max(0, start - 80) : start]
        m = re.search(r"([A-Z][\w'\-\.]+(?:\s+[A-Z][\w'\-\.]*)*),\s*$", lookback)
        if not m:
            return False
        left = m.group(1).strip()
        if _CITY_COMMA_BAD_LEFT_RE.search(left):
            return False
        if left.lower().endswith(" patrol") or left.lower().endswith(" highway"):
            return False
        window_after = text[end : end + 30]
        if _STATE_BAD_TAIL_RE.match(window_after):
            return False
        if self._is_state_street_name(text, start, end):
            return False
        return True

    def _jurisdictional_state_mentions(self, text: str) -> List[str]:
        out: List[str] = []
        seen: set = set()

        for m in _JURISDICTIONAL_AT_STATE_RE.finditer(text):
            state = m.group(1).title()
            if state in seen:
                continue
            start, end = m.start(1), m.end(1)
            window_before = text[max(0, start - 30) : start]
            window_after = text[end : end + 40]
            if _INCIDENTAL_STATE_RE.search(window_before + " " + window_after):
                continue
            if _REGIONAL_PREFIX_RE.search(window_before):
                continue
            if self._is_state_street_name(text, start, end):
                continue
            seen.add(state)
            out.append(state)

        for m in _STATE_RE.finditer(text):
            state = m.group(1).title()
            if state in seen:
                continue
            start, end = m.start(), m.end()
            window_before = text[max(0, start - 30) : start]
            window_after = text[end : end + 40]
            if _INCIDENTAL_STATE_RE.search(window_before + " " + window_after):
                continue
            if _REGIONAL_PREFIX_RE.search(window_before):
                continue
            if self._is_state_street_name(text, start, end):
                continue
            if not self._city_comma_state_signal(text, start, end):
                continue
            seen.add(state)
            out.append(state)

        return out

    def _supplement_jurisdictional_states(self, merged: Dict[str, Any]) -> Dict[str, Any]:
        case_text = merged.get("case_text") or ""
        if not case_text.strip():
            return merged

        locs = list(merged.get("locations") or [])
        added = False
        for state in self._jurisdictional_state_mentions(case_text):
            if self._state_in_locations(state, locs):
                continue
            locs.append(state)
            added = True

        if not added:
            return merged

        filtered = self._filter_location_residue(locs)
        merged["locations"] = filtered if isinstance(filtered, list) else filtered[0]
        return merged

    def _merge_locations(
        self,
        merged: Dict[str, Any],
        ner_entities: Dict[str, List[Any]]
    ) -> Dict[str, Any]:
        """
        Merge locations (geography) from NER into pattern features.
        
        Extracts states, countries, cities, and other geographic entities.
        Normalizes and deduplicates locations.
        
        Args:
            merged: Merged features dict
            ner_entities: NER entities dict
            
        Returns:
            Updated merged dict with locations added
        """
        ner_locations = ner_entities.get('locations', [])
        if not ner_locations:
            return merged
        
        # Normalize and clean locations
        normalized_locations = []
        seen = set()
        
        for loc in ner_locations:
            if not loc or len(loc.strip()) < 2:
                continue
            
            # Clean up location text
            loc_clean = loc.strip()
            loc_lower = loc_clean.lower()
            
            # Skip if already seen (case-insensitive)
            if loc_lower in seen:
                continue
            
            # Normalize common variations
            # US state abbreviations -> full names
            state_abbrev_map = {
                'az': 'Arizona', 'ca': 'California', 'co': 'Colorado', 'fl': 'Florida',
                'il': 'Illinois', 'ny': 'New York', 'tx': 'Texas', 'wa': 'Washington',
                'or': 'Oregon', 'nv': 'Nevada', 'nm': 'New Mexico', 'ut': 'Utah',
                'id': 'Idaho', 'mt': 'Montana', 'wy': 'Wyoming', 'nd': 'North Dakota',
                'sd': 'South Dakota', 'ne': 'Nebraska', 'ks': 'Kansas', 'ok': 'Oklahoma',
                'ar': 'Arkansas', 'mo': 'Missouri', 'ia': 'Iowa', 'mn': 'Minnesota',
                'wi': 'Wisconsin', 'mi': 'Michigan', 'in': 'Indiana', 'oh': 'Ohio',
                'ky': 'Kentucky', 'tn': 'Tennessee', 'al': 'Alabama', 'ms': 'Mississippi',
                'la': 'Louisiana', 'ga': 'Georgia', 'sc': 'South Carolina', 'nc': 'North Carolina',
                'va': 'Virginia', 'wv': 'West Virginia', 'md': 'Maryland', 'de': 'Delaware',
                'nj': 'New Jersey', 'pa': 'Pennsylvania', 'ct': 'Connecticut', 'ri': 'Rhode Island',
                'ma': 'Massachusetts', 'vt': 'Vermont', 'nh': 'New Hampshire', 'me': 'Maine',
                'ak': 'Alaska', 'hi': 'Hawaii', 'dc': 'Washington DC'
            }
            
            # Check if it's a state abbreviation
            if loc_lower in state_abbrev_map:
                loc_clean = state_abbrev_map[loc_lower]
                loc_lower = loc_clean.lower()
            
            # Normalize common location patterns
            # "City, State" -> keep both parts
            if ',' in loc_clean:
                parts = [p.strip() for p in loc_clean.split(',')]
                # If second part is a state abbreviation, expand it
                if len(parts) == 2 and parts[1].lower() in state_abbrev_map:
                    parts[1] = state_abbrev_map[parts[1].lower()]
                loc_clean = ', '.join(parts)
            
            # Capitalize properly (Title Case for locations)
            words = loc_clean.split()
            loc_normalized = ' '.join(word.capitalize() if word.lower() not in ['of', 'de', 'la', 'the'] else word.lower() 
                                     for word in words)
            # Handle special cases - normalize all US variations to "United States"
            loc_lower_clean = loc_normalized.lower().strip()
            if (loc_lower_clean in ['usa', 'u.s.a.', 'u.s.a', 'us'] or
                (loc_lower_clean == 'us' and len(words) == 1) or
                loc_lower_clean == 'america' or
                loc_lower_clean.startswith('the ') and loc_lower_clean.replace('the ', '').strip() == 'united states'):
                loc_normalized = 'United States'
            
            normalized_locations.append(loc_normalized)
            seen.add(loc_lower)
            seen.add(loc_normalized.lower())
        
        filtered = self._filter_location_residue(normalized_locations)
        normalized_locations = filtered if isinstance(filtered, list) else filtered[0]

        if normalized_locations:
            merged['locations'] = normalized_locations

        return merged


def merge_processing(
    pattern_features: Dict[str, Any],
    ner_entities: Optional[Dict[str, List[Any]]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to merge pattern and NER features.
    
    Args:
        pattern_features: Features from Pattern Processing Layer
        ner_entities: Entities from ML Processing Layer (optional)
    
    Returns:
        Merged features dictionary
    """
    merger = MergeProcessing()
    return merger.merge_features(pattern_features, ner_entities)