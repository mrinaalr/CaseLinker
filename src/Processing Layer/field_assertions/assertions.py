"""
Collect, gate, and resolve field assertions for one case (CaseLinker 3.0).

Every method (regex, spaCy token and dependency patterns, Stanza NER, statute
lookup, temporal tagging, the LLM layer, human verdicts) writes its own assertion;
``gate_assertion`` is the single choke point that enforces span support on the
original case_text. Nothing is merged here: resolution.py decides.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_FIELD_LAYER = Path(__file__).resolve().parent
_PROCESSING_LAYER = _FIELD_LAYER.parent
_PATTERN_LAYER = _PROCESSING_LAYER / "Pattern Processing Layer"
_ML_LAYER = _PROCESSING_LAYER / "ML Processing Layer"
for _p in (_FIELD_LAYER, _PROCESSING_LAYER, _PATTERN_LAYER, _ML_LAYER):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import span_gate as sg  # noqa: E402
import resolution  # noqa: E402
import detectors  # noqa: E402
import compiled_rules  # noqa: E402
import people_mask  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


patterns = _load("assertion_patterns", _PATTERN_LAYER / "assertion_patterns.py")
statute_lookup = _load("statute_lookup", _PATTERN_LAYER / "statute_lookup.py")
temporal_tags = _load("temporal_tags", _PATTERN_LAYER / "temporal_tags.py")
spacy_patterns = _load("spacy_patterns", _ML_LAYER / "spacy_patterns.py")
victim_age_gate = _load("victim_age_gate", _PROCESSING_LAYER / "victim_age_gate.py")

HUMAN_VERSION = "victim_age_overrides"
_CUSTODY_NOUN = re.compile(r"\b(?:custody|jail|correctional|detention|prison|bond|bail)\b", re.I)
_TOTAL_LEFT = re.compile(
    r"\b(?:total(?:ing)?(?:\s+(?:prison\s+)?(?:sentence|term))?|in\s+total|combined|aggregate)\s+(?:of\s+)?$",
    re.I,
)


def gate_assertion(text: str, a: Dict) -> Dict:
    """
    Enforce span support. Returns a copy with ``span_ok``, ``span_text``, ``family``,
    and ``extras.gate_reason``. Failed assertions keep their claim but lose the span.
    """
    out = dict(a)
    extras = dict(a.get("extras") or {})
    out["family"] = resolution.family_of(a)
    s, e = a.get("span_start"), a.get("span_end")
    ok, reason = False, "bad_offsets"
    field = a.get("field")

    if s is not None and e is not None and 0 <= s < e <= len(text):
        if field == "age":
            ok, reason = sg.age_support(text, s, e, a.get("value"))
            if not ok and e - s > 3:
                loc, why = sg.age_token_in(text, s, e, a.get("value"))
                if loc:
                    s, e = loc
                    ok, reason = sg.age_support(text, s, e, a.get("value"))
                else:
                    reason = why
            if ok:
                out["value"] = sg.parse_number(text[s:e])
        elif field == "sentence" and a.get("role") == "custody":
            ok = bool(_CUSTODY_NOUN.search(text[s:e]))
            reason = "custody_phrase" if ok else "no_custody_noun"
        elif field == "sentence":
            span = sg.canonical_sentence_span(text, s, e)
            if span is None:
                reason = "no_single_duration_in_span"
            else:
                s, e = span
                ok, reason, info = sg.sentence_support(text, s, e)
                if ok:
                    extras.update(info)
                    kind = sg.sentence_kind(text, s, e)
                    extras["clause_kind"] = kind
                    if _TOTAL_LEFT.search(sg.normalize_surface(text[max(0, s - 40) : s])):
                        extras["total"] = True
                    if s < sg.header_end(text):
                        extras["headline"] = True  # headlines round terms ("33 Years" for 400 months)
                    if kind == "exposure":
                        out["role"] = "exposure"  # clause cue overrides any method label (#24)
                    elif kind == "not_sentence" and a.get("method") != "llm":
                        ok, reason = False, "not_a_sentence_clause"
                    elif not out.get("role"):
                        out["role"] = kind
                    out["value"] = re.sub(r"\s+", " ", sg.normalize_surface(text[s:e])).strip()
        elif field == "investigation_type":
            ok = bool(patterns._TIP_TOKEN_RE.fullmatch(text[s:e].strip()))
            reason = "tip_token" if ok else "no_tip_token"
        elif field == "date":
            ok, reason = bool(text[s:e].strip()), "date_mention"

    extras["gate_reason"] = reason
    out["extras"] = extras
    out["span_ok"] = 1 if ok else 0
    if ok:
        out["span_start"], out["span_end"], out["span_text"] = s, e, text[s:e]
    else:
        out["span_start"] = out["span_end"] = out["span_text"] = None
    return out


def _ner_assertions(text: str, ner_entities: Dict, mentions) -> List[Dict]:
    """
    Stanza family: the age token must sit inside a Stanza DATE/CARDINAL entity.
    Role only from Stanza PERSON attachment + salience (the most-mentioned person
    is the release's defendant); otherwise abstain.
    """
    numbers = ner_entities.get("number_spans") or []
    persons = ner_entities.get("person_spans") or []
    if not numbers:
        return []
    surname_counts: Dict[str, int] = {}
    for ps, pe, ptxt in persons:
        sur = ptxt.split()[-1].strip(".,'’s").casefold() if ptxt.split() else ""
        if sur:
            surname_counts[sur] = surname_counts.get(sur, 0) + 1
    top = max(surname_counts.values()) if surname_counts else 0
    out = []
    for s, e, age, shape in mentions:
        ent = next((n for n in numbers if n[0] <= s and e <= n[1]), None)
        if ent is None:
            continue
        role, conf, entity = "unknown", 0.5, None
        person = next((p for p in persons if 0 <= s - p[1] <= 4 and re.fullmatch(r"\s*[,(]\s*", text[p[1]:s] or " ")), None)
        if person is None and shape == "year_old":
            # "28-year-old John Smith" only; never across a sentence break ("10 years old. Smith was")
            person = next(
                (p for p in persons if re.fullmatch(r"\s*-?\s*years?\s*-?\s*olds?\s+", text[e : p[0]], re.I)), None
            )
        if person:
            entity = person[2]
            sur = entity.split()[-1].strip(".,").casefold()
            if top >= 2 and surname_counts.get(sur) == top and list(surname_counts.values()).count(top) == 1:
                role, conf = "perpetrator", 0.65
        out.append({
            "field": "age", "method": "ner_stanza", "method_version": ner_entities.get("_backend_version", "stanza"),
            "value": age, "role": role, "span_start": s, "span_end": e, "confidence": conf,
            "extras": {"ner_type": ent[2], **({"entity": entity} if entity else {})},
        })
    return out


def _human_assertions(text: str, case_id: str, mentions, overrides: Dict) -> List[Dict]:
    out = []
    for (cid, age), decision in overrides.items():
        if cid != case_id:
            continue
        role = "victim" if decision == "keep" else "excluded"
        spans = [(s, e) for s, e, v, _ in mentions if v == age] or [(None, None)]
        for s, e in spans:
            out.append({
                "field": "age", "method": "human", "method_version": HUMAN_VERSION, "value": age,
                "role": role, "span_start": s, "span_end": e, "confidence": 1.0,
                "extras": {"decision": decision, "source": "config/victim_age_overrides.json"},
            })
    return out


def _press_ages(ctx: detectors.DetectorContext) -> List[Dict]:
    return patterns.age_assertions(ctx.text)


def _press_gate(ctx: detectors.DetectorContext) -> List[Dict]:
    return patterns.victim_gate_assertions(ctx.text, ctx.mentions, victim_age_gate)


def _press_sentences(ctx: detectors.DetectorContext) -> List[Dict]:
    ctx.sentence_raw = patterns.sentence_assertions(ctx.text)
    return list(ctx.sentence_raw)


def _press_cybertip(ctx: detectors.DetectorContext) -> List[Dict]:
    return patterns.cybertip_assertions(ctx.text)


def _press_statute(ctx: detectors.DetectorContext) -> List[Dict]:
    gated = [gate_assertion(ctx.text, a) for a in ctx.sentence_raw if a.get("role") != "custody"]
    durations = [a for a in gated if a["span_ok"]]
    ctx.durations = durations
    return statute_lookup.statute_assertions(
        ctx.text, durations, lambda s, e: sg.sentence_kind(ctx.text, s, e)
    )


def _press_temporal(ctx: detectors.DetectorContext) -> List[Dict]:
    return temporal_tags.temporal_assertions(ctx.text, ctx.durations, ctx.batch_year, ctx.mentions)


def _press_spacy(ctx: detectors.DetectorContext) -> List[Dict]:
    if not ctx.use_spacy:
        return []
    doc = ctx.spacy_doc
    if doc is None:
        nlp = spacy_patterns.load_spacy()
        if nlp is None:
            return []
        doc = nlp(ctx.text)
        ctx.spacy_doc = doc
    return spacy_patterns.dependency_assertions(doc, ctx.mentions) + spacy_patterns.token_assertions(doc, ctx.mentions)


def _ner(ctx: detectors.DetectorContext) -> List[Dict]:
    if not ctx.ner_entities:
        return []
    return _ner_assertions(ctx.text, ctx.ner_entities, ctx.mentions)


def _compiled(ctx: detectors.DetectorContext) -> List[Dict]:
    return compiled_rules.assertions_for(ctx.text, ctx.doc_kind, ctx.compiled_rules)


def _human(ctx: detectors.DetectorContext) -> List[Dict]:
    overrides = ctx.overrides
    if overrides is None:
        from victim_age_overrides import load_victim_age_overrides

        overrides = load_victim_age_overrides()
    return _human_assertions(ctx.text, ctx.case_id, ctx.mentions, overrides)


def _register_builtin_detectors() -> None:
    if detectors.detectors_for("press_release"):
        return
    press = ("press_release",)
    every = detectors.DOCUMENT_KINDS
    detectors.register_detector("press_age", press, _press_ages, order=10)
    detectors.register_detector("press_victim_gate", press, _press_gate, order=20)
    detectors.register_detector("press_sentences", press, _press_sentences, order=30)
    detectors.register_detector("press_cybertip", press, _press_cybertip, order=40)
    detectors.register_detector("press_statute", press, _press_statute, order=50)
    detectors.register_detector("press_temporal", press, _press_temporal, order=60)
    detectors.register_detector("press_spacy", press, _press_spacy, order=70)
    detectors.register_detector("ner_stanza", every, _ner, order=80)
    detectors.register_detector("compiled_rules", every, _compiled, order=90)
    detectors.register_detector("human", every, _human, order=100)


def collect_assertions(
    case_text: str,
    *,
    case_id: str = "",
    ner_entities: Optional[Dict[str, Any]] = None,
    use_spacy: bool = True,
    batch_year: Optional[int] = None,
    overrides: Optional[Dict] = None,
    doc_kind: str = "press_release",
    compiled_rules_override: Optional[List[Dict]] = None,
    spacy_doc: Any = None,
) -> List[Dict]:
    """
    Assertions for one document, gated.

    ``doc_kind`` selects detectors. Press releases are the live set. Other kinds
    run only detectors registered for them (NER, approved compiled rules, human
    verdicts, and anything a caller has registered).
    """
    text = case_text or ""
    if not text.strip():
        return []
    _register_builtin_detectors()
    ctx = detectors.DetectorContext(
        text=text,
        doc_kind=doc_kind,
        case_id=case_id,
        ner_entities=ner_entities,
        mentions=patterns.age_mentions(text),
        batch_year=batch_year,
        overrides=overrides,
        use_spacy=use_spacy,
        compiled_rules=tuple(compiled_rules_override) if compiled_rules_override is not None else None,
        spacy_doc=spacy_doc,
    )
    raw: List[Dict] = []
    for det in detectors.detectors_for(doc_kind):
        raw.extend(det.fn(ctx) or [])
    gated = [g for g in (gate_assertion(text, a) for a in raw) if g["span_ok"] or g["method"] in ("llm", "human")]
    # Imposed terms stay a flat list. The subject of the sentencing clause is an extra.
    if ctx.spacy_doc is not None:
        spacy_patterns.attach_imposed_defendants(ctx.spacy_doc, gated)
    # Names stay in memory; stored rows carry per-case tokens only.
    return people_mask.pseudonymize(gated)


def resolve(
    assertions: List[Dict],
    *,
    batch_date: Optional[str] = None,
    text: Optional[str] = None,
) -> Dict[str, Dict]:
    """Resolve; unsaved assertions get a negative ``seq`` (never a row id) that storage maps to row ids.

    ``text`` is the case narrative for age collapse and related rules.
    """
    for pos, a in enumerate(assertions):
        if a.get("id") is None:
            a["seq"] = -(pos + 1)
    return resolution.resolve_case(assertions, batch_date=batch_date, text=text)
