"""AfH 2.0 Q1: eligibility, evidence tiers, six-class affordance levels, harms.

Reads only the pinned snapshot (``snapshot.py``) and the two config files.
Evidence tiers come from the existing Q1 builder's own functions, so the tier
rules are the ones ``ontology/platform_affordance_evidence`` publishes.
Every row carries the case's content fingerprint and character offsets of the
evidence sentence; no source text is written to ``outputs/``.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from .snapshot import REPO, RESEARCH

CONFIG = RESEARCH / "config"
EVIDENCE_DIR = REPO / "ontology" / "platform_affordance_evidence"
CLASSES = ("Anonymity", "Ephemerality", "ContactDiscovery", "UnmonitoredCommunication",
           "DistributionInfrastructure", "GenerativeSynthesis")
TIERS = ("stated", "inferred", "named_only")
PERIOD_UNCERTAIN_YEARS = 2
SPAN_BASIS = "repaired_text"  # offsets index pe.repair_line_wraps(case_text)

# Sensitivity tier (not the published tier). The 2026-11-17 blind tier review found 25 of 40
# named_only records describe use; most failed the published rules because releases are
# line-wrapped (verb and platform land on different lines) or use storage/receipt verbs the
# keyword list lacks. The sensitivity tier reruns the same rules on unwrapped text with these
# verbs added. Reported beside the published tier, never instead of it.
SENSITIVITY_EXTRA_VERBS = ("stor", "sav", "receiv", "request", "purchas", "possess", "download",
                           "account contain", "member of", "joined", "post")
_UNWRAP = re.compile(r"(?<![.!?:\n])\n(?!\n)")


def unwrap(text: str) -> str:
    """Join single line breaks inside sentences; keep paragraph breaks (the builder's repair)."""
    return evidence_module().repair_line_wraps(text)


def sensitivity_tiers(case_id: str, platforms: List[str], text: str) -> Dict[str, str]:
    pe = evidence_module()
    original = pe.OFFENSE_KEYWORDS
    pe.OFFENSE_KEYWORDS = original + SENSITIVITY_EXTRA_VERBS
    try:
        result = pe.process_case(case_id, platforms, unwrap(text))
    finally:
        pe.OFFENSE_KEYWORDS = original
    return {r["platform"]: r["stated_vs_inferred"] for r in result["records"]}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def evidence_module():
    return _load_module("q1_evidence_builder", EVIDENCE_DIR / "platform_affordance_evidence.py")


@lru_cache(maxsize=1)
def candidates_module():
    return _load_module("q1_build_candidates", EVIDENCE_DIR / "build_candidates.py")


def load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def config_sha(name: str) -> str:
    return hashlib.sha256((CONFIG / name).read_bytes()).hexdigest()


# ---------------------------------------------------------------- eligibility

@dataclass(frozen=True)
class PlatformInfo:
    label: str
    status: str
    family: str
    capabilities: Dict[str, int]          # class key -> first year natively available
    until: Optional[int]
    # default_on: the platform's primary interaction (posting, messaging, storing a file, downloading) uses the
    # capability under the default configuration, without separate activation; secondary features (Stories,
    # vanish mode, opt-in groups) do not count. Rows were classified before the rule was written; known departures
    # are listed in the registry provenance audit and are not changed in AfH 2.0.
    default_on: Dict[str, bool] = field(default_factory=dict)   # registry default_on; rule in afh_manifest/README.md (Operational definitions)
    cap_meta: Dict[str, dict] = field(default_factory=dict)     # confidence, native, ended, sources

    @property
    def strict(self) -> bool:
        return self.status == "specific"

    @property
    def broad(self) -> bool:
        return self.status != "excluded"


def _cap(value) -> dict:
    """A capability row is either a bare first year (platforms-1) or a mapping (platforms-2)."""
    if isinstance(value, dict):
        return value
    return {"since": value, "default_on": False, "confidence": "needs_author_check"}


def platform_registry(cfg: Optional[dict] = None) -> Dict[str, PlatformInfo]:
    cfg = cfg or load_yaml("platforms.yaml")
    out = {}
    for label, row in cfg["platforms"].items():
        caps = {k: _cap(v) for k, v in (row.get("capabilities") or {}).items()}
        caps = {k: v for k, v in caps.items() if v.get("since") is not None and v.get("native", "yes") != "no"}
        out[label] = PlatformInfo(
            label, row["status"], row.get("family", "none"),
            {k: int(v["since"]) for k, v in caps.items()}, row.get("until"),
            {k: bool(v.get("default_on")) for k, v in caps.items()},
            caps,
        )
    return out


def platform_info(label: str, registry: Dict[str, PlatformInfo]) -> PlatformInfo:
    if label in registry:
        return registry[label]
    if label.lower().startswith("unknown"):
        return PlatformInfo(label, "excluded", "none", {}, None)
    # A label the registry has never seen is not silently treated as specific.
    return PlatformInfo(label, "unregistered", "none", {}, None)


def candidate_pairs(case: Dict[str, Any]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """(kept platforms, [(dropped platform, reason)]) using the published candidate rules."""
    bc = candidates_module()
    kept, dropped = [], []
    for p in case["platforms"]:
        if p.lower() in bc.GENERICS or p.lower().startswith("unknown"):
            dropped.append((p, "generic_excluded"))
        elif p == "Gen AI" and not bc.gen_ai_candidate_valid(case["id"], case["text"]):
            dropped.append((p, "gen_ai_embed_only"))
        else:
            kept.append(p)
    return kept, dropped


# ---------------------------------------------------------- per-record levels

def _compile(pattern: Optional[str]):
    return re.compile(pattern, re.I) if pattern else None


@dataclass
class Codebook:
    version: str
    conduct: List[Tuple[str, re.Pattern]]
    classes: Dict[str, dict]
    harms: Dict[str, dict]
    ai_material: Optional[re.Pattern] = None

    @classmethod
    def load(cls, cfg: Optional[dict] = None) -> "Codebook":
        cfg = cfg or load_yaml("codebook.yaml")
        conduct = [(k, re.compile(v, re.I)) for k, v in cfg["conduct_categories"].items()]
        classes = {}
        for name, row in cfg["classes"].items():
            classes[name] = {
                **row,
                "_cue": _compile(row.get("instrumental_cues")),
                "_exclude": _compile(row.get("exclude_cues")),
                "_review": _compile(row.get("review_cues")),
                "_guard": _compile(row.get("undercover_guard") or row.get("detection_guard")),
                "_require": _compile(row.get("require_cues")),
            }
        harms = {}
        for k, v in cfg["harms"].items():
            harms[k] = {
                **v,
                "_cue": _compile(v.get("cue")),
                "_guarded": _compile(v.get("guarded_cue")),
                "_exclude": _compile(v.get("exclude")),
                "_require": _compile(v.get("require")),
                "_live": _compile(v.get("live_cue")),
                "_live_exclude": _compile(v.get("live_exclude")),
                "_cue_reject": _compile(v.get("cue_reject")),
                "_in_person": _compile(v.get("in_person_cue")),
                "_online": _compile(v.get("online_cue")),
            }
        return cls(cfg["version"], conduct, classes, harms, _compile(cfg.get("ai_material_cue")))


def _sentences(text: str) -> List[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if part.strip()]


def _guarded_hit(sentence: str, harm: dict) -> bool:
    """A likeness cue counts only with require on that sentence and without exclude."""
    rx = harm.get("_guarded")
    if not rx or not rx.search(sentence):
        return False
    if harm.get("_exclude") and harm["_exclude"].search(sentence):
        return False
    if harm.get("_require") and not harm["_require"].search(sentence):
        return False
    return True


def _plain_cue_hit(text: str, harm: dict) -> bool:
    """A plain cue match. cue_reject drops a match whose own text matches, and another match can still count."""
    rx = harm.get("_cue")
    if not rx:
        return False
    reject = harm.get("_cue_reject")
    if not reject:
        return bool(rx.search(text))
    return any(not reject.search(match.group(0)) for match in rx.finditer(text))


def _live_sentence(sentence: str, harm: dict) -> bool:
    """Live conduct: medium and conduct in this sentence, and the sentence is not the production charge."""
    rx = harm.get("_live")
    if not rx or not rx.search(sentence):
        return False
    ban = harm.get("_live_exclude")
    return not (ban and ban.search(sentence))


def _live_hit(text: str, harm: dict) -> bool:
    return any(_live_sentence(sentence, harm) for sentence in _sentences(text))


def _cue_hit(text: str, harm: dict) -> bool:
    if _plain_cue_hit(text, harm) or _live_hit(text, harm):
        return True
    return any(_guarded_hit(sentence, harm) for sentence in _sentences(text))


def harm_case_hit(text: str, topics: set, harm: dict) -> bool:
    """Case-level harm from the whole release. A topic and a plain cue are alternatives,
    unless topics_require_cue, which needs both. guarded_cue carries require and exclude.
    live_cue is sentence-bounded. cue_reject drops a plain-cue match, not the whole release."""
    topic_hit = bool(set(topics) & set(harm.get("topics") or []))
    cue_hit = _cue_hit(text, harm)
    if harm.get("topics_require_cue"):
        return topic_hit and cue_hit
    return topic_hit or cue_hit


def harm_direct_hit(sentences: List[str], harm: dict) -> bool:
    """The platform sentence itself carries the cue. Topics do not."""
    for sentence in sentences:
        if _plain_cue_hit(sentence, harm) or _live_sentence(sentence, harm) or _guarded_hit(sentence, harm):
            return True
    return False


def h1_form(text: str, topics: set, harm: dict) -> Optional[str]:
    """in_person (hands_on topic, hands-on, or in-person abuse), online (live conduct or
    obscene material sent to a minor), or both. None when neither side is present."""
    topics = topics or set()
    in_person = "hands_on" in topics or bool(harm.get("_in_person") and harm["_in_person"].search(text or ""))
    online = _live_hit(text or "", harm) or bool(harm.get("_online") and harm["_online"].search(text or ""))
    if in_person and online:
        return "both"
    if in_person:
        return "in_person"
    if online:
        return "online"
    return None


def case_harm_set(text: str, topics: set, codebook: Codebook) -> set:
    """Harms for one press release, including a release that names no platform."""
    return {name for name, harm in codebook.harms.items() if harm_case_hit(text, topics, harm)}


_UNDERCOVER_CLEAR = frozenset({"h1_contact_sexual_abuse", "h4_coerced_by_exposure_threat"})
_DECOY_AGE_ROLES = frozenset({"decoy", "claimed"})
# Removed from h1. Still identifies the attempted-contact group: enticement, not contact abuse.
ENTICEMENT = re.compile(
    r"\b(?:meet\w*\s+(?:in\s+person|up|for\s+sex|to\s+engage)"
    r"|travel\w*\s+(?:\w+\s+){0,4}to\s+meet"
    r"|arrang\w*\s+(?:to\s+)?(?:a\s+)?meet\w*)\b",
    re.I,
)


def outside_uncovered_base(final: set, *, ai_no_identifiable_child: bool, attempted_contact: bool,
                           strict_sting: bool) -> bool:
    """Out of both the numerator and the denominator. A strict sting stays in when any harm remains."""
    if ai_no_identifiable_child or attempted_contact:
        return True
    return bool(strict_sting and not final)


def settled_age_roles(final: Optional[dict]) -> List[str]:
    """Roles on the latest age resolution. A victim or perpetrator list is that role.
    Excluded mentions carry their own role. An empty resolution is no settled role."""
    final = final or {}
    roles: List[str] = []
    if final.get("victims"):
        roles.append("victim")
    if final.get("perpetrators"):
        roles.append("perpetrator")
    for item in final.get("excluded") or []:
        if isinstance(item, dict) and item.get("role"):
            roles.append(str(item["role"]))
    return roles


def undercover_no_real_minor(investigation_types, age_roles: Optional[List[str]]) -> bool:
    """Strict: undercover, at least one settled age role, and every one is decoy or claimed.
    An undercover case with no settled age role is not touched."""
    types = investigation_types or []
    if isinstance(types, str):
        types = [types]
    if "undercover" not in types:
        return False
    roles = [role for role in (age_roles or []) if role]
    if not roles:
        return False
    return all(role in _DECOY_AGE_ROLES for role in roles)


def apply_case_harm_gates(level: set, topics: set, investigation_types=None, age_roles: Optional[List[str]] = None) -> Tuple[set, List[str]]:
    """Drop harms the case does not keep. Returns the kept set and the codes the undercover rule cleared."""
    kept = set(level)
    if "ai_csam" in topics and "h1_contact_sexual_abuse" not in kept and "h2_depicted_in_abuse_imagery" not in kept:
        kept = set()
    cleared: List[str] = []
    if undercover_no_real_minor(investigation_types, age_roles):
        cleared = sorted(kept & _UNDERCOVER_CLEAR)
        kept -= _UNDERCOVER_CLEAR
    return kept, cleared


def conduct_of(sentence: str, codebook: Codebook) -> Optional[str]:
    for name, rx in codebook.conduct:
        if rx.search(sentence):
            return name
    return None


GUARD_CONTEXT = 120  # chars before the sentence: line-wrapped releases split "agent,\nposing as"


def instrumental_hit(sentence: str, spec: dict, context: str = "") -> bool:
    """Cue in the platform sentence; exclusions and guards also see ``context``
    (the sentence plus the release text just before it)."""
    rx = spec["_cue"]
    if not rx or not rx.search(sentence):
        return False
    scope = (context or sentence).replace("\n", " ")
    if spec["_exclude"] and spec["_exclude"].search(scope):
        return False
    if spec["_guard"] and spec["_guard"].search(scope):
        return False
    if spec.get("_require") and not spec["_require"].search(sentence):
        return False
    return True


@dataclass
class Record:
    case_id: str
    fingerprint: str
    source: str
    pub_year: Optional[int]
    platform: str
    status: str
    family: str
    tier: str
    text_found: bool
    tier_sensitivity: str = ""
    tier_linewrap: str = ""
    conduct: List[str] = field(default_factory=list)
    sentence_spans: List[Tuple[int, int]] = field(default_factory=list)
    available: Dict[str, bool] = field(default_factory=dict)          # A_any: shipped by the publication year
    default_on_open: Dict[str, bool] = field(default_factory=dict)    # A: default_on, registry window open
    period_uncertain: Dict[str, bool] = field(default_factory=dict)
    action_relevant: Dict[str, bool] = field(default_factory=dict)
    inferred: Dict[str, bool] = field(default_factory=dict)
    instrumental: Dict[str, bool] = field(default_factory=dict)
    instrumental_span: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    review: Dict[str, str] = field(default_factory=dict)
    ai_material: bool = False   # AI-generated material documented in a platform sentence (any maker)
    harm_direct: Dict[str, bool] = field(default_factory=dict)
    harm_case: Dict[str, bool] = field(default_factory=dict)

    @property
    def primary_tier(self) -> str:
        """Tier every downstream level uses: tiers-1+linewrap-3 (Decision 1). `tier` stays the
        tiers-1 baseline, used only for baseline counts and for re-drawing historical samples."""
        return self.tier_linewrap or self.tier

    def row(self) -> Dict[str, Any]:
        out = {
            "case_id": self.case_id, "fingerprint": self.fingerprint, "source": self.source,
            "pub_year": self.pub_year, "platform": self.platform, "status": self.status,
            "family": self.family, "tier": self.tier, "tier_linewrap": self.tier_linewrap,
            "tier_sensitivity": self.tier_sensitivity,
            "text_found": self.text_found,
            "conduct": "|".join(self.conduct), "ai_material": int(self.ai_material),
            "sentence_spans": ";".join(f"{a}-{b}" for a, b in self.sentence_spans),
        }
        for c in CLASSES:
            out[f"{c}.A"] = int(self.default_on_open.get(c, False))
            out[f"{c}.A_any"] = int(self.available.get(c, False))
            out[f"{c}.B"] = int(self.action_relevant.get(c, False))
            out[f"{c}.I"] = int(self.inferred.get(c, False))
            out[f"{c}.C"] = int(self.instrumental.get(c, False))
            out[f"{c}.period_uncertain"] = int(self.period_uncertain.get(c, False))
            out[f"{c}.review"] = self.review.get(c, "")
        for h in sorted(self.harm_direct):
            out[f"{h}.direct"] = int(self.harm_direct[h])
            out[f"{h}.case"] = int(self.harm_case[h])
        return out


def _spans(text: str, sentences: Iterable[str]) -> List[Tuple[int, int]]:
    out, cursor = [], 0
    for s in sentences:
        i = text.find(s, 0)
        if i < 0:
            continue
        out.append((i, i + len(s)))
        cursor = i
    return sorted(set(out))


def classify_case(case: Dict[str, Any], fingerprint: str, registry: Dict[str, PlatformInfo],
                  codebook: Codebook) -> Tuple[List[Record], List[Dict[str, str]]]:
    pe = evidence_module()
    kept, dropped = candidate_pairs(case)
    excluded = [{"case_id": case["id"], "platform": p, "reason": r} for p, r in dropped]
    if not kept:
        return [], excluded
    result = pe.process_case(case["id"], kept, case["text"])
    excluded += [{"case_id": case["id"], "platform": e["platform"],
                  "reason": "psa_only" if e["exclusion_reason"].startswith("PSA") else "gen_ai_scrape_noise"}
                 for e in result["exclusions"]]
    offense, _psa, _cap = pe.offense_lines(case["text"])
    sens = sensitivity_tiers(case["id"], kept, case["text"])
    linewrap = pe.linewrap_tiers(case["id"], kept, case["text"], result["records"])
    # Cues (conduct, A/B/I/C, harms) read line-repaired sentences: hard wraps split verbs from
    # platform names (Decision 1). Offsets in sentence_spans / instrumental_span refer to the
    # repaired text, pe.repair_line_wraps(case_text) (SPAN_BASIS). Published tiers stay on raw text.
    text = pe.repair_line_wraps(case["text"])
    offense, _psa, _cap = pe.offense_lines(text)
    lower_release = text.lower()
    topics = set(case["topics"])
    out = []
    for r in result["records"]:
        p = r["platform"]
        info = platform_info(p, registry)
        sentences = pe.sentences_with_platform(offense, p) if not r.get("_text_not_found") else []
        rec = Record(case["id"], fingerprint, case["source"], case["pub_year"], p, info.status,
                     info.family, r["stated_vs_inferred"], not r.get("_text_not_found", False),
                     tier_sensitivity=sens.get(p, "dropped"),
                     tier_linewrap=linewrap.get(p, r["stated_vs_inferred"]),
                     sentence_spans=_spans(text, sentences))
        conduct = []
        for s in sentences:
            c = conduct_of(s, codebook)
            if c and c not in conduct:
                conduct.append(c)
        rec.conduct = conduct
        rec.ai_material = bool(codebook.ai_material and rec.primary_tier in ("stated", "inferred")
                               and any(codebook.ai_material.search(s) for s in sentences))
        year = case["pub_year"]
        for cname, spec in codebook.classes.items():
            since = info.capabilities.get(spec["capability"])
            # Every level closes at the registry end year (`ended`). The publication year stands in for the
            # conduct year: a release published after a feature ended does not count it (limitation, §7.5).
            ended = (info.cap_meta.get(spec["capability"]) or {}).get("ended")
            avail = since is not None and year is not None and year >= since and (ended is None or year <= ended)
            rec.available[cname] = avail
            # Level A (AfH 2.0): the capability is on for every use by design (registry default_on), with the
            # same window. A_any is `available`.
            on_open = bool(avail and info.default_on.get(spec["capability"], False))
            rec.default_on_open[cname] = on_open
            rec.period_uncertain[cname] = bool(avail and year - since < PERIOD_UNCERTAIN_YEARS)
            used = rec.primary_tier in ("stated", "inferred")
            rec.action_relevant[cname] = bool(
                avail and used and any(c in spec["action_relevant_conduct"] for c in conduct))
            hit_span = None
            if rec.action_relevant[cname]:
                for s in sentences:
                    found = _spans(text, [s])
                    a, b = found[0] if found else (-1, -1)
                    context = text[max(0, a - GUARD_CONTEXT):b] if a >= 0 else s
                    if instrumental_hit(s, spec, context):
                        hit_span = (a, b)
                        break
            rec.instrumental[cname] = hit_span is not None
            # Analytically inferred: the documented conduct of the relevant kind happened on a
            # platform where this capability is on for every use by design (registry default_on) and
            # its window is open in the publication year (closed at `ended`, like A, the harm tables
            # and recurrence), or the release states it outright (C).
            rec.inferred[cname] = bool(rec.instrumental[cname] or (rec.action_relevant[cname] and on_open))
            if hit_span:
                rec.instrumental_span[cname] = hit_span
            # Review candidates: cue present but not admitted to C.
            if not rec.instrumental[cname] and spec["_cue"] and used:
                if any(spec["_cue"].search(s) for s in sentences):
                    rec.review[cname] = "cue_in_platform_sentence_but_capability_or_conduct_missing"
                elif spec["_cue"].search(lower_release):
                    rec.review[cname] = "cue_elsewhere_in_release"
            if spec.get("_review") and any(spec["_review"].search(s) for s in sentences):
                rec.review.setdefault(cname, "review_cue_in_platform_sentence")
        level, _cleared = apply_case_harm_gates(
            case_harm_set(text, topics, codebook), topics,
            case.get("investigation_types"), case.get("age_roles"))
        for hname, h in codebook.harms.items():
            rec.harm_direct[hname] = bool(
                rec.primary_tier in ("stated", "inferred") and hname in level and harm_direct_hit(sentences, h))
            rec.harm_case[hname] = hname in level
        out.append(rec)
    return out, excluded


# ----------------------------------------------------------------- aggregates

def case_tiers(records: Iterable[Record], keep=lambda r: True, attr: str = "tier") -> Dict[str, str]:
    """Best tier per case (attr "tier" = tiers-1 baseline, "primary_tier" = line-wrap). Exclusive per case."""
    rank = {t: i for i, t in enumerate(reversed(TIERS))}
    best: Dict[str, str] = {}
    for r in records:
        if not keep(r):
            continue
        t = getattr(r, attr)
        if r.case_id not in best or rank[t] > rank[best[r.case_id]]:
            best[r.case_id] = t
    return best


def tier_counts(records: List[Record], keep=lambda r: True) -> Dict[str, Any]:
    best = case_tiers(records, keep)
    c = Counter(best.values())
    kept = [r for r in records if keep(r)]
    rc = Counter(r.tier for r in kept)
    return {
        "cases": len(best),
        **{f"cases_{t}": c.get(t, 0) for t in TIERS},
        "records": len(kept),
        **{f"records_{t}": rc.get(t, 0) for t in TIERS},
        "labels": len({r.platform for r in kept}),
    }
